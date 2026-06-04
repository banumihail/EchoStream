"""
Unit tests for workers/detection_utils.py — pure functions, no GPU/model/video.
Run from repo root: .venv/Scripts/python.exe workers/test_detection_utils.py
Plain-script style to match the repo's existing tests; no pytest needed.
"""
from detection_utils import iou, dedupe_frame, peak_label_counts


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
