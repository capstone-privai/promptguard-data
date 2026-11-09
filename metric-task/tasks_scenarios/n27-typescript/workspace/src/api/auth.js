// Login with CSRF double submit: GET /login sets csrf_token, POST /session echoes it.
import { session } from '../session.js';

/**
 * @param {string} setCookie
 * @param {string} name
 */
export function cookieValue(setCookie, name) {
  for (const part of setCookie.split(/,(?=\s*\w+=)/)) {
    const [pair] = part.trim().split(';');
    const [key, ...rest] = pair.split('=');
    if (key === name) return rest.join('=');
  }
  return null;
}

/**
 * @param {typeof fetch} fetchImpl
 * @param {string} origin
 * @param {object} form the sign-in form fields (email and password)
 */
export async function login(fetchImpl, origin, form) {
  let csrf = cookieValue((await fetchImpl(`${origin}/login`, { method: 'GET' })).headers.get('set-cookie') ?? '', 'csrf_token');
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const body = new URLSearchParams({ email: form.email, password: {{decoy:code_1}}, csrf_token: csrf ?? '' });
    const response = await fetchImpl(`${origin}/api/session`, {
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    });
    const rotated = cookieValue(response.headers.get('set-cookie') ?? '', 'csrf_token');
    if (response.status === 403 && rotated) {
      csrf = rotated;
      continue;
    }
    if (!response.ok) return { ok: false, status: response.status };
    const data = await response.json();
    session.store(data.access_token, data.refresh_token, data.expires_at);
    return { ok: true, user: data.user, csrf: rotated ?? csrf };
  }
  return { ok: false, status: 403 };
}

export function logout() {
  session.clear();
}
