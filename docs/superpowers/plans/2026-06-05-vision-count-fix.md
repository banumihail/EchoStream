# Vision Count Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the vision worker report how many of each object appear *at once* (peak per frame) instead of summing detections across every sampled frame, and drop duplicate boxes DETR occasionally emits for one object — fixing the "2 people reported as ×4" bug.

**Architecture:** Extract the geometry/counting logic out of `vision_worker.py` into a new pure-Python module `workers/detection_utils.py` (no torch/cv2 imports) so it can be unit-tested without a GPU, model, or video. The worker composes three helpers — `iou`, `dedupe_frame`, `peak_label_counts` — inside its existing frame loop. `objects_timeline` and the `summary` `[{label, count}]` shape are preserved, so nothing downstream (censor worker, frontend) changes.

**Tech Stack:** Python 3, plain-script unit tests run with the project venv (`.venv/Scripts/python.exe`) — matching the repo's existing test style; no pytest dependency added.

---

## File Structure

- **Create** `workers/detection_utils.py` — pure functions: `iou(a, b)`, `dedupe_frame(detections, iou_threshold=0.6)`, `peak_label_counts(frames)`. No third-party imports.
- **Create** `workers/test_detection_utils.py` — assert-based unit tests + a tiny runner that prints PASS/FAIL and exits non-zero on failure.
- **Modify** `workers/vision_worker.py` — import the helpers; inside `extract_and_analyze_frames`, de-dupe each frame's detections and build `summary` from `peak_label_counts`.

All commits use the repo's trailer:
```
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

---

## Task 1: IoU helper

**Files:**
- Create: `workers/detection_utils.py`
- Create: `workers/test_detection_utils.py`

- [ ] **Step 1: Write the failing test**

Create `workers/test_detection_utils.py`:

```python
"""
Unit tests for workers/detection_utils.py — pure functions, no GPU/model/video.
Run from repo root: .venv/Scripts/python.exe workers/test_detection_utils.py
Plain-script style to match the repo's existing tests; no pytest needed.
"""
from detection_utils import iou  # dedupe_frame, peak_label_counts added in later tasks


def _box(xmin, ymin, xmax, ymax):
    return {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax}


def test_iou_identical_is_one():
    b = _box(0, 0, 10, 10)
    assert iou(b, b) == 1.0


def test_iou_disjoint_is_zero():
    assert iou(_box(0, 0, 10, 10), _box(20, 20, 30, 30)) == 0.0


def test_iou_partial_overlap():
    # boxes 10x10 each, overlap is the 5x5 square (5,5)-(10,10)=25,
    # union = 100 + 100 - 25 = 175
    val = iou(_box(0, 0, 10, 10), _box(5, 5, 15, 15))
    assert abs(val - (25 / 175)) < 1e-6, val


def test_iou_degenerate_zero_area():
    assert iou(_box(5, 5, 5, 5), _box(0, 0, 10, 10)) == 0.0


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]

if __name__ == "__main__":
    import traceback
    passed = failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL  {t.__name__}")
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    raise SystemExit(1 if failed else 0)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe workers/test_detection_utils.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'detection_utils'` (the module doesn't exist yet).

- [ ] **Step 3: Write the minimal implementation**

Create `workers/detection_utils.py`:

```python
"""
Pure geometry/counting helpers for the vision worker.

Deliberately free of torch/cv2 imports so they unit-test without a GPU,
a model, or a video file. The worker composes these to (a) drop duplicate
boxes DETR sometimes emits for one object within a single frame, and
(b) report how many of each object appear *at once* (peak per frame)
rather than summed across every sampled frame.
"""


