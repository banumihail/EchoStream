"""
Vision Object Detection Worker
Uses DETR-ResNet-50 to identify objects in sampled frames of the video.
"""
import set_cuda_config  # noqa: F401  — must precede torch import
import set_model_cache
import set_ffmpeg_path

import os, sys, cv2, torch
from transformers import pipeline
from PIL import Image
from base_worker import BaseWorker

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.elasticsearch_client import ElasticsearchClient


class VisionWorker(BaseWorker):
    def __init__(self):
        super().__init__(queue_name="vision_queue", worker_name="Vision Worker", worker_key="vision")
        self.es_client = None
        self.device = 0 if torch.cuda.is_available() else -1
        gpu_info = f"GPU ({torch.cuda.get_device_name(0)})" if self.device == 0 else "CPU"
        print(f"[{self.worker_name}] Initializing DETR model on {gpu_info}...")
        # FP16 on GPU — halves activation memory for the encoder/decoder, which
        # is what was OOM'ing in long-mode runs sharing GPU with Whisper-small.
        torch_dtype = torch.float16 if self.device == 0 else torch.float32
        self.vision_classifier = pipeline(
            "object-detection",
            model="facebook/detr-resnet-50",
            device=self.device,
            torch_dtype=torch_dtype,
        )
        print(f"[{self.worker_name}] Model loaded successfully!\n")

    def get_es_client(self):
        if self.es_client is None:
            self.es_client = ElasticsearchClient()
            self.es_client.connect()
        return self.es_client

    def extract_and_analyze_frames(self, video_path, processing_mode="short"):
        print(f"  [1/2] Processing video frames (mode={processing_mode})...")
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video {video_path}")
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if fps == 0: fps = 30
        # Long mode: sample every 30s instead of every 5s. Hour-long meetings
        # go from 720 DETR inferences down to 120.
        sample_seconds = 30 if processing_mode == "long" else 5
        frame_interval = max(1, int(fps * sample_seconds))
        # Cap frame resolution before DETR. Boxes get rescaled back to the
        # original coords so the censor worker can still place blur correctly.
        # Long mode goes lower — moderation cares about persons + big objects,
        # which DETR detects fine at 480p, and this halves activation memory.
        MAX_DIM = 480 if processing_mode == "long" else 720
        scale = 1.0
        if max(src_w, src_h) > MAX_DIM:
            scale = MAX_DIM / max(src_w, src_h)
        all_objects = []
        frame_idx = 0
        seek_step = frame_interval  # use grab() to skip cheaply between samples
        while frame_idx < total_frames:
            # Cheap path: just grab past frames we don't need (no decode).
            for _ in range(min(frame_interval, total_frames - frame_idx) - 1):
                if not cap.grab():
                    frame_idx = total_frames
                    break
                frame_idx += 1
            ret, frame = cap.read()
            if not ret: break
            current_time = frame_idx / fps
            if scale < 1.0:
                frame = cv2.resize(frame, (0, 0), fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb_frame)
            results = self.vision_classifier(pil_image)
            inv = 1.0 / scale if scale != 0 else 1.0
            for res in results:
                if res['score'] < 0.8: continue
                box = res["box"]
                all_objects.append({
                    "timestamp": round(current_time, 2),
                    "label": res["label"],
                    "confidence": round(res["score"], 2),
                    "box": {k: int(v * inv) for k, v in box.items()},
                })
            # Free intermediate Python refs and CUDA cache between samples
            del frame, rgb_frame, pil_image, results
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            frame_idx += 1
        cap.release()
        label_counts = {}
        for obj in all_objects:
            lbl = obj["label"]
            label_counts[lbl] = label_counts.get(lbl, 0) + 1
        summary = [{"label": l, "count": c} for l, c in label_counts.items()]
        print(f"  Found objects: {[s['label'] for s in summary]}")
        return {"objects_timeline": all_objects, "summary": summary}

    def process_task(self, task_data):
        task_id = task_data["task_id"]
        video_path = task_data["file_path"]
        es = self.get_es_client()
        es.update_worker_status(task_id, "vision", "processing")
        if not os.path.isabs(video_path):
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            video_path = os.path.join(project_root, video_path)
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        processing_mode = task_data.get("processing_mode", "short")
        analysis = self.extract_and_analyze_frames(video_path, processing_mode=processing_mode)
        print(f"  [2/2] Saving vision analysis to DB...")
        es.update_worker_status(task_id, "vision", "done", {"vision_analysis": analysis})
        print(f"  [OK] Vision analysis saved.")


if __name__ == "__main__":
    worker = VisionWorker()
    worker.start()
