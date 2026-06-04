# Frontend Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace EchoStream's bare full-page login with a landing page + auth modal, and remove the "AI-ish" tells (glassmorphism, gradient text, generic purple icons, emoji) by aligning the entry/auth screens to the app's existing flat "forensic console" design system.

**Architecture:** Add `Icon.jsx` (bespoke inline-SVG set, `currentColor` strokes) and `LandingPage.jsx` (capability-grid hero). Move the login/register/MFA logic out of `Login.jsx` into `AuthModal.jsx` — an overlay — with the markup restyled from `glass-panel` to the existing `slate` surface. `App.jsx` shows `LandingPage` when logged out and layers the modal on top. De-glass `Security.jsx` the same way. No app-logic changes; the five MFA flows are relocated verbatim.

**Tech Stack:** React 18 + Vite. No test framework in the frontend — **verification is visual**: the running dev server (`http://localhost:5173`) + headless-Chrome screenshots reviewed at each task. (Self-signed API cert: screenshots of static screens render fine; for flows that call the API, the cert must be accepted once or `API_HTTPS=0`.)

**Design tokens (already in `index.css`):** `--ink-1/2/3`, `--bone`/`--bone-dim`/`--bone-faint`, `--acid`, `--rule`/`--rule-bright`, `--serif` (Fraunces), `--sans` (Geist), `--mono` (Geist Mono). Surfaces: `.slate`, `.slate--marks`. Buttons: `.btn`, `.btn-primary`, `.btn-outline`, `.btn-ghost`. Inputs: `.login-input`, `.login-label`. Brand: `.wordmark` (serif, with `em` rendered in acid).

---

## File Structure

- **Create** `frontend/src/components/Icon.jsx` — `<Icon name=... size=... />`; one inline-SVG `<symbol>`-free map. `stroke="currentColor"` so icons inherit `--bone`/`--acid` from context. Single responsibility: iconography.
- **Create** `frontend/src/components/LandingPage.jsx` — logged-out hero + capability grid. Props `onSignIn`, `onGetStarted`.
- **Create** `frontend/src/components/AuthModal.jsx` — overlay hosting login/register/MFA. Props `initialMode`, `onClose`, `onLoggedIn`. Absorbs all logic from `Login.jsx`.
- **Modify** `frontend/src/App.jsx` — render `LandingPage` + `AuthModal` when logged out; app unchanged when logged in.
- **Modify** `frontend/src/index.css` — add landing, modal/overlay, and icon styles; remove dead `glass-panel`/`gradient-text` rules at the end.
- **Modify** `frontend/src/components/Security.jsx` — `glass-panel`→`slate`, `⚠️`→`<Icon name="alert">`.
- **Modify** `frontend/public/icons.svg` — re-stroke social icons from `#aa3bff` to bone (`#efece5`).
- **Delete** `frontend/src/components/Login.jsx` — after `AuthModal` is verified.

Commits use the repo trailer:
```
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

**Verification helper (used by several tasks).** Headless screenshot of a URL (PowerShell):
```powershell
$chrome = "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
$shot = "d:\LICENTA\EchoStream\scratch\fe_check.png"
& $chrome --headless=new --disable-gpu --no-sandbox --ignore-certificate-errors `
  --virtual-time-budget=6000 --user-data-dir="d:\LICENTA\EchoStream\scratch\chrome_profile" `
  --window-size=1440,900 --screenshot="$shot" "<URL>" 2>$null
```
Then Read `scratch/fe_check.png` and confirm it renders as intended (no blank frame, on-brand surfaces, no emoji/purple).

---

## Task 1: Bespoke Icon component

**Files:**
- Create: `frontend/src/components/Icon.jsx`

- [ ] **Step 1: Create the icon set**

Paths reuse the Option-2 mockup the user approved, plus UI glyphs. Create `frontend/src/components/Icon.jsx`:

```jsx
import React from 'react';

