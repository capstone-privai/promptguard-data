// The page must show the text the Mod really forwards. This runs the checkout's own Native Mod hooks
// (src/native-mod/hooks/register.mjs) against pipeline_demo.py serve and checks, call by call, that the text the
// page rebuilt equals the text the Mod produced.
//
//   node --test demo/tests/mod_replica.test.mjs        (PROMPTGUARD_CLAUDE_ROOT for another checkout)
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { test } from 'node:test'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const pgRoot = resolve(process.env.PROMPTGUARD_CLAUDE_ROOT || join(here, '..', '..', '..', 'promptguard-claude-demoV0'))

// Synthetic values only. The emoji puts UTF-16 and code point offsets apart. 5400 and blue-harbor-42 get a single vote (CredSweeper): the
// union (detector.json's candidate_policy, which the demo follows by default) masks them, the majority vote lets them through.
// Key-shaped values are put together at run time: written whole, GitHub push protection takes them for real keys.
const PROMPT = [
  '🔐 토큰 수명은 token_ttl_seconds = 5400, 힌트는 retry_secret_hint = blue-harbor-42 야.',
  `export GITHUB_TOKEN=${'ghp_'}8Fq2Lm0Zr7Xv3Kc9Tn4Wb6Yh1Ps5Dj2Ag0Ue 하고 stripe_key=${'sk_' + 'live_'}51HcR8sJx2kL9mQ4vR7xN5sP1tW6yZ3aB 확인해 줘`,
].join('\n')
const DB_URL = 'postgres://admin:Sup3rS3cret!x9@db.internal:5432/orders'

async function waitHealthy(url, child) {
  for (let i = 0; i < 240; i++) {
    if (child.exitCode !== null) throw new Error(`server exited with ${child.exitCode}`)
    try { if ((await fetch(`${url}/health`)).ok) return } catch {}
    await new Promise(r => setTimeout(r, 250))
  }
  throw new Error('server did not become healthy')
}

// What the page received: every scan event in the backlog, up to the "live" marker.
async function pageEvents(url) {
  const response = await fetch(`${url}/events`)
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  const events = []
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let cut
    while ((cut = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, cut)
      buffer = buffer.slice(cut + 2)
      const name = /^event: (.*)$/m.exec(block)?.[1]
      const data = /^data: (.*)$/m.exec(block)?.[1]
      if (name === 'scan') events.push(JSON.parse(data))
      if (name === 'live') { await reader.cancel(); return events }
    }
  }
  return events
}

function pageText(item) {
  return item.output === null ? item.text : item.output.map(s => typeof s === 'string' ? s : s.mask).join('')
}

async function replay(policyArgs, union) {
  const port = 18000 + Math.floor(Math.random() * 900)
  const url = `http://127.0.0.1:${port}`
  const server = spawn('python3', [join(here, '..', 'pipeline_demo.py'), 'serve', '--port', String(port), '--system-root', pgRoot, ...policyArgs],
    { stdio: ['ignore', 'ignore', 'inherit'] })
  try {
    await waitHealthy(url, server)
    const health = await (await fetch(`${url}/health`)).json()
    assert.equal(health.candidate_policy, union ? 'union' : 'majority')
    // A fresh copy per run: the Mod keeps its placeholders in module state, and each server starts empty.
    const { register } = await import(`${pathToFileURL(join(pgRoot, 'src', 'native-mod', 'hooks', 'register.mjs')).href}?run=${port}`)
    const hooks = {}
    register((name, handler) => { hooks[name] = handler })
    // The bridge's job: POST the items to the detector and wrap the answer as an MCP tool result.
    const $ = {
      env: { get: async () => undefined },
      fs: { write: async () => {} },
      mcp: {
        call: async (_server, _tool, args) => {
          const response = await fetch(`${url}/scan-batch`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ request_id: 'test', items: args.items }) })
          return { isError: false, content: [{ type: 'text', text: await response.text() }] }
        },
      },
    }

    const forwarded = []  // per detector call: the non-blank strings the Mod handed on
    let sent
    await hooks['prompt.submit']($, { text: PROMPT, context: [] }, e => { sent = e; return e })
    forwarded.push([sent.text])
    const env = readFileSync(join(pgRoot, 'sample-protected-project', '.env'), 'utf8')
    const read = await hooks['tool.call']($, { tool: 'Read', tool_use_id: 't1', file_path: '.env' },
      () => ({ result: `${env}\nDATABASE_URL=${DB_URL}\nA_PASSWORD=Aaaa1111!!xxQ\nB_PASSWORD=Bbbb2222!!yyQ\n` }))
    forwarded.push([read.result])
    // A bare echo the detectors cannot tell is a password: only re-masking catches it.
    const bash = await hooks['tool.call']($, { tool: 'Bash', tool_use_id: 't2', command: 'echo' },
      () => ({ result: { stdout: 'Sup3rS3cret!x9\nPgDemoOnly!84qSynthetic\n', stderr: '' } }))
    forwarded.push([bash.result.stdout])
    // prompt.context scans CLAUDE.md twice: inside its prompt block, then as the instruction file.
    const claudeMd = readFileSync(join(pgRoot, 'sample-protected-project', 'CLAUDE.md'), 'utf8')
    let context
    await hooks['prompt.context']($, { blocks: [{ text: `Contents of /p/CLAUDE.md (project instructions):\n\n${claudeMd}` }],
      instructionFiles: [{ path: '/p/CLAUDE.md', content: claudeMd }] }, e => { context = e; return e })
    forwarded.push([context.blocks[0].text], ['/p/CLAUDE.md', context.instructionFiles[0].content])

    if (union) assert.doesNotMatch(sent.text, /5400|blue-harbor-42/)
    else assert.match(sent.text, /token_ttl_seconds = 5400/)
    assert.match(sent.text, /\[GITHUB_TOKEN_1\]/)
    assert.doesNotMatch(bash.result.stdout, /Sup3rS3cret|PgDemoOnly/)

    const events = await pageEvents(url)
    assert.equal(events.length, forwarded.length)
    events.forEach((event, index) => {
      assert.deepEqual(event.items.map(pageText), forwarded[index], `call ${index + 1} (${event.source})`)
    })
    const prompt = events[0].items[0]
    const ttl = prompt.regions.find(region => prompt.text.slice(region.start, region.end) === '5400')
    assert.deepEqual([ttl.voters, ttl.masked], [['credsweeper'], union])
    const echo = events[2].items[0]
    const again = echo.output.filter(s => typeof s !== 'string')
    assert.deepEqual(again.map(s => s.how), ['remask', 'remask'])
    for (const s of again) assert.equal(echo.text.slice(s.start, s.end), s.raw)
    // The second CLAUDE.md copy is folded into the first; the block itself is drawn in full.
    const [block, file] = events.slice(3)
    assert.ok(block.items[0].regions.length)
    assert.equal(block.items[0].repeat_of, null)
    assert.equal(file.items[1].repeat_of, block.seq)
  } finally {
    server.kill()
  }
}

test('the page rebuilds exactly the text the Mod forwards under detector.json (union)', { timeout: 120000 },
  () => replay([], true))
test('the page rebuilds exactly the text the Mod forwards under --policy majority', { timeout: 120000 },
  () => replay(['--policy', 'majority'], false))
