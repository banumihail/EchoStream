# Proiect Securitate Digitală — EchoStream

Reference material for the Digital Security course project. The project layers a multi-method authentication system and tamper-evident audit log onto EchoStream (the bachelor thesis), then documents the before/after in a pentest-style report.

---

## 1. Pitch (Romanian) — for the professor

Drafted in earlier session, ready to deliver verbally or via email.

### EchoStream — pe scurt
Lucrarea mea de licență este o platformă de moderare AI pentru video. Utilizatorul încarcă un fișier (sau un link YouTube), iar sistemul rulează în paralel mai multe modele de învățare automată: **Whisper** pentru transcriere, **BERT (NER)** pentru detecția datelor personale, **DETR** pentru obiecte, **AST** pentru evenimente audio, plus **YuNet + SFace** pentru detecția și recunoașterea facială. La final, un modul de **cenzurare activă** poate aplica blur sau pixelizare doar pe fețele unor persoane specifice — urmărindu-le cadru cu cadru pe baza unei fotografii de referință — și poate atenua porțiunile audio care conțin date sensibile.

Stack tehnic: FastAPI + RabbitMQ + Elasticsearch + React + Docker.

### Problema de securitate
Sistemul procesează prin natura sa **date biometrice și informații cu caracter personal** — fețe identificabile, voci, nume, adrese, fotografii de referință. În forma inițială, **nu exista niciun mecanism de autentificare**: oricine cunoștea adresa API-ului putea enumera task-urile altor utilizatori, descărca videoclipuri originale și cenzurate, vedea transcrierile, declanșa procesare GPU costisitoare sau șterge înregistrări. Un audit preliminar a identificat și alte vulnerabilități: lipsa expirării sesiunii, lipsa protecției împotriva bruteforce, CORS permisiv, lipsa HTTPS, expunere informațională prin OpenAPI public, **IDOR** (acces la resursele altor utilizatori după autentificare).

### Propunere — trei etape
1. **Audit de securitate** — identificarea și clasificarea vulnerabilităților după **Critic / Ridicat / Mediu / Scăzut / Informațional**, cu descriere și capturi de ecran.
2. **Implementare contramăsuri** — sistem MFA cu **5 metode distincte** + modul de alertare pentru acces neautorizat.
3. **Re-audit** — comparativ înainte/după, cu discuția riscurilor reziduale.

### Întrebări pentru profesor
1. Integrarea proiectului cu lucrarea de licență este acceptabilă?
2. "5 metode distincte" = 5 disponibile (utilizatorul alege) sau 5 active simultan?
3. HTTPS cu certificat self-signed pentru demonstrația locală este acceptabil?
4. Structura audit → implementare → re-audit se aliniază așteptărilor?

---

## 2. Risk classification (Romanian — matches sample report format)

| Clasificarea riscului | Caracteristici |
|---|---|
| **Risc critic** | Exploatarea rezultă acces administrator/root; informațiile sunt ușor accesibile; exploatarea este simplă. |
| **Risc ridicat** | Nu aduce privilegii admin, dar oferă acces nerestricționat la date; mai dificil de exploatat. |
| **Risc mediu** | Acces foarte limitat; DoS sau probleme similare; de obicei cere atacatorul în aceeași rețea locală. |
| **Risc scăzut** | Impact mic; exploatarea necesită acces fizic la sistem. |
| **Informațional** | Nu sunt vulnerabilități, dar pot conduce la descoperirea unora. |

---

## 3. Findings already discovered (the "before" chapter)

| # | Vulnerabilitate | Risc | Status |
|---|---|---|---|
| 1 | Lipsa autentificării (toate endpoint-urile API erau publice) | **Critic** | Fixat în Phase 0 |
| 2 | Lipsa tunelului HTTPS (HTTP clear-text) | **Ridicat** | În plan — Phase 8 |
| 3 | IDOR — orice user autenticat vede task-urile tuturor | **Ridicat** | Fixat în Phase 0.5 |
| 4 | Lipsa expirării sesiunii (nu existau sesiuni) | **Mediu** | Fixat în Phase 0 (JWT exp 30 min) |
| 5 | Lipsa mecanismului de blocare bruteforce | **Mediu** | În plan — Phase 6 |
| 6 | CORS permisiv (`allow_origins=["*"]`) | **Mediu** | De documentat și de înăsprit |
| 7 | Acces fără autorizare la fișierele statice `/uploads/*` | **Ridicat** | De abordat (signed URLs, în Phase 6/8) |
| 8 | Expunere informațională via OpenAPI public (`/docs`) | **Informațional** | De documentat (dezactivat în production) |
| 9 | Stack traces în răspunsurile de eroare | **Informațional** | De documentat |
| 10 | Reference photos pentru face blur stocate fără criptare în uploads/refs/ | **Mediu** | De documentat |