// Bespoke evidence-room icon set. Stroke uses currentColor so icons take
// the surrounding text colour (bone, or acid where the parent sets it).
const PATHS = {
  // capability icons (from the approved landing mockup)
  transcript: <path d="M4 7h16M4 12h10M4 17h13" />,
  audio: <><path d="M12 3v18" /><path d="M7 8v8M17 8v8M3 11v2M21 11v2" /></>,
  identity: <><circle cx="9" cy="9" r="5" /><path d="M9 14c-3 0-6 2-6 5M14 12l6 6M20 12l-6 6" /></>,
  pii: <><path d="M12 3l7 3v6c0 4-3 7-7 9-4-2-7-5-7-9V6z" /><path d="M9 12l2 2 4-4" /></>,
  // UI glyphs
  alert: <><path d="M12 3 2 20h20L12 3z" /><path d="M12 10v4" /><path d="M12 17.5h.01" /></>,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="M15.5 15.5 21 21" /></>,
  upload: <><path d="M12 16V4M7 9l5-5 5 5" /><path d="M4 18v2h16v-2" /></>,
};

export default function Icon({ name, size = 20, className = '', style = {}, strokeWidth = 1.5 }) {
  const path = PATHS[name];
  if (!path) return null;
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={style}
    >
      {path}
    </svg>
  );
}
```

- [ ] **Step 2: Temporarily render a gallery for visual review**

In `frontend/src/App.jsx`, temporarily add at the very top of the returned JSX (inside the logged-in or logged-out branch, wherever renders first) a throwaway gallery — OR simpler, create `frontend/src/components/_IconGallery.jsx` and import it into `App.jsx` `return` for one screenshot. Minimal throwaway:

```jsx
// _IconGallery.jsx (throwaway — deleted in Step 4)
import React from 'react';
import Icon from './Icon';
const NAMES = ['transcript', 'audio', 'identity', 'pii', 'alert', 'close', 'search', 'upload'];
export default function IconGallery() {
  return (
    <div style={{ display: 'flex', gap: 28, padding: 40, background: 'var(--ink-1)', color: 'var(--bone)' }}>
      {NAMES.map(n => (
        <div key={n} style={{ textAlign: 'center', color: n === 'alert' ? 'var(--acid)' : 'var(--bone)' }}>
          <Icon name={n} size={32} />
          <div style={{ fontSize: 10, marginTop: 8, color: 'var(--bone-dim)' }}>{n}</div>
        </div>
      ))}
    </div>
  );
}
```

Render it by temporarily replacing the `return (...)` of `App.jsx` with `return <IconGallery />;` (remember the original return — restored in Step 4).

- [ ] **Step 3: Screenshot and review the gallery**

Ensure the dev server is running (`http://localhost:5173`). Run the Verification helper with `<URL>` = `http://localhost:5173/`, then Read `scratch/fe_check.png`.
Expected: 8 clean line-icons on the dark canvas, the `alert` glyph in acid, no purple, no emoji. Tune any path that looks off (this is the bespoke-icon design checkpoint) and re-screenshot until satisfied.

- [ ] **Step 4: Remove the throwaway gallery**

Restore `App.jsx`'s original `return (...)`, remove the temporary `IconGallery` import, and delete `frontend/src/components/_IconGallery.jsx`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Icon.jsx
git commit -m "feat(ui): add bespoke inline-SVG Icon component

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Landing + modal + icon CSS

**Files:**
- Modify: `frontend/src/index.css` (append a new section near the end, before any trailing utilities)

- [ ] **Step 1: Append the styles**

Append to `frontend/src/index.css`:

```css
/* ===================================================================== */
/*                       LANDING + AUTH MODAL                            */
/* ===================================================================== */

.landing { min-height: 100vh; display: flex; flex-direction: column; }
.landing-nav {
  display: flex; align-items: center; justify-content: space-between;
  padding: 20px 40px; border-bottom: 1px solid var(--rule);
}
.landing-nav-actions { display: flex; align-items: center; gap: 14px; }

.landing-hero { max-width: 1180px; margin: 0 auto; width: 100%; padding: 64px 40px 28px; }
.landing-eyebrow {
  font-family: var(--mono); font-size: 11px; letter-spacing: 0.22em;
  text-transform: uppercase; color: var(--bone-dim); margin-bottom: 18px;
}
.landing-title {
  font-family: var(--serif); font-weight: 500; letter-spacing: -0.02em;
  font-size: clamp(34px, 5vw, 56px); line-height: 1.03; max-width: 16ch; color: var(--bone);
}
.landing-sub { color: var(--bone-2); font-size: 16px; line-height: 1.55; max-width: 52ch; margin-top: 18px; }

.landing-tiles {
  max-width: 1180px; margin: 0 auto; width: 100%; padding: 24px 40px 56px;
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;
}
@media (max-width: 860px) { .landing-tiles { grid-template-columns: repeat(2, 1fr); } }
.landing-tile { background: var(--ink-2); border: 1px solid var(--rule); padding: 20px; transition: border-color var(--t-fast); }
.landing-tile:hover { border-color: var(--rule-bright); }
.landing-tile .tile-ic { color: var(--acid); margin-bottom: 12px; }
.landing-tile h4 { font-size: 14px; font-weight: 600; color: var(--bone); margin-bottom: 5px; }
.landing-tile p { font-size: 12.5px; color: var(--bone-dim); line-height: 1.5; }

.landing-models {
  max-width: 1180px; margin: 0 auto; width: 100%; padding: 0 40px 48px;
  font-family: var(--mono); font-size: 11px; letter-spacing: 0.16em; color: var(--bone-faint);
}

/* Auth modal */
.modal-overlay {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(5, 5, 5, 0.72);
  backdrop-filter: blur(2px);
  display: flex; align-items: center; justify-content: center; padding: 24px;
  animation: fade-in var(--t-base);
}
.modal-card {
  position: relative; width: 100%; max-width: 420px;
  background: var(--ink-2); border: 1px solid var(--rule-bright);
  padding: 28px; box-shadow: 0 24px 60px rgba(0, 0, 0, 0.6);
}
.modal-close {
  position: absolute; top: 14px; right: 14px;
  background: transparent; border: none; color: var(--bone-dim); cursor: pointer;
  padding: 4px; line-height: 0; transition: color var(--t-fast);
}
.modal-close:hover { color: var(--bone); }
.modal-title { font-family: var(--serif); font-size: 28px; font-weight: 400; color: var(--bone); letter-spacing: -0.01em; }
.modal-title em { font-style: italic; font-weight: 300; color: var(--acid); }
.modal-subtitle { color: var(--bone-dim); font-size: 13px; margin: 4px 0 20px; }
```

- [ ] **Step 2: Verify it parses (no build break)**

The Vite dev server hot-reloads CSS. Confirm the terminal running `npm run dev` shows no CSS/HMR error (check `scratch/frontend_stderr.log` if backgrounded). Expected: no error; page still loads at `http://localhost:5173`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat(ui): add landing + auth-modal styles

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: LandingPage component

**Files:**
- Create: `frontend/src/components/LandingPage.jsx`

- [ ] **Step 1: Create the component**

```jsx
import React from 'react';
import Icon from './Icon';

const TILES = [
  { icon: 'transcript', title: 'Word-level transcript', body: 'Clickable, searchable, time-synced to the video.' },
  { icon: 'audio', title: 'Audio redaction', body: 'Beep, muffle or silence sensitive speech.' },
  { icon: 'identity', title: 'Identity-aware blur', body: 'Blur one person across frames — or everyone else.' },
  { icon: 'pii', title: 'PII detection', body: "Names, places, orgs flagged the moment they're spoken." },
];

export default function LandingPage({ onSignIn, onGetStarted }) {
  return (
    <div className="landing fade-in">
      <nav className="landing-nav">
        <span className="wordmark">EchoStream</span>
        <div className="landing-nav-actions">
          <button className="btn btn-ghost" onClick={onSignIn}>Sign in</button>
          <button className="btn btn-primary" onClick={onGetStarted}>Get started</button>
        </div>
      </nav>

      <header className="landing-hero">
        <div className="landing-eyebrow">Upload · Detect · Redact</div>
        <h1 className="landing-title">Privacy redaction, done by the pipeline — not by hand.</h1>
        <p className="landing-sub">
          Five models analyse every clip in parallel, then an active-censorship stage physically
          blurs faces and mutes sensitive audio.
        </p>
      </header>

      <section className="landing-tiles">
        {TILES.map(t => (
          <div className="landing-tile" key={t.icon}>
            <Icon name={t.icon} size={22} className="tile-ic" />
            <h4>{t.title}</h4>
            <p>{t.body}</p>
          </div>
        ))}
      </section>

      <div className="landing-models">WHISPER · BERT · DETR · AST · YuNet+SFace</div>
    </div>
  );
}
```

