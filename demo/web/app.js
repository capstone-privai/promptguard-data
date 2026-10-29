'use strict'

// Where the Mod got the text (the `source` it sends with every scan, see register.mjs).
const CHANNELS = {
  user_prompt: '사용자 프롬프트',
  user_command: '! 셸 명령',
  claude_md: 'CLAUDE.md',
  automatic_context: '자동 컨텍스트',
  read_result: '파일 읽기 (Read)',
  grep: '검색 결과 (Grep)',
  bash_stdout: 'Bash 출력',
  bash_error: 'Bash 오류',
  subagent: '서브에이전트',
  mcp: 'MCP 도구 결과',
  tool_result: '도구 결과',
  history: '대화 기록 · 모델 출력',
}
// What the presenter typed always gets its own row, even when nothing in it was flagged.
const ALWAYS_SHOWN = new Set(['user_prompt', 'user_command'])
const KEEP = 300

const feed = document.getElementById('feed')
const empty = document.getElementById('empty')
const quietToggle = document.getElementById('show-quiet')
const quietCount = document.getElementById('quiet-count')
const status = document.getElementById('status')
const statusText = document.getElementById('status-text')

let setup = null
let lastSeq = 0
let live = false
let quiet = 0
const seen = new Map()  // event seq -> time, for rows that repeat an earlier one

function el(tag, className, text) {
  const node = document.createElement(tag)
  if (className) node.className = className
  if (text !== undefined) node.textContent = text
  return node
}

// The rule in force: detector.json's candidate_policy, and under "majority" its vote among the voting modules.
function consensusText(info) {
  if (info.policy === 'union') return '하나라도 찾으면 가림 · 모듈별 스팬을 모두 합쳐 가림'
  const bystanders = info.adapters.filter(name => !info.voters.includes(name))
  return `${ruleWords()} · ${info.required}/${info.voters.length}개 이상이 찾은 자리만 합쳐 가림`
    + (bystanders.length ? ` · ${bystanders.join(', ')}는 표 없음` : '')
}

function clock(seconds) {
  const time = new Date(seconds * 1000)
  return [time.getHours(), time.getMinutes(), time.getSeconds()].map(n => String(n).padStart(2, '0')).join(':')
}

function channelChip(source) {
  const chip = el('span', 'channel', CHANNELS[source] || source)
  chip.append(el('span', 'code', source))
  return chip
}

