# Blur-Strength Slider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the user control the censorship blur strength from the redaction panel — a "Light → Strong" slider that drives the FFmpeg blur sigma / pixelate block size and the OpenCV face-blur kernel end-to-end.

**Architecture:** Extract the strength→parameters mapping into one pure module (`workers/blur_strength.py`) used by both blur paths, so they stay consistent and it's unit-testable. A `blur_strength` integer (1–10, default 5) rides from a UI slider → the `/tasks/{id}/censor` form → the censor payload → those two paths. **Strength 5 reproduces today's exact output** (sigma 15, pixelate factor 12, kernel `max(15, min(w,h)//4)`), so default behaviour is unchanged.

**Tech Stack:** Python (FFmpeg via subprocess, OpenCV), React (Vite). Backend mapping is unit-tested with the repo's plain-script style (`.venv/Scripts/python.exe`); worker wiring + the slider are verified by a live censor run and `npm run build`.

---

## File Structure

- **Create:** `workers/blur_strength.py` — pure helpers `clamp_strength`, `gblur_sigma`, `pixelate_factor`, `opencv_blur_kernel`. No cv2/torch imports.
- **Create:** `workers/test_blur_strength.py` — unit tests (plain-script harness like `test_detection_utils.py`).
- **Modify:** `workers/censor_worker.py` — `_build_video_filter`, `build_ffmpeg_command`, `render_face_blur`, `process_task` thread a `blur_strength` value through.
- **Modify:** `workers/face_utils.py` — `apply_region_effect` takes `strength`.
- **Modify:** `api/main.py` — `/tasks/{task_id}/censor` gains a `blur_strength` form field.
- **Modify:** `frontend/src/components/AnalysisDashboard.jsx` — slider + `blur_strength` in the censor request.

Commits use no co-author trailer (per project preference).

---

## Task 1: Pure blur-strength helpers (TDD)

**Files:**
- Create: `workers/blur_strength.py`
- Create: `workers/test_blur_strength.py`

- [ ] **Step 1: Write the failing test**

Create `workers/test_blur_strength.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe workers/test_blur_strength.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'blur_strength'`.

- [ ] **Step 3: Write the implementation**

Create `workers/blur_strength.py`:

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe workers/test_blur_strength.py`
Expected: PASS; final line `5 passed, 0 failed`.

- [ ] **Step 5: Commit**

```bash
git add workers/blur_strength.py workers/test_blur_strength.py
git commit -m "feat(censor): pure blur-strength->params mapping with unit tests"
```

---

## Task 2: Thread blur_strength through the censor worker

**Files:**
- Modify: `workers/censor_worker.py`
- Modify: `workers/face_utils.py`

- [ ] **Step 1: Use the helpers in `_build_video_filter`**

In `workers/censor_worker.py`, add the import near the top (next to the other worker imports):
```python
from blur_strength import gblur_sigma, pixelate_factor, clamp_strength
```
Change the signature `def _build_video_filter(self, regions, video_mode):` to:
```python
    def _build_video_filter(self, regions, video_mode, blur_strength=5):
```
Replace the effect block:
```python
        if video_mode == "pixelate":
            effect = "scale=iw/12:ih/12:flags=area,scale=iw*12:ih*12:flags=neighbor"
        else:
            effect = "gblur=sigma=15"  # blur (broadcast-style)
```
with:
```python
        if video_mode == "pixelate":
            f = pixelate_factor(blur_strength)
            effect = f"scale=iw/{f}:ih/{f}:flags=area,scale=iw*{f}:ih*{f}:flags=neighbor"
        else:
            effect = f"gblur=sigma={gblur_sigma(blur_strength)}"  # blur (broadcast-style)
```

- [ ] **Step 2: Pass blur_strength through `build_ffmpeg_command`**

Change `def build_ffmpeg_command(self, input_path, output_path, mute_intervals, video_blurs, video_mode="blur", audio_mode="beep"):` to add a `blur_strength=5` parameter at the end of the signature. Then update the internal call `v_part, v_out = self._build_video_filter(regions, video_mode)` to `v_part, v_out = self._build_video_filter(regions, video_mode, blur_strength)`.

- [ ] **Step 3: Pass blur_strength through `render_face_blur`**

Change `def render_face_blur(self, input_path, output_path, identities, face_mode, mute_intervals, video_mode, audio_mode):` to add `blur_strength=5` at the end. Update the per-frame call:
```python
                    face_utils.apply_region_effect(
                        frame, face[0], face[1], face[2], face[3], video_mode
                    )
```
to:
```python
                    face_utils.apply_region_effect(
                        frame, face[0], face[1], face[2], face[3], video_mode, blur_strength
                    )
```

- [ ] **Step 4: Read blur_strength in `process_task` and pass it to both calls**

In `process_task`, next to the other `task_data.get(...)` reads (around `video_mode = task_data.get("video_mode", "blur")`), add:
```python
        blur_strength = clamp_strength(task_data.get("blur_strength", 5))
```
Then add `blur_strength` to BOTH the `render_face_blur(...)` call and the `build_ffmpeg_command(...)` call (append it as the last argument; both signatures now accept it). Also extend the existing modes print to include it, e.g.:
```python
        print(f"  Modes: video={video_mode}, audio={audio_mode}, strength={blur_strength}")
