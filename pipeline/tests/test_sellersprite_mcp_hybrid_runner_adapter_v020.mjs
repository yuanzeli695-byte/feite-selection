import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const fileName = "sellersprite_mcp_hybrid_runner_adapter_v0.2.0.user.js";
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
const plain = (value) => JSON.parse(JSON.stringify(value));

assert.ok(core);
assert.equal(core.version, "0.2.0");
assert.equal(core.featureFlag, "ENABLE_MCP_HYBRID_RUNNER_ADAPTER_V0_2_0");
assert.equal(core.eventProtocol, "runner-adapter/v2");
assert.equal(core.requiredAssistVersion, "0.3.0");
assert.equal(core.minBridgeVersion, "0.3.0");
assert.equal(core.buildFlags.requiredApplicationAuditV1, true);
assert.equal(core.detectRunnerVersion("SellerSprite Integrated Runner 0.3.7"), "0.3.7");
assert.equal(core.detectRunnerVersion("\u5356\u5bb6\u7cbe\u7075\u4e00\u4f53\u5316\u9009\u54c1 0.3.8.2 \u4e2d\u6587 Excel \u7248"), "0.3.8.2");
assert.equal(core.detectRunnerVersion("SellerSprite Integrated Runner 0.3.9"), "");

assert.deepEqual(plain(core.resolveMode("auto", 5)), {
  requestedMode: "auto",
  mode: "focus5",
  balancedExplicit: false,
});
assert.deepEqual(plain(core.resolveMode("auto", 10)), {
  requestedMode: "auto",
  mode: "original",
  balancedExplicit: false,
});
assert.equal(core.resolveMode("balanced", 30).balancedExplicit, true);
assert.equal(core.resolveMode("focus5", 6).mode, "original");

function makeAttributes(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getAttribute(name) { return values.has(name) ? values.get(name) : null; },
    setAttribute(name, value) { values.set(name, String(value)); },
    removeAttribute(name) { values.delete(name); },
  };
}

