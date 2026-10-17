"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

class Element {
  constructor(text = "") { this.text = text; this.children = []; this.style = {}; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute() {}
  addEventListener() {}
  get textContent() { return this.text + this.children.map((child) => child.textContent).join(""); }
}

function app() {
  const elements = new Map();
  const document = {
    querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, new Element());
      return elements.get(selector);
    },
    createElement: () => new Element(),
    createTextNode: (text) => new Element(text),
  };
  const context = vm.createContext({ document, Node: Element });
  const source = fs.readFileSync(path.join(__dirname, "../web/app.js"), "utf8");
  vm.runInContext(source.replace(/\nmain\(\);\s*$/, "\n"), context);
  return { context, elements };
}

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
