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
