import React, { useState, useEffect } from 'react';
import { API_URL, saveSession } from '../lib/auth';
import { startAuthentication } from '@simplewebauthn/browser';
import Icon from './Icon';

const AuthModal = ({ initialMode = 'login', onClose, onLoggedIn }) => {
  // 'login' or 'register' for the first step; once we get an MFA challenge
  // back, step flips to 'mfa' and we render the second factor prompt.
  const [step, setStep] = useState('login');
  const [mode, setMode] = useState(initialMode); // 'login' | 'register' — only used on first step
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [showPassword, setShowPassword] = useState(false);

  // MFA challenge state
  const [challengeToken, setChallengeToken] = useState(null);
  const [mfaMethods, setMfaMethods] = useState([]);
  const [mfaMethod, setMfaMethod] = useState(null);   // which method the user picked
  const [mfaCode, setMfaCode] = useState('');
  // Email-specific: track whether we've already requested an OTP and the masked address
  const [emailRequested, setEmailRequested] = useState(false);
  const [emailMaskedTo, setEmailMaskedTo] = useState(null);
  // Push-specific: 'idle' | 'waiting' | 'denied' | 'expired'
  const [pushState, setPushState] = useState('idle');

  // Esc closes the modal (backdrop click and the ✕ button do too).
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const resetToStart = () => {
    setStep('login');
    setChallengeToken(null);
    setMfaMethods([]);
    setMfaMethod(null);
    setMfaCode('');
    setEmailRequested(false);
    setEmailMaskedTo(null);
    setPushState('idle');
    setPassword('');
    setError(null);
  };

  const startPushApproval = async () => {
    if (!challengeToken) return;
    setError(null);
    setPushState('waiting');
    try {
      const reqRes = await fetch(`${API_URL}/auth/mfa/push/request`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${challengeToken}` },
      });
      if (!reqRes.ok) {
        const d = await reqRes.json().catch(() => ({}));
        throw new Error(d.detail || `Could not send push (${reqRes.status})`);
      }
      // Poll status until approved / denied / expired.
      const poll = setInterval(async () => {
        try {
          const sRes = await fetch(`${API_URL}/auth/mfa/push/status`, {
            headers: { 'Authorization': `Bearer ${challengeToken}` },
          });
          if (!sRes.ok) return;
          const { status } = await sRes.json();
          if (status === 'approved') {
            clearInterval(poll);
            const vRes = await fetch(`${API_URL}/auth/mfa/push/verify`, {
              method: 'POST',
              headers: { 'Authorization': `Bearer ${challengeToken}` },
            });
            if (!vRes.ok) {
              const d = await vRes.json().catch(() => ({}));
              throw new Error(d.detail || 'Verification failed.');
            }
            const data = await vRes.json();
            saveSession({ token: data.access_token, username: data.username });
            onLoggedIn(data.username);
          } else if (status === 'denied' || status === 'expired') {
            clearInterval(poll);
            setPushState(status);
          }
        } catch (err) {
          clearInterval(poll);
          setError(err.message || String(err));
          setPushState('idle');
        }
      }, 2000);
    } catch (err) {
      setError(err.message || String(err));
      setPushState('idle');
    }
  };

  const verifyWithFido2 = async () => {
    if (!challengeToken) return;
    setBusy(true); setError(null);
    try {
      const beginRes = await fetch(`${API_URL}/auth/mfa/fido2/auth/begin`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${challengeToken}` },
      });
      if (!beginRes.ok) {
        const d = await beginRes.json().catch(() => ({}));
        throw new Error(d.detail || `Could not start FIDO2 ceremony (${beginRes.status})`);
      }
      const { options, challenge_token: assertionChallenge } = await beginRes.json();
      // Browser prompts the user for their authenticator here.
      const assertion = await startAuthentication({ optionsJSON: JSON.parse(options) });
      const completeRes = await fetch(`${API_URL}/auth/mfa/fido2/auth/complete`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${challengeToken}`,
        },
        body: JSON.stringify({ challenge_token: assertionChallenge, assertion }),
      });
      if (!completeRes.ok) {
        const d = await completeRes.json().catch(() => ({}));
        throw new Error(d.detail || `FIDO2 verification failed (${completeRes.status})`);
      }
      const data = await completeRes.json();
      saveSession({ token: data.access_token, username: data.username });
      onLoggedIn(data.username);
    } catch (err) {
      if (err && err.name === 'NotAllowedError') setError('Authentication was cancelled.');
      else setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const requestEmailOtp = async () => {
    if (!challengeToken) return;
    setBusy(true); setError(null);
    try {
      const res = await fetch(`${API_URL}/auth/mfa/email/request`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${challengeToken}` },
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `Send failed (${res.status})`);
      }
      const data = await res.json();
      setEmailMaskedTo(data.to);
      setEmailRequested(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password) return;
    setBusy(true);
    setError(null);
    try {
      const endpoint = mode === 'register' ? '/auth/register' : '/auth/login';
      const body = mode === 'register'
        ? { username: username.trim(), password, email: email.trim() || null }
        : { username: username.trim(), password };
      const res = await fetch(`${API_URL}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Request failed (${res.status})`);
      }
      const data = await res.json();
      if (data.mfa_required) {
        // Branch to MFA challenge — do NOT save a session yet.
        setChallengeToken(data.challenge_token);
        setMfaMethods(data.methods || []);
        setMfaMethod((data.methods || [])[0] || null);
        setStep('mfa');
        return;
      }
      saveSession({ token: data.access_token, username: data.username });
      onLoggedIn(data.username);
    } catch (err) {
      setError(err.message || 'Authentication failed.');
    } finally {
      setBusy(false);
    }
  };

  const submitMfa = async (e) => {
    e.preventDefault();
    if (!mfaMethod || !mfaCode.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/auth/mfa/${mfaMethod}/verify`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${challengeToken}`,
        },
        body: JSON.stringify({ code: mfaCode.trim() }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `MFA failed (${res.status})`);
      }
      const data = await res.json();
      saveSession({ token: data.access_token, username: data.username });
      onLoggedIn(data.username);
    } catch (err) {
      setError(err.message || 'Verification failed.');
    } finally {
      setBusy(false);
    }
  };

  const onOverlayMouseDown = (e) => { if (e.target === e.currentTarget) onClose(); };

  // ─── MFA challenge step ───────────────────────────────────────────
  if (step === 'mfa') {
    return (
      <div className="modal-overlay" onMouseDown={onOverlayMouseDown}>
        <div className="modal-card">
          <button className="modal-close" onClick={onClose} aria-label="Close"><Icon name="close" size={18} /></button>
          <div style={{ textAlign: 'center', marginBottom: 24 }}>
            <h1 className="modal-title">Echo<em>Stream</em><span className="lm-cursor" /></h1>
            <p className="modal-subtitle">Two-factor authentication</p>
          </div>
          <form onSubmit={submitMfa}>
            {mfaMethods.length > 1 && (
              <>
                <label className="login-label">Method</label>
                <select
                  className="login-input"
                  value={mfaMethod || ''}
                  onChange={(e) => {
                    setMfaMethod(e.target.value);
                    setMfaCode('');
                    setEmailRequested(false);
                    setEmailMaskedTo(null);
                    setPushState('idle');
                    setError(null);
                  }}
                  disabled={busy}
                >
                  {mfaMethods.map(m => (
                    <option key={m} value={m}>{m.toUpperCase()}</option>
                  ))}
                </select>
              </>
            )}

            {/* Push: send an approval request to Telegram, then poll */}
            {mfaMethod === 'push' && (
              <div style={{ marginTop: 14 }}>
                {pushState === 'idle' && (
                  <>
                    <p style={{ fontSize: '0.88rem', color: 'var(--bone-dim)', marginBottom: 10 }}>
                      We'll send an Approve / Deny prompt to your linked Telegram.
                    </p>
                    <button type="button" className="btn btn-primary" onClick={startPushApproval} disabled={busy} style={{ width: '100%' }}>
                      Send approval request
                    </button>
                  </>
                )}
                {pushState === 'waiting' && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--bone-dim)', fontSize: '0.9rem' }}>
                    <div className="spinner" style={{ width: 16, height: 16 }} />
                    Waiting for you to approve in Telegram…
                  </div>
                )}
                {(pushState === 'denied' || pushState === 'expired') && (
                  <>
                    <p style={{ fontSize: '0.88rem', color: 'var(--alert)', marginBottom: 10 }}>
                      {pushState === 'denied' ? 'Request was denied.' : 'Request expired.'}
                    </p>
                    <button type="button" className="btn btn-primary" onClick={startPushApproval} disabled={busy} style={{ width: '100%' }}>
                      Send again
                    </button>
                  </>
                )}
              </div>
            )}

            {/* FIDO2 has no code field — just trigger the browser ceremony */}
            {mfaMethod === 'fido2' && (
              <div style={{ marginTop: 14 }}>
                <p style={{ fontSize: '0.88rem', color: 'var(--bone-dim)', marginBottom: 10 }}>
                  Use your registered security key (Windows Hello, Touch ID, YubiKey, etc.). Click below and follow the OS prompt.
                </p>
                <button type="button" className="btn btn-primary" onClick={verifyWithFido2} disabled={busy} style={{ width: '100%' }}>
                  {busy ? 'Waiting for authenticator…' : 'Use security key'}
                </button>
              </div>
            )}

            {/* Email needs a "send code" step before we can show the input */}
            {mfaMethod === 'email' && !emailRequested && (
              <div style={{ marginTop: 14 }}>
                <p style={{ fontSize: '0.88rem', color: 'var(--bone-dim)', marginBottom: 10 }}>
                  We'll email you a 6-digit code that expires in 5 minutes.
                </p>
                <button type="button" className="btn btn-primary" onClick={requestEmailOtp} disabled={busy} style={{ width: '100%' }}>
                  {busy ? 'Sending…' : 'Send code to my email'}
                </button>
              </div>
            )}

            {(mfaMethod !== 'email' && mfaMethod !== 'fido2' && mfaMethod !== 'push') || (mfaMethod === 'email' && emailRequested) ? (
              <>
                <label className="login-label">
                  {mfaMethod === 'totp' && 'Code from authenticator app'}
                  {mfaMethod === 'backup' && 'Backup code'}
                  {mfaMethod === 'email' && (emailMaskedTo ? `Code sent to ${emailMaskedTo}` : 'Email code')}
                  {mfaMethod && !['totp','backup','email','fido2'].includes(mfaMethod) && `${mfaMethod.toUpperCase()} code`}
                </label>
                <input
                  className="login-input"
                  type="text"
                  inputMode={mfaMethod === 'backup' ? 'text' : 'numeric'}
                  autoComplete="one-time-code"
                  placeholder={mfaMethod === 'backup' ? 'XXXX-XXXX' : '6 digits'}
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value)}
                  disabled={busy}
                  autoFocus
                  maxLength={mfaMethod === 'backup' ? 12 : 8}
                  style={mfaMethod === 'backup' ? { fontFamily: 'ui-monospace, monospace', letterSpacing: '0.08em' } : {}}
                />
                {mfaMethod === 'email' && (
                  <button type="button" className="password-toggle" onClick={requestEmailOtp}
                          disabled={busy} style={{ position: 'static', display: 'block', marginTop: 6, transform: 'none' }}>
                    Resend code
                  </button>
                )}
              </>
            ) : null}

            {error && (
              <div className="error-banner shake" style={{ marginTop: 14 }}>
                <span className="error-icon"><Icon name="alert" size={16} /></span>
                <p>{error}</p>
              </div>
            )}

            {mfaMethod !== 'fido2' && mfaMethod !== 'push' && (mfaMethod !== 'email' || emailRequested) && (
              <button
                className="btn btn-primary"
                type="submit"
                disabled={busy || !mfaCode.trim()}
                style={{ width: '100%', marginTop: 18 }}
              >
                {busy ? 'Verifying…' : 'Verify'}
              </button>
            )}

            <button
              type="button"
              className="btn btn-outline"
              style={{ width: '100%', marginTop: 10 }}
              onClick={resetToStart}
              disabled={busy}
            >
              Back
            </button>
          </form>
        </div>
      </div>
    );
  }

  // ─── First step (login / register) ────────────────────────────────
  return (
    <div className="modal-overlay" onMouseDown={onOverlayMouseDown}>
      <div className="modal-card">
        <button className="modal-close" onClick={onClose} aria-label="Close"><Icon name="close" size={18} /></button>
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <h1 className="modal-title">Echo<em>Stream</em></h1>
          <p className="modal-subtitle">
            {mode === 'register' ? 'Create an account' : 'Sign in to continue'}
          </p>
        </div>

        <form onSubmit={submit}>
          <label className="login-label">Username</label>
          <input
            className="login-input"
            type="text"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="3-32 alphanumeric"
            disabled={busy}
            autoFocus
          />

          <label className="login-label">Password</label>
          <div className="password-field">
            <input
              className="login-input"
              type={showPassword ? 'text' : 'password'}
              autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              disabled={busy}
            />
            <button
              type="button"
              className="password-toggle"
              onClick={() => setShowPassword(s => !s)}
              disabled={busy}
              tabIndex={-1}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
            >
              {showPassword ? 'Hide' : 'Show'}
            </button>
          </div>

          {mode === 'register' && (
            <>
              <label className="login-label">Email <span style={{ color: 'var(--bone-dim)', fontWeight: 400 }}>(optional, used for email OTP)</span></label>
              <input
                className="login-input"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                disabled={busy}
              />
            </>
          )}

          {error && (
            <div className="error-banner shake" style={{ marginTop: 14 }}>
              <span className="error-icon"><Icon name="alert" size={16} /></span>
              <p>{error}</p>
            </div>
          )}

          <button
            className="btn btn-primary"
            type="submit"
            disabled={busy || !username.trim() || !password}
            style={{ width: '100%', marginTop: 18 }}
          >
            {busy ? (mode === 'register' ? 'Creating…' : 'Signing in…')
                  : (mode === 'register' ? 'Create account' : 'Sign in')}
          </button>

          <button
            type="button"
            className="btn btn-outline"
            style={{ width: '100%', marginTop: 10 }}
            onClick={() => { setMode(mode === 'register' ? 'login' : 'register'); setError(null); }}
            disabled={busy}
          >
            {mode === 'register' ? 'I already have an account' : 'Create a new account'}
          </button>
        </form>
      </div>
    </div>
  );
};

export default AuthModal;