- [ ] **Step 2: Wire a temporary preview**

Temporarily set `App.jsx`'s logged-out branch to `return <LandingPage onSignIn={() => {}} onGetStarted={() => {}} />;` (note the original logged-out branch — restored in Task 4).

- [ ] **Step 3: Screenshot and review**

Run the Verification helper with `<URL>` = `http://localhost:5173/` (logged out — clear localStorage first if needed: the helper uses a clean `--user-data-dir`, so it starts logged out). Read `scratch/fe_check.png`.
Expected: dark hero, serif headline, four capability tiles with acid line-icons, model line at the bottom. On-brand, no glass/gradient/emoji. Tune spacing/sizes here.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/LandingPage.jsx
git commit -m "feat(ui): add LandingPage (capability grid)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: AuthModal + App rewire

**Files:**
- Create: `frontend/src/components/AuthModal.jsx`
- Modify: `frontend/src/App.jsx`
- Delete: `frontend/src/components/Login.jsx`

- [ ] **Step 1: Create `AuthModal.jsx` by relocating Login logic**

Copy the entire contents of `frontend/src/components/Login.jsx` into a new `frontend/src/components/AuthModal.jsx`, then apply these exact changes:

1. Rename the component `const Login = ({ onLoggedIn }) =>` to `const AuthModal = ({ initialMode = 'login', onClose, onLoggedIn }) =>` and update `export default Login;` → `export default AuthModal;`.
2. Initialise mode from the prop: change `const [mode, setMode] = useState('login');` to `const [mode, setMode] = useState(initialMode);`.
3. Add `import Icon from './Icon';` to the imports.
4. Replace BOTH outer wrappers. The component has two `return` blocks (the `step === 'mfa'` block and the first-step block). Wrap each in the modal shell instead of the centered `fade-in` div. Replace:
   ```jsx
   <div className="fade-in" style={{ maxWidth: 420, margin: '80px auto 0' }}>
   ```
   with (in both places):
   ```jsx
   <div className="modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
     <div className="modal-card">
       <button className="modal-close" onClick={onClose} aria-label="Close"><Icon name="close" size={18} /></button>
   ```
   and change each block's closing `</div>` (the matching outer one) to `</div></div>`.
5. Replace the two title blocks. Change:
   ```jsx
   <h1 style={{ fontSize: '2.2rem', fontWeight: 700, marginBottom: 6 }}>
     <span className="gradient-text">EchoStream</span>
   </h1>
   <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem' }}>...</p>
   ```
   with:
   ```jsx
   <h1 className="modal-title">Echo<em>Stream</em></h1>
   <p className="modal-subtitle">...</p>
   ```
   (keep the existing subtitle text expressions in each block.)
6. Change the form wrapper class from `glass-panel` to `slate` in both `<form className="glass-panel" ...>` occurrences (drop the inline `padding: 24` — `.slate` already pads; or keep, harmless).
7. Replace the error-banner emoji. Change both occurrences of:
   ```jsx
   <span className="error-icon">⚠️</span>
   ```
   to:
   ```jsx
   <span className="error-icon"><Icon name="alert" size={16} /></span>
   ```
