from elasticsearch import Elasticsearch
from datetime import datetime
import json
import os

class ElasticsearchClient:
    """
    Shared Elasticsearch client for EchoStream
    Handles connection and indexing/updating operations
    """

    def __init__(self, host=None, port=None):
        self.host = host or os.getenv("ELASTICSEARCH_HOST", "localhost")
        self.port = port or int(os.getenv("ELASTICSEARCH_PORT", "9200"))
        self.client = None
        self.index_name = "echostream_tasks"

    def connect(self):
        """Establish connection to Elasticsearch"""
        self.client = Elasticsearch([f"http://{self.host}:{self.port}"])
        if not self.client.ping():
            raise ConnectionError(f"Could not connect to Elasticsearch at {self.host}:{self.port}")
        
        print(f"[OK] Connected to Elasticsearch at {self.host}:{self.port}")
        self._ensure_index()

    def _ensure_index(self):
        """Create the tasks index if it doesn't exist"""
        if not self.client.indices.exists(index=self.index_name):
            mappings = {
                "mappings": {
                    "properties": {
                        "task_id": {"type": "keyword"},
                        "filename": {"type": "text"},
                        "file_path": {"type": "keyword"},
                        "uploaded_at": {"type": "date"},
                        "status": {"type": "keyword"},
                        "transcript": {"type": "text"},
                        "transcription_metadata": {"type": "object"},
                        "ner_analysis": {"type": "object"},
                        "audio_event_analysis": {"type": "object"},
                        "vision_analysis": {"type": "object"},
                        "has_pii": {"type": "boolean"},
                        "updated_at": {"type": "date"},
                        # Per-worker status tracking to avoid race conditions
                        "asr_status": {"type": "keyword"},
                        "ner_status": {"type": "keyword"},
                        "audio_event_status": {"type": "keyword"},
                        "vision_status": {"type": "keyword"},
                        "censor_status": {"type": "keyword"},
                    }
                }
            }
            self.client.indices.create(index=self.index_name, body=mappings)
            print(f"[OK] Created index '{self.index_name}'")

    def create_task(self, task_data: dict):
        """Initialize a new video processing task in Elasticsearch"""
        task_data["updated_at"] = datetime.now().isoformat()
        # Initialize per-worker statuses
        task_data["asr_status"] = "pending"
        task_data["ner_status"] = "pending"
        task_data["audio_event_status"] = "pending"
        task_data["vision_status"] = "pending"
        task_data["censor_status"] = "idle"
        response = self.client.index(
            index=self.index_name,
            id=task_data["task_id"], # task_id as document id
            document=task_data
        )
        return response

    def get_task(self, task_id: str):
        """Fetch a specific task's data by its ID"""
        try:
            res = self.client.get(index=self.index_name, id=task_id)
            return res.get("_source")
        except Exception:
            return None

    def update_task_status(self, task_id: str, status: str, extra_fields: dict = None):
        """Update task status and any extra fields"""
        doc = {
            "status": status,
            "updated_at": datetime.now().isoformat()
        }
        if extra_fields:
            doc.update(extra_fields)
            
        return self.client.update(
            index=self.index_name,
            id=task_id,
            doc=doc,
            retry_on_conflict=3
        )

    def update_worker_status(self, task_id: str, worker_name: str, worker_status: str, extra_fields: dict = None):
        """
        Update a specific worker's status without touching the global status.
        Also recomputes the aggregate status based on all workers.
        
        Args:
            task_id: The task ID
            worker_name: One of 'asr', 'ner', 'audio_event', 'vision', 'censor'
            worker_status: The new status for this worker (e.g. 'processing', 'done', 'error')
            extra_fields: Additional data fields to store (e.g. transcript, analysis results)
        """
        doc = {
            f"{worker_name}_status": worker_status,
            "updated_at": datetime.now().isoformat()
        }
        if extra_fields:
            doc.update(extra_fields)
        
        # Update the worker-specific fields first
        self.client.update(
            index=self.index_name,
            id=task_id,
            doc=doc,
            retry_on_conflict=3
        )

        # Now recompute the aggregate status
        task = self.get_task(task_id)
        if task:
            asr = task.get("asr_status", "pending")
            ner = task.get("ner_status", "pending")
            audio = task.get("audio_event_status", "pending")
            vision = task.get("vision_status", "pending")
            censor = task.get("censor_status", "idle")

            # Determine aggregate
            if censor == "done":
                aggregate = "censored"
            elif censor == "processing":
                aggregate = "censoring"
            elif all(s == "done" for s in [asr, ner, audio, vision]):
                aggregate = "completed"
            elif any(s == "error" for s in [asr, ner, audio, vision]):
                aggregate = "error"
            elif any(s in ("processing", "done") for s in [asr, ner, audio, vision]):
                aggregate = "analyzing"
            else:
                aggregate = "pending"

            self.client.update(
                index=self.index_name,
                id=task_id,
                doc={"status": aggregate},
                retry_on_conflict=3
            )

    def list_tasks(self, size=20):
        """List recent tasks, newest first"""
        try:
            res = self.client.search(
                index=self.index_name,
                body={
                    "query": {"match_all": {}},
                    "sort": [{"updated_at": {"order": "desc"}}],
                    "size": size
                }
            )
            return [hit["_source"] for hit in res["hits"]["hits"]]
        except Exception:
            return []

    def delete_task(self, task_id: str):
        """Delete a task from Elasticsearch"""
        try:
            self.client.delete(index=self.index_name, id=task_id)
            return True
        except Exception:
            return False

    def close(self):
        """Close connection"""
        if self.client:
            self.client.close()
            print("[OK] Elasticsearch connection closed")
