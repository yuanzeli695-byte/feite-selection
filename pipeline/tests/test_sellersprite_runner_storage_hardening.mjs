import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const runnerPath = path.join(root, "scripts", "sellersprite_integrated_runner_v0.3.8_zh_excel.user.js");
const source = fs.readFileSync(runnerPath, "utf8");
const sandbox = { console, globalThis: {} };
vm.runInNewContext(source, sandbox, { filename: runnerPath });
const core = sandbox.globalThis.SSIntegratedRunnerCore;

const PREFIX = "ssIntegratedRunner:v0.3:";
const INDEX_KEY = `${PREFIX}index`;
const SELECTED_KEY = `${PREFIX}selected`;
const HISTORY_KEY = `${PREFIX}strict-qualified-history`;
const batchKey = (hash) => `${PREFIX}batch:${hash}`;
const sidecarKey = (hash) => `${PREFIX}granular:v1:${hash}`;

class FakeStorage {
  constructor(quota = Number.POSITIVE_INFINITY) {
    this.map = new Map();
    this.quota = quota;
    this.setCalls = 0;
  }

  get length() {
    return this.map.size;
  }

  key(index) {
    return Array.from(this.map.keys())[index] ?? null;
  }

  getItem(key) {
    return this.map.has(String(key)) ? this.map.get(String(key)) : null;
  }

  setItem(key, value) {
    key = String(key);
    value = String(value);
    const next = new Map(this.map);
    next.set(key, value);
    const size = Array.from(next.entries()).reduce((total, [entryKey, entryValue]) => total + entryKey.length + entryValue.length, 0);
    if (size > this.quota) {
      const error = new Error(`Quota exceeded: ${size} > ${this.quota}`);
      error.name = "QuotaExceededError";
      error.code = 22;
      throw error;
    }
    this.map = next;
    this.setCalls += 1;
  }

  removeItem(key) {
    this.map.delete(String(key));
  }

  seed(key, value) {
    this.map.set(String(key), String(value));
  }

  usage() {
    return Array.from(this.map.entries()).reduce((total, [key, value]) => total + key.length + value.length, 0);
  }
}

function asinAt(index) {
  return `B0${String(index).padStart(8, "0")}`;
}

function makeState(hash, rowCount = 1, results = []) {
  return {
    schemaVersion: "sellerSpriteIntegratedBatch/v0.3.0",
    runnerVersion: "0.3.8.1",
    batchName: `batch-${hash}`,
    queueHash: hash,
    createdAt: "2026-07-28T00:00:00.000Z",
    updatedAt: "2026-07-28T00:00:00.000Z",
    targetQualified: 2,
    requestedFinalTargetAtStart: 2,
    remainingTargetAtStart: 2,
    targetControlVersion: "p1-cumulative-remaining-v1",
    queue: Array.from({ length: rowCount }, (_, index) => asinAt(index + 1)),
    results: results.slice(),
    currentIndex: 0,
    currentStep: "traffic",
    status: "running",
    historySkippedAsins: [],
  };
}

function storedJson(storage, key) {
  return JSON.parse(storage.getItem(key));
}

assert.ok(core);
assert.equal(core.storageHardeningEnabled, true);
assert.equal(core.deferredFullJsonEnabled, true);
assert.equal(core.storageHardeningVersion, "storage-hardening-v1");
assert.equal(core.deferredFullJsonVersion, "deferred-full-json-v1");

{
  const storage = new FakeStorage();
  const oldState = makeState("quota-recovery", 1, []);
  storage.seed(batchKey(oldState.queueHash), JSON.stringify(oldState));
  storage.seed(INDEX_KEY, JSON.stringify([{ queueHash: oldState.queueHash, batchName: oldState.batchName, createdAt: oldState.createdAt }]));
  storage.seed(SELECTED_KEY, oldState.queueHash);
  storage.seed(sidecarKey(oldState.queueHash), JSON.stringify({
    schemaVersion: "sellerSpriteGranularTelemetry/v1",
    queueHash: oldState.queueHash,
    batchCreatedAt: oldState.createdAt,
    padding: "x".repeat(12_000),
  }));
  const nextState = makeState(oldState.queueHash, 100, Array.from({ length: 100 }, (_, index) => ({
    row: index + 1,
    targetAsin: asinAt(index + 1),
    strictDecision: index === 0 ? "pass" : "reject",
    note: "evidence".repeat(5),
  })));
  const withoutSidecar = new FakeStorage();
  withoutSidecar.seed(batchKey(oldState.queueHash), JSON.stringify(oldState));
  withoutSidecar.seed(INDEX_KEY, storage.getItem(INDEX_KEY));
  withoutSidecar.seed(SELECTED_KEY, oldState.queueHash);
  withoutSidecar.quota = Number.POSITIVE_INFINITY;
  core.persistBatchStorageWithRecovery(withoutSidecar, nextState);
  storage.quota = withoutSidecar.usage() + 128;
  core.persistBatchStorageWithRecovery(storage, nextState);
  assert.equal(storage.getItem(sidecarKey(oldState.queueHash)), null, "quota recovery must evict only the current non-authoritative sidecar");
  assert.equal(storedJson(storage, batchKey(oldState.queueHash)).results.length, 100);
}

