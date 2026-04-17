"""
Vision Object Detection Worker
Uses DETR-ResNet-50 to identify objects in sampled frames of the video.
"""
import set_model_cache
import set_ffmpeg_path

import os
import sys
import cv2
import torch
from transformers import pipeline
from PIL import Image
from base_worker import BaseWorker

# Add parent directory to import shared modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.elasticsearch_client import ElasticsearchClient


class VisionWorker(BaseWorker):
    """
    Worker that analyzes environmental visuals via sampled frames.
    """

    def __init__(self):
        super().__init__(
            queue_name="vision_queue",
            worker_name="Vision Worker"
        )
        
        self.es_client = None

        self.device = 0 if torch.cuda.is_available() else -1
        gpu_info = f"GPU ({torch.cuda.get_device_name(0)})" if self.device == 0 else "CPU"
        print(f"[{self.worker_name}] Initializing DETR model on {gpu_info}...")

        # DETR is great for object detection
        self.vision_classifier = pipeline(
            "object-detection",
            model="facebook/detr-resnet-50",
            device=self.device
        )
        print(f"[{self.worker_name}] Model loaded successfully!\n")

    def get_es_client(self):
        if self.es_client is None:
            self.es_client = ElasticsearchClient()
            self.es_client.connect()
        return self.es_client

    def extract_and_analyze_frames(self, video_path: str) -> dict:
        print(f"  [1/2] Processing video frames...")
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video {video_path}")
            
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if fps == 0: fps = 30 # fallback
        
        duration = total_frames / fps
        
        # We sample 1 frame every 5 seconds to keep it fast
        interval_secs = 5
        frame_interval = int(fps * interval_secs)
        if frame_interval == 0: frame_interval = 1
        
        all_objects = []
        frame_idx = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
                
            if frame_idx % frame_interval == 0:
                current_time = frame_idx / fps
                
                # Convert BGR (OpenCV) to RGB (PIL)
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(rgb_frame)
                
                # Run detection
                results = self.vision_classifier(pil_image)
                
                # result: [{'score': 0.99, 'label': 'person', 'box': {'xmin':..., 'ymin':...}}, ...]
                for res in results:
                    # Ignore low confidence
                    if res['score'] < 0.8:
                        continue
                    
                    obj_info = {
                        "timestamp": round(current_time, 2),
                        "label": res["label"],
                        "confidence": round(res["score"], 2),
                        "box": res["box"]
                    }
                    all_objects.append(obj_info)
                    
            frame_idx += 1

        cap.release()
        
        # Summarize objects found
        label_counts = {}
        for obj in all_objects:
            lbl = obj["label"]
            label_counts[lbl] = label_counts.get(lbl, 0) + 1
            
        summary = [{"label": lbl, "count": count} for lbl, count in label_counts.items()]
        print(f"  Found objects: {[s['label'] for s in summary]}")
        
        return {
            "objects_timeline": all_objects,
            "summary": summary
        }

    def process_task(self, task_data: dict):
        task_id = task_data["task_id"]
        video_path = task_data["file_path"]

        if not os.path.isabs(video_path):
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            video_path = os.path.join(project_root, video_path)

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        analysis = self.extract_and_analyze_frames(video_path)

        print(f"  [2/2] Saving vision analysis to DB...")
        es = self.get_es_client()
        es.update_task_status(
            task_id=task_id,
            status="analyzing",
            extra_fields={"vision_analysis": analysis}
        )
        print(f"  [OK] Vision analysis saved.")


if __name__ == "__main__":
    worker = VisionWorker()
    worker.start()
