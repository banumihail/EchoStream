"""Map a 1-10 'blur strength' to the concrete parameters each censor path needs.

Pure (no cv2/ffmpeg) so it unit-tests in isolation. Strength 5 reproduces the
pre-slider defaults exactly: FFmpeg gblur sigma 15, pixelate down-scale 12, and
OpenCV kernel max(15, min(w,h)//4)."""


def clamp_strength(strength) -> int:
    """Coerce arbitrary input to an int in [1, 10]; default 5 on bad input."""
    try:
        s = int(strength)
    except (TypeError, ValueError):
        return 5
    return max(1, min(10, s))


def gblur_sigma(strength) -> int:
    """FFmpeg gblur sigma. 5 -> 15 (the previous fixed value)."""
    return clamp_strength(strength) * 3


def pixelate_factor(strength) -> int:
    """Down-scale factor for pixelation (bigger = blockier). 5 -> 12."""
    return max(2, clamp_strength(strength) * 2 + 2)


def opencv_blur_kernel(w: int, h: int, strength) -> int:
    """Odd GaussianBlur kernel size for an OpenCV face region, scaled to both
    the subject size and the strength. 5 -> max(15, min(w,h)//4)."""
    s = clamp_strength(strength)
    k = max(s * 3, (min(w, h) * s) // 20)
    return k | 1  # force odd
