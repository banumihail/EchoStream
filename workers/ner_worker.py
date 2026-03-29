"""
NER (Named Entity Recognition) Worker
Uses BERT-based model to identify and flag sensitive information in transcripts
"""
import os
import torch
import json
from transformers import pipeline
from base_worker import BaseWorker


class NERWorker(BaseWorker):
    """
    Worker that analyzes transcripts to detect PII and sensitive entities
    """

    def __init__(self):
        super().__init__(
            queue_name="transcript_analysis_queue",
            worker_name="NER Worker"
        )

        # Check for GPU
        self.device = 0 if torch.cuda.is_available() else -1
        gpu_info = f"GPU ({torch.cuda.get_device_name(0)})" if self.device == 0 else "CPU"

        print(f"[{self.worker_name}] Initializing NER model on {gpu_info}...")

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
        Save NER analysis results to file

        Args:
            task_id: Task ID
            analysis: Analysis results
        """
        print(f"  [2/2] Saving analysis results...")

        # Convert to absolute path (worker may run from different directory)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        results_dir = os.path.join(project_root, "results")
        os.makedirs(results_dir, exist_ok=True)

        result_file = os.path.join(results_dir, f"{task_id}_ner_analysis.json")
        with open(result_file, "w", encoding="utf-8") as f:
            json.dump({
                "task_id": task_id,
                "analysis": analysis
            }, f, indent=2, ensure_ascii=False)

        print(f"  Results saved to: {result_file}")

    def process_task(self, task_data: dict):
        """
        Process transcript: analyze for entities → flag sensitive info → save results

        Args:
            task_data: Task information from RabbitMQ
        """
        task_id = task_data["task_id"]

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
