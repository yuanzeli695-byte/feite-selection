import assert from "node:assert/strict";
import { createHash, webcrypto } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const bridgePath = new URL("./browser_bridge_v2.user.js", import.meta.url);
const source = readFileSync(bridgePath, "utf8").replace(/\r\n/g, "\n");
const testSource = source.replace(
  /  mount\(\);\n  restoreConnection\(\);\n  setInterval\(pollControl, 2500\);\n  setInterval\(heartbeat, 3000\);\n\}\)\(\);\n$/,
  `  globalThis.__bridgeTest = Object.freeze({
    runnerElements, checkAmazonState, queueSha256, assertConsoleQueueDigest,
    readStrictHistoryEvidence, validateHistoryEvidence, reconcileGeneratedQueue,
    assertGeneratedBatch, batchFingerprint, snapshotRunnerBatchFingerprints,
    assertFreshGeneratedBatch, selectRunnerBatchByHash, waitForFreshGeneratedBatch,
    buildQueueContract, validateQueueContract, activeRunnerBatch,
    assertBatchMatchesContract, requireActiveRunnerBatch, assertStartedBatchWithContract,
    assertRecoverableStartedBatch, validateCompletedResults, registerBatch,
    adoptExistingRunnerBatch, prepareAndStart, executeCommand, restoreConnection,
    uploadMergedJson, heartbeat, state
  });
})();
`,
);

assert.notEqual(testSource, source, "Bridge test hook was not injected");

const STORAGE_KEY = "amazon-selection-console-bridge-v2";
const RUNNER_PREFIX = "ssIntegratedRunner:v0.3:";
const HISTORY_KEY = `${RUNNER_PREFIX}strict-qualified-history`;

function asin(index) {
  return `B0${String(index).padStart(8, "0")}`;
}

function sha256Queue(queue) {
  return createHash("sha256").update(`${queue.join("\n")}\n`, "ascii").digest("hex");
}

function strictHistory(asins = []) {
  return {
    schemaVersion: "strictQualifiedHistory/v1",
    asins: Object.fromEntries(asins.map((value) => [value, { qualifiedAt: "2026-08-08T00:00:00.000Z", source: "strict_delivery" }])),
  };
}

function runnerBatch({
  batchName = "current-batch",
  queueHash = "1234abcd",
  queue = [asin(1), asin(2)],
  skipped = [],
  historyRegistryCount = skipped.length,
  status = "idle",
  currentIndex = 0,
  at = "2026-08-22T03:00:00.000Z",
  results = null,
  qualifiedCount = 0,
  rejectedCount = 0,
} = {}) {
  return {
    batchName,
    queueHash,
    queue: [...queue],
    historySkippedAsins: [...skipped],
    historySkippedCount: skipped.length,
    historyRegistryCount,
    status,
    currentIndex,
    generatedAt: at,
    createdAt: at,
    updatedAt: at,
    results: results ?? new Array(queue.length).fill(null),
    qualifiedCount,
    rejectedCount,
  };
}

function element(textContent = "") {
  return { textContent };
}

const validPanels = {
  runnerText: "卖家精灵一体化选品 0.3.8.13 收起",
  collectorText: "卖家精灵流量采集器 0.4.6.4 已就绪",
  delivery: {
    block: element("Delivering to New York 10010 Update location"),
    line1: element("Delivering to New York 10010"),
    line2: element("Update location"),
  },
};