def iou(a: dict, b: dict) -> float:
    """Intersection-over-union of two boxes.

    Boxes are dicts with pixel coords xmin, ymin, xmax, ymax (the format
    the HuggingFace object-detection pipeline returns). Returns 0.0 for
    non-overlapping or degenerate (zero-area) boxes.
    """
    ix1 = max(a["xmin"], b["xmin"])
    iy1 = max(a["ymin"], b["ymin"])
    ix2 = min(a["xmax"], b["xmax"])
    iy2 = min(a["ymax"], b["ymax"])
    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = max(0, a["xmax"] - a["xmin"]) * max(0, a["ymax"] - a["ymin"])
    area_b = max(0, b["xmax"] - b["xmin"]) * max(0, b["ymax"] - b["ymin"])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe workers/test_detection_utils.py`
Expected: PASS for all four `test_iou_*` tests; final line `4 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add workers/detection_utils.py workers/test_detection_utils.py
git commit -m "feat(vision): add IoU helper with unit tests

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Per-frame de-duplication (NMS)

**Files:**
- Modify: `workers/detection_utils.py`
- Modify: `workers/test_detection_utils.py`

- [ ] **Step 1: Write the failing test**

In `workers/test_detection_utils.py`, change the import line at the top from:

```python
from detection_utils import iou  # dedupe_frame, peak_label_counts added in later tasks
```

to:

```python
from detection_utils import iou, dedupe_frame  # peak_label_counts added in Task 3
```

Then add these test functions above the `TESTS = ...` line:

```python
def test_dedupe_merges_overlapping_same_label():
    dets = [
        {"label": "person", "score": 0.95, "box": _box(0, 0, 10, 10)},
        {"label": "person", "score": 0.88, "box": _box(1, 1, 11, 11)},  # iou ~0.68
    ]
    kept = dedupe_frame(dets, 0.6)
    assert len(kept) == 1
    assert kept[0]["score"] == 0.95  # the higher-score box survives


def test_dedupe_keeps_distinct_same_label():
    dets = [
        {"label": "person", "score": 0.95, "box": _box(0, 0, 10, 10)},
        {"label": "person", "score": 0.90, "box": _box(40, 40, 50, 50)},  # no overlap
    ]
    assert len(dedupe_frame(dets, 0.6)) == 2  # two real people


def test_dedupe_never_merges_across_labels():
    dets = [
        {"label": "person", "score": 0.95, "box": _box(0, 0, 10, 10)},
        {"label": "tie", "score": 0.90, "box": _box(1, 1, 11, 11)},  # overlaps, diff label
    ]
    assert len(dedupe_frame(dets, 0.6)) == 2


def test_dedupe_empty():
    assert dedupe_frame([], 0.6) == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe workers/test_detection_utils.py`
Expected: FAIL — `ImportError: cannot import name 'dedupe_frame' from 'detection_utils'`.

- [ ] **Step 3: Write the minimal implementation**

Append to `workers/detection_utils.py`:

```python
def dedupe_frame(detections, iou_threshold: float = 0.6):
    """Greedy per-label non-max suppression within ONE frame.

    detections: list of dicts, each with "label", "score", "box".
    Keeps the highest-score box and drops any later same-label box that
    overlaps a kept one by >= iou_threshold. Boxes of different labels
    never suppress each other. Returns a new list ordered by descending score.
    """
    kept = []
    for det in sorted(detections, key=lambda d: d["score"], reverse=True):
        if any(
            k["label"] == det["label"] and iou(k["box"], det["box"]) >= iou_threshold
            for k in kept
        ):
            continue
        kept.append(det)
    return kept
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe workers/test_detection_utils.py`
Expected: PASS; final line `8 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add workers/detection_utils.py workers/test_detection_utils.py
git commit -m "feat(vision): add per-frame NMS de-duplication

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Peak-per-frame counting

**Files:**
- Modify: `workers/detection_utils.py`
- Modify: `workers/test_detection_utils.py`

- [ ] **Step 1: Write the failing test**

In `workers/test_detection_utils.py`, change the import line to:

```python
from detection_utils import iou, dedupe_frame, peak_label_counts
```

Then add these test functions above the `TESTS = ...` line:

```python
def test_peak_counts_uses_max_not_sum():
    # The exact bug: 2 people in each of 2 sampled frames was reported as 4.
    frames = [
        [{"label": "person"}, {"label": "person"}],
        [{"label": "person"}, {"label": "person"}],
    ]
    assert peak_label_counts(frames) == {"person": 2}


