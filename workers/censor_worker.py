"""
Active Censorship Action Worker
Orchestrates FFmpeg to physically blur objects and mute sensitive audio.
"""
import set_ffmpeg_path

import os, sys, subprocess
import cv2
import numpy as np
from base_worker import BaseWorker
import face_utils
from blur_strength import gblur_sigma, pixelate_factor, clamp_strength

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.elasticsearch_client import ElasticsearchClient


class CensorWorker(BaseWorker):
    def __init__(self):
        super().__init__(queue_name="censor_queue", worker_name="Censor Action Worker", worker_key="censor")
        self.es_client = None
        self._face_engine = None

    def _get_face_engine(self):
        if self._face_engine is None:
            self._face_engine = face_utils.FaceEngine()
        return self._face_engine

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

    def _build_audio_filter(self, intervals, audio_mode, source="0:a"):
        """filter_complex segment for audio. `source` is the input audio label
        (e.g. "0:a" or "1:a"). Returns (graph_text, output_label) or (None, None)."""
        if not intervals:
            return None, None
        enable_x = "+".join(f"between(t,{s:.2f},{e:.2f})" for s, e in intervals)
        not_x = f"not({enable_x})"

        if audio_mode == "beep":
            # Mute original at intervals; mix in a sine wave that's only audible at those intervals.
            return (
                f"[{source}]volume=0:enable='{enable_x}'[a_muted];"
                f"sine=frequency=1000:sample_rate=44100,volume=0.25,volume=0:enable='{not_x}'[a_beep];"
                f"[a_muted][a_beep]amix=inputs=2:duration=first:normalize=0[a]"
            ), "a"

        if audio_mode == "muffle":
            # Split: original outside intervals, low-pass-filtered version inside intervals.
            return (
                f"[{source}]asplit=2[a_orig][a_lp_in];"
                f"[a_orig]volume=0:enable='{enable_x}'[a_orig_g];"
                f"[a_lp_in]lowpass=f=400[a_lp];"
                f"[a_lp]volume=0:enable='{not_x}'[a_lp_g];"
                f"[a_orig_g][a_lp_g]amix=inputs=2:duration=first:normalize=0[a]"
            ), "a"

        # Default: silence
        return f"[{source}]volume=0:enable='{enable_x}'[a]", "a"

    def _build_video_filter(self, regions, video_mode, blur_strength=5):
        """filter_complex segment for video. Returns (graph_text, output_label) or (None, None)."""
        if not regions:
            return None, None

        if video_mode == "box":
            chained = ",".join(
                f"drawbox=x={r['x']}:y={r['y']}:w={r['w']}:h={r['h']}:"
                f"color=black@1.0:t=fill:enable='between(t,{r['t_start']:.2f},{r['t_end']:.2f})'"
                for r in regions
            )
            return f"[0:v]{chained}[v]", "v"

        # blur / pixelate: per region, crop a copy, apply effect, overlay back with time gating.
        if video_mode == "pixelate":
            f = pixelate_factor(blur_strength)
            effect = f"scale=iw/{f}:ih/{f}:flags=area,scale=iw*{f}:ih*{f}:flags=neighbor"
        else:
            effect = f"gblur=sigma={gblur_sigma(blur_strength)}"  # blur (broadcast-style)

        n = len(regions)
        parts = []
        split_labels = "[base]" + "".join(f"[src{i}]" for i in range(n))
        parts.append(f"[0:v]split={n + 1}{split_labels}")

        for i, r in enumerate(regions):
            parts.append(f"[src{i}]crop={r['w']}:{r['h']}:{r['x']}:{r['y']},{effect}[fx{i}]")

        current = "base"
        for i, r in enumerate(regions):
            next_label = f"step{i}" if i < n - 1 else "v"
            parts.append(
                f"[{current}][fx{i}]overlay={r['x']}:{r['y']}:"
                f"enable='between(t,{r['t_start']:.2f},{r['t_end']:.2f})'[{next_label}]"
            )
            current = next_label

        return ";".join(parts), "v"

    def render_face_blur(self, input_path, output_path, identities, face_mode,
                         mute_intervals, video_mode, audio_mode, blur_strength=5):
        """OpenCV per-frame face-tracking blur supporting multiple reference
        identities and two modes:
          - face_mode='selected': blur faces matching ANY identity (blacklist)
          - face_mode='others':   blur faces matching NONE (whitelist)

        `identities` is a list of dicts: [{'name': str, 'embedding': ndarray}, ...]
        Returns a stats list usable for the dashboard:
          [{'name': str, 'matched_frames': int, 'peak_similarity': float}, ...]
        """
        engine = self._get_face_engine()
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video {input_path}")
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0

        temp_video = output_path + ".video.mp4"
        writer = cv2.VideoWriter(temp_video, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
        if not writer.isOpened():
            cap.release()
            raise RuntimeError("Could not open VideoWriter")

        # Per-identity stats (frames where this identity was the best match) +
        # an aggregate "others" bucket for the whitelist case.
        stats = {ident["name"]: {"matched_frames": 0, "peak_similarity": -1.0} for ident in identities}
        others_blurred_frames = 0
        threshold = face_utils.SIMILARITY_THRESHOLD

        frame_idx = 0
        progress_every = max(1, total // 20) if total else 60
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            faces = engine.detect(frame)
            ident_seen_this_frame = set()
            others_seen_this_frame = False
            for face in faces:
                try:
                    emb = engine.embed(frame, face)
                except cv2.error:
                    continue

                best_name = None
                best_sim = -1.0
                for ident in identities:
                    sim = engine.cosine(ident["embedding"], emb)
                    if sim > best_sim:
                        best_sim = sim
                        if sim >= threshold:
                            best_name = ident["name"]

                # Update per-identity peak even when below threshold (debug aid)
                if best_name is not None:
                    s = stats[best_name]
                    if best_sim > s["peak_similarity"]:
                        s["peak_similarity"] = best_sim

                should_blur = (face_mode == "selected" and best_name is not None) \
                              or (face_mode == "others" and best_name is None)

                if should_blur:
                    face_utils.apply_region_effect(
                        frame, face[0], face[1], face[2], face[3], video_mode, blur_strength
                    )
                    if best_name is not None:
                        ident_seen_this_frame.add(best_name)
                    else:
                        others_seen_this_frame = True

            for name in ident_seen_this_frame:
                stats[name]["matched_frames"] += 1
            if others_seen_this_frame:
                others_blurred_frames += 1

            writer.write(frame)
            frame_idx += 1
            if frame_idx % progress_every == 0:
                pct = (frame_idx / total * 100) if total else 0
                print(f"    Face render: frame {frame_idx}/{total} ({pct:.0f}%)")

        cap.release()
        writer.release()
        print(f"  Face render complete. Frames: {frame_idx}. Mode: {face_mode}")
        for name, s in stats.items():
            print(f"    {name}: {s['matched_frames']} frames, peak sim={s['peak_similarity']:.3f}")
        if face_mode == "others":
            print(f"    Others (blurred): {others_blurred_frames} frames")

        self._mux_audio_back(temp_video, input_path, output_path, mute_intervals, audio_mode)
        if os.path.exists(temp_video):
            os.remove(temp_video)

        # Return a list of stats — flat shape matches what the frontend will render
        result = [
            {"name": name, "matched_frames": s["matched_frames"], "peak_similarity": round(s["peak_similarity"], 3)}
            for name, s in stats.items()
        ]
        if face_mode == "others":
            result.append({"name": "Others (blurred)", "matched_frames": others_blurred_frames, "peak_similarity": None})
        return result

    def _mux_audio_back(self, video_only_path, audio_source_path, output_path,
                        mute_intervals, audio_mode):
        """Combine OpenCV-rendered video (input 0) with audio from the original
        video (input 1), optionally applying interval-based audio censorship."""
        a_part, a_out = self._build_audio_filter(mute_intervals, audio_mode, source="1:a")
        cmd = ["ffmpeg", "-y", "-i", video_only_path, "-i", audio_source_path]
        if a_part:
            cmd.extend([
                "-filter_complex", a_part,
                "-map", "0:v:0", "-map", f"[{a_out}]",
                "-c:v", "libx264", "-c:a", "aac", "-shortest",
            ])
        else:
            cmd.extend([
                "-map", "0:v:0", "-map", "1:a:0?",
                "-c:v", "libx264", "-c:a", "aac", "-shortest",
            ])
        cmd.append(output_path)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg mux failed: {result.stderr[-500:]}")

    def build_ffmpeg_command(self, input_path, output_path, mute_intervals, video_blurs,
                             video_mode="blur", audio_mode="beep", blur_strength=5):
        regions = []
        for blur in video_blurs:
            x = max(0, int(blur["box"]["xmin"]))
            y = max(0, int(blur["box"]["ymin"]))
            w = int(blur["box"]["xmax"]) - x
            h = int(blur["box"]["ymax"]) - y
            # Even dimensions — overlay/scale filters dislike odd values
            if w % 2: w -= 1
            if h % 2: h -= 1
            if w < 4 or h < 4:
                continue
            regions.append({
                "x": x, "y": y, "w": w, "h": h,
                "t_start": max(0.0, blur["timestamp"] - 2.5),
                "t_end": blur["timestamp"] + 2.5,
            })

        cmd = ["ffmpeg", "-y", "-i", input_path]
        v_part, v_out = self._build_video_filter(regions, video_mode, blur_strength)
        a_part, a_out = self._build_audio_filter(mute_intervals, audio_mode)

        if v_part and a_part:
            cmd.extend(["-filter_complex", f"{v_part};{a_part}",
                        "-map", f"[{v_out}]", "-map", f"[{a_out}]",
                        "-c:v", "libx264", "-c:a", "aac"])
        elif v_part:
            cmd.extend(["-filter_complex", v_part,
                        "-map", f"[{v_out}]", "-map", "0:a?",
                        "-c:v", "libx264", "-c:a", "aac"])
        elif a_part:
            cmd.extend(["-filter_complex", a_part,
                        "-map", "0:v", "-map", f"[{a_out}]",
                        "-c:v", "libx264", "-c:a", "aac"])
        else:
            cmd.extend(["-c", "copy"])

        cmd.append(output_path)
        return cmd

    def process_task(self, task_data):
        task_id = task_data["task_id"]
        input_path = task_data["file_path"]
        blur_objects = task_data.get("blur_objects", [])
        censor_audio = task_data.get("censor_audio", False)
        video_mode = task_data.get("video_mode", "blur")
        audio_mode = task_data.get("audio_mode", "beep")
        blur_strength = clamp_strength(task_data.get("blur_strength", 5))
        # New shape: a list of {path, name} dicts. Old shape (single path) still
        # accepted for backwards compatibility.
        face_references = task_data.get("face_references") or []
        legacy_single = task_data.get("target_face_image")
        if legacy_single and not face_references:
            face_references = [{"path": legacy_single, "name": "Target"}]
        face_mode = task_data.get("face_mode", "selected")  # 'selected' | 'others'
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if not os.path.isabs(input_path):
            input_path = os.path.join(project_root, input_path)
        for ref in face_references:
            if ref.get("path") and not os.path.isabs(ref["path"]):
                ref["path"] = os.path.join(project_root, ref["path"])
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

        # Branch: face-tracking blur (OpenCV) vs static-region blur (FFmpeg).
        face_blur_active = bool(face_references) or face_mode == "others"
        if face_blur_active:
            engine = self._get_face_engine()
            identities = []
            for ref in face_references:
                try:
                    emb = engine.embed_reference(ref["path"])
                    identities.append({"name": ref.get("name") or "Unnamed", "embedding": emb})
                    print(f"  Reference embedded: {ref.get('name') or '(unnamed)'} <- {ref['path']}")
                except Exception as e:
                    print(f"  [WARN] Skipping reference '{ref.get('name')}': {e}")
            if face_mode == "selected" and not identities:
                raise RuntimeError("Face-blur 'selected' mode requires at least one valid reference photo.")
            print(f"  [2/3] Face-tracking blur — mode={face_mode}, identities={len(identities)}")
            stats = self.render_face_blur(
                input_path, output_path, identities, face_mode,
                mute_intervals, video_mode, audio_mode, blur_strength,
            )
            print(f"  [3/3] Finalizing state...")
            rel_output = output_path.replace(project_root + os.sep, "").replace("\\", "/")
            es.update_worker_status(task_id, "censor", "done", {
                "censored_file_path": rel_output,
                "face_blur_stats": stats,
                "face_blur_mode": face_mode,
            })
            print(f"  [OK] Face-tracked censored video generated.")
            for ref in face_references:
                try:
                    if ref.get("path") and os.path.exists(ref["path"]):
                        os.remove(ref["path"])
                except OSError:
                    pass
            return

        print(f"  [2/3] Executing FFmpeg rendering pipeline...")
        cmd = self.build_ffmpeg_command(
            input_path, output_path, mute_intervals, video_blurs,
            video_mode=video_mode, audio_mode=audio_mode, blur_strength=blur_strength,
        )
        print(f"  Modes: video={video_mode}, audio={audio_mode}, strength={blur_strength}")
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
