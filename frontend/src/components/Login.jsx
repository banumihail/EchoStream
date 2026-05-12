import React, { useState } from 'react';
import { API_URL, saveSession } from '../lib/auth';

const Login = ({ onLoggedIn }) => {
  const [mode, setMode] = useState('login'); // 'login' | 'register'
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

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
      saveSession({ token: data.access_token, username: data.username });
      onLoggedIn(data.username);
    } catch (err) {
      setError(err.message || 'Authentication failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fade-in" style={{ maxWidth: 420, margin: '80px auto 0' }}>
      <div style={{ textAlign: 'center', marginBottom: 28 }}>
        <h1 style={{ fontSize: '2.2rem', fontWeight: 700, marginBottom: 6 }}>
          <span className="gradient-text">EchoStream</span>
        </h1>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem' }}>
          {mode === 'register' ? 'Create an account' : 'Sign in to continue'}
        </p>
      </div>

      <form className="glass-panel" onSubmit={submit} style={{ padding: 24 }}>
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
        <input
          className="login-input"
          type="password"
          autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="At least 8 characters"
          disabled={busy}
        />

        {mode === 'register' && (
          <>
            <label className="login-label">Email <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>(optional, used for email OTP)</span></label>
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
          <div className="error-banner" style={{ marginTop: 14 }}>
            <span className="error-icon">⚠️</span>
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
  );
};

export default Login;