function loadBridge({
  runnerText = validPanels.runnerText,
  collectorText = validPanels.collectorText,
  delivery = validPanels.delivery,
  captcha = false,
  signedOut = false,
  savedState = {},
  history = strictHistory(),
  batches = [],
  selected = "",
  runnerFactory = null,
  networkHandler = null,
} = {}) {
  const storage = new Map();
  storage.set(STORAGE_KEY, JSON.stringify(savedState));
  if (history !== undefined) storage.set(HISTORY_KEY, JSON.stringify(history));
  for (const batch of batches) storage.set(`${RUNNER_PREFIX}batch:${batch.queueHash}`, JSON.stringify(batch));
  if (selected) storage.set(`${RUNNER_PREFIX}selected`, selected);
  const requests = [];
  const runner = runnerFactory
    ? runnerFactory({ storage, requests })
    : { textContent: runnerText, querySelector() { return null; } };
  runner.textContent ||= runnerText;
  const collector = element(collectorText);
  const output = { value: "" };
  const selectors = new Map([
    ["#glow-ingress-block", delivery.block || null],
    ["#glow-ingress-line1", delivery.line1 || null],
    ["#glow-ingress-line2", delivery.line2 || null],
    ["#ss-v3-output", output],
  ]);
  const document = {
    querySelector(selector) {
      if (selector === "#captchacharacters, form[action*='validateCaptcha']") return captcha ? element() : null;
      if (selector === "form[name='signIn'], #ap_email") return signedOut ? element() : null;
      return selectors.get(selector) || null;
    },
    querySelectorAll(selector) {
      if (selector === "#ss-v3-panel") return [runner];
      if (selector === "#ss-collector-panel") return [collector];
      if (selector === "#glow-ingress-block, #glow-ingress-line1, #glow-ingress-line2") {
        return [delivery.block, delivery.line1, delivery.line2].filter(Boolean);
      }
      return [];
    },
  };
  const context = {
    crypto: webcrypto,
    TextEncoder,
    Uint8Array,
    document,
    Event: class Event {
      constructor(type, options = {}) { this.type = type; this.bubbles = Boolean(options.bubbles); }
    },
    localStorage: {
      getItem(key) { return storage.has(key) ? storage.get(key) : null; },
      setItem(key, value) { storage.set(key, String(value)); },
    },
    GM_xmlhttpRequest(options) {
      const url = new URL(options.url);
      const body = options.data ? JSON.parse(options.data) : null;
      requests.push({ path: url.pathname, method: options.method, body });
      const response = networkHandler ? networkHandler({ path: url.pathname, body, requests }) : { status: 200, body: { ok: true } };
      queueMicrotask(() => options.onload({ status: response.status, responseText: JSON.stringify(response.body || {}) }));
    },
    setTimeout,
    clearTimeout,
    console,
  };
  context.globalThis = context;
  vm.runInNewContext(testSource, context, { filename: "browser_bridge_v2.user.js" });
  return { bridge: context.__bridgeTest, storage, requests, runner, output };
}

function runnerFactory({ queueHash = "1234abcd", skip = [], generate = true, startMode = "running" } = {}) {
  return ({ storage }) => {
    const controls = { generateClicks: 0, startClicks: 0 };
    const inputs = Object.fromEntries(["name", "operator", "target", "remaining", "queue"].map((name) => [name, {
      value: "",
      dispatchEvent() {},
    }]));
    const picker = {
      value: storage.get(`${RUNNER_PREFIX}selected`) || "",
      options: [],
      dispatchEvent() { storage.set(`${RUNNER_PREFIX}selected`, this.value); },
    };
    const generateButton = {
      disabled: false,
      click() {
        controls.generateClicks += 1;
        if (!generate) return;
        const approved = inputs.queue.value.split(/\s+/).filter(Boolean);
        const skipSet = new Set(skip);
        const queue = approved.filter((value) => !skipSet.has(value));
        const history = JSON.parse(storage.get(HISTORY_KEY));
        const at = new Date().toISOString();
        const batch = runnerBatch({
          batchName: inputs.name.value,
          queueHash,
          queue,
          skipped: skip,
          historyRegistryCount: Object.keys(history.asins).length,
          at,
        });
        storage.set(`${RUNNER_PREFIX}batch:${queueHash}`, JSON.stringify(batch));
        storage.set(`${RUNNER_PREFIX}selected`, queueHash);
        picker.value = queueHash;
        picker.options = [{ value: queueHash, textContent: `${inputs.name.value} (${queueHash})` }];
      },
    };
    const startButton = {
      disabled: startMode === "disabled",
      click() {
        controls.startClicks += 1;
        if (startMode === "noop") return;
        const hash = storage.get(`${RUNNER_PREFIX}selected`);
        const batch = JSON.parse(storage.get(`${RUNNER_PREFIX}batch:${hash}`));
        batch.status = startMode;
        batch.currentIndex = 0;
        batch.currentStep = "navigate";
        batch.updatedAt = new Date().toISOString();
        storage.set(`${RUNNER_PREFIX}batch:${hash}`, JSON.stringify(batch));
      },
    };
    const map = new Map([
      ["#ss-v3-name", inputs.name], ["#ss-v3-operator", inputs.operator],
      ["#ss-v3-target", inputs.target], ["#ss-v3-remaining", inputs.remaining],
      ["#ss-v3-queue", inputs.queue], ["#ss-v3-picker", picker],
      ["#ss-v3-generate", generateButton], ["#ss-v3-start", startButton],
    ]);
    return { textContent: validPanels.runnerText, controls, querySelector(selector) { return map.get(selector) || null; } };
  };
}

