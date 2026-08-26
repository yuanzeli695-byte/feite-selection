import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const fileName = "sellersprite_mcp_hybrid_runner_adapter_v0.1.0.user.js";
const source = fs.readFileSync(path.join(root, "scripts", fileName), "utf8");

class FakeEvent {
  constructor(type, options = {}) {
    this.type = type;
    this.detail = options.detail;
  }
}

class FakeWindow {
  constructor() {
    this.listeners = new Map();
    this.onDispatch = null;
  }
  addEventListener(type, listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(listener);
  }
  removeEventListener(type, listener) {
    if (this.listeners.has(type)) this.listeners.get(type).delete(listener);
  }
  dispatchEvent(event) {
    for (const listener of Array.from(this.listeners.get(event.type) || [])) listener(event);
    if (this.onDispatch) this.onDispatch(event);
    return true;
  }
}

const fakeDocument = {
  documentElement: null,
  panels: [],
  assists: [],
  querySelectorAll(selector) {
    if (selector === "#ss-v3-panel") return this.panels;
    if (selector === "#ss-mcp-hybrid-assist-panel") return this.assists;
    return [];
  },
};
const fakeWindow = new FakeWindow();
const sandbox = {
  console,
  globalThis: {},
  Event: FakeEvent,
  CustomEvent: FakeEvent,
  document: fakeDocument,
  window: fakeWindow,
  setTimeout,
  clearTimeout,
};
vm.runInNewContext(source, sandbox, { filename: fileName });
const core = sandbox.globalThis.SSMcpHybridRunnerAdapterCore;

assert.ok(core);
assert.equal(core.version, "0.1.0");
assert.equal(core.featureFlag, "ENABLE_MCP_HYBRID_RUNNER_ADAPTER_V0_1");
assert.equal(core.eventProtocol, "runner-adapter/v1");
assert.equal(core.requiredAssistVersion, "0.2.1");
assert.equal(core.detectRunnerVersion("SellerSprite Integrated Runner 0.3.7 收起"), "0.3.7");
assert.equal(core.detectRunnerVersion("卖家精灵一体化选品 0.3.8.2 中文 Excel 版 收起"), "0.3.8.2");
assert.equal(core.detectRunnerVersion("SellerSprite Integrated Runner 0.3.9"), "");

function makeRunnerPanel({ title = "SellerSprite Integrated Runner 0.3.7", pickerValue = "" } = {}) {
  const queue = { value: "B0AAAA0001", disabled: false, readOnly: false };
  const picker = { value: pickerValue };
  const generateButton = {};
  return {
    queue,
    picker,
    generateButton,
    querySelector(selector) {
      if (selector === "h3") return { textContent: title };
      return null;
    },
    querySelectorAll(selector) {
      if (selector === "#ss-v3-queue") return [queue];
      if (selector === "#ss-v3-picker") return [picker];
      if (selector === "#ss-v3-generate") return [generateButton];
      return [];
    },
  };
}

assert.throws(() => core.discoverRunner(true), (error) => error.code === "runner_panel_count");
fakeDocument.panels = [makeRunnerPanel(), makeRunnerPanel()];
assert.throws(() => core.discoverRunner(true), (error) => error.code === "runner_panel_count");
fakeDocument.panels = [makeRunnerPanel({ title: "SellerSprite Integrated Runner 0.3.9" })];
assert.throws(() => core.discoverRunner(true), (error) => error.code === "runner_version");
fakeDocument.panels = [makeRunnerPanel({ pickerValue: "existing-batch" })];
assert.throws(() => core.discoverRunner(true), (error) => error.code === "runner_not_draft");
fakeDocument.panels = [makeRunnerPanel()];
assert.equal(core.discoverRunner(true).version, "0.3.7");

assert.deepEqual(Array.from(core.parseQueue(" b0aaaa0001\nB0AAAA0002 B0AAAA0001 ")), [
  "B0AAAA0001",
  "B0AAAA0002",
  "B0AAAA0001",
]);
assert.throws(() => core.parseQueue(""), (error) => error.code === "queue_empty");
assert.throws(() => core.parseQueue("B0AAAA0001\nINVALID"), (error) => error.code === "queue_invalid");

const expected = {
  requestId: "runner-adapter:1:abc",
  text: "B0AAAA0001\nB0AAAA0002\nB0AAAA0001",
  asins: ["B0AAAA0001", "B0AAAA0002", "B0AAAA0001"],
  mode: "balanced",
};
const validDetail = {
  requestId: expected.requestId,
  eventProtocol: "runner-adapter/v1",
  original: expected.asins.slice(),
  ranked: ["B0AAAA0002", "B0AAAA0001", "B0AAAA0001"],
  mode: "balanced",
  multisetUnchanged: true,
  finalAuthority: false,
  allowedAction: "reorder_only",
};

