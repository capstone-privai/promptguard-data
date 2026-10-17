"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const { execFileSync } = require("node:child_process");

class Element {
  constructor(text = "", tag = "") {
    this.text = text; this.tag = tag; this.children = []; this.style = {};
    this.attributes = {}; this.listeners = new Map(); this.parentNode = null;
  }
  append(...children) {
    for (let child of children) {
      if (!(child instanceof Element)) child = new Element(String(child));
      if (child.fragment) { this.append(...child.children); child.children = []; continue; }
      child.parentNode = this;
      this.children.push(child);
    }
  }
  replaceChildren(...children) {
    for (const child of this.children) child.parentNode = null;
    this.children = []; this.append(...children);
  }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(name, handler) { this.listeners.set(name, handler); }
  get isConnected() { return this.connected || Boolean(this.parentNode?.isConnected); }
  cloneNode(deep) {
    const copy = new Element(this.text, this.tag);
    copy.className = this.className;
    if (deep) copy.append(...this.children.map((child) => child.cloneNode(true)));
    return copy;
  }
  get textContent() { return this.text + this.children.map((child) => child.textContent).join(""); }
}

function app(globals = {}) {
  const elements = new Map();
  const document = {
    querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, Object.assign(new Element(), { connected: true }));
      return elements.get(selector);
    },
    body: new Element(),
    createElement: (tag) => new Element("", tag),
    createDocumentFragment: () => Object.assign(new Element(), { fragment: true }),
    createTextNode: (text) => new Element(text),
  };
  const context = vm.createContext({ document, Node: Element, ...globals });
  const source = fs.readFileSync(path.join(__dirname, "../web/app.js"), "utf8");
  vm.runInContext(source.replace(/\nmain\(\);\s*$/, "\n"), context);
  return { context, elements };
}

const response = (data, status = 200) => ({ ok: status < 400, status, json: async () => data });
const descendants = (node) => [node, ...node.children.flatMap(descendants)];
const retryButton = (node) => descendants(node).find((child) => child.tag === "button" && child.textContent === "다시 시도");

function resultsFixture() {
  return {
    index: {
      generated_at: "same", tracks: ["detection", "latency"], latest: "a",
      commits: [{ sha: "a", short: "a", task: ["ta"],
        detection: { key: "da", state: "done" }, latency: { key: "la", state: "done" } }],
      task_batches: [{ key: "ta", name: "fixture", provenance: "clean" }],
    },
    status: { index_at: "same" },
  };
}

function examplesFixture() {
  return {
    ...resultsFixture(), detection: { key: "da" }, outcome: "missed",
    summary: {
      datasets: [{ key: "sessions", label: "fixture", groups: ["-"] }],
      channels: [{ key: "prompt", label: "prompt" }], types: [{ key: "SECRET", label: "secret" }],
      cells: [[0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0]], items: [[0, 0, 0, 1, 0, 1]],
    },
  };
}

test("failed example requests can be retried; successful empty results stay cached", async () => {
  let requests = 0;
  const { context } = app({ fetch: async () => response({ examples: [] }, ++requests === 1 ? 503 : 200) });
  context.fixture = examplesFixture();
  vm.runInContext("Object.assign(state, fixture);", context);
  await assert.rejects(vm.runInContext("loadExamples()", context), /HTTP 503/);
  assert.equal(vm.runInContext("state.examples.size", context), 0);
  assert.equal((await vm.runInContext("loadExamples()", context)).length, 0);
  await vm.runInContext("loadExamples()", context);
  assert.equal(requests, 2);
});

test("example errors have a manual retry and recover during unchanged-index polling", async () => {
  let requests = 0;
  const { context, elements } = app({ fetch: async (url) => url === "api/status"
    ? response({ index_at: "same" }) : response({ examples: [] }, ++requests === 1 ? 503 : 200) });
  context.fixture = examplesFixture();
  vm.runInContext("Object.assign(state, fixture); renderChip = () => {};", context);
  await vm.runInContext("renderOutcomes()", context);
  assert.ok(elements.get("#outcomes").textContent.includes("불러오지 못했어요"));
  assert.ok(retryButton(elements.get("#outcomes")));
  assert.ok(!elements.get("#outcomes").textContent.includes("표본에 없어요"));
  await vm.runInContext("pollStatus()", context);
  assert.equal(requests, 2);
  assert.ok(elements.get("#outcomes").textContent.includes("표본에 없어요"));
});

