"""
Audio Event Detection Worker
Uses AST (Audio Spectrogram Transformer) to classify ambient background sounds and events in videos.
"""
import set_cuda_config  # noqa: F401  — must precede torch import
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
            worker_name="Audio Event Worker",
            worker_key="audio_event"
        )
        
        self.es_client = None

        self.device = 0 if torch.cuda.is_available() else -1
        gpu_info = f"GPU ({torch.cuda.get_device_name(0)})" if self.device == 0 else "CPU"
        print(f"[{self.worker_name}] Initializing AST model on {gpu_info}...")

        # AST finetuned on AudioSet for ambient sound recognition. Use FP16 on
        # GPU to halve VRAM (3.4 GB -> 1.7 GB activation footprint at peak).
        torch_dtype = torch.float16 if self.device == 0 else torch.float32
        self.audio_classifier = pipeline(
            "audio-classification",
            model="MIT/ast-finetuned-audioset-10-10-0.4593",
            device=self.device,
            torch_dtype=torch_dtype,
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
        
    def analyze_audio(self, audio_path: str, processing_mode: str = "short") -> dict:
        if processing_mode != "long":
            print(f"  [2/3] Analyzing audio events with AST (single-pass)...")
            results = self.audio_classifier(audio_path)
            print(f"  Top event: {results[0]['label']} ({results[0]['score']:.2f})")
            return {"events": results}

        # Long mode: scan in non-overlapping windows so we get a timeline of
        # events instead of one global "top label" averaged across an hour.
        print(f"  [2/3] Analyzing audio events in windows (long mode)...")
        WINDOW_SECONDS = 60  # bumped from 30s -> 60s: half the inferences, equivalent coverage
        SR = 16000  # AST expects 16 kHz
        audio, _ = librosa.load(audio_path, sr=SR, mono=True)
        timeline = []
        global_counts = {}
        n_windows = max(1, int(len(audio) // (WINDOW_SECONDS * SR)) + (1 if len(audio) % (WINDOW_SECONDS * SR) else 0))
        for w in range(n_windows):
            start = w * WINDOW_SECONDS * SR
            end = min(len(audio), start + WINDOW_SECONDS * SR)
            chunk = audio[start:end]
            if len(chunk) < SR:  # skip windows shorter than 1s
                continue
            preds = self.audio_classifier({"raw": chunk, "sampling_rate": SR}, top_k=3)
            timeline.append({
                "start": round(start / SR, 2),
                "end": round(end / SR, 2),
                "events": preds,
            })
            for p in preds:
                global_counts[p["label"]] = global_counts.get(p["label"], 0) + 1
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        # Build a "top events overall" list ordered by how often they appeared in the top-3 of any window
        ranked = sorted(global_counts.items(), key=lambda kv: -kv[1])[:8]
        events_overall = [{"label": lbl, "score": cnt / max(1, n_windows)} for lbl, cnt in ranked]
        if events_overall:
            print(f"  Most common event across windows: {events_overall[0]['label']}")
        return {"events": events_overall, "timeline": timeline}

    def process_task(self, task_data: dict):
        task_id = task_data["task_id"]
        video_path = task_data["file_path"]
        processing_mode = task_data.get("processing_mode", "short")

        # Mark as processing
        es = self.get_es_client()
        es.update_worker_status(task_id, "audio_event", "processing")

        if not os.path.isabs(video_path):
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            video_path = os.path.join(project_root, video_path)

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        # Unique temp file to avoid collision with ASR worker
        audio_path = video_path.replace(".mp4", f"_{task_id}_events.wav")

        try:
            self.extract_audio(video_path, audio_path)
            analysis = self.analyze_audio(audio_path, processing_mode=processing_mode)

            print(f"  [3/3] Saving event analysis to DB...")
            es.update_worker_status(
                task_id=task_id,
                worker_name="audio_event",
                worker_status="done",
                extra_fields={"audio_event_analysis": analysis}
            )
            print(f"  [OK] Audio event analysis saved.")

        finally:
            if os.path.exists(audio_path):
                os.remove(audio_path)


if __name__ == "__main__":
    worker = AudioEventWorker()
    worker.start()