8. Remove the now-unused MFA-step "Back" behavior that returned to a full page — keep `resetToStart` as-is (it stays within the modal).

- [ ] **Step 2: Rewire `App.jsx`**

Replace the contents of `frontend/src/App.jsx` with:

```jsx
import React, { useState, useEffect } from 'react';
import './index.css';
import Navbar from './components/Navbar';
import UploadDashboard from './components/UploadDashboard';
import AnalysisDashboard from './components/AnalysisDashboard';
import TaskHistory from './components/TaskHistory';
import LandingPage from './components/LandingPage';
import AuthModal from './components/AuthModal';
import Security from './components/Security';
import { isTokenLikelyValid, getUsername, clearSession } from './lib/auth';

function App() {
  const [authedUser, setAuthedUser] = useState(() => (isTokenLikelyValid() ? getUsername() : null));
  const [currentView, setCurrentView] = useState('upload');
  const [taskId, setTaskId] = useState(null);
  const [authModal, setAuthModal] = useState(null); // null | 'login' | 'register'

  useEffect(() => {
    const onExpired = () => setAuthedUser(null);
    window.addEventListener('echostream:auth-expired', onExpired);
    return () => window.removeEventListener('echostream:auth-expired', onExpired);
  }, []);

  const handleLogout = () => {
    clearSession();
    setAuthedUser(null);
    setTaskId(null);
    setCurrentView('upload');
  };

  const handleUploadSuccess = (id) => { setTaskId(id); setCurrentView('analysis'); };
  const handleSelectTask = (id) => { setTaskId(id); setCurrentView('analysis'); };
  const handleReset = () => { setTaskId(null); setCurrentView('upload'); };
  const handleNavigate = (view) => { if (view === 'upload') setTaskId(null); setCurrentView(view); };

  if (!authedUser) {
    return (
      <div className="app-shell">
        <LandingPage onSignIn={() => setAuthModal('login')} onGetStarted={() => setAuthModal('register')} />
        {authModal && (
          <AuthModal
            initialMode={authModal}
            onClose={() => setAuthModal(null)}
            onLoggedIn={(u) => { setAuthModal(null); setAuthedUser(u); }}
          />
        )}
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Navbar currentView={currentView} onNavigate={handleNavigate} username={authedUser} onLogout={handleLogout} />
      <div className="page-content">
        {currentView === 'upload' && <UploadDashboard onUploadSuccess={handleUploadSuccess} />}
        {currentView === 'analysis' && taskId && <AnalysisDashboard taskId={taskId} onReset={handleReset} />}
        {currentView === 'history' && <TaskHistory onSelectTask={handleSelectTask} />}
        {currentView === 'security' && <Security />}
      </div>
    </div>
  );
}

export default App;
```

- [ ] **Step 3: Delete `Login.jsx`**

```bash
git rm frontend/src/components/Login.jsx
```

- [ ] **Step 4: Visual smoke — landing, modal, login flow**

Ensure the API cert is accepted (open `https://localhost:8000` once in a normal browser and click through, OR set `API_HTTPS=0` and `frontend/.env` to `http://localhost:8000` for the demo). With the dev server running:
1. Screenshot `http://localhost:5173/` (helper) → landing renders.
2. In a real Chrome (not headless), click "Get started" → modal opens on register; "Sign in" → modal opens on login; Esc / ✕ / backdrop close it.
3. Log in with `smoketest` / `smoketest123` → modal closes, app shows. Then log out.
4. Log in with `mihail` / `12345678` → confirm an MFA step (e.g. TOTP) renders **inside the modal** and completes.

Expected: all four pass; no `glass-panel` look, no gradient text, no emoji on the auth screens.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.jsx frontend/src/components/AuthModal.jsx
git commit -m "feat(ui): landing + auth modal replace full-page login

Login/register/MFA logic relocated from Login.jsx into AuthModal (an
overlay); App shows LandingPage when logged out. MFA flows unchanged.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: De-glass Security + fix icons.svg

