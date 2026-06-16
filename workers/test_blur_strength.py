"""Unit tests for workers/blur_strength.py — pure functions, no cv2.
Run from repo root: .venv/Scripts/python.exe workers/test_blur_strength.py"""
from blur_strength import clamp_strength, gblur_sigma, pixelate_factor, opencv_blur_kernel


def test_clamp_range():
    assert clamp_strength(0) == 1
    assert clamp_strength(11) == 10
    assert clamp_strength(5) == 5


def test_clamp_bad_input_defaults_to_5():
    assert clamp_strength(None) == 5
    assert clamp_strength("x") == 5


def test_sigma_default_matches_current():
    # The pre-existing FFmpeg blur was gblur=sigma=15 at the default strength.
    assert gblur_sigma(5) == 15
    assert gblur_sigma(1) == 3
    assert gblur_sigma(10) == 30


def test_pixelate_factor_default_matches_current():
    # The pre-existing pixelate down-scale factor was 12 at the default strength.
    assert pixelate_factor(5) == 12
    assert pixelate_factor(1) >= 2
    assert pixelate_factor(10) > pixelate_factor(5)


def test_opencv_kernel_default_matches_current_and_is_odd():
    # Pre-existing kernel was max(15, min(w,h)//4) | 1 at the default strength.
    w, h = 200, 120  # min = 120 -> //4 = 30
    assert opencv_blur_kernel(w, h, 5) == 31  # max(15, 30) -> 31 (odd)
    assert opencv_blur_kernel(40, 40, 5) == 15  # max(15, 10) -> 15 (already odd)
    assert opencv_blur_kernel(200, 120, 10) > opencv_blur_kernel(200, 120, 5)
    assert opencv_blur_kernel(200, 120, 3) % 2 == 1  # always odd


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]

if __name__ == "__main__":
    import traceback
    passed = failed = 0
    for t in TESTS:
        try:
            t(); print(f"PASS  {t.__name__}"); passed += 1
        except Exception:
            print(f"FAIL  {t.__name__}"); traceback.print_exc(); failed += 1
    print(f"\n{passed} passed, {failed} failed")
    raise SystemExit(1 if failed else 0)
