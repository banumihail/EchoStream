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
        self.users_index = "echostream_users"
        self.auth_events_index = "echostream_auth_events"

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
                        # Per-user access control — set on creation from the
                        # authenticated user. Filters list_tasks_by_owner().
                        "owner_username": {"type": "keyword"},
                    }
                }
            }
            self.client.indices.create(index=self.index_name, body=mappings)
            print(f"[OK] Created index '{self.index_name}'")

        if not self.client.indices.exists(index=self.users_index):
            user_mappings = {
                "mappings": {
                    "properties": {
                        "username": {"type": "keyword"},
                        "password_hash": {"type": "keyword", "index": False},
                        "created_at": {"type": "date"},
                        "mfa_methods": {"type": "keyword"},      # ["totp","email","backup","fido2","push"]
                        "totp_secret": {"type": "keyword", "index": False},
                        "backup_codes_hashed": {"type": "keyword", "index": False},
                        "email": {"type": "keyword"},
                        "email_otp_hash": {"type": "keyword", "index": False},
                        "email_otp_expires": {"type": "date"},
                        "email_otp_sent_at": {"type": "date"},
                        "pushover_user_key": {"type": "keyword", "index": False},
                        "telegram_chat_id": {"type": "keyword"},
                        "telegram_pairing_token": {"type": "keyword"},
                        "pending_push": {"type": "object", "enabled": False},
                        "fido2_credentials": {"type": "object", "enabled": False},
                        "failed_logins": {"type": "integer"},
                        "locked_until": {"type": "date"},
                    }
                }
            }
            self.client.indices.create(index=self.users_index, body=user_mappings)
            print(f"[OK] Created index '{self.users_index}'")

        if not self.client.indices.exists(index=self.auth_events_index):
            event_mappings = {
                "mappings": {
                    "properties": {
                        "timestamp": {"type": "date"},
                        "username": {"type": "keyword"},
                        "ip": {"type": "ip"},
                        "user_agent": {"type": "text"},
                        "event_type": {"type": "keyword"},        # login_success, login_fail, register, mfa_success, mfa_fail, lockout, logout
                        "mfa_method": {"type": "keyword"},        # totp, email, backup, fido2, push, password
                        "outcome": {"type": "keyword"},           # ok, denied, locked
                        "reason": {"type": "text"},
                    }
                }
            }
            self.client.indices.create(index=self.auth_events_index, body=event_mappings)
            print(f"[OK] Created index '{self.auth_events_index}'")

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

    def list_tasks(self, size=20, owner_username: str = None):
        """List recent tasks, newest first.

        If owner_username is provided, only that user's tasks are returned —
        the standard path for the authenticated dashboard. Pass None only for
        admin/migration scripts."""
        if owner_username is not None:
            query = {"term": {"owner_username": owner_username}}
        else:
            query = {"match_all": {}}
        try:
            res = self.client.search(
                index=self.index_name,
                body={
                    "query": query,
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

    # ─────────────────────────────────────────────────────────────────
    # User accounts
    # ─────────────────────────────────────────────────────────────────
    def create_user(self, user_doc: dict):
        """Index a new user. user_doc['username'] is used as the document id
        to make uniqueness atomic (op_type=create raises if it exists)."""
        return self.client.index(
            index=self.users_index,
            id=user_doc["username"].lower(),
            document=user_doc,
            op_type="create",
        )

    def get_user(self, username: str):
        try:
            res = self.client.get(index=self.users_index, id=username.lower())
            return res.get("_source")
        except Exception:
            return None

    def update_user(self, username: str, fields: dict):
        return self.client.update(
            index=self.users_index,
            id=username.lower(),
            doc=fields,
            retry_on_conflict=3,
        )

    def find_user_by(self, field: str, value: str):
        """Return the first user whose `field` exactly equals `value`, or None.
        Used by the Telegram poller to resolve a pairing token to a user."""
        try:
            res = self.client.search(
                index=self.users_index,
                body={"query": {"term": {field: value}}, "size": 1},
            )
            hits = res["hits"]["hits"]
            return hits[0]["_source"] if hits else None
        except Exception:
            return None

    # ─────────────────────────────────────────────────────────────────
    # Auth audit log
    # ─────────────────────────────────────────────────────────────────
    def log_auth_event(self, event: dict):
        """Index an auth event (login attempt, MFA verification, lockout, etc.).
        Failures here are non-fatal — the auth flow must not break because we
        couldn't log it."""
        try:
            event.setdefault("timestamp", datetime.now().isoformat())
            self.client.index(index=self.auth_events_index, document=event)
        except Exception as e:
            print(f"[WARN] Could not log auth event: {e}")

    def close(self):
        """Close connection"""
        if self.client:
            self.client.close()
            print("[OK] Elasticsearch connection closed")