test("failed summary, latency and task requests recover without an index change", async () => {
  const requests = new Map();
  const { context, elements } = app({ fetch: async (url) => {
    if (url === "api/status") return response({ index_at: "same" });
    const count = (requests.get(url) || 0) + 1;
    requests.set(url, count);
    return response({ marker: url }, count === 1 ? 503 : 200);
  } });
  context.fixture = resultsFixture();
  vm.runInContext("Object.assign(state, fixture); renderAll = () => {}; renderChip = () => {};", context);
  await vm.runInContext("loadResults()", context);
  vm.runInContext("renderKpis(); renderLatency(); renderTask();", context);
  for (const selector of ["#kpis", "#latency-body", "#task-body"]) {
    assert.ok(elements.get(selector).textContent.includes("불러오지 못했어요"), selector);
    assert.ok(retryButton(elements.get(selector)), selector);
  }
  await vm.runInContext("pollStatus()", context);
  for (const field of ["summary", "latency", "task"]) {
    assert.ok(vm.runInContext(`state.${field}.marker`, context));
  }
  assert.deepEqual([...requests.values()], [2, 2, 2]);
});

for (const [field, panel] of [["summary", "#kpis"], ["latency", "#latency-body"], ["task", "#task-body"]]) {
  test(`static exports can manually retry a failed ${field} request`, async () => {
    const requests = new Map();
    const { context, elements } = app({ fetch: async (url) => {
      if (url === "api/status") return response(null, 404);
      const count = (requests.get(url) || 0) + 1;
      requests.set(url, count);
      return response({ marker: url }, count === 1 ? 503 : 200);
    } });
    context.fixture = resultsFixture();
    vm.runInContext("Object.assign(state, fixture); renderAll = () => {};", context);
    await vm.runInContext("loadResults()", context);
    await vm.runInContext("pollStatus()", context);
    assert.equal(vm.runInContext("state.statusPolling", context), false);
    vm.runInContext("renderKpis(); renderLatency(); renderTask();", context);
    const button = retryButton(elements.get(panel));
    assert.ok(button);
    await button.listeners.get("click")();
    assert.ok(vm.runInContext(`state.${field}.marker`, context));
  });
}

test("static exports can manually retry failed examples", async () => {
  let requests = 0;
  const { context, elements } = app({ fetch: async () => response({ examples: [] }, ++requests === 1 ? 503 : 200) });
  context.fixture = { ...examplesFixture(), statusPolling: false };
  vm.runInContext("Object.assign(state, fixture);", context);
  await vm.runInContext("renderOutcomes()", context);
  const button = retryButton(elements.get("#outcomes"));
  assert.ok(button);
  await button.listeners.get("click")();
  assert.equal(requests, 2);
  assert.ok(elements.get("#outcomes").textContent.includes("표본에 없어요"));
});

for (const change of ["commit", "key"]) {
  test(`an old result retry cannot overwrite a newer ${change}`, async () => {
    let settle;
    const { context } = app({ fetch: (url) => url.includes("/da/")
      ? new Promise((resolve) => { settle = () => resolve(response({ marker: "old" })); })
      : Promise.resolve(response({ marker: "new" })) });
    context.fixture = resultsFixture();
    context.fixture.index.tracks = ["detection"];
    context.fixture.index.task_batches = [];
    vm.runInContext("Object.assign(state, fixture);", context);
    const old = vm.runInContext("loadResults()", context);
    if (change === "commit") {
      vm.runInContext('state.index.commits.push({sha: "b", detection: {key: "db", state: "done"}}); state.sha = "b";', context);
    } else vm.runInContext('state.index.commits[0].detection.key = "db";', context);
    assert.equal(await vm.runInContext("loadResults()", context), true);
    settle();
    assert.equal(await old, false);
    assert.equal(vm.runInContext("state.summary.marker", context), "new");
    assert.equal(vm.runInContext("state.summaryKey", context), "db");
  });
}

for (const status of [200, 503]) {
test(`an old example response (${status}) cannot replace the newly selected result's examples`, async () => {
  let settle;
  const { context, elements } = app({ fetch: (url) => url.includes("/da/")
    ? new Promise((resolve) => { settle = () => resolve(response({ examples: [{ id: "old", tags: ["SECRET:missed"] }] }, status)); })
    : Promise.resolve(response({ examples: [] })) });
  context.fixture = examplesFixture();
  vm.runInContext("Object.assign(state, fixture);", context);
  const old = vm.runInContext("renderOutcomes()", context);
  vm.runInContext('state.detection = {key: "db"};', context);
  await vm.runInContext("renderOutcomes()", context);
  settle();
  await old;
  assert.ok(elements.get("#outcomes").textContent.includes("표본에 없어요"));
  assert.ok(!elements.get("#outcomes").textContent.includes("불러오지 못했어요"));
});
}

