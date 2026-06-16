import React, { useState, useEffect } from 'react';
import { authFetch } from '../lib/auth';
import Icon from './Icon';

const Security = () => {
  const [me, setMe] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // TOTP enrollment flow state
  const [totpSetup, setTotpSetup] = useState(null); // { secret, otpauth_uri, qr_data_url }
  const [totpCode, setTotpCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState(null);

  const refresh = async () => {
    setLoading(true);
    try {
      const res = await authFetch('/auth/me');
      if (!res.ok) throw new Error(`Could not load profile (${res.status})`);
      setMe(await res.json());
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to load profile.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  const startTotpSetup = async () => {
    setBusy(true); setError(null); setInfo(null);
    try {
      const res = await authFetch('/auth/mfa/totp/setup', { method: 'POST' });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `Setup failed (${res.status})`);
      }
      setTotpSetup(await res.json());
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const confirmTotp = async (e) => {
    e.preventDefault();
    if (!totpCode.trim()) return;
    setBusy(true); setError(null);
    try {
      const res = await authFetch('/auth/mfa/totp/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: totpCode.trim() }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `Confirmation failed (${res.status})`);
      }
      setTotpSetup(null);
      setTotpCode('');
      setInfo('TOTP enrolled. You\'ll be asked for a code on your next sign-in.');
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const disableTotp = async () => {
    if (!window.confirm('Disable TOTP? You will lose your second factor until you re-enroll.')) return;
    setBusy(true); setError(null);
    try {
      const res = await authFetch('/auth/mfa/totp/disable', { method: 'POST' });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `Disable failed (${res.status})`);
      }
      setInfo('TOTP disabled.');
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <div className="fade-in" style={{ textAlign: 'center', padding: 60 }}><div className="spinner" /></div>;

  const totpEnrolled = me?.mfa_methods?.includes('totp');

  return (
    <div className="fade-in" style={{ maxWidth: 720, margin: '40px auto 0' }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: '1.8rem', fontWeight: 700, marginBottom: 4 }}>Security</h1>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.95rem' }}>
          Two-factor authentication for <strong>{me?.username}</strong>
        </p>
      </div>

      {error && (
        <div className="error-banner" style={{ marginBottom: 16 }}>
          <span className="error-icon"><Icon name="alert" size={16} /></span>
          <p>{error}</p>
        </div>
      )}
      {info && (
        <div className="slate" style={{ padding: 14, marginBottom: 16, borderLeft: '3px solid var(--success)' }}>
          <p style={{ margin: 0, color: 'var(--success)' }}>{info}</p>
        </div>
      )}

      {/* TOTP card */}
      <div className="slate" style={{ padding: 22, marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '1.1rem' }}>Authenticator app (TOTP)</h3>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.88rem', margin: '6px 0 0' }}>
              Google Authenticator, Authy, 1Password, Bitwarden — any RFC 6238 client.
            </p>
          </div>
          <span className={`badge ${totpEnrolled ? 'completed' : ''}`} style={{ flexShrink: 0 }}>
            {totpEnrolled ? 'ENROLLED' : 'NOT ENROLLED'}
          </span>
        </div>

        {!totpEnrolled && !totpSetup && (
          <button className="btn btn-primary" onClick={startTotpSetup} disabled={busy} style={{ marginTop: 14 }}>
            {busy ? 'Generating…' : 'Set up TOTP'}
          </button>
        )}

        {!totpEnrolled && totpSetup && (
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--rule-bright)' }}>
            <p style={{ fontSize: '0.88rem', marginBottom: 12 }}>
              1. Scan this QR code with your authenticator app.<br />
              2. Enter the 6-digit code it shows to finish enrolling.
            </p>
            <div style={{ display: 'flex', gap: 18, alignItems: 'flex-start', marginBottom: 14, flexWrap: 'wrap' }}>
              <img
                src={totpSetup.qr_data_url}
                alt="TOTP QR code"
                style={{ width: 180, height: 180, background: '#fff', padding: 8, borderRadius: 6 }}
              />
              <div style={{ flex: 1, minWidth: 220 }}>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: 4 }}>
                  Can't scan? Enter this secret manually:
                </div>
                <code style={{
                  display: 'block', padding: 10, background: 'rgba(0,0,0,0.3)',
                  borderRadius: 6, wordBreak: 'break-all', fontSize: '0.82rem'
                }}>{totpSetup.secret}</code>
              </div>
            </div>
            <form onSubmit={confirmTotp} style={{ display: 'flex', gap: 10 }}>
              <input
                className="login-input"
                type="text"
                inputMode="numeric"
                placeholder="6-digit code"
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value.replace(/\s+/g, ''))}
                disabled={busy}
                maxLength={8}
                style={{ flex: 1 }}
                autoFocus
              />
              <button className="btn btn-primary" type="submit" disabled={busy || !totpCode.trim()}>
                {busy ? 'Checking…' : 'Confirm'}
              </button>
              <button
                type="button"
                className="btn btn-outline"
                disabled={busy}
                onClick={() => { setTotpSetup(null); setTotpCode(''); }}
              >
                Cancel
              </button>
            </form>
          </div>
        )}

        {totpEnrolled && (
          <button className="btn btn-outline" onClick={disableTotp} disabled={busy} style={{ marginTop: 14 }}>
            {busy ? 'Working…' : 'Disable TOTP'}
          </button>
        )}
      </div>
    </div>
  );
};

export default Security;