function clip(text, max) {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

// ---- the four columns ----

// Values no detector flagged this time, masked again because the Mod already holds them.
function remasked(item) {
  const spans = (item.output || []).filter(s => typeof s !== 'string' && s.how === 'remask')
  return spans.filter(s => !item.regions.some(r => r.start < s.end && s.start < r.end))
}

const CONTEXT = 24     // characters kept on each side of a highlight
const PLAIN_LINES = 4  // lines shown of a text with nothing highlighted
const PLAIN_CHARS = 160
const AROUND_CHARS = 60 // characters kept of the line above and below a highlighted line

// Only what matters, at a glance: the lines that hold a highlight, cut to a window around each highlight, and one
// line above and below them for context, with ⋯ for skipped lines and … for cut line ends. spans are sorted, disjoint {start, end} in UTF-16 offsets;
// draw(span, start, end) renders the part of a span inside one window.
function excerpt(box, text, spans, draw) {
  // Never cut between the halves of a surrogate pair.
  const startAt = i => (i > 0 && (text.charCodeAt(i) & 0xfc00) === 0xdc00 ? i - 1 : i)
  const endAt = i => (i < text.length && (text.charCodeAt(i - 1) & 0xfc00) === 0xd800 ? i + 1 : i)
  const lines = []
  let at = 0
  for (const line of text.split('\n')) { lines.push([at, at + line.length]); at += line.length + 1 }
  const hits = lines.map(([a, b]) => spans.filter(span => span.start < b && a < span.end))
  const marked = hits.map(list => list.length > 0)
  const shown = spans.length ? marked.map((_, i) => marked[i - 1] || marked[i] || marked[i + 1]) : lines.map((_, i) => i < PLAIN_LINES)
  // ⋯ only where something was left out: skipping blank lines (a trailing newline, say) is not worth a mark.
  const blank = ([a, b]) => !text.slice(a, b).trim()
  let skipped = false
  const omit = () => { if (skipped) box.append(el('span', 'omit', '⋯'), '\n'); skipped = false }
  lines.forEach(([a, b], i) => {
    if (!shown[i]) { skipped ||= !blank(lines[i]); return }
    omit()
    const windows = []
    for (const span of hits[i]) {
      const w = [startAt(Math.max(a, span.start - CONTEXT)), endAt(Math.min(b, span.end + CONTEXT))]
      if (windows.length && w[0] <= windows.at(-1)[1]) windows.at(-1)[1] = Math.max(windows.at(-1)[1], w[1])
      else windows.push(w)
    }
    if (!windows.length) windows.push([a, endAt(Math.min(b, a + (spans.length ? AROUND_CHARS : PLAIN_CHARS)))])
    windows.forEach(([w0, w1], k) => {
      if (k > 0 || w0 > a) box.append(el('span', 'cut', '…'))
      let cursor = w0
      for (const span of hits[i]) {
        const s0 = Math.max(span.start, w0)
        const s1 = Math.min(span.end, w1)
        if (s0 >= s1) continue
        box.append(text.slice(cursor, s0), draw(span, s0, s1))
        cursor = s1
      }
      box.append(text.slice(cursor, w1))
    })
    if (windows.at(-1)[1] < b) box.append(el('span', 'cut', '…'))
    box.append('\n')
  })
  omit()
  if (box.lastChild?.nodeType === Node.TEXT_NODE && box.lastChild.data === '\n') box.lastChild.remove()
}

function inputColumn(item) {
  const box = el('pre', 'textbox')
  const marks = [
    ...item.regions.map((region, index) => ({ ...region, className: region.masked ? 'hit' : 'miss', region: index })),
    ...remasked(item).map(span => ({ ...span, className: 'again', tag: '↺' })),
  ].sort((a, b) => a.start - b.start)
  excerpt(box, item.text, marks, (span, start, end) => {
    const mark = el('mark', span.className)
    if (span.region !== undefined) mark.dataset.region = span.region
    // The curves tie a highlight to its flow, so only re-masked values carry a sign (on their first piece when
    // the value runs over several lines).
    if (span.tag && start === span.start) mark.append(el('span', 'tag', span.tag))
    mark.append(item.text.slice(start, end))
    return mark
  })
  box.addEventListener('scroll', () => drawLinks(box.closest('.lane')))
  return box
}

// The consensus rule in the words the column head uses.
function ruleWords() {
  return setup.consensus === 'majority' ? '과반' : setup.consensus === 'any' ? '하나라도'
    : setup.consensus === 'unanimous' ? '만장일치' : `${setup.required}표 이상`
}

const TRACK_CONTEXT = 6  // characters of the same line kept on each side of a region in its span tracks
const TRACK_CHARS = 72   // longer regions are cut, the same way in every track so they stay aligned

// The stretch of text every track of a region shows: the region with a little of its line around it.
function trackWindow(text, region) {
  let start = region.start
  let end = region.end
  while (start > 0 && region.start - start < TRACK_CONTEXT && text[start - 1] !== '\n') start--
  while (end < text.length && end - region.end < TRACK_CONTEXT && text[end] !== '\n') end++
  return [start, end]
}

// One row of a region's span picture: the window's text, dimmed, with the spans in it highlighted. Every row of a
// region shows the same characters, so the spans line up from row to row like bars on a shared axis.
function track(text, [w0, w1], spans, className) {
  const row = el('div', 'track')
  const end = Math.min(w1, w0 + TRACK_CHARS)
  const shown = s => s.replace(/\n/g, '⏎').replace(/\t/g, '→')
  const merged = []
  for (const { start, end: stop } of [...spans].sort((a, b) => a.start - b.start)) {
    const s0 = Math.max(start, w0)
    const s1 = Math.min(stop, end)
    if (s0 >= s1) continue
    if (merged.length && s0 <= merged.at(-1)[1]) merged.at(-1)[1] = Math.max(merged.at(-1)[1], s1)
    else merged.push([s0, s1])
  }
  let cursor = w0
  for (const [s0, s1] of merged) {
    row.append(shown(text.slice(cursor, s0)), el('mark', className, shown(text.slice(s0, s1))))
    cursor = s1
  }
  row.append(shown(text.slice(cursor, end)))
  if (end < w1) row.append(el('span', 'cut', '…'))
  return row
}

// One region's path through the ensemble: the same text reaches every module (curves from the input box, see
// drawLinks), each module's spans in the region are drawn on its own track (solid line in when it found
// something, dashed when it did not), and the tracks are gathered into the final span, their union (bracket,
// panel). The bracket is drawn per row so its arms meet each row's center.
// One row of the bracket: the stroke across from the track, and the halves of the upright above and below its
// center. Every stroke carries the tracks that pass through it on their way to the bracket's middle, where the
// line to the final span leaves: solid when at least one of them holds a span, dashed when none does.
function bracketArm(region, i) {
  const voted = setup.adapters.map(name => region.voters.includes(name))
  const middle = (voted.length - 1) / 2
  const any = (from, to) => voted.slice(from, to).some(Boolean)
  const arm = el('div', 'arm')
  const stroke = (name, solid) => arm.append(el('span', `${name}${solid ? '' : ' dashed'}`))
  stroke('across', voted[i])
  if (i > 0) stroke('up', i <= middle ? any(0, i) : any(i))
  if (i < voted.length - 1) stroke('down', i >= middle ? any(i + 1) : any(0, i + 1))
  return arm
}

function flow(item, region, index) {
  const wrap = el('div', 'flow')
  wrap.dataset.region = index
  const head = el('div', 'flow-head')
  head.append(el('span', 'value', clip(item.text.slice(region.start, region.end), 40)))
  const active = setup.adapters.length
  const frame = trackWindow(item.text, region)
  const grid = el('div', `flow-grid ${region.masked ? 'hit' : 'miss'}`)
  const span = `1 / ${active + 1}`
  const place = (node, column, row) => { node.style.gridColumn = column; node.style.gridRow = row; grid.append(node); return node }
  place(el('div', 'panel'), '4 / 7', span)
  place(el('div', 'trunk out'), '5', span)
  ;[...setup.adapters, ...setup.skipped].forEach((name, i) => {
    const row = String(i + 1)
    const skipped = i >= active
    const voted = region.voters.includes(name)
    const box = place(el('div', `module${skipped ? ' off' : voted ? ' yes' : ' no'}`), '2', row)
    const top = el('div', 'module-top')
    top.append(el('span', 'module-name', name), el('span', 'mark-icon', skipped ? '–' : voted ? '✓' : '✕'))
    box.append(top)
    const votes = region.votes.filter(v => v.adapter === name)
    if (skipped) box.append(el('div', 'module-rule', '설치 안 됨 · 제외'))
    else if (votes.length) {
      // One module may flag the same value with several rules: one row, all its spans on the track.
      const rule = el('div', 'module-rule', `${[...new Set(votes.map(v => v.type))].join(' / ')} · ${votes[0].rule}${votes.length > 1 ? ` 외 ${votes.length - 1}` : ''}${setup.voters.includes(name) ? '' : ' · 표 없음'}`)
      rule.title = votes.map(v => `${v.type} · ${v.rule}`).join('\n')
      box.append(rule)
    } else box.append(el('div', 'module-rule', '탐지 없음'))
    if (skipped) return
    const spans = place(track(item.text, frame, votes, 'found'), '4', row)
    if (!voted) spans.classList.add('idle')
    const parts = [box, place(el('div', `wire${voted ? ' yes' : ''}`), '3', row), spans, place(bracketArm(region, i), '5', row)]
    for (const node of parts) node.style.setProperty('--i', i)
  })
  const final = place(el('div', 'final'), '6', span)
  final.append(el('div', 'final-label', '최종 스팬 (합집합)'), track(item.text, frame, region.final, 'hit'))
  // Under the majority vote a region can fall short: say why nothing is masked, counting voting modules only.
  const counted = region.voters.filter(name => setup.voters.includes(name)).length
  final.append(el('div', 'decision', region.masked ? '가림' : `통과 · ${counted}/${setup.voters.length}개만 찾아 기준 미달`))
  wrap.append(head, grid)
  return wrap
}

function flowColumn(item) {
  const list = el('div', 'flows')
  const again = remasked(item)
  if (again.length) list.append(el('div', 'again-note', `↺ 앞에서 가린 값이 다시 나와 탐지 없이 같은 자리표시자로 가림 (${again.length}곳)`))
  if (!item.regions.length && !again.length) list.append(el('span', 'none', `모듈 ${setup.adapters.length}개 모두 탐지 없음 · 후보 없음`))
  item.regions.forEach((region, index) => list.append(flow(item, region, index)))
  return list
}

function outputColumn(item, ok) {
  const wrap = el('div')
  const box = el('pre', 'textbox')
  // Flatten the segments into one text with the placeholders as spans, so it is cut like the input.
  let text = ''
  const masks = []
  for (const segment of item.output || [item.text]) {
    if (typeof segment === 'string') { text += segment; continue }
    // start and end become offsets in this text; the region the placeholder came from keeps its input offsets.
    const region = segment.how === 'vote' ? item.regions.findIndex(r => r.start < segment.end && segment.start < r.end) : -1
    masks.push({ ...segment, region, start: text.length, end: text.length + segment.mask.length })
    text += segment.mask
  }
  excerpt(box, text, masks, span => {
    const chip = el('span', `placeholder${span.how === 'remask' ? ' remask' : ''}`, span.mask)
    if (span.region >= 0) chip.dataset.region = span.region
    chip.title = span.how === 'remask'
      ? `앞에서 가린 값이 다시 나와 같은 자리표시자로 가림 (원래 값: ${span.raw})`
      : `원래 값: ${span.raw}`
    return chip
  })
  wrap.append(box)
  if (!ok) wrap.append(el('div', 'fail', `탐지기 오류${item.errors.length ? ` (${item.errors.join(', ')})` : ''}: Mod가 이 단계를 가리지 못합니다`))
  return wrap
}

function column(label, child, className) {
  const col = el('div', `col ${className}`)
  col.dataset.label = label
  col.append(child)
  return col
}

const SVG = 'http://www.w3.org/2000/svg'

// The same text goes from the input box to every module of each region: one stem per region leaves the box at
// the height of the region's mark (clamped to the visible part when the box is scrolled) and splits into a curve
// per module just before the modules. The verdict then goes on as an arrow from the panel to the region's
// placeholder in the forwarded text. Drawn from the laid-out positions, so it is redrawn on scroll and resize.
function drawLinks(lane, entering = false) {
  if (!lane) return
  lane.querySelector(':scope > svg.links')?.remove()
  const box = lane.querySelector('.col.input .textbox')
  const flows = lane.querySelectorAll('.flow')
  if (!box || !flows.length) return
  const base = lane.getBoundingClientRect()
  const from = box.getBoundingClientRect()
  const svg = document.createElementNS(SVG, 'svg')
  svg.classList.add('links')
  // Only the first drawing grows out of the box; redraws on scroll or resize appear at once.
  if (entering) svg.classList.add('enter')
  const curve = (x0, y0, x1, y1) => {
    const pull = (x1 - x0) * 0.6
    const path = document.createElementNS(SVG, 'path')
    path.setAttribute('d', `M${x0},${y0} C${x0 + pull},${y0} ${x1 - pull},${y1} ${x1},${y1}`)
    path.setAttribute('pathLength', '1')
    svg.append(path)
    return path
  }
  for (const flow of flows) {
    const modules = [...flow.querySelectorAll('.module:not(.off)')].map(module => module.getBoundingClientRect())
    if (!modules.length) continue
    const mark = box.querySelector(`mark[data-region="${flow.dataset.region}"]`)?.getBoundingClientRect()
    const y = mark ? mark.top + mark.height / 2 : from.top + 20
    const x0 = from.right - base.left
    const y0 = Math.min(Math.max(y, from.top + 12), from.bottom - 12) - base.top
    const x1 = modules[0].left - base.left
    if (x1 - x0 < 16) continue  // stacked layout on narrow screens: nothing to join
    // The split point: a third of the way over, level with the middle of the region's modules.
    const hub = [x0 + (x1 - x0) * 0.35, (modules[0].top + modules.at(-1).bottom) / 2 - base.top]
    curve(x0, y0, ...hub)
    for (const to of modules) curve(...hub, x1, to.top + to.height / 2 - base.top).classList.add('branch')
    const panel = flow.querySelector('.panel').getBoundingClientRect()
    const out = lane.querySelector('.col.output .textbox')?.getBoundingClientRect()
    if (!out || out.left - panel.right < 12) continue
    const kind = flow.querySelector('.flow-grid.hit') ? 'hit' : 'miss'
    const chip = lane.querySelector(`.col.output [data-region="${flow.dataset.region}"]`)?.getBoundingClientRect()
    const x2 = panel.right - base.left
    const x3 = out.left - base.left - 6
    const target = chip ? chip.top + chip.height / 2 : panel.top + panel.height / 2
    const top = Math.max(panel.top, out.top) + 14
    const bottom = Math.min(panel.bottom, out.bottom) - 14
    let y2, y3
    if (top <= bottom) {
      // Side by side: a straight arrow, at the placeholder's line when it is within reach.
      y2 = y3 = Math.min(Math.max(target, top), bottom) - base.top
    } else {
      // The panel sits below the text box: leave from the panel's nearest point and rise into the box.
      y2 = (panel.top > out.bottom ? panel.top + 16 : panel.bottom - 16) - base.top
      y3 = Math.min(Math.max(target, out.top + 12), out.bottom - 12) - base.top
    }
    const arrow = document.createElementNS(SVG, 'path')
    const pull = (x3 - x2) * 0.9
    arrow.setAttribute('d', y2 === y3 ? `M${x2},${y2} H${x3}` : `M${x2},${y2} C${x2 + pull},${y2} ${x3 - pull},${y3} ${x3},${y3}`)
    arrow.setAttribute('pathLength', '1')
    arrow.classList.add('out', kind)
    svg.append(arrow)
    const tip = document.createElementNS(SVG, 'path')
    tip.setAttribute('d', `M${x3 - 6},${y3 - 4} L${x3},${y3} L${x3 - 6},${y3 + 4}`)
    tip.classList.add('tip', kind)
    svg.append(tip)
  }
  lane.append(svg)
}

function lane(item, ok) {
  const row = el('div', 'lane')
  row.append(
    column('들어온 입력', inputColumn(item), 'input'),
    column('탐지 모듈 → 스팬 합집합', flowColumn(item), 'ensemble'),
    column('모델로 보내는 텍스트', outputColumn(item, ok), 'output'),
  )
  return row
}

// ---- events ----

function interesting(item) {
  return (item.regions.length > 0 || item.output !== null || item.errors.length > 0) && !item.repeat_of
}

// Rows the server matched to an earlier row: the same text, masked with the same placeholders (see Tap.repeat_of).
function repeatNote(items) {
  const when = [...new Set(items.map(item => seen.has(item.repeat_of) ? clock(seen.get(item.repeat_of)) : '앞'))]
  return `${when.join(', ')}에 보인 내용을 한 번 더 검사 · 같은 자리표시자로 가림${items.length > 1 ? ` (${items.length}개)` : ''}`
}

function render(event) {
  const card = el('article', 'event')
  const head = el('div', 'event-head')
  head.append(channelChip(event.source), el('span', 'time', clock(event.time)))
  const flagged = event.items.filter(interesting)
  const repeats = event.items.filter(item => item.repeat_of)
  const always = ALWAYS_SHOWN.has(event.source)
  if (flagged.length || !event.ok || always) {
    card.append(head)
    const shown = always || !event.ok ? event.items : flagged
    for (const item of shown) card.append(lane(item, event.ok))
    const folded = repeats.filter(item => !shown.includes(item))
    if (folded.length) card.append(el('div', 'pass', repeatNote(folded)))
    const rest = event.items.length - shown.length - folded.length
    if (rest) card.append(el('div', 'pass', `탐지 없는 텍스트 ${rest}개는 그대로 함께 전송`))
    return card
  }
  // Nothing new: one line, hidden unless the toggle is on.
  card.classList.add('quiet')
  const row = el('div', 'lane')
  const first = el('div', 'col')
  first.append(head, el('div', 'preview', (repeats.length ? repeats : event.items).map(item => item.text).join(' ⏎ ')))
  const nothing = el('div', 'col')
  nothing.append(el('span', 'none', repeats.length ? repeatNote(repeats) : `모듈 ${setup.adapters.length}개 모두 탐지 없음 · 후보 없음`))
  const pass = el('div', 'col')
  pass.append(el('span', 'pass', repeats.length ? '→ 같은 자리표시자로 전송' : '→ 그대로 전송'))
  row.append(first, nothing, pass)
  card.append(row)
  quiet += 1
  quietCount.textContent = quiet.toLocaleString()
  return card
}

function scrollToFirstMark(card) {
  for (const box of card.querySelectorAll('.textbox')) {
    const target = box.querySelector('mark, .placeholder')
    if (target && box.scrollHeight > box.clientHeight) box.scrollTop = Math.max(0, target.offsetTop - 24)
  }
}

function add(event) {
  if (event.seq <= lastSeq) return
  lastSeq = event.seq
  seen.set(event.seq, event.time)
  if (seen.size > KEEP) seen.delete(seen.keys().next().value)
  const card = render(event)
  if (live && !card.classList.contains('quiet')) card.classList.add('fresh')
  empty.remove()
  feed.prepend(card)
  scrollToFirstMark(card)
  for (const row of card.querySelectorAll('.lane')) drawLinks(row, live)
  // Done arriving: a later redraw (scroll, resize) must not replay the entrance.
  if (live) setTimeout(() => card.classList.remove('fresh'), 3000)
  while (feed.childElementCount > KEEP) feed.lastElementChild.remove()
}

function clear() {
  feed.replaceChildren(empty)
  quiet = 0
  quietCount.textContent = '0'
}

function setStatus(state, text) {
  status.className = `status ${state}`
  statusText.textContent = text
}

function connect() {
  const source = new EventSource('events')
  source.addEventListener('setup', message => {
    const info = JSON.parse(message.data)
    if (setup && setup.boot !== info.boot) { clear(); lastSeq = 0; seen.clear() }
    setup = info
    live = false
    document.getElementById('rule').textContent = consensusText(info)
    setStatus('live', '연결됨')
  })
  source.addEventListener('scan', message => add(JSON.parse(message.data)))
  source.addEventListener('live', () => { live = true })
  source.onerror = () => setStatus('down', '연결 끊김 · 다시 시도 중')
}

let resizing = 0
window.addEventListener('resize', () => {
  cancelAnimationFrame(resizing)
  resizing = requestAnimationFrame(() => { for (const row of feed.querySelectorAll('.lane')) drawLinks(row) })
})
quietToggle.addEventListener('change', () => document.body.classList.toggle('show-quiet', quietToggle.checked))
document.getElementById('clear').addEventListener('click', clear)
connect()