test("a result that has not been evaluated has no request-failure retry", async () => {
  const { context, elements } = app({ fetch: async () => { throw new Error("unexpected fetch"); } });
  context.fixture = resultsFixture();
  context.fixture.index.commits[0].detection.state = "queued";
  context.fixture.index.commits[0].latency.state = "queued";
  context.fixture.index.task_batches = [];
  vm.runInContext("Object.assign(state, fixture);", context);
  await vm.runInContext("loadResults()", context);
  vm.runInContext("renderKpis(); renderLatency(); renderTask();", context);
  assert.ok(elements.get("#kpis").textContent.includes("아직 평가된 결과가 없어요"));
  assert.ok(elements.get("#latency-body").textContent.includes("아직 잰 결과가 없어요"));
  assert.ok(!retryButton(elements.get("#kpis")));
  assert.ok(!retryButton(elements.get("#latency-body")));
});

function taskFixture(stats) {
  return {
    index: { commits: [], task_batches: [{ key: "batch" }] },
    taskPick: { batch: { key: "batch" }, chosen: true },
    task: {
      name: "fixture", conditions: ["promptguard"], valid: 2, runs: 2, tasks: 1, reps: 2,
      by_condition: { promptguard: { cost_usd: 0, ...stats } },
      by_category: [], by_task: [], invalid: [],
    },
  };
}

for (const [label, stats, expected] of [
  ["partial capture", { leaked_rate: 1, leak_measured: 1, leak_unmeasured: 1 }, "100%"],
  ["unmeasured", { leaked_rate: null, leak_measured: 0, leak_unmeasured: 2 }, "미측정"],
  ["measured without leaks", { leaked_rate: 0, leak_measured: 2, leak_unmeasured: 0 }, "0%"],
]) {
  test(`task leak tile: ${label}`, () => {
    const { context, elements } = app();
    context.fixture = taskFixture(stats);
    vm.runInContext("Object.assign(state, fixture); renderTask();", context);
    const grid = elements.get("#task-body").children.find((node) => node.className === "tiles");
    const tile = grid.children[2].textContent;
    assert.ok(tile.includes(expected), tile);
    assert.ok(tile.includes(`측정 ${stats.leak_measured}회 · 미측정 ${stats.leak_unmeasured}회`), tile);
    if (stats.leaked_rate == null) assert.ok(!tile.includes("0%"), tile);
  });
}

test("only clean batches can be selected as a commit's own result", () => {
  const { context } = app();
  context.fixture = {
    index: {
      commits: [{ sha: "a", task: ["clean", "dirty", "legacy"] }],
      task_batches: [
        { key: "clean", provenance: "clean" },
        { key: "dirty", provenance: "dirty" },
        { key: "legacy" },
      ],
    },
  };
  vm.runInContext("Object.assign(state, fixture);", context);
  assert.equal(vm.runInContext("pickTask().batch.key", context), "clean");
  vm.runInContext('state.taskKey = "dirty";', context);
  assert.equal(vm.runInContext("pickTask().chosen", context), true);
  assert.ok(!vm.runInContext("pickTask().own", context));
});

for (const [status, expected] of [["dirty", "미커밋 변경 있음"], ["unknown", "이력 미확인"]]) {
  test(`task provenance is visible: ${status}`, () => {
    const { context, elements } = app();
    context.fixture = taskFixture({ leaked_rate: null, leak_measured: 0, leak_unmeasured: 2 });
    context.fixture.taskPick.batch.provenance = status;
    vm.runInContext("Object.assign(state, fixture); renderTask();", context);
    assert.ok(elements.get("#task-body").textContent.includes(expected));
    assert.ok(vm.runInContext("batchLabel(state.taskPick.batch)", context).includes(expected));
  });
}