---

## 4. The 5 MFA methods (implementation plan)

| # | Metodă | Tehnologie | Status |
|---|---|---|---|
| 1 | **TOTP** (Google Authenticator) | `pyotp` + `qrcode`, RFC 6238 | Phase 1 (next) |
| 2 | **Coduri de rezervă** | HMAC-SHA256, 10 single-use codes | Phase 2 |
| 3 | **OTP prin email** | SMTP via **Mailtrap**, 6-digit, 5-min expiry | Phase 3 |
| 4 | **FIDO2 / WebAuthn** | `webauthn` (Python) + `@simplewebauthn/browser`, Windows Hello / YubiKey | Phase 4 |
| 5 | **Notificări push** | Pushover (sau Telegram bot) cu Approve/Deny | Phase 5 |

### Two-step login flow (shared across all methods)

1. `POST /auth/login` with username + password
2. If user has any `mfa_methods`, response is `{mfa_required: true, challenge_token, methods: [...]}` (short-lived JWT, 5 min, `purpose: mfa-challenge`)
3. Frontend prompts the user; user picks a method and provides the second factor
4. `POST /auth/mfa/{method}/verify` with `challenge_token + code` → returns the real session JWT with `mfa: true`

---

## 5. Alerting module (Phase 7)

Every authentication attempt is indexed to `echostream_auth_events`:

```json
{
  "timestamp": "2026-05-09T15:30:00",
  "username": "alice",
  "ip": "192.168.1.42",
  "user_agent": "Mozilla/5.0 ...",
  "event_type": "login_fail | login_success | mfa_success | mfa_fail | register | idor_attempt | lockout",
  "mfa_method": "password | totp | email | backup | fido2 | push",
  "outcome": "ok | denied | locked",
  "reason": "..."
}
```

Three Kibana alert rules:
1. **Failed-login burst** — `event_type:login_fail AND outcome:denied` count ≥5 per IP in 10 min
2. **New-IP successful login** — `event_type:login_success` and the IP has not been seen in the last 30 days for that username
3. **MFA bypass attempt** — `event_type:login_success` followed by 3× `event_type:mfa_fail` for the same username within 5 min

Delivery: email or webhook (Telegram bot is the easiest demo target).

---

## 6. Key technical decisions — talking points for the defense

| Decision | Why |
|---|---|
| **Argon2id** over bcrypt | OWASP-recommended since 2022; memory-hard, GPU/ASIC resistant. Tunable parameters (time_cost=3, memory_cost=64 MiB, parallelism=2). |
| **JWT (HS256)** over server sessions | Stateless; integrates with existing infrastructure (no new session store); aligns with REST API style. Trade-off: revocation needs a denylist (acceptable for the demo scope). |
| **FIDO2 in addition to TOTP** | TOTP is phishable (a phishing site can relay the 6-digit code in real time); FIDO2 binds the credential to the origin and is unphishable. Defense in depth. |
| **Multiple MFA methods enrollable** | Account recovery: if the user loses their phone, backup codes or email OTP still work. Single-method MFA = single point of lockout. |
| **404 (not 403) on IDOR** | Returning 403 confirms the resource exists, enabling enumeration. 404 hides both existence and ownership. |
| **Per-user audit log in ES, not flat file** | Centralized, queryable, alert-able from Kibana (which is already running). One fewer service to add. |
| **CPU-bound BERT NER** | Frees 430 MB GPU VRAM for Whisper/AST/DETR; BERT on CPU processes one short transcript per task — latency is not on the critical path. |
| **PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:128** | Windows-compatible (the `expandable_segments` value is Linux-only). Reduces fragmentation when 5 worker processes share the GPU. |

---

## 7. Report structure (matches the sample template)