**Files:**
- Modify: `frontend/src/components/Security.jsx`
- Modify: `frontend/public/icons.svg`

- [ ] **Step 1: Swap glass-panel → slate in Security.jsx**

In `frontend/src/components/Security.jsx`, replace every `className="glass-panel"` with `className="slate"` (6 occurrences, at the panels around lines 376, 382, 459, 525, 603, 665). The inline `style` props (padding etc.) stay.

- [ ] **Step 2: Replace the emoji in Security.jsx**

Add `import Icon from './Icon';` to the imports. Replace:
```jsx
<span className="error-icon">⚠️</span>
```
with:
```jsx
<span className="error-icon"><Icon name="alert" size={16} /></span>
```

- [ ] **Step 3: Re-stroke the social icons**

In `frontend/public/icons.svg`, replace every `stroke="#aa3bff"` with `stroke="#efece5"` (bone). Leave the `fill="#08060d"` brand glyphs (bluesky/discord/github/x) as-is — those are filled logos, not strokes.

- [ ] **Step 4: Visual review of Security tab**

Log in (any account) and open the Security tab; screenshot via the helper at `http://localhost:5173/` after navigating (or in real Chrome). 
Expected: Security panels are flat `slate` surfaces (no frosted blur), the warning shows the custom alert icon, any social icons render in bone, not purple.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Security.jsx frontend/public/icons.svg
git commit -m "refactor(ui): de-glass Security panel, drop emoji, de-purple icons

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Remove dead CSS + final smoke

**Files:**
- Modify: `frontend/src/index.css`

- [ ] **Step 1: Confirm no references remain**

Run:
```bash
cd "d:/LICENTA/EchoStream" && grep -rnE "glass-panel|gradient-text|⚠️|aa3bff" frontend/src frontend/public
```
Expected: no matches in `.jsx`/`.svg`. If any remain, fix them before continuing.

- [ ] **Step 2: Remove dead rules from index.css**

If (and only if) `glass-panel` or `gradient-text` rules exist in `frontend/src/index.css`, delete those rule blocks (search the file for `.glass-panel` and `.gradient-text`). If they are not defined there, skip — no change needed. Re-run the dev server and confirm no styling regressions on the app dashboards (which never used those classes).

- [ ] **Step 3: Final visual smoke**

Screenshot, via the helper, in this order and Read each:
1. `http://localhost:5173/` logged out → landing.
2. Real-Chrome manual: open modal, log in as `smoketest`, view Upload + History + an Analysis case, open Security.
Expected: cohesive forensic-console look across landing, modal, and app; no glass, no gradient text, no emoji, no purple icons; vision summary on a processed clip shows peak-per-frame counts (from Plan A).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/index.css
git commit -m "chore(ui): remove dead glassmorphism/gradient CSS

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review notes (author)

- **Spec coverage:** Workstream 1 (landing + modal, login off its own page, MFA preserved, logged-in nav unchanged) → Tasks 3 & 4. Workstream 2 (de-glass → `slate`, bespoke `Icon.jsx`, re-stroke social icons, drop emoji) → Tasks 1, 4 (auth de-glass), 5, 6. ✓
- **Placeholder scan:** every code step shows complete code or an exact transformation referencing concrete existing code (`Login.jsx`); verification steps give exact commands/URLs and expected results. Icon-path tuning at the Task 1 checkpoint is a design activity, not a placeholder. ✓
- **Name consistency:** `Icon` props (`name`, `size`, `className`, `style`, `strokeWidth`); `AuthModal` props (`initialMode`, `onClose`, `onLoggedIn`); `LandingPage` props (`onSignIn`, `onGetStarted`); `App` state `authModal` (`null|'login'|'register'`). Used identically across tasks. ✓
- **Risk:** the only non-trivial step is relocating Login→AuthModal (Step 4.1). Mitigation: copy verbatim, apply the enumerated class swaps only — no logic edits — and the Task 4 visual smoke exercises both a no-MFA (`smoketest`) and an MFA (`mihail`) login through the modal.