test("accepts only the approved localized panels and US delivery ZIP", () => {
  const { bridge } = loadBridge();
  assert.doesNotThrow(() => bridge.runnerElements());
  assert.match(bridge.checkAmazonState("10010"), /10010/);
  assert.throws(() => loadBridge({ collectorText: "卖家精灵流量采集器 0.4.6.3" }).bridge.runnerElements(), /Collector 版本/);
  assert.throws(() => bridge.checkAmazonState("85008"), /配送地址/);
  assert.throws(() => loadBridge({ captcha: true }).bridge.checkAmazonState("10010"), /CAPTCHA/);
});

test("recomputes and requires the canonical console queue SHA-256", async () => {
  const queue = [asin(1), asin(2)];
  const { bridge } = loadBridge();
  assert.deepEqual(await bridge.assertConsoleQueueDigest({ queueAsins: queue, queueSha256: sha256Queue(queue) }), queue);
  await assert.rejects(bridge.assertConsoleQueueDigest({ queueAsins: queue, queueSha256: "" }), /SHA-256 缺失/);
  await assert.rejects(bridge.assertConsoleQueueDigest({ queueAsins: queue, queueSha256: "a".repeat(64) }), /与批准队列内容不一致/);
});

test("accepts the real 47 approved = 46 pending + one strict-history hit contract", () => {
  const skipped = "B0GZ2YV4VB";
  const approved = Array.from({ length: 47 }, (_, index) => asin(index + 1));
  approved[25] = skipped;
  const historyAsins = [skipped, ...Array.from({ length: 273 }, (_, index) => `B0H${String(index).padStart(7, "0")}`)];
  const { bridge } = loadBridge({ history: strictHistory(historyAsins) });
  const payload = { batchName: "vases", queueAsins: approved, queueSha256: sha256Queue(approved) };
  const actual = approved.filter((value) => value !== skipped);
  const verified = bridge.assertGeneratedBatch(runnerBatch({
    batchName: "vases", queue: actual, skipped: [skipped], historyRegistryCount: 274,
  }), payload);
  assert.equal(verified.bridgeQueueReconciliation.mode, "runner_history_skip");
  assert.equal(verified.bridgeQueueReconciliation.approvedQueueCount, 47);
  assert.equal(verified.bridgeQueueReconciliation.runnerQueueCount, 46);
  assert.deepEqual(verified.bridgeQueueReconciliation.historySkippedAsins, [skipped]);
});

