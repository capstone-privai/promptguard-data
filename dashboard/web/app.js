"use strict";

/* PromptGuard evaluation dashboard.
 * Loads data/index.json (commits and their results), then for the shown commit
 * data/results/detection/<key>/summary.json (count cells: dataset × sub-group × channel × type),
 * examples on demand, and data/results/latency/<key>/latency.json. Every metric shown is computed here from
 * the count cells, so any filter combination gives exact numbers. Text from the data only ever enters the page
 * through textContent. */

// ------------------------------------------------------------------ helpers

const $ = (selector, root = document) => root.querySelector(selector);
const SVG_NS = "http://www.w3.org/2000/svg";

function add(node, ...children) {
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function h(tag, props, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value == null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "style") node.style.cssText = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  return add(node, children);
}

function s(tag, attrs, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value == null) continue;
    if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  return add(node, children);
}

function clear(node) {
  node.replaceChildren();
  return node;
}

const pct = (value) => (value == null ? "—" : (value * 100).toFixed(1));
const int = (value) => (value == null ? "—" : Number(value).toLocaleString("ko-KR"));

function ms(value) {
  if (value == null) return "—";
  if (value >= 100) return Math.round(value).toLocaleString("ko-KR");
  if (value >= 10) return value.toFixed(0);
  if (value >= 1) return value.toFixed(1);
  return value.toFixed(2);
}

function pctValue(value) {
  return h("span", null, pct(value), value == null ? null : h("span", { class: "unit" }, "%"));
}

function msValue(value) {
  return h("span", null, ms(value), value == null ? null : h("span", { class: "unit" }, "ms"));
}

function dateLabel(iso) {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : `${date.getMonth() + 1}월 ${date.getDate()}일`;
}

