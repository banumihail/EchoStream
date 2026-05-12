"""
ASR (Automatic Speech Recognition) Worker
Uses OpenAI's Whisper model to transcribe audio from videos
"""
# Set model cache and FFmpeg paths before importing libraries
import set_cuda_config  # noqa: F401  — must precede torch import
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
            worker_name="ASR Worker",
            worker_key="asr"
        )

        # Initialize RabbitMQ client for publishing to NER queue
        self.publisher = None
        
        # Initialize Elasticsearch client
        self.es_client = None

        # Check for GPU
        self.device = 0 if torch.cuda.is_available() else -1
        gpu_info = f"GPU ({torch.cuda.get_device_name(0)})" if self.device == 0 else "CPU"

        print(f"[{self.worker_name}] Initializing Whisper-base on {gpu_info}...")

        # Whisper-base for both short and long mode — keeps the worker simple
        # and avoids GPU-contention crashes from a second lazy-loaded model.
        # Do NOT set chunk_length_s — that triggers an experimental pipeline path
        # that rejects Whisper-specific generate_kwargs like condition_on_prev_tokens.
        self.transcriber = pipeline(
            "automatic-speech-recognition",
            model="openai/whisper-base",
            device=self.device,
        )

        print(f"[{self.worker_name}] Model loaded successfully!\n")

    def get_publisher(self):
        """Create a fresh publisher connection to avoid heartbeat timeouts during long transcriptions"""
        publisher = RabbitMQClient()
        publisher.connect()
        publisher.declare_queue("transcript_analysis_queue")
        return publisher

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

    @staticmethod
    def _clamp_inflated_word_timestamps(chunks, max_duration=1.5):
        """
        Whisper systematically allocates leading/trailing audio (intros, music,
        silence) to the first and last transcribed words, producing absurd
        durations like "For" = 14.5s. Detect any word whose duration exceeds
        max_duration and shrink it to a realistic length based on word length,
        anchoring to the side that's most likely correct.
        """
        if not chunks:
            return chunks
        fixed = []
        n = len(chunks)
        for i, c in enumerate(chunks):
            ts = c.get("timestamp")
            if not ts or ts[0] is None or ts[1] is None or ts[1] <= ts[0]:
                fixed.append(c)
                continue
            start, end = ts
            if (end - start) <= max_duration:
                fixed.append(c)
                continue
            word = (c.get("text") or "").strip()
            est = max(0.2, min(max_duration, len(word) * 0.08))
            if i == 0:
                fixed.append({**c, "timestamp": (max(0.0, end - est), end)})
            elif i == n - 1:
                fixed.append({**c, "timestamp": (start, start + est)})
            else:
                prev_end = chunks[i - 1].get("timestamp", (start, start))[1] or start
                next_start = chunks[i + 1].get("timestamp", (end, end))[0] or end
                anchored_start = max(start, prev_end)
                anchored_end = min(end, max(next_start, anchored_start + est))
                fixed.append({**c, "timestamp": (anchored_start, anchored_end)})
        return fixed

    def transcribe_audio(self, audio_path: str, processing_mode: str = "short") -> dict:
        """
        Transcribe audio using Whisper

        Args:
            audio_path: Path to audio file

        Returns:
            Dictionary with transcription result
        """
        print(f"  [2/3] Transcribing audio with whisper-base (mode={processing_mode})...")
        # Word-level timestamps — every word gets its own (start, end). This fixes
        # Whisper's long-form sentence-stitching drift (which can produce 24s
        # "first sentence" or end-before-start chunks on >30s audio) and lets the
        # frontend highlight per word and seek per word.
        result = self.transcriber(
            audio_path,
            return_timestamps="word",
            generate_kwargs={"language": "en", "condition_on_prev_tokens": False, "temperature": 0}
        )
        if isinstance(result.get("chunks"), list):
            result["chunks"] = self._clamp_inflated_word_timestamps(result["chunks"])
        print(f"  Transcription complete!")
        return result

    def save_results(self, task_id: str, transcription: dict):
        """
        Save transcription results to Elasticsearch
        """
        print(f"  [3/3] Saving results to Elasticsearch...")
        es = self.get_es_client()
        
        # Use per-worker status update to avoid race conditions
        es.update_worker_status(
            task_id=task_id,
            worker_name="asr",
            worker_status="done",
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
        processing_mode = task_data.get("processing_mode", "short")

        # Mark as processing
        es = self.get_es_client()
        es.update_worker_status(task_id, "asr", "processing")

        # Convert to absolute path (worker may run from different directory)
        if not os.path.isabs(video_path):
            # Get project root (parent of workers directory)
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            video_path = os.path.join(project_root, video_path)

        # Verify video exists
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        # Create temporary audio file path
        audio_path = video_path.replace(".mp4", f"_{task_id}_asr.wav")

        try:
            # Step 1: Extract audio
            self.extract_audio(video_path, audio_path)
            # Step 2: Transcribe
            transcription = self.transcribe_audio(audio_path, processing_mode=processing_mode)

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
            publisher.close()
            print(f"  Published to NER queue")

        finally:
            # Cleanup temporary audio file
            if os.path.exists(audio_path):
                os.remove(audio_path)
                print(f"  Cleaned up temporary audio file")
            # Free GPU cache so the next task / other workers see headroom
            if torch.cuda.is_available():
                torch.cuda.empty_cache()


if __name__ == "__main__":
    worker = ASRWorker()
    worker.start()
