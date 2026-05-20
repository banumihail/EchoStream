import React, { useState, useEffect } from 'react';
import { authFetch } from '../lib/auth';
import { startRegistration } from '@simplewebauthn/browser';

const Security = () => {
  const [me, setMe] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // TOTP enrollment flow state
  const [totpSetup, setTotpSetup] = useState(null); // { secret, otpauth_uri, qr_data_url }
  const [totpCode, setTotpCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState(null);

  // Backup codes — `codes` is non-null only the one time after generation
  const [backupCodes, setBackupCodes] = useState(null);

  // Email OTP enrollment state
  const [emailDraft, setEmailDraft] = useState('');
  const [emailOtpPending, setEmailOtpPending] = useState(false); // true after setup, waiting for confirm
  const [emailOtpCode, setEmailOtpCode] = useState('');

  // FIDO2 / WebAuthn state
  const [fido2Credentials, setFido2Credentials] = useState([]);
  const [fido2Label, setFido2Label] = useState('');

  // Push (Telegram) enrollment state
  const [pushDeepLink, setPushDeepLink] = useState(null);
  const [pushPolling, setPushPolling] = useState(false);

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
  useEffect(() => { if (me?.email) setEmailDraft(me.email); }, [me]);

  const refreshFido2 = async () => {
    try {
      const res = await authFetch('/auth/mfa/fido2/credentials');
      if (res.ok) setFido2Credentials(await res.json());
    } catch { /* ignore */ }
  };
  useEffect(() => { if (me?.mfa_methods?.includes('fido2')) refreshFido2(); else setFido2Credentials([]); }, [me]);

  const enrollFido2 = async () => {
    setBusy(true); setError(null); setInfo(null);
    try {
      const begin = await authFetch('/auth/mfa/fido2/register/begin', { method: 'POST' });
      if (!begin.ok) {
        const d = await begin.json().catch(() => ({}));
        throw new Error(d.detail || `Could not start registration (${begin.status})`);
      }
      const { options, challenge_token } = await begin.json();
      // The browser's authenticator prompt happens here.
      const attestation = await startRegistration({ optionsJSON: JSON.parse(options) });
      const complete = await authFetch('/auth/mfa/fido2/register/complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          challenge_token,
          attestation,
          label: fido2Label.trim() || 'Security key',
        }),
      });
      if (!complete.ok) {
        const d = await complete.json().catch(() => ({}));
        throw new Error(d.detail || `Registration failed (${complete.status})`);
      }
      setFido2Label('');
      setInfo('Security key enrolled.');
      await refresh();
      await refreshFido2();
    } catch (err) {
      // The simplewebauthn library uses err.name for browser-side cancellation
      if (err && err.name === 'NotAllowedError') setError('Registration was cancelled.');
      else setError(err.message || String(err));
    } finally {
      setBusy(false);
    }
  };

  const removeFido2Credential = async (credential_id) => {
    if (!window.confirm('Remove this security key?')) return;
    setBusy(true); setError(null);
    try {
      const res = await authFetch(`/auth/mfa/fido2/credentials/${encodeURIComponent(credential_id)}`, { method: 'DELETE' });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `Removal failed (${res.status})`);
      }
      setInfo('Security key removed.');
      await refresh();
      await refreshFido2();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

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

  const generateBackupCodes = async () => {
    if (me?.backup_codes_remaining > 0 &&
        !window.confirm('Regenerating will invalidate your previous backup codes. Continue?')) return;
    setBusy(true); setError(null); setInfo(null);
    try {
      const res = await authFetch('/auth/mfa/backup/generate', { method: 'POST' });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `Generation failed (${res.status})`);
      }
      const data = await res.json();
      setBackupCodes(data.codes);
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const copyBackupCodes = async () => {
    if (!backupCodes) return;
    try {
      await navigator.clipboard.writeText(backupCodes.join('\n'));
      setInfo('Copied to clipboard.');
    } catch {
      setError('Could not access clipboard.');
    }
  };

  const downloadBackupCodes = () => {
    if (!backupCodes) return;
    const blob = new Blob(
      [`EchoStream backup codes for ${me?.username}\nGenerated ${new Date().toISOString()}\n\n${backupCodes.join('\n')}\n`],
      { type: 'text/plain' },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `echostream-backup-codes-${me?.username}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const disableBackupCodes = async () => {
    if (!window.confirm('Disable backup codes? You lose your account-recovery factor.')) return;
    setBusy(true); setError(null);
    try {
      const res = await authFetch('/auth/mfa/backup/disable', { method: 'POST' });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `Disable failed (${res.status})`);
      }
      setBackupCodes(null);
      setInfo('Backup codes disabled.');
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const startEmailSetup = async () => {
    setBusy(true); setError(null); setInfo(null);
    try {
      const res = await authFetch('/auth/mfa/email/setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(emailDraft.trim() ? { email: emailDraft.trim() } : {}),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `Send failed (${res.status})`);
      }
      const data = await res.json();
      setEmailOtpPending(true);
      setInfo(data.channel === 'console'
        ? `Code printed to API console (SMTP not configured). Email: ${data.email}`
        : `Code sent to ${data.email}.`);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const confirmEmailOtp = async (e) => {
    e.preventDefault();
    if (!emailOtpCode.trim()) return;
    setBusy(true); setError(null);
    try {
      const res = await authFetch('/auth/mfa/email/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: emailOtpCode.trim() }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `Confirm failed (${res.status})`);
      }
      setEmailOtpPending(false);
      setEmailOtpCode('');
      setInfo('Email OTP enrolled. You\'ll be able to pick "email" at sign-in.');
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const disableEmailMfa = async () => {
    if (!window.confirm('Disable email OTP as a second factor?')) return;
    setBusy(true); setError(null);
    try {
      const res = await authFetch('/auth/mfa/email/disable', { method: 'POST' });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `Disable failed (${res.status})`);
      }
      setInfo('Email OTP disabled.');
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const startPushEnroll = async () => {
    setBusy(true); setError(null); setInfo(null);
    try {
      const res = await authFetch('/auth/mfa/push/enroll/begin', { method: 'POST' });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `Could not start (${res.status})`);
      }
      const data = await res.json();
      setPushDeepLink(data.deep_link);
      setPushPolling(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  // Poll for pairing completion while the enrollment link is showing.
  useEffect(() => {
    if (!pushPolling) return;
    const id = setInterval(async () => {
      try {
        const res = await authFetch('/auth/mfa/push/enroll/status');
        if (res.ok && (await res.json()).enrolled) {
          setPushPolling(false);
          setPushDeepLink(null);
          setInfo('Telegram linked. Push approvals are now enabled.');
          await refresh();
        }
      } catch { /* ignore */ }
    }, 2000);
    return () => clearInterval(id);
  }, [pushPolling]);

  const disablePush = async () => {
    if (!window.confirm('Unlink Telegram and disable push approvals?')) return;
    setBusy(true); setError(null);
    try {
      const res = await authFetch('/auth/mfa/push/disable', { method: 'POST' });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail || `Disable failed (${res.status})`);
      }
      setPushDeepLink(null); setPushPolling(false);
      setInfo('Push disabled.');
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
          Multi-factor authentication for <strong>{me?.username}</strong>
        </p>
      </div>

      {error && (
        <div className="error-banner" style={{ marginBottom: 16 }}>
          <span className="error-icon">⚠️</span>
          <p>{error}</p>
        </div>
      )}
      {info && (
        <div className="glass-panel" style={{ padding: 14, marginBottom: 16, borderLeft: '3px solid var(--success)' }}>
          <p style={{ margin: 0, color: 'var(--success)' }}>{info}</p>
        </div>
      )}

      {/* TOTP card */}
      <div className="glass-panel" style={{ padding: 22, marginBottom: 16 }}>
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
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--glass-border)' }}>
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

      {/* Backup codes card */}
      <div className="glass-panel" style={{ padding: 22, marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '1.1rem' }}>Backup codes</h3>
            <p style={{ color: 'var(--bone-dim)', fontSize: '0.88rem', margin: '6px 0 0' }}>
              Single-use codes that let you sign in if you lose access to your authenticator app. Generate, save them somewhere safe, and use one when you can't reach your phone.
            </p>
          </div>
          <span className={`badge ${me?.backup_codes_remaining > 0 ? 'completed' : ''}`} style={{ flexShrink: 0 }}>
            {me?.backup_codes_remaining > 0 ? `${me.backup_codes_remaining} / 10 LEFT` : 'NONE'}
          </span>
        </div>

        {backupCodes && (
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--rule-bright)' }}>
            <p style={{ fontSize: '0.85rem', color: 'var(--alert)', marginBottom: 10 }}>
              These codes will not be shown again. Copy or download them now.
            </p>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(2, 1fr)',
              gap: 8,
              marginBottom: 14,
              fontFamily: 'var(--mono, ui-monospace, SFMono-Regular, monospace)',
              fontSize: '0.95rem',
            }}>
              {backupCodes.map((c, i) => (
                <code key={i} style={{
                  padding: '8px 12px',
                  background: 'var(--ink-2)',
                  border: '1px solid var(--rule-bright)',
                  borderRadius: 0,
                  letterSpacing: '0.08em',
                  textAlign: 'center',
                }}>{c}</code>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 10 }}>
              <button className="btn btn-outline" onClick={copyBackupCodes} disabled={busy}>Copy</button>
              <button className="btn btn-outline" onClick={downloadBackupCodes} disabled={busy}>Download .txt</button>
              <button className="btn btn-primary" onClick={() => setBackupCodes(null)} disabled={busy}>I've saved them</button>
            </div>
          </div>
        )}

        {!backupCodes && (
          <div style={{ marginTop: 14, display: 'flex', gap: 10 }}>
            <button className="btn btn-primary" onClick={generateBackupCodes} disabled={busy || !me?.mfa_passed}>
              {busy ? 'Generating…' : (me?.backup_codes_remaining > 0 ? 'Regenerate codes' : 'Generate backup codes')}
            </button>
            {me?.backup_codes_remaining > 0 && (
              <button className="btn btn-outline" onClick={disableBackupCodes} disabled={busy}>
                Disable
              </button>
            )}
          </div>
        )}

        {!me?.mfa_passed && (
          <p style={{ fontSize: '0.8rem', color: 'var(--bone-dim)', marginTop: 10 }}>
            Sign in with your authenticator first to manage backup codes.
          </p>
        )}
      </div>

      {/* Email OTP card */}
      <div className="glass-panel" style={{ padding: 22, marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '1.1rem' }}>Email OTP</h3>
            <p style={{ color: 'var(--bone-dim)', fontSize: '0.88rem', margin: '6px 0 0' }}>
              A 6-digit code emailed to you on sign-in. Useful as a fallback if your authenticator app is unavailable.
            </p>
          </div>
          <span className={`badge ${me?.mfa_methods?.includes('email') ? 'completed' : ''}`} style={{ flexShrink: 0 }}>
            {me?.mfa_methods?.includes('email') ? 'ENROLLED' : 'NOT ENROLLED'}
          </span>
        </div>

        {!me?.mfa_methods?.includes('email') && !emailOtpPending && (
          <div style={{ marginTop: 14 }}>
            <label className="login-label">Email address</label>
            <input
              className="login-input"
              type="email"
              placeholder="you@example.com"
              value={emailDraft}
              onChange={(e) => setEmailDraft(e.target.value)}
              disabled={busy || !me?.mfa_passed}
              style={{ marginBottom: 10 }}
            />
            <button className="btn btn-primary" onClick={startEmailSetup}
                    disabled={busy || !emailDraft.trim() || !me?.mfa_passed}>
              {busy ? 'Sending…' : 'Send verification email'}
            </button>
            {!me?.mfa_passed && (
              <p style={{ fontSize: '0.8rem', color: 'var(--bone-dim)', marginTop: 8 }}>
                Sign in with your authenticator first to enroll email OTP.
              </p>
            )}
          </div>
        )}

        {!me?.mfa_methods?.includes('email') && emailOtpPending && (
          <form onSubmit={confirmEmailOtp} style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid var(--rule-bright)' }}>
            <label className="login-label">6-digit code from your inbox</label>
            <div style={{ display: 'flex', gap: 10 }}>
              <input
                className="login-input"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                placeholder="6 digits"
                value={emailOtpCode}
                onChange={(e) => setEmailOtpCode(e.target.value.replace(/\D/g, ''))}
                disabled={busy}
                autoFocus
                style={{ flex: 1 }}
              />
              <button className="btn btn-primary" type="submit" disabled={busy || emailOtpCode.length !== 6}>
                {busy ? 'Checking…' : 'Confirm'}
              </button>
              <button type="button" className="btn btn-outline" disabled={busy}
                      onClick={() => { setEmailOtpPending(false); setEmailOtpCode(''); }}>
                Cancel
              </button>
            </div>
          </form>
        )}

        {me?.mfa_methods?.includes('email') && (
          <div style={{ marginTop: 14 }}>
            <p style={{ fontSize: '0.85rem', color: 'var(--bone-dim)', margin: '0 0 10px' }}>
              Codes will be sent to <strong style={{ color: 'var(--bone)' }}>{me.email}</strong>.
            </p>
            <button className="btn btn-outline" onClick={disableEmailMfa} disabled={busy}>
              {busy ? 'Working…' : 'Disable email OTP'}
            </button>
          </div>
        )}
      </div>

      {/* FIDO2 / WebAuthn card */}
      <div className="glass-panel" style={{ padding: 22, marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '1.1rem' }}>Security keys (FIDO2 / WebAuthn)</h3>
            <p style={{ color: 'var(--bone-dim)', fontSize: '0.88rem', margin: '6px 0 0' }}>
              Phishing-resistant. Use Windows Hello, Touch ID, a fingerprint sensor, or a USB security key (YubiKey, SoloKey).
            </p>
          </div>
          <span className={`badge ${me?.mfa_methods?.includes('fido2') ? 'completed' : ''}`} style={{ flexShrink: 0 }}>
            {me?.mfa_methods?.includes('fido2') ? `${fido2Credentials.length} ENROLLED` : 'NOT ENROLLED'}
          </span>
        </div>

        {fido2Credentials.length > 0 && (
          <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--rule-bright)', display: 'flex', flexDirection: 'column', gap: 6 }}>
            {fido2Credentials.map(c => (
              <div key={c.credential_id} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '8px 12px', background: 'var(--ink-2)', border: '1px solid var(--rule-bright)',
              }}>
                <div>
                  <div style={{ fontSize: '0.92rem' }}>{c.label || 'Security key'}</div>
                  <div style={{ fontSize: '0.74rem', color: 'var(--bone-dim)' }}>
                    Added {c.created_at ? new Date(c.created_at).toLocaleString() : ''}
                    {c.last_used_at ? ` · last used ${new Date(c.last_used_at).toLocaleString()}` : ''}
                  </div>
                </div>
                <button className="btn btn-outline" style={{ padding: '4px 10px', fontSize: '0.72rem' }}
                        onClick={() => removeFido2Credential(c.credential_id)} disabled={busy}>
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}

        <div style={{ marginTop: 14 }}>
          <label className="login-label">Label for this key (optional)</label>
          <div style={{ display: 'flex', gap: 10 }}>
            <input
              className="login-input"
              type="text"
              placeholder="e.g. YubiKey Blue, Laptop Hello"
              value={fido2Label}
              onChange={(e) => setFido2Label(e.target.value)}
              maxLength={64}
              disabled={busy || !me?.mfa_passed}
              style={{ flex: 1 }}
            />
            <button className="btn btn-primary" onClick={enrollFido2} disabled={busy || !me?.mfa_passed}>
              {busy ? 'Waiting…' : 'Add security key'}
            </button>
          </div>
          {!me?.mfa_passed && (
            <p style={{ fontSize: '0.8rem', color: 'var(--bone-dim)', marginTop: 8 }}>
              Sign in with your authenticator first to manage security keys.
            </p>
          )}
        </div>
      </div>

      {/* Push notification (Telegram) card */}
      <div className="glass-panel" style={{ padding: 22, marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16 }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '1.1rem' }}>Push approval (Telegram)</h3>
            <p style={{ color: 'var(--bone-dim)', fontSize: '0.88rem', margin: '6px 0 0' }}>
              Get an Approve / Deny prompt in Telegram when you sign in. No code to type.
            </p>
          </div>
          <span className={`badge ${me?.mfa_methods?.includes('push') ? 'completed' : ''}`} style={{ flexShrink: 0 }}>
            {me?.mfa_methods?.includes('push') ? 'ENROLLED' : 'NOT ENROLLED'}
          </span>
        </div>

        {!me?.mfa_methods?.includes('push') && !pushDeepLink && (
          <div style={{ marginTop: 14 }}>
            <button className="btn btn-primary" onClick={startPushEnroll} disabled={busy || !me?.mfa_passed}>
              {busy ? 'Preparing…' : 'Connect Telegram'}
            </button>
            {!me?.mfa_passed && (
              <p style={{ fontSize: '0.8rem', color: 'var(--bone-dim)', marginTop: 8 }}>
                Sign in with your authenticator first to connect push.
              </p>
            )}
          </div>
        )}

        {!me?.mfa_methods?.includes('push') && pushDeepLink && (
          <div style={{ marginTop: 14, paddingTop: 14, borderTop: '1px solid var(--rule-bright)' }}>
            <p style={{ fontSize: '0.88rem', marginBottom: 10 }}>
              Open this link in Telegram and tap <strong>Start</strong>. This page will update automatically once linked.
            </p>
            <a href={pushDeepLink} target="_blank" rel="noreferrer" className="btn btn-primary" style={{ textDecoration: 'none' }}>
              Open in Telegram
            </a>
            <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 8, color: 'var(--bone-dim)', fontSize: '0.82rem' }}>
              <div className="spinner" style={{ width: 14, height: 14 }} /> Waiting for you to tap Start…
            </div>
            <code style={{ display: 'block', marginTop: 10, padding: 8, background: 'var(--ink-2)', border: '1px solid var(--rule-bright)', fontSize: '0.75rem', wordBreak: 'break-all' }}>
              {pushDeepLink}
            </code>
          </div>
        )}

        {me?.mfa_methods?.includes('push') && (
          <div style={{ marginTop: 14 }}>
            <button className="btn btn-outline" onClick={disablePush} disabled={busy}>
              {busy ? 'Working…' : 'Disable push'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default Security;