function dateTimeLabel(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("ko-KR", { month: "long", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function duration(seconds) {
  if (seconds == null) return "";
  const minutes = Math.floor(seconds / 60);
  return minutes ? `${minutes}분 ${Math.round(seconds % 60)}초` : `${Math.round(seconds)}초`;
}

function sizeLabel(chars) {
  if (chars >= 1024 && chars % 1024 === 0) return `${chars / 1024}K`;
  return String(chars);
}

function hash32(text) {
  let value = 0x811c9dc5;
  for (let index = 0; index < text.length; index++) {
    value ^= text.charCodeAt(index);
    value = Math.imul(value, 0x01000193) >>> 0;
  }
  return value;
}

async function getJSON(url) {
  const response = await fetch(url, { cache: "no-cache" });
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  return response.json();
}

// ------------------------------------------------------------------ vocabulary

const METRICS = [
  { key: "precision", label: "Precision", short: "P", cls: "p", color: "var(--p)" },
  { key: "recall", label: "Recall", short: "R", cls: "r", color: "var(--r)" },
  { key: "f1", label: "F1", short: "F1", cls: "f1", color: "var(--f1)" },
];

const OUTCOMES = {
  exact: { label: "정확", cls: "st-exact", note: "비밀값만 정확히 가림" },
  over: { label: "넓게 가림", cls: "st-over", note: "비밀값은 다 가렸지만 앞뒤 텍스트까지 가림 (실패로 셈)" },
  partial: { label: "일부 노출", cls: "st-partial", note: "비밀값 일부만 가려 나머지가 노출됨" },
  missed: { label: "놓침", cls: "st-missed", note: "비밀값을 한 글자도 가리지 못함" },
  fp: { label: "과잉 마스킹", cls: "st-fp", note: "정답과 겹치지 않는 곳을 가림" },
  clean: { label: "정상 통과", cls: "st-clean", note: "정답도 없고 가린 곳도 없음" },
};
const GOLD_OUTCOMES = ["exact", "over", "partial", "missed"];
const TAB_ORDER = ["exact", "over", "partial", "missed", "fp", "clean"];
const DEFAULT_TAB_ORDER = ["missed", "partial", "over", "fp", "exact", "clean"];
const EDIT_NOTES = { tp: "정답 안쪽을 가림", wide: "정답보다 넓게 가림", fp: "정답과 겹치지 않는 곳을 가림 (과잉 마스킹)" };
const AXES = [
  { key: "dataset", label: "데이터셋" },
  { key: "type", label: "유형" },
  { key: "channel", label: "채널" },
  { key: "group", label: "하위 분류" },
];
const PAGE = 6;

// ------------------------------------------------------------------ state

const state = {
  index: null,
  status: null,
  statusPolling: true,
  sha: null, // commit chosen by the reader; null follows the newest commit
  detection: null, // { commit, key, stale, fallbackFrom }
  summary: null,
  latencyPick: null,
  latency: null,
  examples: new Map(), // `${key}/${stem}` → Promise<examples>
  filters: { d: null, t: null, c: null, g: null },
  outcome: null,
  by: "dataset",
  sort: null, // { column, direction }
  shown: PAGE,
  trendDataset: "",
  trendTable: false,
  kpiOpen: null,
  tileOpen: null,
  openExamples: new Set(),
  taskKey: null, // batch chosen by the reader; null follows the selected commit
  taskPick: null,
  task: null,
  taskLoaded: null,
  taskOpen: null,
  taskFailuresOpen: false,
};

function readHash() {
  const params = new URLSearchParams(location.hash.slice(1));
  state.sha = params.get("c");
  state.filters = { d: params.get("d"), t: params.get("t"), c: params.get("ch"), g: params.get("g") };
  state.outcome = params.get("o");
  state.by = AXES.some((axis) => axis.key === params.get("by")) ? params.get("by") : "dataset";
  state.trendDataset = params.get("td") || "";
}

function writeHash() {
  const params = new URLSearchParams();
  if (state.sha) params.set("c", state.sha.slice(0, 12));
  const { d, t, c, g } = state.filters;
  if (d) params.set("d", d);
  if (t) params.set("t", t);
  if (c) params.set("ch", c);
  if (g) params.set("g", g);
  if (state.outcome) params.set("o", state.outcome);
  if (state.by !== "dataset") params.set("by", state.by);
  if (state.trendDataset) params.set("td", state.trendDataset);
  const text = params.toString();
  history.replaceState(null, "", text ? `#${text}` : location.pathname + location.search);
}

// ------------------------------------------------------------------ index and picks

const commits = () => (state.index ? state.index.commits : []);
const tracks = () => (state.index ? state.index.tracks || [] : []);

function selectedCommit() {
  const list = commits();
  if (!list.length) return null;
  if (state.sha) {
    const found = list.find((commit) => commit.sha.startsWith(state.sha));
    if (found) return found;
  }
  return list[list.length - 1];
}

function isLatest(commit) {
  return commit && state.index && commit.sha === state.index.latest;
}

/** The result to show for the selected commit: its own, the same detector's under an older benchmark, or the
 * newest earlier commit's. */
function pick(track) {
  const list = commits();
  const target = selectedCommit();
  if (!target || !target[track]) return { commit: target, key: null, record: target && target[track] };
  const record = target[track];
  if (record.state === "done") return { commit: target, key: record.key, record };
  if (record.stale) return { commit: target, key: record.stale.key, record, stale: true };
  for (let index = list.indexOf(target) - 1; index >= 0; index--) {
    const earlier = list[index][track];
    if (earlier && earlier.state === "done") {
      return { commit: list[index], key: earlier.key, record: earlier, fallbackFrom: target };
    }
  }
  return { commit: target, key: null, record };
}

function doneCommits(track) {
  return commits().filter((commit) => commit[track] && commit[track].state === "done");
}

function previousDistinct(track, commit, key) {
  const list = commits();
  for (let index = list.findIndex((item) => item.sha === commit.sha) - 1; index >= 0; index--) {
    const record = list[index][track];
    if (record && record.state === "done" && record.key !== key) return { commit: list[index], record };
  }
  return null;
}

// ------------------------------------------------------------------ count cells

function filterIndices(filters = state.filters) {
  const summary = state.summary;
  const d = filters.d == null ? null : summary.datasets.findIndex((item) => item.key === filters.d);
  const g = d == null || d < 0 || filters.g == null ? null : summary.datasets[d].groups.indexOf(filters.g);
  const c = filters.c == null ? null : summary.channels.findIndex((item) => item.key === filters.c);
  const t = filters.t == null ? null : summary.types.findIndex((item) => item.key === filters.t);
  return { d, g, c, t };
}

function sumCells(f) {
  const out = [0, 0, 0, 0, 0, 0, 0];
  for (const row of state.summary.cells) {
    if ((f.d == null || row[0] === f.d) && (f.g == null || row[1] === f.g) && (f.c == null || row[2] === f.c)
        && (f.t == null || row[3] === f.t)) {
      for (let index = 0; index < 7; index++) out[index] += row[4 + index];
    }
  }
  return out;
}

function sumItems(f) {
  const out = [0, 0, 0];
  for (const row of state.summary.items) {
    if ((f.d == null || row[0] === f.d) && (f.g == null || row[1] === f.g) && (f.c == null || row[2] === f.c)) {
      for (let index = 0; index < 3; index++) out[index] += row[3 + index];
    }
  }
  return out; // items, clean items, lines
}

function prf(counts) {
  const gold = counts[0] + counts[1] + counts[2] + counts[3];
  const edits = counts[4] + counts[5] + counts[6];
  const recall = gold ? counts[0] / gold : null;
  const precision = edits ? counts[4] / edits : null;
  const f1 = precision == null || recall == null ? null
    : precision + recall === 0 ? 0 : (2 * precision * recall) / (precision + recall);
  return { precision, recall, f1, gold, edits, counts };
}

function validateFilters() {
  const summary = state.summary;
  const f = state.filters;
  if (f.d && !summary.datasets.some((item) => item.key === f.d)) f.d = null;
  if (!f.d) f.g = null;
  if (f.g && !summary.datasets.find((item) => item.key === f.d).groups.includes(f.g)) f.g = null;
  if (f.c && !summary.channels.some((item) => item.key === f.c)) f.c = null;
  if (f.t && !summary.types.some((item) => item.key === f.t)) f.t = null;
  if (state.by === "group" && !f.d) state.by = "dataset";
}

// ------------------------------------------------------------------ chart

/** A line chart on one y axis: a crosshair snaps to the nearest x, the tooltip lists every series there. */
function lineChart(container, options) {
  const { labels, series, height = 210, yFormat, tooltip, onSelect, selected, xPositions, band, endLabels } = options;
  const width = Math.max(240, container.clientWidth || 480);
  const margin = { top: 12, right: endLabels ? 58 : 14, bottom: 26, left: 40 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;
  const count = labels.length;
  const positions = xPositions || labels.map((_label, index) => index);
  const xMin = Math.min(...positions);
  const xMax = Math.max(...positions);
  const x = (index) => margin.left + (xMax === xMin ? plotWidth / 2 : ((positions[index] - xMin) / (xMax - xMin)) * plotWidth);
  const values = series.flatMap((line) => line.values).concat(band ? band.high : []).filter((value) => value != null);
  let [low, high] = options.domain ? options.domain(values) : [0, Math.max(1, ...values)];
  if (high <= low) high = low + 1;
  const y = (value) => margin.top + plotHeight - ((value - low) / (high - low)) * plotHeight;
  const svg = s("svg", { viewBox: `0 0 ${width} ${height}`, height, role: "img", "aria-label": options.label || "" });

  for (const tick of options.ticks ? options.ticks(low, high) : niceTicks(low, high)) {
    svg.append(s("line", { class: "grid", x1: margin.left, x2: width - margin.right, y1: y(tick), y2: y(tick) }));
    svg.append(s("text", { x: margin.left - 8, y: y(tick) + 4, "text-anchor": "end" }, yFormat(tick)));
  }
  if (selected != null && count > 1) {
    const step = plotWidth / Math.max(1, count - 1);
    svg.append(s("rect", { class: "selected", x: x(selected) - step / 2, y: margin.top, width: step, height: plotHeight, rx: 6 }));
  }
  const every = Math.max(1, Math.ceil(count / Math.max(1, Math.floor(plotWidth / 64))));
  labels.forEach((label, index) => {
    // the last label always shows, so a regular one too close to it gives way
    if (index !== count - 1 && (index % every || x(count - 1) - x(index) < 56)) return;
    svg.append(s("text", { x: x(index), y: height - 6, "text-anchor": "middle" }, label));
  });
  svg.append(s("line", { class: "axis", x1: margin.left, x2: width - margin.right, y1: margin.top + plotHeight, y2: margin.top + plotHeight }));

  if (band) {
    const top = band.high.map((value, index) => `${x(index)},${y(value ?? band.low[index])}`);
    const bottom = band.low.map((value, index) => `${x(index)},${y(value)}`).reverse();
    svg.append(s("polygon", { class: "band", points: top.concat(bottom).join(" "), fill: band.color }));
  }
  for (const line of series) {
    const points = line.values.map((value, index) => (value == null ? null : [x(index), y(value)]));
    let path = "";
    points.forEach((point, index) => {
      if (!point) return;
      path += `${path && points[index - 1] ? "L" : "M"}${point[0].toFixed(1)},${point[1].toFixed(1)}`;
    });
    if (count > 1) svg.append(s("path", { class: "line", d: path, stroke: line.color }));
    points.forEach((point) => point && svg.append(s("circle", { class: "marker", cx: point[0], cy: point[1], r: 4, fill: line.color })));
  }
  if (endLabels) {
    const last = count - 1;
    const placed = series
      .map((line) => ({ line, value: line.values[last] }))
      .filter((item) => item.value != null)
      .map((item) => ({ ...item, at: y(item.value), want: y(item.value) }))
      .sort((a, b) => a.at - b.at);
    for (let index = 1; index < placed.length; index++) {
      placed[index].at = Math.max(placed[index].at, placed[index - 1].at + 13);
    }
    for (const item of placed) {
      if (Math.abs(item.at - item.want) > 1) {
        svg.append(s("line", { class: "cross", x1: x(last) + 6, y1: item.want, x2: x(last) + 12, y2: item.at }));
      }
      svg.append(s("text", { class: "end-label", x: x(last) + 14, y: item.at + 4 }, `${item.line.short} ${endLabels(item.value)}`));
    }
  }

  const cross = s("line", { class: "cross", y1: margin.top, y2: margin.top + plotHeight, visibility: "hidden" });
  svg.append(cross);
  const tip = h("div", { class: "tooltip", hidden: true });
  let current = null;
  const show = (index) => {
    current = index;
    cross.setAttribute("x1", x(index));
    cross.setAttribute("x2", x(index));
    cross.setAttribute("visibility", "visible");
    clear(tip);
    add(tip, tooltip(index));
    tip.hidden = false;
    const left = x(index) + 12;
    tip.style.left = `${Math.min(left, width - tip.offsetWidth - 4)}px`;
    if (left + tip.offsetWidth > width) tip.style.left = `${Math.max(0, x(index) - tip.offsetWidth - 12)}px`;
    tip.style.top = `${margin.top}px`;
  };
  const hide = () => {
    current = null;
    cross.setAttribute("visibility", "hidden");
    tip.hidden = true;
  };
  const nearest = (event) => {
    const box = svg.getBoundingClientRect();
    const px = ((event.clientX - box.left) / box.width) * width;
    let best = 0;
    for (let index = 1; index < count; index++) if (Math.abs(x(index) - px) < Math.abs(x(best) - px)) best = index;
    return best;
  };
  svg.append(s("rect", {
    x: margin.left - 12, y: 0, width: plotWidth + 24, height, fill: "transparent",
    style: onSelect ? "cursor:pointer" : null,
    onpointermove: (event) => show(nearest(event)),
    onpointerleave: hide,
    onclick: (event) => onSelect && onSelect(nearest(event)),
  }));
  svg.setAttribute("tabindex", "0");
  svg.addEventListener("keydown", (event) => {
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      const start = current == null ? (selected ?? count - 1) : current;
      show(Math.max(0, Math.min(count - 1, start + (event.key === "ArrowRight" ? 1 : -1))));
    } else if (event.key === "Enter" && current != null && onSelect) {
      onSelect(current);
    } else if (event.key === "Escape") {
      hide();
    }
  });
  svg.addEventListener("blur", hide);
  clear(container);
  container.append(svg, tip);
}

function niceTicks(low, high) {
  const span = high - low;
  const raw = span / 4;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((factor) => factor * power).find((candidate) => candidate >= raw) || raw;
  const ticks = [];
  for (let tick = Math.ceil(low / step) * step; tick <= high + 1e-9; tick += step) ticks.push(Number(tick.toFixed(10)));
  return ticks;
}

/** A 0–100% window around the values, at least 20 points tall, in steps of 10. */
function percentDomain(values) {
  if (!values.length) return [0, 1];
  let low = Math.max(0, Math.floor((Math.min(...values) * 100 - 5) / 10) * 10);
  let high = Math.min(100, Math.ceil((Math.max(...values) * 100 + 5) / 10) * 10);
  if (high - low < 20) {
    high = Math.min(100, low + 20);
    low = Math.max(0, high - 20);
  }
  return [low / 100, high / 100];
}

function sparkline(values, currentIndex, color) {
  const node = h("span", { class: "spark-wrap" });
  node.dataset.values = JSON.stringify(values);
  node.dataset.current = String(currentIndex);
  node.dataset.color = color;
  return node;
}

function drawSparklines(root = document) {
  for (const node of root.querySelectorAll(".spark-wrap")) {
    const values = JSON.parse(node.dataset.values);
    const current = Number(node.dataset.current);
    const width = Math.max(60, node.clientWidth || node.parentElement.clientWidth - 28);
    const height = 30;
    const present = values.filter((value) => value != null);
    clear(node);
    if (present.length < 2) continue;
    const low = Math.min(...present);
    const high = Math.max(...present);
    const x = (index) => 4 + (index / (values.length - 1)) * (width - 8);
    const y = (value) => (high === low ? height / 2 : 4 + (1 - (value - low) / (high - low)) * (height - 8));
    let path = "";
    values.forEach((value, index) => {
      if (value != null) path += `${path ? "L" : "M"}${x(index).toFixed(1)},${y(value).toFixed(1)}`;
    });
    const svg = s("svg", { class: "spark", viewBox: `0 0 ${width} ${height}`, height, "aria-hidden": "true" },
      s("path", { d: path, fill: "none", stroke: "var(--axis)", "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
    if (values[current] != null) {
      svg.append(s("circle", { cx: x(current), cy: y(values[current]), r: 4, fill: node.dataset.color, stroke: "var(--surface-2)", "stroke-width": 2 }));
    }
    node.append(svg);
  }
}

// ------------------------------------------------------------------ header and status

function statusDot() {
  const status = state.status || (state.index && state.index.status) || {};
  if (status.state === "error") return "dot bad";
  if (status.state === "evaluating" || status.state === "syncing" || status.state === "starting") return "dot busy";
  const latest = commits().at(-1);
  if (latest && tracks().some((track) => latest[track] && latest[track].state === "failed")) return "dot bad";
  if (latest && tracks().some((track) => latest[track] && ["queued", "running"].includes(latest[track].state))) return "dot busy";
  return "dot";
}

function statusText() {
  const status = state.status || (state.index && state.index.status) || {};
  if (status.state === "evaluating") {
    const progress = status.progress && status.progress.total ? ` ${Math.floor((status.progress.done / status.progress.total) * 100)}%` : "";
    return `${status.message || "평가 중"}${progress}`;
  }
  if (status.state === "syncing") return status.message || "저장소를 받는 중";
  if (status.state === "error") return `서비스 오류: ${status.message || ""}`;
  if (status.state === "serve-only") return "평가는 돌리지 않고 결과만 보여 주는 중";
  return status.last_sync ? `최신 상태 · ${dateTimeLabel(status.last_sync)}에 확인` : "";
}

function renderChip() {
  const chip = $("#commit-chip");
  clear(chip);
  const commit = selectedCommit();
  if (!commit) {
    add(chip, h("span", { class: statusDot() }), h("span", { class: "soft" }, state.index ? "평가할 커밋이 없어요" : "결과 없음"));
    return;
  }
  const branch = state.index.repo.branch;
  add(chip,
    h("span", { class: statusDot() }),
    h("span", null, isLatest(commit) ? branch : "과거 커밋"),
    h("span", { class: "mono" }, commit.short),
    h("span", { class: "soft" }, dateLabel(commit.date)));
}

function openPopover(anchor, build) {
  closePopover();
  const card = h("div", { class: "popover", role: "dialog" });
  add(card, build(card));
  document.body.append(card);
  const box = anchor.getBoundingClientRect();
  const left = Math.min(window.scrollX + box.right - card.offsetWidth, window.scrollX + document.documentElement.clientWidth - card.offsetWidth - 16);
  card.style.left = `${Math.max(16, left)}px`;
  card.style.top = `${window.scrollY + box.bottom + 8}px`;
  anchor.setAttribute("aria-expanded", "true");
  const away = (event) => {
    if (!card.contains(event.target) && !anchor.contains(event.target)) closePopover();
  };
  const escape = (event) => event.key === "Escape" && closePopover();
  setTimeout(() => document.addEventListener("click", away), 0);
  document.addEventListener("keydown", escape);
  state.popover = { card, anchor, away, escape };
}

function closePopover() {
  const open = state.popover;
  if (!open) return;
  open.card.remove();
  open.anchor.setAttribute("aria-expanded", "false");
  document.removeEventListener("click", open.away);
  document.removeEventListener("keydown", open.escape);
  state.popover = null;
}

function commitPopover() {
  const commit = selectedCommit();
  const summary = state.summary;
  const web = state.index && state.index.repo.web;
  const rows = [];
  if (commit) {
    rows.push(["커밋", web ? h("a", { href: `${web}/commit/${commit.sha}`, target: "_blank", rel: "noopener" }, h("span", { class: "mono" }, commit.short)) : h("span", { class: "mono" }, commit.short)]);
    rows.push(["작성", `${commit.author} · ${dateTimeLabel(commit.date)}`]);
    rows.push(["탐지기 지문", h("span", { class: "mono" }, commit.fingerprint)]);
  }
  if (summary) {
    const detector = summary.system.detector || {};
    const adapters = (detector.adapters || []).map((adapter) => `${adapter.name} ${adapter.version}`).join(", ");
    rows.push(["앙상블", `${adapters || "—"} · ${detector.consensus || ""}`]);
    if ((detector.skipped || []).length) rows.push(["빠진 어댑터", detector.skipped.map((item) => `${item.name} (${item.reason})`).join(", ")]);
    rows.push(["탐지 평가", `${state.detection.commit.short} · ${dateTimeLabel(summary.evaluated_at)} · ${duration(summary.wall_seconds)}`]);
    rows.push(["데이터셋", `${summary.datasets.length}개 · 정답 ${int(summary.datasets.reduce((total, item) => total + item.gold, 0))}개`]);
    const failedOpen = summary.datasets.reduce((total, item) => total + item.failed_open, 0);
    if (failedOpen) rows.push(["fail-open", `${int(failedOpen)}개 item (탐지기 결과가 거부돼 원문 그대로 나감)`]);
    rows.push(["gitleaks", summary.benchmark.gitleaks || "없음 (평가 기기에 설치되지 않음)"]);
  }
  const failures = commit ? tracks().filter((track) => commit[track] && commit[track].state === "failed") : [];
  return [
    h("h3", null, commit ? commit.title : "PromptGuard"),
    h("dl", null, rows.map(([term, value]) => [h("dt", null, term), h("dd", null, value)])),
    failures.map((track) => h("div", { class: "note" }, `${track === "detection" ? "탐지 성능" : "탐지 지연"} 평가 실패: ${commit[track].error}`)),
    h("div", { class: "note" }, statusText() || "상태 정보 없음"),
    h("div", { class: "actions" },
      commit && !isLatest(commit) ? h("button", { class: "ghost", type: "button", onclick: () => { closePopover(); selectCommit(null); } }, "최신 커밋 보기") : null,
      failures.length && state.status && state.status.state !== "serve-only"
        ? h("button", { class: "ghost", type: "button", onclick: () => { closePopover(); fetch("api/refresh?retry=1", { method: "POST" }).then(pollStatus); } }, "실패한 평가 다시 돌리기")
        : null),
  ];
}

// ------------------------------------------------------------------ hero

function renderKpis() {
  const box = clear($("#kpis"));
  const more = clear($("#kpi-more"));
  const summary = state.summary;
  if (!summary) {
    box.append(h("div", { class: "empty", style: "grid-column: 1 / -1" }, emptyDetectionText()));
    return;
  }
  const totals = summary.totals;
  // A stale result was scored on an older benchmark; comparing it with this benchmark's numbers would mislead.
  const previous = state.detection.stale ? null : previousDistinct("detection", state.detection.commit, state.detection.key);
  const history = doneCommits("detection");
  const currentIndex = history.findIndex((commit) => commit.detection.key === state.detection.key && commit.sha === state.detection.commit.sha);
  for (const metric of METRICS) {
    const value = totals[metric.key];
    let delta = null;
    if (previous && previous.record.headline[metric.key] != null && value != null) {
      const change = (value - previous.record.headline[metric.key]) * 100;
      delta = Math.abs(change) < 0.05
        ? h("span", null, `${previous.commit.short} 대비 변화 없음`)
        : h("span", null, h("span", { class: change > 0 ? "up" : "down" }, `${change > 0 ? "▲" : "▼"} ${Math.abs(change).toFixed(1)}%p`), ` ${previous.commit.short} 대비`);
    }
    box.append(h("button", {
      class: "kpi", type: "button", "aria-expanded": String(state.kpiOpen === metric.key),
      onclick: () => { state.kpiOpen = state.kpiOpen === metric.key ? null : metric.key; renderKpis(); },
    },
    h("span", { class: "kpi-label" }, h("i", { class: `key ${metric.cls}` }), metric.label),
    h("span", { class: "kpi-value" }, pctValue(value)),
    h("span", { class: "delta" }, delta),
    sparkline(history.slice(-12).map((commit) => commit.detection.headline[metric.key]),
      currentIndex - Math.max(0, history.length - 12), metric.color)));
  }
  if (state.kpiOpen) more.append(kpiDetail(state.kpiOpen));
  requestAnimationFrame(() => drawSparklines(box));
}

function kpiDetail(key) {
  const counts = state.summary.totals.counts;
  const gold = counts.exact + counts.over + counts.partial + counts.missed;
  const edits = counts.edits_tp + counts.edits_over + counts.edits_fp;
  const definitions = {
    precision: [
      "시스템이 가린 곳 중 정답 비밀값 하나 안에 들어간 비율이에요.",
      [["정답 안을 가림", int(counts.edits_tp)], ["정답보다 넓게 가림", int(counts.edits_over)], ["정답 밖을 가림 (과잉 마스킹)", int(counts.edits_fp)], ["가린 곳 전체", int(edits)]],
    ],
    recall: [
      "정답 비밀값 중 정확히 그 부분만 가린 비율이에요. 앞뒤 텍스트까지 넓게 가리거나 일부만 가리면 실패로 셉니다.",
      [["정확", int(counts.exact)], ["넓게 가림", int(counts.over)], ["일부 노출", int(counts.partial)], ["놓침", int(counts.missed)], ["정답 전체", int(gold)]],
    ],
    f1: ["Precision과 Recall의 조화평균이에요: 2PR / (P + R).", []],
  };
  const [text, rows] = definitions[key];
  return h("div", { class: "more" },
    h("strong", null, METRICS.find((metric) => metric.key === key).label), " — ", text,
    rows.length ? h("dl", null, rows.map(([term, value]) => [h("dt", null, term), h("dd", null, value)])) : null,
    h("div", { style: "margin-top:8px" },
      `데이터셋 ${state.summary.datasets.length}개의 정답과 가린 곳을 모두 합쳐 계산해요. 채점 채널은 사용자 프롬프트, 지침, 도구 결과이고 에이전트가 쓴 명령(tool_input)은 채점하지 않아요. 유형은 맞히지 않아도 됩니다.`));
}

function emptyDetectionText() {
  const pickInfo = state.detection;
  const record = pickInfo && pickInfo.record;
  if (!state.index) return "아직 평가 결과가 없어요. 서비스가 첫 평가를 돌리고 있을 수 있어요.";
  if (record && record.state === "failed") return "이 커밋의 탐지 성능 평가가 실패했어요. 위 커밋 버튼에서 이유를 볼 수 있어요.";
  if (record && record.state === "running") return "이 커밋을 평가하는 중이에요.";
  return "아직 평가된 결과가 없어요.";
}

function renderHeroNote() {
  const box = clear($("#hero-note"));
  const pickInfo = state.detection;
  if (!pickInfo || !pickInfo.key) return;
  const parts = [];
  if (pickInfo.fallbackFrom) {
    const record = pickInfo.fallbackFrom.detection;
    const why = record.state === "failed" ? "평가가 실패해서" : record.state === "running" ? "평가 중이라" : "아직 평가 전이라";
    parts.push(`${pickInfo.fallbackFrom.short} 커밋은 ${why} ${pickInfo.commit.short} 커밋의 결과를 보여 주고 있어요.`);
  } else if (pickInfo.stale) {
    parts.push("데이터셋이나 채점기가 바뀌어 다시 평가하는 중이에요. 지금 숫자는 이전 기준이에요.");
  }
  const commit = selectedCommit();
  if (state.sha && commit && !isLatest(commit)) {
    parts.push(h("span", null, `과거 커밋(${commit.short})을 보고 있어요. `,
      h("button", { class: "link", type: "button", onclick: () => selectCommit(null) }, "최신으로")));
  }
  if (parts.length) box.append(h("div", { class: "note" }, parts));
}

function renderTrend() {
  const select = clear($("#trend-dataset"));
  const body = clear($("#trend-body"));
  const history = doneCommits("detection");
  const summary = state.summary;
  const datasetOptions = summary ? summary.datasets : [];
  select.append(h("option", { value: "" }, "전체 데이터셋"));
  for (const dataset of datasetOptions) select.append(h("option", { value: dataset.key }, dataset.label));
  if (state.trendDataset && !datasetOptions.some((item) => item.key === state.trendDataset)) state.trendDataset = "";
  select.value = state.trendDataset;
  $("#trend-table-toggle").setAttribute("aria-pressed", String(state.trendTable));
  if (!history.length) {
    body.append(h("div", { class: "empty" }, "평가된 커밋이 생기면 여기에 추이가 그려져요."));
    return;
  }
  const valueOf = (commit, key) => {
    const headline = commit.detection.headline;
    const source = state.trendDataset ? (headline.datasets || {})[state.trendDataset] : headline;
    return source ? source[key] : null;
  };
  const selected = history.findIndex((commit) => commit.sha === state.detection?.commit?.sha);
  body.append(h("div", { class: "legend" }, METRICS.map((metric) => h("span", null, h("i", { class: `key ${metric.cls}` }), metric.label))));
  if (state.trendTable) {
    body.append(h("table", { class: "plain" },
      h("thead", null, h("tr", null, h("th", null, "커밋"), h("th", null, "날짜"), METRICS.map((metric) => h("th", { class: "num" }, `${metric.short} %`)))),
      h("tbody", null, history.slice().reverse().map((commit) => h("tr", null,
        h("td", null, h("span", { style: "font-family:var(--mono)" }, commit.short), " ", h("span", { class: "muted" }, commit.title)),
        h("td", null, dateLabel(commit.date)),
        METRICS.map((metric) => h("td", { class: "num" }, pct(valueOf(commit, metric.key)))))))));
    return;
  }
  const chart = h("div", { class: "chart" });
  body.append(chart);
  if (history.length === 1) body.append(h("div", { class: "muted", style: "font-size:12px;margin-top:6px" }, "평가된 커밋이 하나뿐이에요."));
  lineChart(chart, {
    label: "커밋별 Precision, Recall, F1",
    labels: history.map((commit) => commit.short),
    series: METRICS.map((metric) => ({ ...metric, values: history.map((commit) => valueOf(commit, metric.key)) })),
    domain: percentDomain,
    yFormat: (value) => `${Math.round(value * 100)}%`,
    endLabels: (value) => pct(value),
    selected: selected >= 0 ? selected : null,
    tooltip: (index) => {
      const commit = history[index];
      return [
        h("div", { class: "t-title" }, h("span", { class: "mono" }, commit.short), ` · ${dateLabel(commit.date)}`, h("br"), commit.title),
        METRICS.map((metric) => h("div", { class: "t-row" }, h("i", { class: `key ${metric.cls}` }), h("b", null, `${pct(valueOf(commit, metric.key))}%`), h("span", null, metric.label))),
      ];
    },
    onSelect: (index) => selectCommit(history[index].sha),
  });
}

// ------------------------------------------------------------------ details

function selectField(label, value, options, onChange, extra = {}) {
  const select = h("select", { "aria-label": label, disabled: extra.disabled || null, onchange: (event) => onChange(event.target.value || null) },
    h("option", { value: "" }, extra.allLabel || "전체"),
    options.map((option) => h("option", { value: option.value }, option.label)));
  select.value = value || "";
  return h("div", { class: "field" }, h("span", null, label),
    h("span", { class: `select${extra.info ? " with-info" : ""}` }, select, extra.info || null));
}

function setFilter(key, value) {
  state.filters[key] = value;
  if (key === "d") state.filters.g = null;
  if (key === "d" && !value && state.by === "group") state.by = "dataset";
  if (value && AXIS_FILTER[state.by] === key) state.by = nextAxis(state.by); // the table would show one row
  state.sort = null;
  state.shown = PAGE;
  state.openExamples.clear();
  writeHash();
  renderDetails();
}

/** The first axis not pinned by a filter, after drilling into `axis`. */
function nextAxis(axis) {
  return ["dataset", "group", "type", "channel"].find((candidate) =>
    candidate !== axis && !state.filters[AXIS_FILTER[candidate]] && (candidate !== "group" || state.filters.d)) || axis;
}

function renderFilters() {
  const box = clear($("#filters"));
  const summary = state.summary;
  const dataset = summary.datasets.find((item) => item.key === state.filters.d);
  const info = dataset ? h("button", {
    class: "info", type: "button", "aria-label": `${dataset.label} 설명`, "aria-expanded": "false",
    onclick: (event) => openPopover(event.currentTarget, () => datasetInfo(dataset)),
  }, "i") : null;
  box.append(
    selectField("데이터셋", state.filters.d, summary.datasets.map((item) => ({ value: item.key, label: item.label })), (value) => setFilter("d", value), { info, allLabel: "전체 데이터셋" }),
    selectField("비밀 유형", state.filters.t, summary.types.map((item) => ({ value: item.key, label: item.label })), (value) => setFilter("t", value), { allLabel: "전체 유형" }),
    selectField("채널", state.filters.c, summary.channels.map((item) => ({ value: item.key, label: item.label })), (value) => setFilter("c", value), { allLabel: "전체 채널" }),
    selectField(dataset ? dataset.group_label : "하위 분류", state.filters.g, dataset ? dataset.groups.map((group) => ({ value: group, label: group })) : [], (value) => setFilter("g", value), { disabled: !dataset, allLabel: dataset ? "전체" : "데이터셋을 고르면 열려요" }),
  );
  $("#reset").hidden = !Object.values(state.filters).some(Boolean);
}

function datasetInfo(dataset) {
  return [
    h("h3", null, dataset.label),
    dataset.about ? h("div", null, dataset.about) : null,
    h("dl", null,
      h("dt", null, "세션 · item"), h("dd", null, `${int(dataset.sessions)} · ${int(dataset.items)}`),
      h("dt", null, "채점하는 정답"), h("dd", null, int(dataset.gold)),
      h("dt", null, "시스템이 가린 곳"), h("dd", null, int(dataset.edits)),
      h("dt", null, "채점 줄 수"), h("dd", null, int(dataset.lines)),
      dataset.failed_open ? [h("dt", null, "fail-open"), h("dd", null, `${int(dataset.failed_open)}개 item`)] : null,
      h("dt", null, "파일"), h("dd", { class: "mono" }, `${dataset.key}.jsonl · ${dataset.sessions_sha256.slice(0, 12)}`)),
  ];
}

function renderSlice() {
  const box = clear($("#slice"));
  const result = prf(sumCells(filterIndices()));
  for (const metric of METRICS) {
    box.append(h("div", { class: "slice-metric" },
      h("span", { class: "label" }, h("i", { class: `key ${metric.cls}` }), metric.label),
      h("span", { class: "value" }, pctValue(result[metric.key]))));
  }
  box.append(h("div", { class: "slice-counts" }, `정답 ${int(result.gold)} · 가린 곳 ${int(result.edits)}`));
}

function axisRows(axis) {
  const summary = state.summary;
  const base = filterIndices();
  const rows = [];
  const push = (key, label, override) => {
    const result = prf(sumCells({ ...base, ...override }));
    if (result.gold || result.edits) rows.push({ key, label, ...result });
  };
  if (axis === "dataset") summary.datasets.forEach((item, index) => push(item.key, item.label, { d: index, g: index === base.d ? base.g : null }));
  if (axis === "type") summary.types.forEach((item, index) => push(item.key, item.label, { t: index }));
  if (axis === "channel") summary.channels.forEach((item, index) => push(item.key, item.label, { c: index }));
  if (axis === "group" && base.d != null && base.d >= 0) summary.datasets[base.d].groups.forEach((group, index) => push(group, group, { g: index }));
  if (state.sort) {
    const { column, direction } = state.sort;
    rows.sort((a, b) => ((a[column] ?? -1) - (b[column] ?? -1)) * direction);
  }
  return rows;
}

const AXIS_FILTER = { dataset: "d", type: "t", channel: "c", group: "g" };

function drill(axis, key) {
  const filter = AXIS_FILTER[axis];
  const unset = state.filters[filter] === key;
  state.filters[filter] = unset ? null : key;
  if (filter === "d") state.filters.g = null;
  if (!unset) {
    state.by = nextAxis(axis);
  } else if (axis === "dataset" && state.by === "group") {
    state.by = "dataset";
  }
  state.sort = null;
  state.shown = PAGE;
  state.openExamples.clear();
  writeHash();
  renderDetails();
}

function renderBreakdown() {
  const box = clear($("#breakdown"));
  const summary = state.summary;
  const dataset = summary.datasets.find((item) => item.key === state.filters.d);
  const seg = h("div", { class: "seg", role: "group", "aria-label": "나눠 보기" }, AXES.map((axis) => h("button", {
    type: "button", "aria-pressed": String(state.by === axis.key), disabled: axis.key === "group" && !dataset ? true : null,
    title: axis.key === "group" && !dataset ? "데이터셋을 먼저 고르세요" : null,
    onclick: () => { state.by = axis.key; state.sort = null; writeHash(); renderBreakdown(); },
  }, axis.key === "group" && dataset ? dataset.group_label : axis.label)));
  box.append(h("div", { class: "section-title" }, h("span", null, "나눠 보기"), seg));
  const rows = axisRows(state.by);
  if (!rows.length) {
    box.append(h("div", { class: "empty" }, "이 조건에 맞는 정답도, 가린 곳도 없어요."));
    return;
  }
  const sortButton = (column, label) => {
    const active = state.sort && state.sort.column === column;
    return h("button", {
      type: "button",
      onclick: () => {
        state.sort = !active ? { column, direction: -1 } : state.sort.direction === -1 ? { column, direction: 1 } : null;
        renderBreakdown();
      },
    }, label, active ? h("span", { class: "sort" }, state.sort.direction === -1 ? "↓" : "↑") : null);
  };
  const filterKey = state.filters[AXIS_FILTER[state.by]];
  const axisLabel = state.by === "group" && dataset ? dataset.group_label : AXES.find((axis) => axis.key === state.by).label;
  box.append(h("table", { class: "bd-table" },
    h("thead", null, h("tr", null,
      h("th", { class: "name-col" }, axisLabel),
      METRICS.map((metric) => h("th", null, sortButton(metric.key, `${metric.label} %`))),
      h("th", { class: "num hide-sm gold-col" }, sortButton("gold", "정답")))),
    h("tbody", null, rows.map((row) => h("tr", {
      class: filterKey === row.key ? "on" : null, tabindex: "0",
      onclick: () => drill(state.by, row.key),
      onkeydown: (event) => (event.key === "Enter" || event.key === " ") && (event.preventDefault(), drill(state.by, row.key)),
    },
    h("td", { class: "name", title: row.label }, row.label),
    METRICS.map((metric) => h("td", null, h("div", { class: "mcell" },
      h("span", { class: `v${row[metric.key] == null ? " na" : ""}` }, pct(row[metric.key])),
      h("span", { class: `bar ${metric.cls}` }, row[metric.key] == null ? null : h("i", { style: `width:${(row[metric.key] * 100).toFixed(1)}%` }))))),
    h("td", { class: "num hide-sm" }, int(row.gold)))))));
}

function outcomeCounts() {
  const f = filterIndices();
  const counts = sumCells(f);
  const items = sumItems(f);
  return { exact: counts[0], over: counts[1], partial: counts[2], missed: counts[3], fp: counts[6], clean: f.t == null ? items[1] : 0 };
}

async function renderOutcomes() {
  const box = clear($("#outcomes"));
  const counts = outcomeCounts();
  const goldTotal = GOLD_OUTCOMES.reduce((total, key) => total + counts[key], 0);
  if (!state.outcome || !counts[state.outcome]) state.outcome = DEFAULT_TAB_ORDER.find((key) => counts[key]) || null;
  box.append(h("div", { class: "section-title" }, h("span", null, "판정과 예시")));
  if (goldTotal) {
    box.append(h("div", { class: "ob", role: "img", "aria-label": GOLD_OUTCOMES.map((key) => `${OUTCOMES[key].label} ${counts[key]}`).join(", ") },
      GOLD_OUTCOMES.filter((key) => counts[key]).map((key) => h("i", { class: OUTCOMES[key].cls, style: `flex:${counts[key]}`, title: `${OUTCOMES[key].label} ${int(counts[key])}` }))));
  }
  box.append(h("div", { class: "tabs", role: "tablist" }, TAB_ORDER.filter((key) => key !== "clean" || counts.clean).map((key) => h("button", {
    class: "tab", type: "button", role: "tab", "aria-selected": String(state.outcome === key), disabled: counts[key] ? null : true,
    onclick: () => { state.outcome = key; state.shown = PAGE; state.openExamples.clear(); writeHash(); renderOutcomes(); },
  }, h("span", { class: `sw ${OUTCOMES[key].cls}${key === "fp" ? " hollow" : ""}` }), OUTCOMES[key].label, h("b", null, int(counts[key]))))));
  box.append(h("div", { class: "hl-legend" },
    h("span", null, h("span", { class: "g" }, "정답 비밀값"), " 밑줄"),
    h("span", null, h("span", { class: "m" }, "시스템이 가린 곳"), " 배경")));
  const list = h("div", { class: "examples" });
  box.append(list);
  if (!state.outcome) {
    list.append(h("div", { class: "empty" }, "보여 줄 예시가 없어요."));
    return;
  }
  const outcome = state.outcome;
  const examples = await loadExamples();
  if (outcome !== state.outcome || !list.isConnected) return; // a newer render replaced this one
  const matched = examples.filter((example) => matches(example, outcome));
  if (!matched.length) {
    list.append(h("div", { class: "empty" }, "이 조건의 예시는 표본에 없어요."));
    return;
  }
  for (const example of matched.slice(0, state.shown)) list.append(exampleCard(example, outcome));
  if (matched.length > state.shown) {
    list.append(h("button", { class: "ghost more-btn", type: "button", onclick: () => { state.shown += PAGE; renderOutcomes(); } },
      `예시 더 보기 (${matched.length - state.shown})`));
  }
}

async function loadExamples() {
  const stem = state.filters.d || "_all";
  const cacheKey = `${state.detection.key}/${stem}`;
  if (!state.examples.has(cacheKey)) {
    state.examples.set(cacheKey, getJSON(`data/results/detection/${state.detection.key}/examples/${stem}.json`)
      .then((data) => {
        const list = data.examples.map((example) => ({ ...example, dataset: example.dataset || stem }));
        if (stem !== "_all") return list.sort((a, b) => hash32(a.id) - hash32(b.id));
        const byDataset = new Map();
        for (const example of list) byDataset.set(example.dataset, [...(byDataset.get(example.dataset) || []), example]);
        const queues = [...byDataset.values()].map((items) => items.sort((a, b) => hash32(a.id) - hash32(b.id)));
        const mixed = [];
        while (queues.some((queue) => queue.length)) for (const queue of queues) if (queue.length) mixed.push(queue.shift());
        return mixed;
      })
      .catch(() => []));
  }
  return state.examples.get(cacheKey);
}

function matches(example, outcome) {
  const { t, c, g } = state.filters;
  if (c && example.channel !== c) return false;
  if (g && example.group !== g) return false;
  if (outcome === "clean") return example.tags.includes("clean");
  return example.tags.some((tag) => tag.endsWith(`:${outcome}`) && (!t || tag.startsWith(`${t}:`)));
}

function typeLabel(key) {
  const found = state.summary.types.find((item) => item.key === key);
  return found ? found.label : key;
}

function datasetLabel(key) {
  const found = state.summary.datasets.find((item) => item.key === key);
  return found ? found.label : key;
}

function channelLabel(key) {
  const found = state.summary.channels.find((item) => item.key === key);
  return found ? found.label : key;
}

function exampleCard(example, outcome) {
  const t = state.filters.t;
  let kind = null;
  if (GOLD_OUTCOMES.includes(outcome)) kind = (example.gold.find((span) => span[3] === outcome && (!t || span[2] === t)) || [])[2];
  if (outcome === "fp") kind = (example.edits.find((edit) => edit[2] === "fp" && (!t || edit[3] === t)) || [])[3];
  const open = state.openExamples.has(example.id);
  const toggle = () => {
    if (state.openExamples.has(example.id)) state.openExamples.delete(example.id);
    else state.openExamples.add(example.id);
    card.replaceWith(exampleCard(example, outcome));
  };
  const before = example.offset > 0 ? h("span", { class: "cut" }, "…") : null;
  const after = example.offset + example.text.length < example.length ? h("span", { class: "cut" }, "…") : null;
  const card = h("article", { class: `ex${open ? "" : " collapsed"}` },
    h("button", { class: "ex-head", type: "button", "aria-expanded": String(open), onclick: toggle },
      h("span", { class: "badge" }, h("i", { class: OUTCOMES[outcome].cls }), OUTCOMES[outcome].label),
      kind ? h("span", { class: "ex-type" }, typeLabel(kind)) : null,
      h("span", { class: "ex-meta" }, [datasetLabel(example.dataset), channelLabel(example.channel), example.group !== "-" ? example.group : null].filter(Boolean).join(" · "))),
    h("pre", { onclick: open ? null : toggle }, before, highlighted(example.text, example.gold, example.edits), after));
  if (open) card.append(exampleDetail(example, before, after));
  return card;
}

function highlighted(text, gold, edits) {
  const cuts = new Set([0, text.length]);
  for (const span of gold) { cuts.add(span[0]); cuts.add(span[1]); }
  for (const edit of edits) { cuts.add(edit[0]); cuts.add(edit[1]); }
  const points = [...cuts].filter((point) => point >= 0 && point <= text.length).sort((a, b) => a - b);
  const fragment = document.createDocumentFragment();
  for (let index = 0; index < points.length - 1; index++) {
    const start = points[index];
    const end = points[index + 1];
    const inGold = gold.some((span) => span[0] <= start && end <= span[1]);
    const inEdit = edits.some((edit) => edit[0] <= start && end <= edit[1]);
    const piece = text.slice(start, end);
    if (!inGold && !inEdit) fragment.append(piece);
    else fragment.append(h("span", { class: [inGold ? "g" : "", inEdit ? "m" : ""].join(" ").trim() }, piece));
  }
  return fragment;
}

function maskedText(text, gold, edits) {
  const fragment = document.createDocumentFragment();
  const shifted = (start, end) => gold
    .filter((span) => span[1] > start && span[0] < end)
    .map((span) => [Math.max(span[0], start) - start, Math.min(span[1], end) - start]);
  let cursor = 0;
  for (const edit of [...edits].sort((a, b) => a[0] - b[0])) {
    if (edit[0] > cursor) fragment.append(highlighted(text.slice(cursor, edit[0]), shifted(cursor, edit[0]), []));
    fragment.append(h("span", { class: "ph" }, edit[4] || "[가림]"));
    cursor = Math.max(cursor, edit[1]);
  }
  fragment.append(highlighted(text.slice(cursor), shifted(cursor, text.length), []));
  return fragment;
}

function exampleDetail(example, before, after) {
  const notes = [];
  for (const span of example.gold) {
    notes.push(h("li", null, h("i", { class: OUTCOMES[span[3]].cls }),
      h("span", null, `정답 ${typeLabel(span[2])}: `, h("b", null, OUTCOMES[span[3]].label), ` — ${OUTCOMES[span[3]].note}`)));
  }
  for (const edit of example.edits) {
    if (edit[2] === "tp") continue;
    notes.push(h("li", null, h("i", { class: edit[2] === "fp" ? "st-fp" : "st-over" }),
      h("span", null, "가림 ", h("code", null, edit[4] || "[가림]"), ` — ${EDIT_NOTES[edit[2]]}`, edit[2] === "fp" ? ` (${typeLabel(edit[3])}로 셈)` : "")));
  }
  return h("div", { class: "ex-detail" },
    h("h4", null, "모델에 간 텍스트"),
    example.edits.length
      ? h("pre", null, before ? before.cloneNode(true) : null, maskedText(example.text, example.gold, example.edits), after ? after.cloneNode(true) : null)
      : h("p", { class: "muted", style: "margin:0 0 10px;font-size:12.5px" }, "이 부분은 가린 곳이 없어 위 원문 그대로 모델에 갔어요."),
    notes.length ? h("ul", { class: "ex-notes" }, notes) : null,
    h("div", { class: "ex-id" }, `${example.session} · item ${example.item} · ${example.offset.toLocaleString()}–${(example.offset + example.text.length).toLocaleString()}자 / ${example.length.toLocaleString()}자`));
}

function renderDetails() {
  const details = $("#details");
  if (!state.summary) {
    details.hidden = true;
    return;
  }
  details.hidden = false;
  validateFilters();
  renderFilters();
  renderSlice();
  renderBreakdown();
  renderOutcomes();
}

// ------------------------------------------------------------------ latency

function renderLatency() {
  const section = $("#latency");
  const body = clear($("#latency-body"));
  clear($("#latency-tools"));
  if (!state.index || !tracks().includes("latency")) {
    section.hidden = !state.index;
    body.append(h("div", { class: "empty" }, "이 서버는 탐지 지연을 재지 않도록 설정돼 있어요."));
    return;
  }
  section.hidden = false;
  const pickInfo = state.latencyPick;
  if (!pickInfo || !pickInfo.key || !state.latency) {
    const record = pickInfo && pickInfo.record;
    const text = record && record.state === "failed" ? `이 커밋의 지연 측정이 실패했어요: ${record.error}`
      : record && record.state === "running" ? "이 커밋의 지연을 재는 중이에요."
      : "아직 잰 결과가 없어요. 탐지 성능 평가가 끝나면 이어서 재요.";
    body.append(h("div", { class: "empty" }, text));
    return;
  }
  const data = state.latency;
  const ensemble = data.detectors.find((item) => item.label === "ensemble") || data.detectors[0];
  if (pickInfo.fallbackFrom || pickInfo.stale) {
    body.append(h("div", { class: "note", style: "margin:0 0 12px" }, pickInfo.stale
      ? "측정 환경이 바뀌어 다시 재는 중이에요. 지금 숫자는 이전 측정이에요."
      : `${pickInfo.fallbackFrom.short} 커밋은 아직 재지 않아서 ${pickInfo.commit.short} 커밋의 측정을 보여 주고 있어요.`));
  }
  const history = doneCommits("latency");
  const currentIndex = history.findIndex((commit) => commit.sha === pickInfo.commit.sha);
  const largestBatch = ensemble.batch_sweep[ensemble.batch_sweep.length - 1];
  const fit = ensemble.fit_items;
  const tiles = [
    { key: "single_1k", label: "텍스트 1개 · 1KB", value: ensemble.single_1k.p50, sub: `p95 ${ms(ensemble.single_1k.p95)}ms`,
      spark: history.slice(-12).map((commit) => commit.latency.headline.single_1k_p50),
      detail: "Native Mod처럼 텍스트 하나를 보낸 탐지기 호출 한 번의 시간(탐지기가 보고한 detector_ms)의 중앙값이에요. 합성 로그·코드 텍스트 1,024자, 비밀이 있는 것과 없는 것을 합쳐 셉니다." },
    { key: "single_64k", label: "텍스트 1개 · 64KB", value: ensemble.single_64k.p50, sub: `p95 ${ms(ensemble.single_64k.p95)}ms`,
      detail: "큰 도구 결과 하나(65,536자)를 보낸 호출의 중앙값이에요." },
    { key: "per_string", label: "문자열 1개 늘 때마다", value: fit ? fit.ms_per_string : null, plus: true,
      sub: largestBatch ? `${int(largestBatch.batch)}개면 ${ms(largestBatch.p50)}ms` : "",
      detail: `1,024자 텍스트를 1·4·16·64·256개 묶어 보낸 호출에 직선을 맞춘 기울기예요${fit ? `(${ms(fit.fixed_ms)}ms + ${ms(fit.ms_per_string)}ms × 문자열 수)` : ""}. Final Guard처럼 한 번에 여러 문자열을 보낼 때 늘어나는 시간입니다.` },
    { key: "timeouts", label: "5초 넘은 호출", count: ensemble.over_timeout, sub: `표본 ${int(ensemble.all.n)}개 중`,
      detail: `HTTP 왕복이 시스템의 탐지기 timeout(${int(data.timeout_ms)}ms)을 넘은 표본 수예요. 시스템은 fail-closed라 실제라면 그 호출의 텍스트가 막힙니다.` },
  ];
  if (ensemble.guard) {
    tiles.push({ key: "guard", label: "Guard 요청 1개 (p95)", value: ensemble.guard.p95, sub: `p50 ${ms(ensemble.guard.p50)}ms · 요청 ${int(ensemble.guard.requests)}개`,
      detail: "metric-task 요청 기록을 Final Guard가 보냈을 호출로 재생했을 때, 요청 하나에서 기다리는 탐지 시간이에요." });
  }
  const grid = h("div", { class: "tiles", style: tiles.length > 4 ? "grid-template-columns:repeat(auto-fit,minmax(150px,1fr))" : null });
  for (const tile of tiles) {
    grid.append(h("button", {
      class: "tile", type: "button", "aria-expanded": String(state.tileOpen === tile.key),
      onclick: () => { state.tileOpen = state.tileOpen === tile.key ? null : tile.key; renderLatency(); },
    },
    h("div", { class: "label" }, tile.label),
    h("div", { class: "value" }, tile.count != null ? int(tile.count) : [tile.plus && tile.value != null ? "+" : "", msValue(tile.value)]),
    h("div", { class: "sub" }, tile.sub),
    tile.spark ? sparkline(tile.spark, currentIndex - Math.max(0, history.length - 12), "var(--lat)") : null));
  }
  body.append(grid);
  const open = tiles.find((tile) => tile.key === state.tileOpen);
  if (open) {
    body.append(h("div", { class: "more" }, open.detail, h("dl", null,
      h("dt", null, "측정 기기"), h("dd", null, `${data.machine.platform} · CPU ${data.machine.cpu_count}개`),
      h("dt", null, "worker 시작"), h("dd", null, `${ms(ensemble.startup_ms)}ms · 첫 호출 ${ms(ensemble.cold && ensemble.cold.detector_ms)}ms`),
      h("dt", null, "HTTP 왕복 − 탐지"), h("dd", null, `중앙값 ${ms(ensemble.gap_p50)}ms`),
      h("dt", null, "반복"), h("dd", null, `호출마다 ${data.repeat}번, 백분위수는 nearest rank`),
      h("dt", null, "측정"), h("dd", null, `${pickInfo.commit.short} · ${dateTimeLabel(data.evaluated_at)}`))));
  }

  const charts = h("div", { class: "charts2" });
  const sizeChart = h("div", { class: "chart" });
  const batchChart = h("div", { class: "chart" });
  charts.append(h("div", null, h("div", { class: "mini-title" }, "텍스트 크기별 (텍스트 1개, 중앙값과 p95)"), sizeChart),
    h("div", null, h("div", { class: "mini-title" }, `한 번에 보낸 문자열 수별 (각 ${sizeLabel(data.batch_item_chars)}자)`), batchChart));
  body.append(charts);
  const sweepChart = (container, sweep, keyName, labelOf, unitLabel) => lineChart(container, {
    label: unitLabel,
    labels: sweep.map((point) => labelOf(point[keyName])),
    xPositions: sweep.map((point) => Math.log2(point[keyName])),
    series: [{ key: "p50", short: "p50", color: "var(--lat)", values: sweep.map((point) => point.p50) }],
    band: { low: sweep.map((point) => point.p50), high: sweep.map((point) => point.p95), color: "var(--lat)" },
    height: 170,
    domain: (values) => [0, Math.max(1, ...values) * 1.1],
    yFormat: (value) => (value === 0 ? "0" : ms(value)),
    tooltip: (index) => [
      h("div", { class: "t-title" }, unitLabel(sweep[index][keyName])),
      h("div", { class: "t-row" }, h("i", { class: "key lat" }), h("b", null, `${ms(sweep[index].p50)}ms`), h("span", null, "중앙값")),
      h("div", { class: "t-row" }, h("i", { class: "key", style: "background:var(--axis)" }), h("b", null, `${ms(sweep[index].p95)}ms`), h("span", null, "p95")),
    ],
  });
  state.drawLatencyCharts = () => {
    if (ensemble.size_sweep.length) sweepChart(sizeChart, ensemble.size_sweep, "size", sizeLabel, (size) => `텍스트 1개, ${int(size)}자`);
    if (ensemble.batch_sweep.length) sweepChart(batchChart, ensemble.batch_sweep, "batch", String, (batch) => `문자열 ${batch}개 × ${int(data.batch_item_chars)}자`);
  };

  if (data.detectors.length > 1) {
    const rows = data.detectors.map((item) => ({ label: item.label === "ensemble" ? "앙상블 (시스템)" : `${item.label} 단독`, value: item.single_1k.p50, strong: item.label === "ensemble" }));
    const max = Math.max(...rows.map((row) => row.value || 0), 0.001);
    body.append(h("div", { class: "mini-title", style: "margin-top:20px" }, "어댑터별 · 텍스트 1개 1KB 중앙값"),
      h("div", { class: "hbars", style: "margin-top:6px" }, rows.map((row) => h("div", { class: "hbar" },
        h("span", { class: `name${row.strong ? " strong" : ""}` }, row.label),
        h("span", { class: "bar lat" }, h("i", { style: `width:${Math.max(0.5, ((row.value || 0) / max) * 100).toFixed(1)}%` })),
        h("span", { class: "num" }, `${ms(row.value)}ms`)))));
  }
  requestAnimationFrame(() => {
    state.drawLatencyCharts();
    drawSparklines(body);
  });
}

// ------------------------------------------------------------------ metric-task

const CONDITION_LABELS = { none: "마스킹 없음", gold: "정답만 가림", promptguard: "PromptGuard" };

function taskBatches() {
  return state.index ? state.index.task_batches ?? null : null;
}

/** The batch run on the selected commit, the reader's choice, or else the newest batch of any commit. */
function pickTask() {
  const batches = taskBatches();
  if (!batches || !batches.length) return null;
  if (state.taskKey) {
    const chosen = batches.find((batch) => batch.key === state.taskKey);
    if (chosen) return { batch: chosen, chosen: true };
  }
  const commit = selectedCommit();
  const own = commit && commit.task ? batches.filter((batch) => commit.task.includes(batch.key)) : [];
  if (own.length) return { batch: own[own.length - 1], own: true };
  return { batch: batches[batches.length - 1], own: false };
}

function batchLabel(batch) {
  const commit = batch.commit;
  const short = commit ? commit.short : (batch.system_commit || "").slice(0, 7) || "커밋 모름";
  return `${batch.name} · ${short} · ${dateLabel(batch.started_at)}`;
}

function rateText(value) {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

function renderTask() {
  const section = $("#task");
  const batches = taskBatches();
  const tools = clear($("#task-tools"));
  const body = clear($("#task-body"));
  section.hidden = batches == null;
  if (batches == null) return;
  if (!batches.length) {
    body.append(h("div", { class: "empty" }, "아직 읽어 온 metric-task 실행이 없어요. ",
      h("button", { class: "link", type: "button", onclick: () => { state.taskOpen = state.taskOpen === "how" ? null : "how"; renderTask(); } }, "추가하는 법")));
    if (state.taskOpen === "how") body.append(taskHowTo());
    return;
  }
  const pickInfo = state.taskPick;
  const select = h("select", { "aria-label": "metric-task 배치", onchange: (event) => { state.taskKey = event.target.value || null; state.taskOpen = null; loadTask().then(renderTask); } },
    h("option", { value: "" }, "이 커밋 기준 (자동)"),
    batches.slice().reverse().map((batch) => h("option", { value: batch.key }, batchLabel(batch))));
  select.value = state.taskKey || "";
  tools.append(h("div", { class: "select" }, select));
  if (!pickInfo || !state.task) {
    body.append(h("div", { class: "empty" }, "배치를 불러오지 못했어요."));
    return;
  }
  const data = state.task;
  const batch = pickInfo.batch;
  const commit = selectedCommit();
  if (!pickInfo.own && !pickInfo.chosen) {
    body.append(h("div", { class: "note", style: "margin:0 0 12px" },
      `이 커밋${commit ? `(${commit.short})` : ""}으로 돌린 실행이 없어서 가장 최근 실행(${batchLabel(batch)})을 보여 주고 있어요. `,
      h("button", { class: "link", type: "button", "aria-expanded": String(state.taskOpen === "how"),
        onclick: () => { state.taskOpen = state.taskOpen === "how" ? null : "how"; renderTask(); } }, "실행을 추가하는 법")));
    if (state.taskOpen === "how") body.append(h("div", { style: "margin:0 0 12px" }, taskHowTo()));
  }
  const conditions = data.by_condition;
  const pg = conditions.promptguard || {};
  const context = (key, field) => data.conditions.filter((name) => name !== "promptguard" && conditions[name])
    .map((name) => `${CONDITION_LABELS[name] || name} ${rateText(conditions[name][field])}`).join(" · ");
  const tiles = [
    { key: "success", label: "과제 성공률 · PromptGuard", value: pg.success_rate, sub: context("success", "success_rate"),
      detail: "채점 기준을 모두 통과하고 비밀값도 망가뜨리지 않은 실행의 비율이에요. 마스킹 없음(none)은 탐지기가 아무것도 찾지 않는 조건, 정답만 가림(gold)은 과제에 심은 비밀만 정확히 가리는 이상적인 조건이에요. 셋 다 같은 Native Mod를 쓰고 탐지기만 바꿉니다." },
    { key: "seen", label: "비밀이 모델에 보인 실행 · PromptGuard", value: pg.seen_rate, sub: context("seen", "seen_rate"),
      detail: "transcript의 사용자 쪽 행(프롬프트, 도구 결과)에 정답 비밀값이 그대로 남은 실행의 비율이에요. 시스템 프롬프트로 들어간 비밀은 여기 잡히지 않고 서버 누출로 잽니다." },
    { key: "leaked", label: "서버로 비밀이 간 실행 · PromptGuard", value: data.captured ? pg.leaked_rate : null,
      sub: data.captured ? context("leaked", "leaked_rate") : "이 배치는 요청 기록을 켜지 않았어요",
      detail: "API로 실제로 나간 요청 본문(시스템 프롬프트, 도구 정의, 대화 이력)에서 과제의 비밀이 어떤 형태로든 발견된 실행의 비율이에요. 모델이 앞서 쓴 텍스트를 되풀이한 것(echo)은 빼요." },
    { key: "runs", label: "실행", count: data.valid,
      sub: `과제 ${int(data.tasks)}개 × 조건 ${data.conditions.length}개 × ${data.reps || "?"}회 · $${Object.values(conditions).reduce((total, item) => total + item.cost_usd, 0).toFixed(1)}`,
      detail: `유효한 실행만 셉니다(전체 ${int(data.runs)}회 중 ${int(data.valid)}회). Mod 실패, API 거절, transcript가 없는 실행은 뺍니다.` },
  ];
  const grid = h("div", { class: "tiles" });
  for (const tile of tiles) {
    grid.append(h("button", {
      class: "tile", type: "button", "aria-expanded": String(state.taskOpen === tile.key),
      onclick: () => { state.taskOpen = state.taskOpen === tile.key ? null : tile.key; renderTask(); },
    },
    h("div", { class: "label" }, tile.label),
    h("div", { class: "value" }, tile.count != null ? int(tile.count)
      : h("span", null, tile.value == null ? "—" : Math.round(tile.value * 100), tile.value == null ? null : h("span", { class: "unit" }, "%"))),
    h("div", { class: "sub" }, tile.sub)));
  }
  body.append(grid);
  const open = tiles.find((tile) => tile.key === state.taskOpen);
  if (open) {
    const own = batch.commit;
    body.append(h("div", { class: "more" }, open.detail, h("dl", null,
      h("dt", null, "배치"), h("dd", null, `${data.name} · ${dateTimeLabel(data.started_at)}`),
      h("dt", null, "PromptGuard 커밋"), h("dd", null, own ? `${own.short} · ${own.title}` : (data.system_commit || "기록 없음")),
      h("dt", null, "모델"), h("dd", null, `${data.model || "—"} · ${data.claude_version || ""}`),
      h("dt", null, "데이터 커밋"), h("dd", null, (data.data_commit || "—").slice(0, 7)),
      data.invalid.length ? [h("dt", null, "무효 실행"), h("dd", null, data.invalid.map((item) => `${item.task} ${item.condition} r${item.rep}`).join(", "))] : null)));
  }

  body.append(h("div", { class: "mini-title", style: "margin-top:20px" }, "과제 유형별 성공률"));
  const others = data.conditions.filter((name) => name !== "promptguard");
  body.append(h("table", { class: "bd-table task-table" },
    h("thead", null, h("tr", null,
      h("th", { class: "name-col" }, "유형"),
      h("th", null, h("span", { style: "display:inline-flex;align-items:center;gap:6px" }, h("i", { class: "key task" }), "PromptGuard")),
      others.map((name) => h("th", { class: "ctx" }, CONDITION_LABELS[name] || name)))),
    h("tbody", null, data.by_category.map((category) => {
      const mine = category.conditions.promptguard || {};
      return h("tr", null,
        h("td", { class: "name", title: category.label }, category.label),
        h("td", null, h("div", { class: "mcell" },
          h("span", { class: `v${mine.success_rate == null ? " na" : ""}` }, rateText(mine.success_rate)),
          h("span", { class: "bar task" }, mine.success_rate == null ? null : h("i", { style: `width:${(mine.success_rate * 100).toFixed(1)}%` })),
          h("span", { class: "muted", style: "font-size:11.5px;width:44px;text-align:right" }, mine.runs ? `${mine.success}/${mine.runs}` : ""))),
        others.map((name) => h("td", { class: "ctx" }, rateText((category.conditions[name] || {}).success_rate))));
    }))));

  const failing = data.by_task.filter((item) => item.rates.promptguard != null && item.rates.none != null && item.rates.promptguard < item.rates.none);
  if (failing.length) {
    body.append(h("button", { class: "link", type: "button", style: "margin-top:14px", "aria-expanded": String(state.taskFailuresOpen),
      onclick: () => { state.taskFailuresOpen = !state.taskFailuresOpen; renderTask(); } },
    `마스킹 없이는 성공했는데 PromptGuard에서 실패한 과제 ${failing.length}개 ${state.taskFailuresOpen ? "접기" : "보기"}`));
    if (state.taskFailuresOpen) {
      const markCell = (marks) => h("span", { class: "marks" }, (marks || []).map((mark) => h("span", { class: mark.startsWith("O") ? null : "bad" }, mark)));
      body.append(h("ul", { class: "fail-list" },
        h("li", { class: "head" }, h("span", null, "과제"), h("span", null, "유형"), data.conditions.map((name) => h("span", null, CONDITION_LABELS[name] || name))),
        failing.map((item) => h("li", null,
          h("span", { class: "name", title: item.task }, item.task),
          h("span", { class: "muted" }, (data.by_category.find((category) => category.key === item.category) || {}).label || item.category),
          data.conditions.map((name) => markCell(item.marks[name]))))),
      h("div", { class: "muted", style: "font-size:12px;margin-top:6px" }, "O 성공 · X 과제 실패 · x 과제는 했지만 비밀 훼손 · * 비밀이 서버에 감 · 반복 실행을 이어 적음"));
    }
  }
}

function taskHowTo() {
  return h("div", { class: "more" },
    "metric-task는 Claude API 비용이 들어서 대시보드가 직접 돌리지 않아요. 누군가 ",
    h("code", null, "python3 metric-task/scripts/m2.py run --tasks all --conditions none,gold,promptguard ..."),
    "으로 돌린 배치 폴더를 서버의 metric-task 폴더(기본 runs/metric-task/)에 두면 다음 확인 때 읽어요. 필요한 것은 배치 폴더의 batch.json과 runs.csv뿐이에요(비밀값이 없는 파일). batch.json에 적힌 PromptGuard 커밋에 맞춰 보여 줍니다.");
}

async function loadTask() {
  state.taskPick = pickTask();
  const key = state.taskPick && state.taskPick.batch.key;
  if (!key) {
    state.task = null;
    state.taskLoaded = null;
    return;
  }
  if (state.taskLoaded === key) return;
  try {
    state.task = await getJSON(`data/results/task/${key}/task.json`);
    state.taskLoaded = key;
  } catch {
    state.task = null;
    state.taskLoaded = null;
  }
}

// ------------------------------------------------------------------ loading

async function loadResults() {
  state.detection = pick("detection");
  state.latencyPick = tracks().includes("latency") ? pick("latency") : null;
  const jobs = [];
  if (state.detection.key && (!state.summary || state.summaryKey !== state.detection.key)) {
    jobs.push(getJSON(`data/results/detection/${state.detection.key}/summary.json`)
      .then((summary) => { state.summary = summary; state.summaryKey = state.detection.key; })
      .catch(() => { state.summary = null; state.summaryKey = null; }));
  } else if (!state.detection.key) {
    state.summary = null;
    state.summaryKey = null;
  }
  const latencyKey = state.latencyPick && state.latencyPick.key;
  if (latencyKey && state.latencyKey !== latencyKey) {
    jobs.push(getJSON(`data/results/latency/${latencyKey}/latency.json`)
      .then((data) => { state.latency = data; state.latencyKey = latencyKey; })
      .catch(() => { state.latency = null; state.latencyKey = null; }));
  } else if (!latencyKey) {
    state.latency = null;
    state.latencyKey = null;
  }
  jobs.push(loadTask());
  await Promise.all(jobs);
}

/** Names and descriptions come from index.json when it has them, so a renamed dataset needs no new evaluation. */
function applyCatalog() {
  const catalog = state.index && state.index.catalog;
  if (!catalog || !state.summary) return;
  for (const dataset of state.summary.datasets) Object.assign(dataset, catalog.datasets[dataset.key] || {});
  for (const type of state.summary.types) type.label = catalog.types[type.key] || type.label;
  for (const channel of state.summary.channels) channel.label = catalog.channels[channel.key] || channel.label;
}

function renderAll() {
  applyCatalog();
  renderChip();
  renderKpis();
  renderHeroNote();
  renderTrend();
  renderDetails();
  renderLatency();
  renderTask();
}

async function selectCommit(sha) {
  state.sha = sha && state.index && sha === state.index.latest ? null : sha;
  state.shown = PAGE;
  state.openExamples.clear();
  writeHash();
  document.body.style.opacity = "0.6";
  await loadResults();
  document.body.style.opacity = "";
  renderAll();
}

async function refreshIndex() {
  try {
    state.index = await getJSON("data/index.json");
  } catch {
    state.index = null;
  }
  await loadResults();
  renderAll();
}

async function pollStatus() {
  if (!state.statusPolling) return;
  try {
    const status = await getJSON("api/status");
    const changed = state.status && status.index_at && status.index_at !== state.status.index_at;
    state.status = status;
    if (changed || (state.index && status.index_at && status.index_at > state.index.generated_at)) await refreshIndex();
    else renderChip();
  } catch {
    state.statusPolling = false; // a static copy has no API; index.json carries the last status
  }
}

let resizeTimer = null;
function onResize() {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    if (state.summary) renderTrend();
    if (state.drawLatencyCharts && state.latency) state.drawLatencyCharts();
    drawSparklines();
  }, 120);
}

async function main() {
  readHash();
  $("#commit-chip").addEventListener("click", (event) => {
    if (state.popover && state.popover.anchor === event.currentTarget) closePopover();
    else openPopover(event.currentTarget, commitPopover);
  });
  $("#trend-dataset").addEventListener("change", (event) => { state.trendDataset = event.target.value; writeHash(); renderTrend(); });
  $("#trend-table-toggle").addEventListener("click", () => { state.trendTable = !state.trendTable; renderTrend(); });
  $("#reset").addEventListener("click", () => {
    state.filters = { d: null, t: null, c: null, g: null };
    state.by = "dataset";
    state.sort = null;
    state.outcome = null;
    writeHash();
    renderDetails();
  });
  window.addEventListener("resize", onResize);
  window.addEventListener("hashchange", async () => {
    const before = state.sha;
    readHash();
    if (before !== state.sha) await selectCommit(state.sha);
    else renderDetails();
  });
  await refreshIndex();
  await pollStatus();
  setInterval(pollStatus, 15000);
}

main();
