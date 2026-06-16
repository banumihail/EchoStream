import React, { useState, useEffect } from 'react';
import { API_URL, saveSession } from '../lib/auth';
import Icon from './Icon';

const AuthModal = ({ initialMode = 'login', onClose, onLoggedIn }) => {
  // 'login' or 'register' for the first step; once we get an MFA challenge
  // back, step flips to 'mfa' and we render the TOTP code prompt.
  const [step, setStep] = useState('login');
  const [mode, setMode] = useState(initialMode); // 'login' | 'register'
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [showPassword, setShowPassword] = useState(false);

  // MFA (TOTP) challenge state
  const [challengeToken, setChallengeToken] = useState(null);
  const [mfaCode, setMfaCode] = useState('');

  // Esc closes the modal (backdrop click and the ✕ button do too).
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const resetToStart = () => {
    setStep('login');
    setChallengeToken(null);
    setMfaCode('');
    setPassword('');
    setError(null);
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password) return;
    setBusy(true);
    setError(null);
    try {
      const endpoint = mode === 'register' ? '/auth/register' : '/auth/login';
      const res = await fetch(`${API_URL}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Request failed (${res.status})`);
      }
      const data = await res.json();
      if (data.mfa_required) {
        // Branch to the TOTP challenge — do NOT save a session yet.
        setChallengeToken(data.challenge_token);
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
    if (!mfaCode.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/auth/mfa/totp/verify`, {
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

  // ─── MFA challenge step (TOTP) ────────────────────────────────────
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
            <label className="login-label">Code from authenticator app</label>
            <input
              className="login-input"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="6 digits"
              value={mfaCode}
              onChange={(e) => setMfaCode(e.target.value)}
              disabled={busy}
              autoFocus
              maxLength={8}
            />
            {error && (
              <div className="error-banner shake" style={{ marginTop: 14 }}>
                <span className="error-icon"><Icon name="alert" size={16} /></span>
                <p>{error}</p>
              </div>
            )}
            <button className="btn btn-primary" type="submit" disabled={busy || !mfaCode.trim()} style={{ width: '100%', marginTop: 18 }}>
              {busy ? 'Verifying…' : 'Verify'}
            </button>
            <button type="button" className="btn btn-outline" style={{ width: '100%', marginTop: 10 }} onClick={resetToStart} disabled={busy}>
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