{
  const storage = new FakeStorage();
  const oldState = makeState("fatal-quota", 1, []);
  storage.seed(batchKey(oldState.queueHash), JSON.stringify(oldState));
  storage.seed(INDEX_KEY, JSON.stringify([{ queueHash: oldState.queueHash, batchName: oldState.batchName, createdAt: oldState.createdAt }]));
  storage.seed(SELECTED_KEY, oldState.queueHash);
  storage.quota = storage.usage() + 300;
  const oversized = makeState(oldState.queueHash, 100, Array.from({ length: 100 }, (_, index) => ({
    row: index + 1,
    targetAsin: asinAt(index + 1),
    strictDecision: "reject",
    evidence: "y".repeat(500),
  })));
  assert.throws(
    () => core.persistBatchStorageWithRecovery(storage, oversized),
    (error) => error && error.code === "SS_STORAGE_PERSISTENCE_FAILED",
  );
  const persisted = storedJson(storage, batchKey(oldState.queueHash));
  assert.equal(persisted.currentIndex, 0);
  assert.equal(persisted.results.length, 0, "failed retry must leave the last-good row state intact");
}

{
  const storage = new FakeStorage();
  const state = makeState("hundred-rows", 100, Array.from({ length: 100 }, (_, index) => ({
    row: index + 1,
    targetAsin: asinAt(index + 1),
    strictDecision: index % 2 ? "reject" : "pass",
  })));
  core.persistBatchStorageWithRecovery(storage, state);
  assert.equal(storedJson(storage, batchKey(state.queueHash)).results.length, 100, "100-row evidence must persist without truncation");
  assert.equal(storedJson(storage, INDEX_KEY).length, 1);
}

{
  const storage = new FakeStorage();
  for (let index = 0; index < 40; index += 1) {
    const state = makeState(`reattach-${String(index).padStart(2, "0")}`, 1, []);
    state.createdAt = `2026-07-28T${String(index % 24).padStart(2, "0")}:00:00.000Z`;
    state.updatedAt = state.createdAt;
    storage.seed(batchKey(state.queueHash), JSON.stringify(state));
  }
  storage.seed(INDEX_KEY, "[]");
  const result = core.reconcileStorageRecords(storage, null);
  assert.equal(result.index.length, 40, "all valid batch keys must be reattached without a 30-entry cap");
  assert.equal(storedJson(storage, INDEX_KEY).length, 40);
}

{
  const storage = new FakeStorage();
  const first = makeState("valid-a", 1, []);
  const second = makeState("valid-b", 1, []);
  second.createdAt = "2026-07-28T01:00:00.000Z";
  second.updatedAt = second.createdAt;
  storage.seed(batchKey(first.queueHash), JSON.stringify(first));
  storage.seed(batchKey(second.queueHash), JSON.stringify(second));
  storage.seed(`${PREFIX}batch:broken`, "{not-json");
  storage.seed(INDEX_KEY, JSON.stringify([
    { queueHash: first.queueHash, batchName: first.batchName, createdAt: first.createdAt },
    { queueHash: "missing", batchName: "missing", createdAt: "" },
  ]));
  storage.seed(SELECTED_KEY, "missing");
  storage.seed(sidecarKey(first.queueHash), JSON.stringify({
    schemaVersion: "sellerSpriteGranularTelemetry/v1",
    queueHash: first.queueHash,
    batchCreatedAt: first.createdAt,
  }));
  storage.seed(sidecarKey("missing"), JSON.stringify({ queueHash: "missing", batchCreatedAt: "" }));
  const result = core.reconcileStorageRecords(storage, null);
  assert.deepEqual(Array.from(result.index, (item) => item.queueHash), [first.queueHash, second.queueHash]);
  assert.equal(result.selectedHash, first.queueHash);
  assert.notEqual(storage.getItem(sidecarKey(first.queueHash)), null, "valid sidecar must remain");
  assert.equal(storage.getItem(sidecarKey("missing")), null, "orphan sidecar must be removed");
  assert.notEqual(storage.getItem(batchKey(first.queueHash)), null, "valid batch A must remain");
  assert.notEqual(storage.getItem(batchKey(second.queueHash)), null, "valid batch B must remain");
  assert.notEqual(storage.getItem(`${PREFIX}batch:broken`), null, "automatic reconciliation must not delete batch records");
  storage.setCalls = 0;
  core.reconcileStorageRecords(storage, null);
  assert.equal(storage.setCalls, 0, "unchanged reconciliation must not rewrite index or selected state");
}