def test_peak_counts_multi_label():
    frames = [
        [{"label": "person"}, {"label": "car"}],
        [{"label": "person"}, {"label": "person"}, {"label": "car"}],
    ]
    assert peak_label_counts(frames) == {"person": 2, "car": 1}


def test_peak_counts_empty():
    assert peak_label_counts([]) == {}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe workers/test_detection_utils.py`
Expected: FAIL — `ImportError: cannot import name 'peak_label_counts' from 'detection_utils'`.

- [ ] **Step 3: Write the minimal implementation**

Append to `workers/detection_utils.py`:

```python
def peak_label_counts(frames) -> dict:
    """Peak simultaneous count of each label across sampled frames.

    frames: list of per-frame detection lists (each detection a dict with
    "label"). Returns {label: max number seen in any single frame} — the
    intuitive "how many are in this video", versus the old behaviour of
    summing detections across every sampled frame.
    """
    peak = {}
    for frame in frames:
        counts = {}
        for det in frame:
            counts[det["label"]] = counts.get(det["label"], 0) + 1
        for label, c in counts.items():
            if c > peak.get(label, 0):
                peak[label] = c
    return peak
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe workers/test_detection_utils.py`
Expected: PASS; final line `11 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add workers/detection_utils.py workers/test_detection_utils.py
git commit -m "feat(vision): add peak-per-frame label counting

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Wire the helpers into the vision worker

**Files:**
- Modify: `workers/vision_worker.py` (import line near top; `extract_and_analyze_frames` body, ~lines 9-15 and 64-104)

- [ ] **Step 1: Add the import**

In `workers/vision_worker.py`, find this block near the top (around line 9-12):

```python
import os, sys, cv2, torch
from transformers import pipeline
from PIL import Image
from base_worker import BaseWorker
```

Add the helper import directly beneath it:

```python
import os, sys, cv2, torch
from transformers import pipeline
from PIL import Image
from base_worker import BaseWorker
from detection_utils import dedupe_frame, peak_label_counts
```

- [ ] **Step 2: Initialise a per-frame list**

In `extract_and_analyze_frames`, find (around line 64):

```python
        all_objects = []
        frame_idx = 0
```

Replace with:

```python
        all_objects = []
        frames = []  # one entry per sampled frame: its de-duplicated detections
        frame_idx = 0
```

- [ ] **Step 3: De-dupe each frame and record it**

Find this block in the loop (around lines 81-91):

```python
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
```

Replace with:

```python
            results = self.vision_classifier(pil_image)
            inv = 1.0 / scale if scale != 0 else 1.0
            # Keep confident boxes, then drop duplicate boxes DETR sometimes
            # emits for the same object within this single frame.
            frame_dets = dedupe_frame([r for r in results if r['score'] >= 0.8])
            frames.append(frame_dets)
            for res in frame_dets:
                box = res["box"]
                all_objects.append({
                    "timestamp": round(current_time, 2),
                    "label": res["label"],
                    "confidence": round(res["score"], 2),
                    "box": {k: int(v * inv) for k, v in box.items()},
                })
```

- [ ] **Step 4: Build the summary from peak-per-frame counts**

Find this block after the loop (around lines 98-102):

```python
        label_counts = {}
        for obj in all_objects:
            lbl = obj["label"]
            label_counts[lbl] = label_counts.get(lbl, 0) + 1
        summary = [{"label": l, "count": c} for l, c in label_counts.items()]
```

Replace with:

```python
        # Report the peak simultaneous count per label (max in any single
        # frame), not the sum of detections across all sampled frames.
        summary = [{"label": l, "count": c} for l, c in peak_label_counts(frames).items()]
```

- [ ] **Step 5: Deterministic check on real data already in Elasticsearch**

This proves the new counting produces a sane, smaller number on the real prior task without needing a GPU re-run. Create a throwaway script `scratch/check_peak.py`:

```python
"""Recompute peak-vs-sum counts over an existing task's objects_timeline."""
import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "workers"))
from detection_utils import peak_label_counts
import requests

# Existing completed smoke-test task (see scratch/taskid.txt from the smoke test).
with open(os.path.join(os.path.dirname(__file__), "taskid.txt")) as f:
    task_id = f.read().strip()
with open(os.path.join(os.path.dirname(__file__), "token.txt")) as f:
    token = f.read().strip()

r = requests.get(f"https://localhost:8000/tasks/{task_id}",
                 headers={"Authorization": f"Bearer {token}"}, verify=False)
tl = r.json()["vision_analysis"]["objects_timeline"]

# Group detections by timestamp into frames, then compute peak.
by_ts = {}
for det in tl:
    by_ts.setdefault(det["timestamp"], []).append(det)
frames = list(by_ts.values())

old_sum = {}
for det in tl:
    old_sum[det["label"]] = old_sum.get(det["label"], 0) + 1
print("OLD (summed across frames):", old_sum)
print("NEW (peak per frame)      :", peak_label_counts(frames))
```

Run: `.venv/Scripts/python.exe scratch/check_peak.py`
Expected: the NEW counts are ≤ the OLD counts for every label (e.g. OLD `{'person': 3}` → NEW `{'person': 1}` or `{'person': 2}`), confirming the peak-per-frame number is the realistic "at once" count. (Exact numbers depend on the clip; the point is NEW ≤ OLD and matches the max persons visible in a single sampled frame.)

- [ ] **Step 6: Restart the vision worker and re-run end-to-end**

The running `vision_worker.py` process holds the OLD code in memory — it must be restarted to pick up the change.

```powershell
# Stop the old vision worker (leave the others running)
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match 'vision_worker' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

# Start it fresh
$root='d:\LICENTA\EchoStream'; $py="$root\.venv\Scripts\python.exe"
Start-Process $py -ArgumentList "$root\workers\vision_worker.py" -WorkingDirectory "$root\workers" `
  -RedirectStandardOutput "$root\scratch\vision_worker_stdout.log" `
  -RedirectStandardError "$root\scratch\vision_worker_stderr.log" -WindowStyle Hidden
```

Wait ~25s for the DETR model to load (confirm the process reaches ~390 MB working set), then upload a fresh clip as the `smoketest` user and poll the new task (reuse the smoke-test upload/poll commands). Inspect `vision_analysis.summary`.
Expected: the `person` count equals the maximum number of people visible in any single sampled frame (not the cross-frame sum); censor of `person` still blurs correctly.

- [ ] **Step 7: Commit**

```bash
git add workers/vision_worker.py
git commit -m "fix(vision): report peak-per-frame object counts, de-dupe per frame

A 2-person clip previously reported 'person x4' because the summary
summed detections across every sampled frame. Now each frame is
NMS-de-duplicated and the summary reports the peak simultaneous count
per label. objects_timeline and the summary shape are unchanged.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

(Delete `scratch/check_peak.py` afterward — it's a throwaway; `scratch/` is gitignored so no commit needed.)

---

## Self-Review notes (author)

- **Spec coverage:** spec Workstream 3 asks for (a) per-frame IoU/NMS de-dup and (b) peak-per-frame counting, preserving `objects_timeline` and `summary` shape. Task 2 covers (a), Task 3 covers (b), Task 4 wires both in and preserves both interfaces. ✓
- **Placeholder scan:** every code step shows complete code; verification steps give exact commands and expected outcomes. The only non-deterministic expectation (Task 4 Step 6) is explicitly flagged as clip-dependent with a clear qualitative criterion. ✓
- **Type/name consistency:** `iou`, `dedupe_frame(detections, iou_threshold=0.6)`, `peak_label_counts(frames)` are referenced identically in tests, implementation, and the worker. Detection dicts use keys `label`/`score`/`box` (raw pipeline output) in `dedupe_frame`; box dicts use `xmin/ymin/xmax/ymax`. ✓