test("rejects unknown omissions, reorder, extras, duplicate or invented skips", () => {
  const queue = [asin(1), asin(2), asin(3), asin(4)];
  const payload = { batchName: "current-batch", queueAsins: queue, queueSha256: sha256Queue(queue) };
  const { bridge } = loadBridge({ history: strictHistory([asin(2), asin(3)]) });
  const base = { batchName: "current-batch", historyRegistryCount: 2 };
  assert.throws(() => bridge.assertGeneratedBatch(runnerBatch({ ...base, queue: [asin(1), asin(3), asin(4)], skipped: [] }), payload), /实际队列不是/);
  assert.throws(() => bridge.assertGeneratedBatch(runnerBatch({ ...base, queue: [asin(3), asin(1), asin(4)], skipped: [asin(2)] }), payload), /无法重构/);
  assert.throws(() => bridge.assertGeneratedBatch(runnerBatch({ ...base, queue: [asin(1), asin(9), asin(3), asin(4)], skipped: [asin(2)] }), payload), /无法重构/);
  assert.throws(() => bridge.assertGeneratedBatch({ ...runnerBatch({ ...base, queue: [asin(1), asin(4)], skipped: [asin(2), asin(3)] }), historySkippedAsins: [asin(2), asin(2)] }, payload), /重复 ASIN/);
  assert.throws(() => bridge.assertGeneratedBatch(runnerBatch({ ...base, queue: [asin(1), asin(2), asin(3)], skipped: [asin(4)] }), payload), /缺少严格合格记录|无法重构/);
});

test("requires valid strict-history schema, count and nonempty member records", () => {
  const skipped = asin(2);
  const approved = [asin(1), skipped];
  const payload = { batchName: "current-batch", queueAsins: approved, queueSha256: sha256Queue(approved) };
  const batch = runnerBatch({ queue: [asin(1)], skipped: [skipped], historyRegistryCount: 1 });
  assert.throws(() => loadBridge({ history: null }).bridge.assertGeneratedBatch(batch, payload), /schema 无效/);
  assert.throws(() => loadBridge({ history: { schemaVersion: "wrong", asins: {} } }).bridge.assertGeneratedBatch(batch, payload), /schema 无效/);
  assert.throws(() => loadBridge({ history: { schemaVersion: "strictQualifiedHistory/v1", asins: { [skipped]: true } } }).bridge.assertGeneratedBatch(batch, payload), /记录无效/);
  assert.throws(() => loadBridge({ history: strictHistory([skipped]) }).bridge.assertGeneratedBatch({ ...batch, historyRegistryCount: -1 }, payload), /台账计数无效/);
  assert.throws(() => loadBridge({ history: strictHistory([skipped]) }).bridge.assertGeneratedBatch({ ...batch, historySkippedCount: 0 }, payload), /计数与清单不一致/);
  assert.doesNotThrow(() => loadBridge({ history: strictHistory([skipped, asin(3)]) }).bridge.assertGeneratedBatch(batch, payload));
});

test("accepts a same-name same-hash fresh reset and rejects stale or dirty batches", () => {
  const queue = [asin(1), asin(2)];
  const payload = { batchName: "same-name", queueAsins: queue, queueSha256: sha256Queue(queue) };
  const { bridge } = loadBridge();
  const old = runnerBatch({ batchName: "same-name", queue, at: "2026-08-22T02:00:00.000Z", status: "done", results: [{ targetAsin: asin(1) }, null] });
  const fresh = runnerBatch({ batchName: "same-name", queue, at: "2026-08-22T03:00:00.100Z" });
  const context = { startedAtMs: Date.parse("2026-08-22T03:00:00.000Z"), beforeFingerprints: [bridge.batchFingerprint(old)] };
  assert.doesNotThrow(() => bridge.assertFreshGeneratedBatch(fresh, payload, context));
  assert.throws(() => bridge.assertFreshGeneratedBatch(old, payload, context), /待开始状态|未产生本次/);
  assert.throws(() => bridge.assertFreshGeneratedBatch({ ...fresh, results: [{ targetAsin: asin(1) }, null] }, payload, context), /旧结果/);
  assert.throws(() => bridge.assertFreshGeneratedBatch({ ...fresh, generatedAt: "2026-08-22T02:59:59.999Z" }, payload, context), /未产生本次/);
});

