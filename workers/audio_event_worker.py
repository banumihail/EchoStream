"""
Audio Event Detection Worker
Uses AST (Audio Spectrogram Transformer) to classify ambient background sounds and events in videos.
"""
import set_model_cache
import set_ffmpeg_path

import os
import sys
import torch
from moviepy import VideoFileClip
from transformers import pipeline
import librosa
from base_worker import BaseWorker

# Add parent directory to import shared modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.elasticsearch_client import ElasticsearchClient


class AudioEventWorker(BaseWorker):
    """
    Worker that analyzes environmental audio events natively without relying on speech.
    """

    def __init__(self):
        super().__init__(
            queue_name="audio_event_queue",
            worker_name="Audio Event Worker"
        )
        
        self.es_client = None

        self.device = 0 if torch.cuda.is_available() else -1
        gpu_info = f"GPU ({torch.cuda.get_device_name(0)})" if self.device == 0 else "CPU"
        print(f"[{self.worker_name}] Initializing AST model on {gpu_info}...")

        # We use a robust audio classification model. 
        # AST finetuned on AudioSet gives great ambient sound recognition.
        self.audio_classifier = pipeline(
            "audio-classification",
            model="MIT/ast-finetuned-audioset-10-10-0.4593",
            device=self.device
        )
        print(f"[{self.worker_name}] Model loaded successfully!\n")

    def get_es_client(self):
        if self.es_client is None:
            self.es_client = ElasticsearchClient()
            self.es_client.connect()
        return self.es_client

    def extract_audio(self, video_path: str, audio_path: str):
        print(f"  [1/3] Extracting audio for event analysis...")
        video = VideoFileClip(video_path)
        video.audio.write_audiofile(audio_path, logger=None)
        video.close()
        
    def analyze_audio(self, audio_path: str) -> dict:
        print(f"  [2/3] Analyzing audio events with AST...")
        # Load audio using librosa to feed to transformers natively
        # Note: pipeliness can also take filepaths directly.
        results = self.audio_classifier(audio_path)
        
        # results is a list of dicts: [{'score': 0.9, 'label': 'Speech'}, ...]
        print(f"  Found top event: {results[0]['label']} ({results[0]['score']:.2f})")
        return {"events": results}

    def process_task(self, task_data: dict):
        task_id = task_data["task_id"]
        video_path = task_data["file_path"]

        if not os.path.isabs(video_path):
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            video_path = os.path.join(project_root, video_path)

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        # Unique temp file to avoid collision with ASR worker
        audio_path = video_path.replace(".mp4", f"_{task_id}_events.wav")

        try:
            self.extract_audio(video_path, audio_path)
            analysis = self.analyze_audio(audio_path)

            print(f"  [3/3] Saving event analysis to DB...")
            es = self.get_es_client()
            es.update_task_status(
                task_id=task_id,
                status="analyzing",
                extra_fields={"audio_event_analysis": analysis}
            )
            print(f"  [OK] Audio event analysis saved.")

        finally:
            if os.path.exists(audio_path):
                os.remove(audio_path)


if __name__ == "__main__":
    worker = AudioEventWorker()
    worker.start()
