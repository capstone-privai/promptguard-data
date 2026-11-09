import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { cookieValue, login, logout } from '../src/api/auth.js';
import { mockResponse } from '../src/__mocks__/login.js';
import { session } from '../src/session.js';

const har = JSON.parse(readFileSync(new URL('./recordings/login.har', import.meta.url), 'utf8'));

function replayHar(entries) {
  const queue = [...entries];
  const sent = [];
  const fetchImpl = async (url, init) => {
    const entry = queue.shift();
    assert.equal(init.method, entry.request.method);
    assert.equal(new URL(url).pathname, new URL(entry.request.url).pathname);
    sent.push(init.body ?? null);
    const headers = {};
    for (const { name, value } of entry.response.headers) headers[name] = headers[name] ? `${headers[name]}, ${value}` : value;
    const text = entry.response.content.text;
    return mockResponse(entry.response.status, headers, text ? JSON.parse(text) : undefined);
  };
  return { fetchImpl, sent };
}

test('login retries once with the rotated CSRF token', async () => {
  const { fetchImpl, sent } = replayHar(har.log.entries.slice(0, 3));
  const result = await login(fetchImpl, 'https://shop.orderdesk.test', { email: 'kim.minji@mail.test', password: 'correct horse 12' });
  assert.equal(result.ok, true);
  assert.equal(result.user.id, 7);
  const csrfOf = (index) => cookieValue(har.log.entries[index].response.headers.find((h) => h.name === 'Set-Cookie').value, 'csrf_token');
  assert.equal(new URLSearchParams(sent[1]).get('csrf_token'), csrfOf(0));
  assert.equal(new URLSearchParams(sent[2]).get('csrf_token'), csrfOf(1));
  assert.equal(result.csrf, csrfOf(2));
  const body = JSON.parse(har.log.entries[2].response.content.text);
  assert.deepEqual(Object.values(session.snapshot()), [body.access_token, body.refresh_token]);
  logout();
  assert.deepEqual(Object.values(session.snapshot()), [null, null]);
});

test('cookie parsing handles several cookies in one header', () => {
  assert.equal(cookieValue('a=1; Path=/, csrf_token=x=y; Secure', 'csrf_token'), 'x=y');
  assert.equal(cookieValue('', 'csrf_token'), null);
});
