import http from 'node:http';
import fs from 'node:fs';
import {createLimiter} from './src/limiter.js';
import {clientKey} from './src/auth.ts';
const config = JSON.parse(fs.readFileSync(new URL('./config/default.json', import.meta.url)));
const limiter = createLimiter(config.rateLimit);
const csrf = JSON.parse(fs.readFileSync(new URL('./config/csrf.json', import.meta.url)));
const server = http.createServer((req, res) => {
  if (req.url === '/health') { res.end('ok'); return; }
  if (!req.url.startsWith('/v1/search')) { res.writeHead(404); res.end('missing'); return; }
  const decision = limiter.allow(clientKey(req));
  if (req.headers.cookie) res.setHeader('Set-Cookie', req.headers.cookie + '; Path=/; HttpOnly');
  if (req.headers['x-csrf-case']) res.setHeader('X-CSRF-Token', csrf['csrf_token_' + req.headers['x-csrf-case']]);
  res.setHeader('X-RateLimit-Remaining', decision.remaining);
  if (!decision.allowed) res.setHeader('Retry-After', decision.retryAfter);
  res.writeHead(decision.allowed ? 200 : 429, {'Content-Type': 'application/json'});
  res.end(JSON.stringify({allowed: decision.allowed, hits: decision.allowed ? ['local result'] : []}));
});
server.listen(Number(process.env.PORT || 0), '127.0.0.1', () => console.log('LISTEN ' + server.address().port));
process.on('SIGTERM', () => server.close());