for (const [label, text, ranges, edits, masked, goldText] of [
  ["before the span", "🔑 secret=ABC", [[9, 12]], [[9, 12]], "🔑 secret=[SECRET_1]", "ABC"],
  ["inside the span", "AB🔑C", [[0, 4]], [[0, 4]], "[SECRET_1]", "AB🔑C"],
  ["after the span", "ABC 🔑", [[0, 3]], [[0, 3]], "[SECRET_1] 🔑", "ABC"],
  ["multiple spans", "🔑 AB 🔒 CD 🧪", [[2, 4], [7, 9]], [[2, 4], [7, 9]], "🔑 [SECRET_1] 🔒 [SECRET_2] 🧪", "ABCD"],
  ["partial masking", "🔑 A🔐B 🔒 C", [[2, 5], [8, 9]], [[3, 4]], "🔑 A[SECRET_1]B 🔒 C", "A🔐BC"],
  ["first character", "😀x", [[0, 1]], [[0, 1]], "[SECRET_1]x", "😀"],
  ["ASCII", "secret=ABC", [[7, 10]], [[7, 10]], "secret=[SECRET_1]", "ABC"],
]) {
  test(`example Unicode offsets: ${label}`, () => {
    const { context } = app();
    context.fixture = {
      text, gold: ranges.map(([start, end]) => [start, end, "SECRET", "exact"]),
      edits: edits.map(([start, end], index) => [start, end, "tp", "SECRET", `[SECRET_${index + 1}]`]),
    };
    const original = vm.runInContext("highlighted(fixture.text, fixture.gold, fixture.edits)", context);
    assert.equal(original.textContent, text);
    const marked = descendants(original).filter((node) => (node.className || "").split(" ").includes("g"));
    assert.equal(marked.map((node) => node.textContent).join(""), goldText);
    const covered = descendants(original).filter((node) => (node.className || "").split(" ").includes("m"));
    assert.equal(covered.map((node) => node.textContent).join(""), label === "partial masking" ? "🔐" : goldText);
    const result = vm.runInContext("maskedText(fixture.text, fixture.gold, fixture.edits)", context);
    assert.equal(result.textContent, masked);
    // Remaining gold characters must still be underlined after replacing an emoji or an earlier span.
    const remaining = descendants(result).filter((node) => (node.className || "").split(" ").includes("g"));
    assert.equal(remaining.map((node) => node.textContent).join(""), label === "partial masking" ? "ABC" : "");
  });
}

test("Python example windows retain their coordinates, highlights and clipping markers in the UI", () => {
  const text = "앞".repeat(20) + "🧪🔑 secret=A🔐BC 🔒" + "뒤".repeat(20);
  const source = { text, channel: "prompt", group: "-",
    gold: [[20, 22, "SECRET", "exact"], [30, 34, "SECRET", "exact"]],
    edits: [[20, 22, "tp", "SECRET", "[SECRET_1]"], [30, 34, "tp", "SECRET", "[SECRET_2]"]] };
  const script = `import json, sys
sys.path.insert(0, 'dashboard')
from pipeline.collect import _example
source = json.loads(sys.argv[1])
print(json.dumps([_example(('unicode', 0), source, start, end)
                  for start, end in [(21, 36), (21, len(source['text']) - 1),
                                     (21, len(source['text'])), (31, 34)]]))`;
  const examples = JSON.parse(execFileSync("python3", ["-c", script, JSON.stringify(source)],
    { cwd: path.resolve(__dirname, "../.."), encoding: "utf8" }));
  const { context } = app();
  context.fixture = examplesFixture();
  vm.runInContext("Object.assign(state, fixture);", context);
  for (const [index, example] of examples.entries()) {
    context.example = { ...example, dataset: "sessions" };
    const card = vm.runInContext('state.openExamples.add(example.id); exampleCard(example, "exact")', context);
    const detail = descendants(card).find((node) => node.className === "ex-id");
    const end = example.offset + [...example.text].length;
    assert.ok(detail.textContent.includes(`${example.offset}–${end}자 / ${example.length}자`), detail.textContent);
    const original = card.children.find((node) => node.tag === "pre");
    const marked = descendants(original).filter((node) => (node.className || "").split(" ").includes("g"));
    assert.equal(marked.map((node) => node.textContent).join(""), index === 3 ? "🔐BC" : "🔑A🔐BC");
    const cuts = descendants(original).filter((node) => node.className === "cut");
    assert.equal(cuts.length, index === 2 ? 1 : 2);
    const masked = descendants(card).find((node) => node.className === "ex-detail").children.find((node) => node.tag === "pre");
    if (index === 0) assert.equal(masked.textContent, "…[SECRET_1] secret=[SECRET_2] 🔒…");
    if (index === 3) assert.equal(masked.textContent, "…[SECRET_2]…");
  }
});
