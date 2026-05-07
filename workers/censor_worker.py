"""
Active Censorship Action Worker
Orchestrates FFmpeg to physically blur objects and mute sensitive audio.
"""
import set_ffmpeg_path

import os, sys, subprocess
from base_worker import BaseWorker

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.elasticsearch_client import ElasticsearchClient


class CensorWorker(BaseWorker):
    def __init__(self):
        super().__init__(queue_name="censor_queue", worker_name="Censor Action Worker", worker_key="censor")
        self.es_client = None

    def get_es_client(self):
        if self.es_client is None:
            self.es_client = ElasticsearchClient()
            self.es_client.connect()
        return self.es_client

    def find_audio_mute_intervals(self, ner_analysis, transcription_metadata):
        intervals = []
        if not ner_analysis or not transcription_metadata:
            return intervals
        chunks = transcription_metadata.get("chunks", [])
        if not chunks:
            return intervals
        full_text = transcription_metadata.get("text", "")
        chunk_mappings = []
        last_found_index = 0
        for chunk in chunks:
            text = chunk["text"]
            start_char = full_text.find(text, last_found_index)
            if start_char == -1:
                start_char = last_found_index
            end_char = start_char + len(text)
            last_found_index = end_char
            ts = chunk.get("timestamp", [0.0, 0.0])
            t_start = float(ts[0]) if ts[0] is not None else 0.0
            t_end = float(ts[1]) if ts[1] is not None else t_start + 2.0
            chunk_mappings.append({"ts_start": t_start, "ts_end": t_end, "char_start": start_char, "char_end": end_char})
        flagged = ner_analysis.get("flagged_entities", [])
        for entity in flagged:
            e_start, e_end = entity["start"], entity["end"]
            for m in chunk_mappings:
                if not (e_end <= m["char_start"] or e_start >= m["char_end"]):
                    intervals.append((max(0, m["ts_start"] - 0.2), m["ts_end"] + 0.2))
        return sorted(list(set(intervals)))

    def build_ffmpeg_command(self, input_path, output_path, mute_intervals, video_blurs):
        from moviepy import VideoFileClip
        try:
            clip = VideoFileClip(input_path)
            vid_w, vid_h = clip.size
            clip.close()
        except:
            vid_w, vid_h = 1920, 1080
        cmd = ["ffmpeg", "-y", "-i", input_path]
        aframes = []
        for start, end in mute_intervals:
            aframes.append(f"volume=0:enable='between(t,{start:.2f},{end:.2f})'")
        afilter = ",".join(aframes) if aframes else None
        vframes = []
        for blur in video_blurs:
            x = max(0, int(blur["box"]["xmin"]))
            y = max(0, int(blur["box"]["ymin"]))
            w = int(blur["box"]["xmax"]) - x
            h = int(blur["box"]["ymax"]) - y
            t_start = max(0.0, blur["timestamp"] - 2.5)
            t_end = blur["timestamp"] + 2.5
            
            # Simple black box overlay using drawbox
            vframes.append(f"drawbox=x={x}:y={y}:w={w}:h={h}:color=black@1.0:t=fill:enable='between(t,{t_start:.2f},{t_end:.2f})'")
            
        vfilter = ",".join(vframes) if vframes else None

        if afilter and vfilter:
            fc = f"[0:v]{vfilter}[v];[0:a]{afilter}[a]"
            cmd.extend(["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-c:a", "aac"])
        elif vfilter:
            fc = f"[0:v]{vfilter}[v]"
            cmd.extend(["-filter_complex", fc, "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-c:a", "aac"])
        elif afilter:
            fc = f"[0:a]{afilter}[a]"
            cmd.extend(["-filter_complex", fc, "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-c:a", "aac"])
        else:
            cmd.extend(["-c", "copy"])
        cmd.append(output_path)
        return cmd

    def process_task(self, task_data):
        task_id = task_data["task_id"]
        input_path = task_data["file_path"]
        blur_objects = task_data.get("blur_objects", [])
        censor_audio = task_data.get("censor_audio", False)
        if not os.path.isabs(input_path):
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            input_path = os.path.join(project_root, input_path)
        es = self.get_es_client()
        es.update_worker_status(task_id, "censor", "processing")
        task = es.get_task(task_id)
        print(f"  [1/3] Parsing timestamps from Elasticsearch...")
        mute_intervals = []
        if censor_audio:
            mute_intervals = self.find_audio_mute_intervals(task.get("ner_analysis"), task.get("transcription_metadata"))
            print(f"  Audio mutes planned: {len(mute_intervals)}")
            for iv in mute_intervals:
                print(f"    Mute: {iv[0]:.2f}s - {iv[1]:.2f}s")
        video_blurs = []
        vision = task.get("vision_analysis", {})
        if vision and blur_objects:
            for obj in vision.get("objects_timeline", []):
                if obj["label"] in blur_objects:
                    video_blurs.append(obj)
            print(f"  Video blurs planned: {len(video_blurs)}")
        output_path = input_path.replace(".mp4", "_censored.mp4")
        print(f"  [2/3] Executing FFmpeg rendering pipeline...")
        cmd = self.build_ffmpeg_command(input_path, output_path, mute_intervals, video_blurs)
        print(f"  FFmpeg command: {cmd}")
        if "-c" in cmd and "copy" in cmd:
            result = subprocess.run(["ffmpeg", "-y", "-i", input_path, "-c", "copy", output_path], capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg copy failed: {result.stderr[-200:]}")
        else:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"  [ERROR] FFmpeg failed with code {result.returncode}")
                print(f"  FFmpeg stderr: {result.stderr[-500:]}")
                raise RuntimeError(f"FFmpeg censorship failed: {result.stderr[-200:]}")
        print(f"  [3/3] Finalizing state...")
        rel_output = output_path.replace(os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + os.sep, "").replace('\\', '/')
        es.update_worker_status(task_id, "censor", "done", {"censored_file_path": rel_output})
        print(f"  [OK] Censored video generated successfully!")


if __name__ == "__main__":
    worker = CensorWorker()
    worker.start()