test("persists the approved contract and revalidates it while history may only grow", async () => {
  const skipped = asin(2);
  const approved = [asin(1), skipped, asin(3)];
  const payload = { batchName: "contract", queueAsins: approved, queueSha256: sha256Queue(approved) };
  const generated = runnerBatch({ batchName: "contract", queue: [asin(1), asin(3)], skipped: [skipped], historyRegistryCount: 1 });
  const savedState = { batchId: "batch123", expectedBatchName: "contract", expectedQueueHash: "1234abcd" };
  const loaded = loadBridge({ savedState, history: strictHistory([skipped]), batches: [generated], selected: generated.queueHash });
  const verified = loaded.bridge.assertGeneratedBatch(generated, payload);
  const contract = loaded.bridge.buildQueueContract({ id: "cmd-contract", batchId: "batch123" }, payload, verified);
  loaded.bridge.state.queueContract = contract;
  assert.equal((await loaded.bridge.validateQueueContract()).runnerQueueAsins.length, 2);
  loaded.storage.set(HISTORY_KEY, JSON.stringify(strictHistory([skipped, asin(99)])));
  assert.doesNotThrow(() => loaded.bridge.assertBatchMatchesContract(generated, contract));
  loaded.storage.set(HISTORY_KEY, JSON.stringify(strictHistory([asin(99)])));
  assert.throws(() => loaded.bridge.assertBatchMatchesContract(generated, contract), /缺少严格合格记录/);
  loaded.storage.set(HISTORY_KEY, JSON.stringify(strictHistory([skipped, asin(99)])));
  assert.throws(() => loaded.bridge.assertBatchMatchesContract({ ...generated, queue: [asin(3), asin(1)] }, contract), /无法重构|偏离/);
});

test("allows strict history to grow between Runner Generate and Bridge reconciliation", () => {
  const skipped = asin(2);
  const approved = [asin(1), skipped, asin(3)];
  const payload = { batchName: "history-growth", queueAsins: approved, queueSha256: sha256Queue(approved) };
  const generated = runnerBatch({
    batchName: "history-growth",
    queue: [asin(1), asin(3)],
    skipped: [skipped],
    historyRegistryCount: 1,
  });
  const { bridge } = loadBridge({ history: strictHistory([skipped, asin(99)]) });
  assert.doesNotThrow(() => bridge.assertGeneratedBatch(generated, payload));
});

test("requires observed running state before a Start can be accepted", () => {
  const queue = [asin(1), asin(2)];
  const payload = { batchName: "start", queueAsins: queue, queueSha256: sha256Queue(queue) };
  const idle = runnerBatch({ batchName: "start", queue });
  const savedState = { batchId: "batch123" };
  const loaded = loadBridge({ savedState, batches: [idle], selected: idle.queueHash });
  const verified = loaded.bridge.assertGeneratedBatch(idle, payload);
  const contract = loaded.bridge.buildQueueContract({ batchId: "batch123" }, payload, verified);
  loaded.bridge.state.queueContract = contract;
  assert.throws(() => loaded.bridge.assertStartedBatchWithContract(contract), /状态 idle/);
  loaded.storage.set(`${RUNNER_PREFIX}batch:${idle.queueHash}`, JSON.stringify({ ...idle, status: "running", currentStep: "navigate" }));
  assert.equal(loaded.bridge.assertStartedBatchWithContract(contract).status, "running");
});

test("recovers a contract-matching running batch after it has advanced", () => {
  const queue = [asin(1), asin(2), asin(3)];
  const payload = { batchName: "advanced", queueAsins: queue, queueSha256: sha256Queue(queue) };
  const base = runnerBatch({ batchName: "advanced", queue });
  const advanced = {
    ...base,
    status: "running",
    currentIndex: 2,
    results: [{ targetAsin: asin(1) }, { targetAsin: asin(2) }, null],
  };
  const loaded = loadBridge({ savedState: { batchId: "batch123" }, batches: [advanced], selected: advanced.queueHash });
  const verified = loaded.bridge.assertGeneratedBatch(base, payload);
  const contract = loaded.bridge.buildQueueContract({ batchId: "batch123" }, payload, verified);
  loaded.bridge.state.queueContract = contract;
  assert.equal(loaded.bridge.assertRecoverableStartedBatch(contract).currentIndex, 2);
  loaded.storage.set(`${RUNNER_PREFIX}batch:${advanced.queueHash}`, JSON.stringify({ ...advanced, currentIndex: 1 }));
  assert.throws(() => loaded.bridge.assertRecoverableStartedBatch(contract), /当前行与已保存结果前缀/);
});

