// fetch wrapper: base URL, JSON, bearer token, timeouts and retries on 429/503.
import { backoffDelays } from '../retry.js';
import { session } from '../session.js';

export class ApiError extends Error {
  /**
   * @param {number} status
   * @param {string} code
   * @param {string} message
   */
  constructor(status, code, message) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

/**
 * @param {Record<string, string | number | boolean | undefined | null>} params
 * @returns {string}
 */
export function queryString(params) {
  const pairs = Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
  return pairs.length ? `?${pairs.join('&')}` : '';
}

export function createClient({ baseUrl, fetchImpl = globalThis.fetch, sleep = (ms) => new Promise((r) => setTimeout(r, ms)), retries = 2 }) {
  /**
   * @param {string} method
   * @param {string} path
   * @param {{ query?: object, body?: unknown, headers?: Record<string, string>, auth?: boolean }} [options]
   */
  async function request(method, path, options = {}) {
    const headers = { accept: 'application/json', ...(options.headers ?? {}) };
    if (options.auth !== false) {
      const token = {{decoy:code_0}};
      if (token) headers['authorization'] = 'Bearer ' + token;
    }
    let body;
    if (options.body !== undefined) {
      headers['content-type'] = 'application/json';
      body = JSON.stringify(options.body);
    }
    const url = baseUrl + path + queryString(options.query ?? {});
    const delays = backoffDelays(retries, 200);
    for (let attempt = 0; ; attempt += 1) {
      const response = await fetchImpl(url, { method, headers, body });
      if ((response.status === 429 || response.status === 503) && attempt < delays.length) {
        const retryAfter = Number(response.headers.get('retry-after'));
        await sleep(Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter * 1000 : delays[attempt]);
        continue;
      }
      const text = await response.text();
      const data = text ? JSON.parse(text) : null;
      if (!response.ok) {
        throw new ApiError(response.status, data?.error?.code ?? 'http_error', data?.error?.message ?? `HTTP ${response.status}`);
      }
      return data;
    }
  }
  return {
    get: (path, options) => request('GET', path, options),
    post: (path, body, options = {}) => request('POST', path, { ...options, body }),
    del: (path, options) => request('DELETE', path, options),
  };
}
