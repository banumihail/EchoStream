from elasticsearch import Elasticsearch
from datetime import datetime
import json

class ElasticsearchClient:
    """
    Shared Elasticsearch client for EchoStream
    Handles connection and indexing/updating operations
    """

    def __init__(self, host="localhost", port=9200):
        self.host = host
        self.port = port
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
                        "has_pii": {"type": "boolean"},
                        "updated_at": {"type": "date"}
                    }
                }
            }
            self.client.indices.create(index=self.index_name, body=mappings)
            print(f"[OK] Created index '{self.index_name}'")

    def create_task(self, task_data: dict):
        """Initialize a new video processing task in Elasticsearch"""
        task_data["updated_at"] = datetime.now().isoformat()
        response = self.client.index(
            index=self.index_name,
            id=task_data["task_id"], # task_id as document id
            document=task_data
        )
        return response

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
            doc=doc
        )

    def close(self):
        """Close connection"""
        if self.client:
            self.client.close()
            print("[OK] Elasticsearch connection closed")
