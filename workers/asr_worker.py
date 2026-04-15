"""
ASR (Automatic Speech Recognition) Worker
Uses OpenAI's Whisper model to transcribe audio from videos
"""
# Set model cache and FFmpeg paths before importing libraries
import set_model_cache
import set_ffmpeg_path

import os
import torch
import json
import sys
from moviepy import VideoFileClip
from transformers import pipeline
from base_worker import BaseWorker

# Add parent directory to import shared modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.rabbitmq_client import RabbitMQClient
from shared.elasticsearch_client import ElasticsearchClient


class ASRWorker(BaseWorker):
    """
    Worker that extracts audio from video and transcribes it using Whisper
    """

    def __init__(self):
        super().__init__(
            queue_name="video_processing_queue",
            worker_name="ASR Worker"
        )

        # Initialize RabbitMQ client for publishing to NER queue
        self.publisher = None
        
        # Initialize Elasticsearch client
        self.es_client = None

        # Check for GPU
        self.device = 0 if torch.cuda.is_available() else -1
        gpu_info = f"GPU ({torch.cuda.get_device_name(0)})" if self.device == 0 else "CPU"

        print(f"[{self.worker_name}] Initializing Whisper model on {gpu_info}...")

        # Initialize Whisper pipeline
        # Using 'base' model for balance between speed and accuracy
        # Options: tiny, base, small, medium, large
        self.transcriber = pipeline(
            "automatic-speech-recognition",
            model="openai/whisper-base",
            device=self.device
        )

        print(f"[{self.worker_name}] Model loaded successfully!\n")

    def get_publisher(self):
        """Lazy initialization of publisher"""
        if self.publisher is None:
            self.publisher = RabbitMQClient()
            self.publisher.connect()
            self.publisher.declare_queue("transcript_analysis_queue")
        return self.publisher

    def get_es_client(self):
        """Lazy initialization of ES client"""
        if self.es_client is None:
            self.es_client = ElasticsearchClient()
            self.es_client.connect()
        return self.es_client

    def extract_audio(self, video_path: str, audio_path: str):
        """
        Extract audio from video file

        Args:
            video_path: Path to input video
            audio_path: Path to save extracted audio
        """
        print(f"  [1/3] Extracting audio from video...")
        video = VideoFileClip(video_path)
        video.audio.write_audiofile(audio_path, logger=None)
        video.close()
        print(f"  Audio saved to: {audio_path}")

    def transcribe_audio(self, audio_path: str) -> dict:
        """
        Transcribe audio using Whisper

        Args:
            audio_path: Path to audio file

        Returns:
            Dictionary with transcription result
        """
        print(f"  [2/3] Transcribing audio with Whisper...")
        result = self.transcriber(audio_path)
        print(f"  Transcription complete!")
        return result

    def save_results(self, task_id: str, transcription: dict):
        """
        Save transcription results to Elasticsearch
        """
        print(f"  [3/3] Saving results to Elasticsearch...")
        es = self.get_es_client()
        
        # We only save the text to not bloat the database if it's very large,
        # but could store 'transcription' fully in 'transcription_metadata'.
        es.update_task_status(
            task_id=task_id,
            status="analyzing",
            extra_fields={
                "transcript": transcription["text"],
                "transcription_metadata": transcription
            }
        )
        print(f"  Results saved to database.")

    def process_task(self, task_data: dict):
        """
        Process video: extract audio → transcribe → save results

        Args:
            task_data: Task information from RabbitMQ
        """
        task_id = task_data["task_id"]
        video_path = task_data["file_path"]

        # Convert to absolute path (worker may run from different directory)
        if not os.path.isabs(video_path):
            # Get project root (parent of workers directory)
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            video_path = os.path.join(project_root, video_path)

        # Verify video exists
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        # Create temporary audio file path
        audio_path = video_path.replace(".mp4", ".wav")

        try:
            # Step 1: Extract audio
            self.extract_audio(video_path, audio_path)

            # Step 2: Transcribe
            transcription = self.transcribe_audio(audio_path)

            # Step 3: Save results
            self.save_results(task_id, transcription)

            print(f"\n  Transcript preview: {transcription['text'][:100]}...")

            # Step 4: Send to NER queue for analysis
            print(f"\n  [4/4] Sending transcript to NER queue...")
            publisher = self.get_publisher()
            ner_task = {
                "task_id": task_id,
                "transcript": transcription['text']
            }
            publisher.publish_message("transcript_analysis_queue", ner_task)
            print(f"  Published to NER queue")

        finally:
            # Cleanup temporary audio file
            if os.path.exists(audio_path):
                os.remove(audio_path)
                print(f"  Cleaned up temporary audio file")


if __name__ == "__main__":
    worker = ASRWorker()
    worker.start()
