// Frontend auth helpers — token storage + authFetch wrapper.
// Single source of truth for the JWT lives in localStorage so a page refresh
// keeps the user logged in until the token expires.

const TOKEN_KEY = 'echostream.token';
const USER_KEY = 'echostream.user';
export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function saveSession({ token, username }) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, username);
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function getUsername() {
  return localStorage.getItem(USER_KEY);
}

// Quick local check that doesn't validate the signature, just expiry.
// The server is still the source of truth — this just avoids a needless API call.
export function isTokenLikelyValid() {
  const t = getToken();
  if (!t) return false;
  try {
    const [, payloadB64] = t.split('.');
    const payload = JSON.parse(atob(payloadB64.replace(/-/g, '+').replace(/_/g, '/')));
    if (!payload.exp) return true;
    return payload.exp * 1000 > Date.now();
  } catch {
    return false;
  }
}

// Wrapper around fetch that attaches the Bearer token and surfaces 401s.
// Returns the Response — callers handle .json()/.ok themselves.
export async function authFetch(path, options = {}) {
  const token = getToken();
  const headers = new Headers(options.headers || {});
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const url = path.startsWith('http') ? path : `${API_URL}${path}`;
  const res = await fetch(url, { ...options, headers });
  if (res.status === 401) {
    clearSession();
    // Bubble up — App.jsx watches localStorage to bounce back to login.
    window.dispatchEvent(new CustomEvent('echostream:auth-expired'));
  }
  return res;
}