```

- [ ] **Step 5: Use the strength in `face_utils.apply_region_effect`**

In `workers/face_utils.py`, add at the top:
```python
from blur_strength import pixelate_factor, opencv_blur_kernel
```
Change `def apply_region_effect(frame, x, y, w, h, mode):` to:
```python
def apply_region_effect(frame, x, y, w, h, mode, strength=5):
```
Replace the pixelate line `sw = max(1, w // 12); sh = max(1, h // 12)` with:
```python
        f = pixelate_factor(strength)
        sw = max(1, w // f); sh = max(1, h // f)
```
Replace the blur block:
```python
        # Kernel ~odd, scaled to face size so blur strength tracks subject scale
        k = max(15, (min(w, h) // 4) | 1)
        frame[y:y + h, x:x + w] = cv2.GaussianBlur(region, (k, k), 0)
```
with:
```python
        # Kernel scaled to face size AND the chosen strength (odd).
        k = opencv_blur_kernel(w, h, strength)
        frame[y:y + h, x:x + w] = cv2.GaussianBlur(region, (k, k), 0)
```

- [ ] **Step 6: Verify the worker compiles**

```bash
cd "d:/LICENTA/EchoStream" && .venv/Scripts/python.exe -m py_compile workers/censor_worker.py workers/face_utils.py workers/blur_strength.py && echo "compile OK"
```
Expected: `compile OK`.

- [ ] **Step 7: Commit**

```bash
git add workers/censor_worker.py workers/face_utils.py
git commit -m "feat(censor): thread blur_strength through FFmpeg + OpenCV blur paths"
```

---

## Task 3: Accept blur_strength on the censor endpoint

**Files:**
- Modify: `api/main.py` (`/tasks/{task_id}/censor`)

- [ ] **Step 1: Add the form field and payload key**

In `api/main.py`, in the `censor_video` handler signature (the `@app.post("/tasks/{task_id}/censor")` function), add a parameter alongside the existing `Form(...)` ones:
```python
    blur_strength: int = Form(5),
```
Then in the `censor_payload` dict that is published to the censor queue, add:
```python
        "blur_strength": max(1, min(10, blur_strength)),
```

- [ ] **Step 2: Verify**

```bash
cd "d:/LICENTA/EchoStream" && .venv/Scripts/python.exe -c "import api.main; print('import OK')"
grep -n "blur_strength" api/main.py
```
Expected: `import OK`; two hits (the `Form` param and the payload key).

- [ ] **Step 3: Commit**

```bash
git add api/main.py
git commit -m "feat(api): accept blur_strength on the censor endpoint"
```

---

## Task 4: Blur-strength slider in the redaction panel

**Files:**
- Modify: `frontend/src/components/AnalysisDashboard.jsx`

- [ ] **Step 1: Add state**

Next to the other redaction-config state (e.g. `const [videoMode, setVideoMode] = useState('blur');`), add:
```jsx
  const [blurStrength, setBlurStrength] = useState(5);
```

- [ ] **Step 2: Send it in the censor request**

In `handleCensor`, where the `FormData` is built (next to `fd.append('video_mode', videoMode);`), add:
```jsx
      fd.append('blur_strength', String(blurStrength));
```

- [ ] **Step 3: Add the slider to the Visual-redaction card**

In the Visual-redaction card, immediately after the "Method" `<select>` for `videoMode`, add (only shown for blur/pixelate — `box` has no strength):
```jsx
                {(videoMode === 'blur' || videoMode === 'pixelate') && (
                  <div style={{ marginTop: 14 }}>
                    <span className="field-label">Strength</span>
                    <input
                      type="range"
                      min={1}
                      max={10}
                      step={1}
                      value={blurStrength}
                      onChange={(e) => setBlurStrength(Number(e.target.value))}
                      style={{ width: '100%', accentColor: 'var(--acid)' }}
                    />
                    <div className="smallcaps" style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--bone-dim)' }}>
                      <span>Light</span><span>Strong</span>
                    </div>
                  </div>
                )}
```

- [ ] **Step 4: Verify build**

```bash
cd "d:/LICENTA/EchoStream/frontend" && npm run build 2>&1 | tail -3
```
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/AnalysisDashboard.jsx
git commit -m "feat(ui): blur-strength slider in the redaction panel"
```

---

## Task 5: End-to-end verification

**Files:** none (verification only)

- [ ] **Step 1: Static checks**

```bash
cd "d:/LICENTA/EchoStream"
.venv/Scripts/python.exe workers/test_blur_strength.py | tail -1
.venv/Scripts/python.exe -m py_compile workers/censor_worker.py workers/face_utils.py
.venv/Scripts/python.exe -c "import api.main; print('backend import OK')"
( cd frontend && npm run build 2>&1 | tail -1 )
```
Expected: tests pass, compile OK, import OK, build OK.

- [ ] **Step 2: Live low-vs-high censor (stack running; restart the censor worker first so it loads the new code)**

Restart `censor_worker.py`, then censor the same analysed task twice via the API — once with `blur_strength=1`, once with `blur_strength=10` — and confirm the two `_censored.mp4` outputs differ visibly (and that `blur_strength=5` reproduces the pre-slider look). Reuse the smoke-test upload/censor curl commands; add `-F "blur_strength=1"` / `-F "blur_strength=10"`.
Expected: stronger setting = visibly heavier blur; default `5` unchanged from before.

---

## Self-Review notes (author)

- **Spec coverage:** spec Change B asks for a Light→Strong slider (shown for blur+pixelate) driving the FFmpeg sigma, pixelate block size, and OpenCV kernel, default reproducing current. Task 1 = mapping (tested, default==current), Task 2 = both worker paths, Task 3 = endpoint, Task 4 = slider + request. ✓
- **Placeholder scan:** every code step shows complete code or an exact, anchored transformation; verification gives exact commands. The one visual judgement (Task 5 Step 2) has a clear criterion. ✓
- **Consistency:** `blur_strength` (snake_case) on the wire/backend/worker; `blurStrength` (camelCase) in React; helper names `clamp_strength`/`gblur_sigma`/`pixelate_factor`/`opencv_blur_kernel` match across Tasks 1–2; default 5 everywhere. ✓