function makeRunnerPanel({
  title = "SellerSprite Integrated Runner 0.3.7",
  pickerValue = "",
  queueTag = "TEXTAREA",
} = {}) {
  const queue = {
    tagName: queueTag,
    value: "B0AAAA0001",
    disabled: false,
    readOnly: false,
    events: [],
    dispatchEvent(event) { this.events.push(event.type); return true; },
  };
  const picker = { tagName: "SELECT", value: pickerValue };
  const attrs = makeAttributes();
  const generateButton = {
    tagName: "BUTTON",
    disabled: false,
    ...attrs,
  };
  return {
    id: "ss-v3-panel",
    tagName: "DIV",
    queue,
    picker,
    generateButton,
    querySelector(selector) {
      if (selector === "h3") return { tagName: "H3", textContent: title };
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

function makeAssistPanel({
  version = "0.3.0",
  bridgeVersion = "0.3.0",
  enabled = true,
  featureEnabled = "true",
} = {}) {
  const attributes = {
    "data-ss-mcp-version": version,
    "data-ss-mcp-event-protocol": "runner-adapter/v2",
    "data-ss-mcp-final-authority": "false",
    "data-ss-mcp-feature-flag": "ENABLE_MCP_HYBRID_ASSIST_V0_3_0",
    "data-ss-mcp-feature-enabled": featureEnabled,
    "data-ss-mcp-audit-required": "true",
    "data-ss-mcp-bridge-version": bridgeVersion,
  };
  return {
    getAttribute(name) { return attributes[name] ?? null; },
    querySelector(selector) {
      return selector === "#ss-mcp-assist-enabled" ? { checked: enabled } : null;
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
fakeDocument.panels = [makeRunnerPanel({ queueTag: "INPUT" })];
assert.throws(() => core.discoverRunner(true), (error) => error.code === "runner_queue_contract");
fakeDocument.panels = [makeRunnerPanel()];
assert.equal(core.discoverRunner(true).version, "0.3.7");

assert.throws(() => core.discoverAssist(), (error) => error.code === "assist_panel_count");
fakeDocument.assists = [makeAssistPanel({ version: "0.2.1" })];
assert.throws(() => core.discoverAssist(), (error) => error.code === "assist_version");
fakeDocument.assists = [makeAssistPanel({ bridgeVersion: "0.2.9" })];
assert.throws(() => core.discoverAssist(), (error) => error.code === "bridge_version");
fakeDocument.assists = [makeAssistPanel({ enabled: false })];
assert.throws(() => core.discoverAssist(), (error) => error.code === "assist_disabled");
fakeDocument.assists = [makeAssistPanel()];
assert.equal(core.discoverAssist(), fakeDocument.assists[0]);

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
  requestedMode: "auto",
  mode: "focus5",
  balancedExplicit: false,
};
const rankingReceipt = {
  schemaVersion: "sellerSpriteMcpAuditReceipt/v1",
  requestId: expected.requestId,
  auditId: "rank:1234abcd:5678abcd",
  persisted: true,
  idempotent: false,
  finalAuthority: false,
};
const validDetail = {
  requestId: expected.requestId,
  eventProtocol: "runner-adapter/v2",
  assistVersion: "0.3.0",
  original: expected.asins.slice(),
  ranked: ["B0AAAA0002", "B0AAAA0001", "B0AAAA0001"],
  requestedMode: "auto",
  mode: "focus5",
  balancedExplicit: false,
  multisetUnchanged: true,
  finalAuthority: false,
  allowedAction: "reorder_only",
  auditRequired: true,
  rankingAuditConfirmed: true,
  rankingAudit: rankingReceipt,
};

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
  () => core.validateRankedResponse({ ...validDetail, rankingAuditConfirmed: false }, expected),
  (error) => error.code === "ranking_audit_missing",
);
assert.throws(
  () => core.validateRankedResponse({
    ...validDetail,
    rankingAudit: { ...rankingReceipt, requestId: "runner-adapter:old" },
  }, expected),
  (error) => error.code === "audit_receipt",
);
assert.throws(
  () => core.validateRankedResponse({ ...validDetail, ranked: ["B0AAAA0002", "B0AAAA0001", "B0AAAA0003"] }, expected),
  (error) => error.code === "response_multiset",
);

class FakeQueue {
  constructor(value, transform = null) {
    this.value = value;
    this.events = [];
    this.transform = transform;
  }
  dispatchEvent(event) {
    this.events.push(event.type);
    if (this.transform) this.value = this.transform(this.value, event.type);
    return true;
  }
}

const queue = new FakeQueue(expected.text);
const picker = { value: "" };
assert.deepEqual(Array.from(core.applyRankedQueue(queue, picker, expected, validDetail)), validDetail.ranked);
assert.equal(queue.value, validDetail.ranked.join("\n"));
assert.deepEqual(queue.events, ["input", "change"]);
assert.equal(core.restoreQueue(queue, picker, expected, validDetail.ranked.join("\n")), true);
assert.equal(queue.value, expected.text);
assert.deepEqual(queue.events, ["input", "change", "input", "change"]);

const changedQueue = new FakeQueue("B0AAAA0002");
assert.throws(
  () => core.applyRankedQueue(changedQueue, picker, expected, validDetail),
  (error) => error.code === "queue_changed",
);
assert.throws(
  () => core.restoreQueue(changedQueue, picker, expected, validDetail.ranked.join("\n")),
  (error) => error.code === "rollback_queue_changed",
);

const buttonAttrs = makeAttributes();
const generateButton = { disabled: false, ...buttonAttrs };
const lock = core.lockGenerateButton(generateButton, expected.requestId);
assert.equal(generateButton.disabled, true);
assert.equal(generateButton.getAttribute("data-ss-mcp-audit-lock"), expected.requestId);
core.releaseGenerateButton(lock);
assert.equal(generateButton.disabled, false);
assert.equal(generateButton.getAttribute("data-ss-mcp-audit-lock"), null);

const rollbackQueue = new FakeQueue(expected.text);
core.applyRankedQueue(rollbackQueue, picker, expected, validDetail);
const rollbackAttrs = makeAttributes();
const rollbackButton = { disabled: false, ...rollbackAttrs };
const rollbackLock = core.lockGenerateButton(rollbackButton, expected.requestId);
const rollbackOutcome = core.rollbackAfterAuditFailure(
  rollbackQueue,
  picker,
  expected,
  validDetail.ranked.join("\n"),
  rollbackLock,
);
assert.equal(rollbackOutcome.rollbackSucceeded, true);
assert.equal(rollbackOutcome.mutationApplied, false);
assert.equal(rollbackOutcome.generateLocked, false);
assert.equal(rollbackQueue.value, expected.text);
assert.equal(rollbackButton.disabled, false);

const blockedRollbackQueue = new FakeQueue("B0AAAA0003");
const blockedAttrs = makeAttributes();
const blockedButton = { disabled: false, ...blockedAttrs };
const blockedLock = core.lockGenerateButton(blockedButton, expected.requestId);
const blockedOutcome = core.rollbackAfterAuditFailure(
  blockedRollbackQueue,
  picker,
  expected,
  validDetail.ranked.join("\n"),
  blockedLock,
);
assert.equal(blockedOutcome.rollbackSucceeded, false);
assert.equal(blockedOutcome.mutationApplied, true);
assert.equal(blockedOutcome.generateLocked, true);
assert.equal(blockedButton.disabled, true);

fakeWindow.onDispatch = (event) => {
  if (event.type === "ss-mcp-hybrid:rank-request") {
    fakeWindow.dispatchEvent(new FakeEvent("ss-mcp-hybrid:queue-ranked", { detail: validDetail }));
  }
};
const rankedResponse = await core.waitForRanking(expected);
assert.deepEqual(Array.from(rankedResponse.ranked), validDetail.ranked);

const applicationExpected = {
  requestId: expected.requestId,
  auditId: "apply:1234abcd:5678abcd",
};
const applicationReceipt = {
  schemaVersion: "sellerSpriteMcpAuditReceipt/v1",
  requestId: applicationExpected.requestId,
  auditId: applicationExpected.auditId,
  persisted: true,
  idempotent: false,
  finalAuthority: false,
};
fakeWindow.onDispatch = (event) => {
  if (event.type === "ss-mcp-hybrid:audit-request") {
    fakeWindow.dispatchEvent(new FakeEvent("ss-mcp-hybrid:audit-confirmed", {
      detail: {
        eventProtocol: "runner-adapter/v2",
        requestId: applicationExpected.requestId,
        auditId: applicationExpected.auditId,
        receipt: applicationReceipt,
        persisted: true,
        finalAuthority: false,
      },
    }));
  }
};
assert.equal((await core.waitForAuditConfirmation(applicationExpected, { finalAuthority: false })).persisted, true);

fakeWindow.onDispatch = (event) => {
  if (event.type === "ss-mcp-hybrid:audit-request") {
    fakeWindow.dispatchEvent(new FakeEvent("ss-mcp-hybrid:audit-error", {
      detail: {
        requestId: applicationExpected.requestId,
        auditId: applicationExpected.auditId,
        message: "disk unavailable",
      },
    }));
  }
};
await assert.rejects(
  core.waitForAuditConfirmation(applicationExpected, { finalAuthority: false }),
  (error) => error.code === "audit_failed",
);

const pairedBundle = JSON.parse(fs.readFileSync(
  path.join(root, "runs", "mcp_hybrid_assist_v0.2_paired30", "evidence_bundle.json"),
  "utf8",
));
const pairedQueue = pairedBundle.evidence.map((row) => row.targetAsin);
assert.equal(pairedQueue.length, 30);
assert.equal(core.resolveMode("auto", pairedQueue.length).mode, "original");

assert.equal(source.includes("localStorage"), false);
assert.equal(source.includes("strict-qualified-history"), false);
assert.equal(source.includes(".click("), false);
assert.match(source, /batchCreated:\s*false/);
assert.match(source, /batchStarted:\s*false/);
assert.match(source, /strictHistoryWritten:\s*false/);
assert.match(source, /rollbackAfterAuditFailure\(runner\.queue/);
assert.match(source, /data-ss-mcp-audit-lock/);
assert.match(source, /new MutationObserver/);

console.log("SellerSprite MCP Hybrid Runner Adapter 0.2.0 tests: PASS");