```
Cuprins
1. Introducere — descrierea EchoStream, suprafața de atac, perimetrul auditului
2. Niveluri de risc — tabelul Critic/Ridicat/Mediu/Scăzut/Informațional
3. Vulnerabilități găsite (înainte)
   3.1 Lipsa autentificării                                  [Critic]
   3.2 IDOR — broken object-level authorization              [Ridicat]
   3.3 Lipsa tunelului SSL                                   [Ridicat]
   3.4 Lipsa expirării sesiunii                              [Mediu]
   3.5 Lipsa unui mecanism de blocare bruteforce             [Mediu]
   3.6 CORS permisiv                                         [Mediu]
   3.7 Acces neautorizat la fișiere statice                  [Ridicat]
   3.8 OpenAPI public                                        [Informațional]
   3.9 Stack traces în răspunsuri                            [Informațional]
   3.10 Fotografii de referință stocate necriptate           [Mediu]
4. Implementarea contramăsurilor
   4.1 Hashing parole cu Argon2id
   4.2 Sesiuni JWT cu expirare
   4.3 TOTP (Google Authenticator)
   4.4 Coduri de rezervă
   4.5 OTP prin email
   4.6 FIDO2 / WebAuthn
   4.7 Notificări push
   4.8 Owner-scoped access (mitigare IDOR)
   4.9 Rate-limiting și account lockout
   4.10 Modul de alertare în Kibana
   4.11 HTTPS cu certificat self-signed
5. Re-audit — tabel comparativ înainte / după
6. Concluzii și limitări (riscuri reziduale)
7. Bibliografie
```

---

## 8. Useful technical notes (English — implementation details)

### TOTP enrollment
- Secret: 32-byte base32 string (`pyotp.random_base32()`)
- Provisioning URI: `pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name="EchoStream")`
- QR: `qrcode.make(uri).save(buffer, format="PNG")` → base64
- Verification window: ±1 step (30 s) to tolerate clock drift: `TOTP(secret).verify(code, valid_window=1)`

### Backup codes
- Generate 10 codes: `secrets.token_urlsafe(6)` each
- Display once at enrollment, never again
- Store as `hmac.new(server_key, code, hashlib.sha256).hexdigest()` so a DB leak can't unlock accounts
- Mark used codes (set to `None`) — single-use

### Mailtrap
- Sign up at https://mailtrap.io (free dev inbox)
- Use the SMTP credentials from the inbox settings
- Env vars: `SMTP_HOST=sandbox.smtp.mailtrap.io`, `SMTP_PORT=2525`, `SMTP_USER=...`, `SMTP_PASS=...`
- Email is captured by the inbox, never delivered to a real recipient — perfect for a demo

### FIDO2 / WebAuthn
- Python: `pip install webauthn`
- Frontend: `npm install @simplewebauthn/browser`
- Two flows: registration (create credential) and authentication (verify credential)
- Origin must match exactly — `http://localhost:5173` (demo) or the real origin (production)
- Windows Hello, Touch ID, Android fingerprint all work as platform authenticators; YubiKey works over USB

### Pushover
- Free tier: 7,500 messages/month
- User key + app token = identify and authorize
- Approve/Deny via webhook callback or short-poll on a status endpoint

### Rate limiting / lockout
- Track in user document: `failed_logins`, `locked_until`
- After 5 consecutive password fails → 15-min lockout
- IP-based rate limit via `slowapi` (`pip install slowapi`) — 30 req / 5 min on `/auth/login`

### HTTPS self-signed cert (Windows)
```powershell
mkcert -install
mkcert localhost 127.0.0.1 ::1
# generates localhost.pem and localhost-key.pem
```
Then in `api/main.py`:
```python
uvicorn.run(app, host="0.0.0.0", port=8443,
            ssl_keyfile="localhost-key.pem", ssl_certfile="localhost.pem")
```

---

## 9. Bibliography hints (start here)

- **OWASP Authentication Cheat Sheet** — https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- **OWASP Password Storage Cheat Sheet** — Argon2id parameter recommendations
- **OWASP Top 10 — Broken Access Control** (A01:2021) — IDOR section
- **RFC 6238** — TOTP specification
- **RFC 4226** — HOTP specification
- **NIST SP 800-63B** — Digital Identity Guidelines (authentication assurance levels)
- **W3C WebAuthn Level 3** — https://www.w3.org/TR/webauthn-3/
- **FIDO Alliance — Why WebAuthn matters** for the "TOTP is phishable" argument

---

## 10. Open items to confirm with professor

- [ ] Integration with bachelor thesis is acceptable
- [ ] "5 methods distinct" interpretation
- [ ] Self-signed HTTPS acceptable for demo
- [ ] Structure audit → implementation → re-audit aligns
- [ ] Report language: Romanian (assumed from sample)
- [ ] Page count expectation
- [ ] Screenshot tooling (DevTools / Burp / ZAP)