{
  const storage = new FakeStorage();
  const completed = makeState("completed-delete", 1, []);
  completed.status = "done";
  const running = makeState("running-keep", 1, []);
  running.createdAt = "2026-07-28T03:00:00.000Z";
  running.updatedAt = running.createdAt;
  storage.seed(batchKey(completed.queueHash), JSON.stringify(completed));
  storage.seed(batchKey(running.queueHash), JSON.stringify(running));
  storage.seed(sidecarKey(completed.queueHash), JSON.stringify({
    schemaVersion: "sellerSpriteGranularTelemetry/v1",
    queueHash: completed.queueHash,
    batchCreatedAt: completed.createdAt,
  }));
  storage.seed(INDEX_KEY, JSON.stringify([
    { queueHash: completed.queueHash, batchName: completed.batchName, createdAt: completed.createdAt },
    { queueHash: running.queueHash, batchName: running.batchName, createdAt: running.createdAt },
  ]));
  storage.seed(SELECTED_KEY, completed.queueHash);
  const removed = core.removeCompletedBatchStorage(storage, completed.queueHash);
  assert.equal(removed.removedQueueHash, completed.queueHash);
  assert.equal(storage.getItem(batchKey(completed.queueHash)), null);
  assert.equal(storage.getItem(sidecarKey(completed.queueHash)), null);
  assert.notEqual(storage.getItem(batchKey(running.queueHash)), null, "other valid batches must remain");
  assert.equal(storage.getItem(SELECTED_KEY), running.queueHash, "selection must move to a remaining valid batch");
  assert.throws(
    () => core.removeCompletedBatchStorage(storage, running.queueHash),
    /只有状态为 done/,
  );
  assert.notEqual(storage.getItem(batchKey(running.queueHash)), null, "unfinished batch deletion must fail closed");
}

{
  const state = {
    toJSON() {
      throw new Error("full JSON serialization must be deferred");
    },
  };
  assert.match(core.panelOutputValue(state), /延迟生成/);
}

{
  const storage = new FakeStorage();
  const oldState = makeState("history-order", 1, []);
  storage.seed(batchKey(oldState.queueHash), JSON.stringify(oldState));
  storage.seed(INDEX_KEY, JSON.stringify([{ queueHash: oldState.queueHash, batchName: oldState.batchName, createdAt: oldState.createdAt }]));
  storage.seed(SELECTED_KEY, oldState.queueHash);
  storage.quota = storage.usage() + 200;
  const nextState = makeState(oldState.queueHash, 1, []);
  const result = {
    row: 1,
    targetAsin: nextState.queue[0],
    strictDecision: "pass",
    finishedAt: "2026-07-28T02:00:00.000Z",
    evidence: "z".repeat(5_000),
  };
  let historyWrites = 0;
  let historyReads = 0;
  assert.throws(
    () => core.commitCompletedRow(
      nextState,
      0,
      result,
      (state) => core.persistBatchStorageWithRecovery(storage, state),
      (asin) => {
        historyWrites += 1;
        storage.setItem(HISTORY_KEY, JSON.stringify({ schemaVersion: "strictQualifiedHistory/v1", asins: { [asin]: {} } }));
        return storedJson(storage, HISTORY_KEY);
      },
      () => {
        historyReads += 1;
        return { schemaVersion: "strictQualifiedHistory/v1", asins: {} };
      },
    ),
    (error) => error && error.code === "SS_STORAGE_PERSISTENCE_FAILED",
  );
  assert.equal(historyReads, 0, "strict history must not be read before result persistence succeeds");
  assert.equal(historyWrites, 0, "strict history must not be written before result persistence succeeds");
  assert.equal(storage.getItem(HISTORY_KEY), null);
}

assert.doesNotMatch(source, /index\.slice\(0, 30\)/, "hardened path must not truncate the batch index");
assert.match(source, /ENABLE_STORAGE_HARDENING = true/);
assert.match(source, /ENABLE_DEFERRED_FULL_JSON = true/);
assert.match(source, /function clearSelectedBatch[\s\S]*?inventory\.orphanSidecarKeys\.concat\(inventory\.invalidBatchKeys\)/);
assert.doesNotMatch(source, /function clearSelectedBatch[\s\S]*?localStorage\.removeItem\(stateKey\(/);
assert.match(source, /删除已完成批次/);

console.log("SellerSprite Runner 0.3.8.1 storage hardening tests: PASS");
