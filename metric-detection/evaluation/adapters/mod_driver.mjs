// Runs a PromptGuard checkout's own Native Mod (src/native-mod/hooks/register.mjs) for the evaluation.
//
//   node mod_driver.mjs <register.mjs>      then JSON lines on stdin, one answer line on stdout per request
//
// Every commit's register.mjs exports only `register(on)`, which registers its hooks. The driver registers them
// with a stub `on` (keeping each hook's `.catch` backstop, as the engine does) and runs each text through the
// `prompt.submit` hook, with a stubbed `$`: no environment variables are set (the Mod's defaults, as shipped), file
// writes go nowhere, and the detector call ($.mcp.call 'pgdetector' 'scan_batch') is answered with the worker result
// the evaluation got from the checkout's detector. Everything else is the Mod's own code: its scanBatch checks,
// redactText and numbering, remaskText / remaskPartial and its handling of a failed scan.
//
// The shim: the module source is evaluated unchanged, from a data: URL, with one line appended that exports a few of
// its top-level names under a __pg_ prefix (only those it declares): `redactText` (required), `reverseVault`
// (required), `maskedForm` and `BLOCKED_TEXT`. They are read, never patched. After a hook succeeds, the driver calls
// redactText once more with the same findings: the ledger already holds every value, so it returns the hook's
// detector-pass text (before remask) without changing any state. The caller maps output to original-text edits with
// it (node_mod.py). The Mod's placeholder ledger is module state, so every evaluated session gets a fresh module
// instance (the URL differs per session), as every Claude Code session loads the Mod afresh.
//
// Requests:  {"op": "describe"}  {"op": "session"}  {"op": "item", "text": ..., "result": <worker result>}
// Answers:   describe -> {node, exposed, fail_closed}; session -> {ok: true};
//            item -> {status: "ok" | "blocked" | "failed_open", text, stage1?, vault?, error?}
//            stage1 and vault (reverseVault as [raw, masked form, placeholder]) only when remask changed the text.
//            A request the driver cannot serve -> {driver_error: message}.
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { createInterface } from 'node:readline'

const modPath = path.resolve(process.argv[2] || '')
const source = readFileSync(modPath, 'utf8')
const pluginRoot = path.resolve(path.dirname(modPath), '..')
const declares = name => new RegExp(`^(?:export\\s+)?(?:const|let|var|function|async\\s+function|class)\\s+${name}\\b`, 'm').test(source)
const EXPOSED = ['redactText', 'reverseVault', 'maskedForm', 'BLOCKED_TEXT'].filter(declares)
for (const name of ['redactText', 'reverseVault']) {
  if (!EXPOSED.includes(name)) {
    process.stdout.write(JSON.stringify({ driver_error: `${modPath} declares no top-level ${name}; this Mod cannot be driven` }) + '\n')
    process.exit(3)
  }
}
const shimmed = `${source}\nexport { ${EXPOSED.map(name => `${name} as __pg_${name}`).join(', ')} }\n`

let generation = 0
let mod = null

async function newSession() {
  generation += 1
  const url = `data:text/javascript;base64,${Buffer.from(`${shimmed}// evaluated session ${generation}\n`).toString('base64')}`
  const module = await import(url)
  const handlers = {}
  const catches = {}
  module.register((name, ...rest) => {
    handlers[name] = rest.at(-1)
    return { catch(handler) { catches[name] = handler; return this } }
  })
  if (typeof handlers['prompt.submit'] !== 'function') throw new Error('the Mod registers no prompt.submit hook')
  mod = { module, handlers, catches }
}

// The engine's `next`: passes the event on; `called` tells a .catch backstop whether the hook got that far.
function makeNext() {
  const next = async event => { next.called = true; return event }
  next.called = false
  next.signal = new AbortController().signal
  return next
}

function stub(result) {
  return {
    env: { get: async () => undefined },
    fs: { write: async () => {}, read: async file => readFileSync(file, 'utf8') },
    plugin: { root: pluginRoot },
    mcp: {
      call: async (_server, _tool, { items }) => {
        if (items.length !== 1) throw new Error(`expected one text per scan, got ${items.length}`)
        return { isError: false, content: [{ type: 'text', text: JSON.stringify({ ok: Boolean(result?.ok), items: items.map(item => ({ id: item.id, ...result })) }) }] }
      },
    },
  }
}

async function runItem({ text, result }) {
  if (!mod) throw new Error('no session')
  const { module, handlers, catches } = mod
  const event = { text }
  let out
  let status = 'ok'
  let error
  try {
    out = (await handlers['prompt.submit'](stub(result), event, makeNext())).text
  } catch (thrown) {
    if (typeof catches['prompt.submit'] === 'function') {
      out = (await catches['prompt.submit'](stub(result), event, makeNext())).text
    } else {  // no backstop: the engine skips the failed hook and the text goes out unchanged
      status = 'failed_open'
      error = String(thrown?.message || thrown)
      out = text
    }
  }
  if (typeof out !== 'string') throw new Error('the prompt.submit hook returned no text')
  const blocked = module.__pg_BLOCKED_TEXT
  if (status === 'ok' && blocked !== undefined && out === blocked) status = 'blocked'
  const answer = { status, text: out }
  if (error !== undefined) answer.error = error
  if (status === 'ok' && out !== text) {
    const stage1 = module.__pg_redactText(text, result.findings)
    if (stage1 !== out) {
      answer.stage1 = stage1
      const masked = module.__pg_maskedForm || (value => value)
      answer.vault = [...module.__pg_reverseVault.entries()].map(([raw, placeholder]) => [raw, masked(placeholder), placeholder])
    }
  }
  return answer
}

const lines = createInterface({ input: process.stdin, crlfDelay: Infinity })
for await (const line of lines) {
  if (!line.trim()) continue
  let answer
  try {
    const request = JSON.parse(line)
    if (request.op === 'describe') answer = { node: process.version, mod: modPath, exposed: EXPOSED, fail_closed: EXPOSED.includes('BLOCKED_TEXT') }
    else if (request.op === 'session') { await newSession(); answer = { ok: true } }
    else if (request.op === 'item') answer = await runItem(request)
    else throw new Error(`unknown op ${request.op}`)
  } catch (thrown) {
    answer = { driver_error: String(thrown?.stack || thrown) }
  }
  process.stdout.write(JSON.stringify(answer) + '\n')
}
