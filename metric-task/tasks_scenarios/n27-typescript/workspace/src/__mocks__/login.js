// Canned responses of the login endpoints for component tests (captured from staging, 2026-10-21).
/**
 * @param {number} status
 * @param {Record<string, string>} headers
 * @param {unknown} body
 */
export function mockResponse(status, headers, body) {
  const lower = Object.fromEntries(Object.entries(headers).map(([k, v]) => [k.toLowerCase(), v]));
  return {
    status,
    ok: status >= 200 && status < 300,
    headers: { get: (name) => lower[name.toLowerCase()] ?? null },
    json: async () => body,
    text: async () => (body === undefined ? '' : JSON.stringify(body)),
  };
}

export const LOGIN_SUCCESS = {
  status: 200,
  headers: {
    'Content-Type': 'application/json',
    'Set-Cookie': 'sid={{secret:session_cookie_0}}; Path=/; HttpOnly; Secure; SameSite=Lax',
  },
  body: { user: { id: 7, name: 'Kim Minji' }, expires_at: 1893456000 },
};

export const ADMIN_LOGIN = {
  status: 200,
  headers: {
    'Content-Type': 'application/json',
    'Set-Cookie': 'sid={{secret:session_cookie_1}}; Path=/admin; HttpOnly; Secure; SameSite=Strict',
  },
  body: { user: { id: 1, name: 'Han Mirae', admin: true }, expires_at: 1893456000 },
};

/** @param {{ status: number, headers: Record<string, string>, body: unknown }} canned */
export function replay(canned) {
  return async () => mockResponse(canned.status, canned.headers, canned.body);
}