test("full start behavior audits before Start and confirms running before ACK", async () => {
  const queue = [asin(1), asin(2)];
  const payload = { batchName: "live-start", operator: "liyuanze", targetQualified: 20, queueAsins: queue, queueSha256: sha256Queue(queue), deliveryZip: "10010" };
  const loaded = loadBridge({
    savedState: { pairingToken: "pair-code" },
    runnerFactory: runnerFactory(),
  });
  await loaded.bridge.executeCommand({ id: "cmd1", batchId: "batch123", batchToken: "token", action: "start", payload });
  assert.equal(loaded.runner.controls.generateClicks, 1);
  assert.equal(loaded.runner.controls.startClicks, 1);
  assert.equal(loaded.bridge.state.connected, true);
  assert.deepEqual(loaded.requests.map((item) => item.path), ["/bridge/register", "/bridge/event", "/bridge/control/ack"]);
  assert.equal(loaded.requests[0].body.commandId, "cmd1");
  assert.equal(loaded.requests[0].body.executionMode, "generated_for_command");
  assert.equal(loaded.requests[1].body.commandId, "cmd1");
  assert.equal(loaded.requests.at(-1).body.status, "accepted");
});

test("registration audit failure or Start no-op never ACKs a false start", async () => {
  const queue = [asin(1), asin(2)];
  const payload = { batchName: "fail-start", operator: "liyuanze", targetQualified: 20, queueAsins: queue, queueSha256: sha256Queue(queue), deliveryZip: "10010" };
  const auditFailure = loadBridge({
    savedState: { pairingToken: "pair-code" },
    runnerFactory: runnerFactory(),
    networkHandler: ({ path }) => path === "/bridge/event" ? { status: 500, body: { error: "audit failed" } } : { status: 200, body: { ok: true } },
  });
  await auditFailure.bridge.executeCommand({ id: "cmd2", batchId: "batch123", batchToken: "token", action: "start", payload });
  assert.equal(auditFailure.runner.controls.startClicks, 0);
  assert.equal(auditFailure.bridge.state.connected, false);
  assert.equal(auditFailure.requests.at(-1).body.status, "failed");

  const noOp = loadBridge({ savedState: { pairingToken: "pair-code" }, runnerFactory: runnerFactory({ startMode: "noop" }) });
  await noOp.bridge.executeCommand({ id: "cmd3", batchId: "batch123", batchToken: "token", action: "start", payload });
  assert.equal(noOp.runner.controls.startClicks, 1);
  assert.equal(noOp.bridge.state.connected, false);
  assert.equal(noOp.requests.at(-1).body.status, "failed");
});

test("safely adopts an already running matching batch without regenerating or restarting", async () => {
  const skipped = asin(2);
  const approved = [asin(1), skipped, asin(3), asin(4)];
  const running = runnerBatch({
    batchName: "adopt-running",
    queue: [asin(1), asin(3), asin(4)],
    skipped: [skipped],
    historyRegistryCount: 1,
    status: "running",
    currentIndex: 2,
    results: [{ targetAsin: asin(1) }, { targetAsin: asin(3) }, null],
  });
  const payload = {
    batchName: "adopt-running", operator: "liyuanze", targetQualified: 20,
    queueAsins: approved, queueSha256: sha256Queue(approved), deliveryZip: "10010",
  };
  const loaded = loadBridge({
    savedState: { pairingToken: "pair-code" },
    history: strictHistory([skipped]),
    batches: [running],
    selected: running.queueHash,
    runnerFactory: runnerFactory(),
  });
  await loaded.bridge.executeCommand({ id: "cmd-adopt", batchId: "batch123", batchToken: "token", action: "start", payload });
  assert.equal(loaded.runner.controls.generateClicks, 0);
  assert.equal(loaded.runner.controls.startClicks, 0);
  assert.equal(loaded.bridge.state.connected, true);
  assert.equal(loaded.bridge.state.queueContract.runnerQueueHash, running.queueHash);
  assert.equal(loaded.bridge.state.queueContract.execution.mode, "adopted_existing");
  assert.deepEqual(loaded.requests.map((item) => item.path), ["/bridge/register", "/bridge/event", "/bridge/control/ack"]);
  assert.equal(loaded.requests[0].body.commandId, "cmd-adopt");
  assert.equal(loaded.requests[0].body.executionMode, "adopted_existing");
});