function makeAssistPanel({ version = "0.2.1", enabled = true } = {}) {
  return {
    getAttribute(name) {
      if (name === "data-ss-mcp-version") return version;
      if (name === "data-ss-mcp-event-protocol") return "runner-adapter/v1";
      if (name === "data-ss-mcp-final-authority") return "false";
      return "";
    },
    querySelector(selector) {
      return selector === "#ss-mcp-assist-enabled" ? { checked: enabled } : null;
    },
  };
}

assert.throws(() => core.discoverAssist(), (error) => error.code === "assist_panel_count");
fakeDocument.assists = [makeAssistPanel({ version: "0.2.0" })];
assert.throws(() => core.discoverAssist(), (error) => error.code === "assist_version");
fakeDocument.assists = [makeAssistPanel({ enabled: false })];
assert.throws(() => core.discoverAssist(), (error) => error.code === "assist_disabled");
fakeDocument.assists = [makeAssistPanel()];
assert.equal(core.discoverAssist(), fakeDocument.assists[0]);

assert.deepEqual(Array.from(core.validateRankedResponse(validDetail, expected)), validDetail.ranked);
assert.throws(
  () => core.validateRankedResponse({ ...validDetail, requestId: "runner-adapter:old" }, expected),
  (error) => error.code === "response_stale",
);
assert.throws(
  () => core.validateRankedResponse({ ...validDetail, finalAuthority: true }, expected),
  (error) => error.code === "response_authority",
);
assert.throws(
  () => core.validateRankedResponse({ ...validDetail, original: ["B0AAAA0002", "B0AAAA0001", "B0AAAA0001"] }, expected),
  (error) => error.code === "response_original",
);
assert.throws(
  () => core.validateRankedResponse({ ...validDetail, ranked: ["B0AAAA0002", "B0AAAA0001", "B0AAAA0003"] }, expected),
  (error) => error.code === "response_multiset",
);
assert.throws(
  () => core.validateRankedResponse({ ...validDetail, ranked: ["B0AAAA0002", "B0AAAA0001"] }, expected),
  (error) => error.code === "response_count",
);

class FakeQueue {
  constructor(value, failEvent = false) {
    this.value = value;
    this.events = [];
    this.failEvent = failEvent;
  }
  dispatchEvent(event) {
    this.events.push(event.type);
    if (this.failEvent) throw new Error("event failure");
    return true;
  }
}

const queue = new FakeQueue(expected.text);
const picker = { value: "" };
assert.deepEqual(Array.from(core.applyRankedQueue(queue, picker, expected, validDetail)), validDetail.ranked);
assert.equal(queue.value, validDetail.ranked.join("\n"));
assert.deepEqual(queue.events, ["input", "change"]);

const changedQueue = new FakeQueue("B0AAAA0002");
assert.throws(
  () => core.applyRankedQueue(changedQueue, picker, expected, validDetail),
  (error) => error.code === "queue_changed",
);
assert.equal(changedQueue.value, "B0AAAA0002");

const selectedQueue = new FakeQueue(expected.text);
assert.throws(
  () => core.applyRankedQueue(selectedQueue, { value: "existing-batch" }, expected, validDetail),
  (error) => error.code === "runner_not_draft",
);
assert.equal(selectedQueue.value, expected.text);

const eventFailureQueue = new FakeQueue(expected.text, true);
assert.throws(() => core.applyRankedQueue(eventFailureQueue, picker, expected, validDetail), /event failure/);
assert.equal(eventFailureQueue.value, expected.text);

fakeWindow.onDispatch = (event) => {
  if (event.type === "ss-mcp-hybrid:rank-request") {
    fakeWindow.dispatchEvent(new FakeEvent("ss-mcp-hybrid:queue-ranked", { detail: validDetail }));
  }
};
const rankedResponse = await core.waitForRanking(expected);
assert.deepEqual(Array.from(rankedResponse.ranked), validDetail.ranked);

fakeWindow.onDispatch = (event) => {
  if (event.type === "ss-mcp-hybrid:rank-request") {
    fakeWindow.dispatchEvent(new FakeEvent("ss-mcp-hybrid:rank-error", {
      detail: { requestId: expected.requestId, message: "Bridge not connected" },
    }));
  }
};
await assert.rejects(core.waitForRanking(expected), (error) => error.code === "assist_error");

sandbox.setTimeout = (callback) => { callback(); return 1; };
fakeWindow.onDispatch = null;
await assert.rejects(core.waitForRanking(expected), (error) => error.code === "assist_timeout");

assert.equal(source.includes("localStorage"), false);
assert.equal(source.includes("strict-qualified-history"), false);
assert.equal(source.includes(".click("), false);
assert.match(source, /batchCreated:\s*false/);
assert.match(source, /batchStarted:\s*false/);
assert.match(source, /adapterMutation:\s*false/);
assert.match(source, /if \(pending\) return/);
assert.match(source, /new MutationObserver/);

console.log("SellerSprite MCP Hybrid Runner Adapter tests: PASS");
