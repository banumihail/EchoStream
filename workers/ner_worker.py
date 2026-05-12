"""
NER (Named Entity Recognition) Worker
Uses BERT-based model to identify and flag sensitive information in transcripts
"""
import set_cuda_config  # noqa: F401  — must precede torch import
import os
import torch
import json
from transformers import pipeline
from base_worker import BaseWorker
import sys

# Add parent directory to import shared modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.elasticsearch_client import ElasticsearchClient


class NERWorker(BaseWorker):
    """
    Worker that analyzes transcripts to detect PII and sensitive entities
    """

    def __init__(self):
        super().__init__(
            queue_name="transcript_analysis_queue",
            worker_name="NER Worker",
            worker_key="ner"
        )

        # Initialize Elasticsearch client
        self.es_client = None

        # NER runs on CPU. BERT-base is fast enough on CPU (it processes one
        # transcript string per task, not video frames), and keeping it off
        # the GPU frees ~430 MB VRAM for Whisper, AST, and DETR.
        self.device = -1
        print(f"[{self.worker_name}] Initializing NER model on CPU...")

        # Initialize NER pipeline with BERT-based model
        self.ner_pipeline = pipeline(
            "ner",
            model="dslim/bert-base-NER",  # Pre-trained BERT for NER
            aggregation_strategy="simple",  # Group tokens into entities
            device=self.device
        )

        # Define sensitive entity types to flag
        self.sensitive_entities = ["PER", "LOC", "ORG"]  # Person, Location, Organization

        print(f"[{self.worker_name}] Model loaded successfully!\n")

    def get_es_client(self):
        """Lazy initialization of ES client"""
        if self.es_client is None:
            self.es_client = ElasticsearchClient()
            self.es_client.connect()
        return self.es_client

    def analyze_text(self, text: str) -> dict:
        """
        Analyze text for named entities and flag sensitive information

        Args:
            text: Text to analyze

        Returns:
            Dictionary with entities and flags
        """
        print(f"  [1/2] Analyzing text for entities...")

        # Run NER
        entities = self.ner_pipeline(text)

        # Categorize entities
        flagged_entities = []
        all_entities = []

        for entity in entities:
            entity_info = {
                "text": entity["word"],
                "type": entity["entity_group"],
                "score": float(entity["score"]),  # Convert numpy float32 to Python float
                "start": int(entity["start"]),
                "end": int(entity["end"])
            }
            all_entities.append(entity_info)

            # Flag sensitive entities
            if entity["entity_group"] in self.sensitive_entities:
                flagged_entities.append(entity_info)

        print(f"  Found {len(all_entities)} entities ({len(flagged_entities)} flagged)")

        return {
            "all_entities": all_entities,
            "flagged_entities": flagged_entities,
            "contains_pii": len(flagged_entities) > 0
        }

    def save_results(self, task_id: str, analysis: dict):
        """
        Save NER analysis results to Elasticsearch
        """
        print(f"  [2/2] Saving analysis results to Elasticsearch...")
        es = self.get_es_client()
        
        # Use per-worker status update to avoid race conditions
        es.update_worker_status(
            task_id=task_id,
            worker_name="ner",
            worker_status="done",
            extra_fields={
                "ner_analysis": analysis,
                "has_pii": analysis["contains_pii"]
            }
        )
        print(f"  Results saved to database.")

    def process_task(self, task_data: dict):
        """
        Process transcript: analyze for entities → flag sensitive info → save results

        Args:
            task_data: Task information from RabbitMQ
        """
        task_id = task_data["task_id"]

        # Mark as processing
        es = self.get_es_client()
        es.update_worker_status(task_id, "ner", "processing")

        # Get transcript directly from message (sent by ASR worker)
        text = task_data.get("transcript", "")

        if not text:
            raise ValueError(f"No transcript found in task data for task {task_id}")

        # Analyze text
        analysis = self.analyze_text(text)

        # Save results
        self.save_results(task_id, analysis)

        # Print summary
        if analysis["contains_pii"]:
            print(f"\n  [WARNING] PII Detected!")
            print(f"  Flagged entities:")
            for entity in analysis["flagged_entities"][:5]:  # Show first 5
                print(f"    - {entity['type']}: {entity['text']} (confidence: {entity['score']:.2f})")
        else:
            print(f"\n  [OK] No PII detected")


if __name__ == "__main__":
    worker = NERWorker()
    worker.start()