test("does not acknowledge a selected paused batch as a newly accepted Start", async () => {
  const queue = [asin(1), asin(2)];
  const paused = runnerBatch({ batchName: "paused-existing", queue, status: "paused" });
  const payload = { batchName: paused.batchName, queueAsins: queue, queueSha256: sha256Queue(queue) };
  const loaded = loadBridge({
    savedState: { pairingToken: "pair-code" },
    batches: [paused],
    selected: paused.queueHash,
  });
  await assert.rejects(
    loaded.bridge.adoptExistingRunnerBatch(
      { id: "cmd-paused", batchId: "batch123", batchToken: "token", action: "start", payload },
      payload,
    ),
    /当前批次已暂停/,
  );
  assert.equal(loaded.requests.length, 0);
  assert.equal(loaded.bridge.state.connected, false);
});

test("completed results must be a contiguous ordered prefix of the contracted queue", () => {
  const queue = [asin(1), asin(2), asin(3)];
  const { bridge } = loadBridge();
  const contract = { runnerQueueAsins: queue };
  assert.doesNotThrow(() => bridge.validateCompletedResults({ results: [{ targetAsin: asin(1) }, { targetAsin: asin(2) }, null] }, contract));
  assert.throws(() => bridge.validateCompletedResults({ results: [{ targetAsin: asin(2) }, null, null] }, contract), /结果 ASIN 顺序/);
  assert.throws(() => bridge.validateCompletedResults({ results: [null, { targetAsin: asin(2) }, null] }, contract), /连续写入/);
});

test("early-target completion uploads only the contiguous non-null result prefix", async () => {
  const queue = [asin(1), asin(2), asin(3)];
  const done = runnerBatch({
    batchName: "early-done",
    queue,
    status: "done",
    currentIndex: 2,
    results: [
      { targetAsin: asin(1), qualified: true },
      { targetAsin: asin(2), qualified: true },
      null,
    ],
  });
  const payload = { batchName: "early-done", queueAsins: queue, queueSha256: sha256Queue(queue) };
  const savedState = { batchId: "batch123", batchToken: "token", connected: true };
  const loaded = loadBridge({ savedState, batches: [done], selected: done.queueHash });
  const verified = loaded.bridge.assertGeneratedBatch(done, payload);
  loaded.bridge.state.queueContract = loaded.bridge.buildQueueContract({ id: "cmd-upload", batchId: "batch123" }, payload, verified);
  await loaded.bridge.uploadMergedJson();
  const upload = loaded.requests.find((item) => item.path === "/bridge/merged-json");
  assert.ok(upload, "merged JSON was uploaded");
  assert.equal(upload.body.mergedJson.results.length, 2);
  assert.equal(upload.body.mergedJson.results.some((row) => row == null), false);
  assert.equal(upload.body.mergedJson.bridgeExecution.mode, "generated_for_command");
  assert.equal(upload.body.commandId, "cmd-upload");
  assert.equal(upload.body.executionMode, "generated_for_command");
});

test("advertises script 2.1.6 and sends it on poll/register while preserving protocol 2.1.3", () => {
  assert.match(source, /@version\s+2\.1\.6/);
  assert.match(source, /const BRIDGE_VERSION = "2\.1\.3"/);
  assert.match(source, /const SCRIPT_VERSION = "2\.1\.6"/);
  assert.match(source, /\/bridge\/control\/poll[\s\S]*scriptVersion: SCRIPT_VERSION/);
  assert.match(source, /\/bridge\/register[\s\S]*scriptVersion: SCRIPT_VERSION/);
  assert.match(source, /Selection Console Bridge \$\{BRIDGE_VERSION\} \/ script \$\{SCRIPT_VERSION\}/);
});
