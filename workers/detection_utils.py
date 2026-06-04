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
