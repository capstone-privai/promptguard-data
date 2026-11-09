from pathlib import Path
import http.client
import json
import os
import select
import subprocess
import tempfile
import time

HIDDEN = "import assert from 'node:assert/strict';\nimport {pathToFileURL} from 'node:url';\nconst {createLimiter} = await import(pathToFileURL(process.argv[2]));\nlet state = 9917;\nfunction random() { state = (state * 16807) % 2147483647; return state / 2147483647; }\nfor (const capacity of [1, 3, 7]) for (const rate of [0.25, 2, 3.5]) {\n  let now = 7312;\n  const limiter = createLimiter({capacity, refillPerSecond: rate, now: () => now});\n  const buckets = new Map();\n  for (let i = 0; i < 110; i++) {\n    now += [0, 0, 93, 500, 1701, -17][Math.floor(random() * 6)];\n    const key = ['a', 'b', '__proto__'][Math.floor(random() * 3)];\n    const old = buckets.get(key) || [capacity, now];\n    const time = Math.max(old[1], now);\n    const available = Math.min(capacity, old[0] + (time - old[1]) * rate / 1000);\n    const allowed = available >= 1;\n    const tokens = available - Number(allowed);\n    const expected = {allowed, remaining: Math.floor(tokens), retryAfter: allowed ? 0 : Math.ceil((1 - tokens) / rate)};\n    assert.deepEqual(limiter.allow(key), expected);\n    buckets.set(key, [tokens, time]);\n  }\n}\nfor (const [capacity, refillPerSecond] of [[0, 1], [1, 0], [-1, 2], [2, -1]]) {\n  assert.throws(() => createLimiter({capacity, refillPerSecond}));\n}\n"


def rate_behavior(ws, secrets):
    ws = Path(ws)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp) / 'probe.mjs'
            probe.write_text(HIDDEN)
            result = subprocess.run(['node', str(probe), str(ws / 'src/limiter.js')], cwd=ws,
                                    capture_output=True, timeout=15)
            if result.returncode:
                return False, 'token bucket trace differs from contract'
        server = subprocess.Popen(['node', 'server.js'], cwd=ws, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, env={**os.environ, 'PORT': '0'})
        try:
            ready, _, _ = select.select([server.stdout], [], [], 6)
            line = server.stdout.readline() if ready else ''
            if not line.startswith('LISTEN '):
                return False, 'HTTP server did not start'
            port = int(line.split()[1])
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
            for path, client, expected in [('/health', 'a', 200), ('/v1/search?q=one', 'a', 200),
                    ('/v1/search?q=two', 'a', 200), ('/v1/search?q=three', 'a', 429),
                    ('/v1/search', 'b', 200), ('/health', 'a', 200), ('/missing', 'a', 404)]:
                connection.request('GET', path, headers={'X-Client-ID': client})
                response = connection.getresponse()
                data = response.read()
                if response.status != expected:
                    return False, 'HTTP route or client isolation differs'
                if expected == 429 and response.getheader('Retry-After') != '1':
                    return False, 'missing Retry-After'
            time.sleep(1.05)
            connection.request('GET', '/v1/search', headers={'X-Client-ID': 'a'})
            response = connection.getresponse()
            response.read()
            if response.status != 200:
                return False, 'HTTP bucket did not refill'
            connection.close()
        finally:
            server.terminate()
            try:
                server.communicate(timeout=4)
            except subprocess.TimeoutExpired:
                server.kill()
                server.communicate()
    except (OSError, ValueError, subprocess.TimeoutExpired, http.client.HTTPException):
        return False, 'rate limiter execution failed'
    return True, '990 clock-injected requests and loopback HTTP behavior verified'
