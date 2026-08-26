import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function loadCore(fileName, transform) {
  let source = fs.readFileSync(path.join(root, "scripts", fileName), "utf8");
  if (transform) source = transform(source);
  const sandbox = { console, globalThis: {}, location: { href: "https://www.amazon.com/dp/B0AAAA0001" }, URL };
  vm.runInNewContext(source, sandbox, { filename: fileName });
  return { core: sandbox.globalThis.SSIntegratedRunnerCore, source };
}

const baseline = loadCore("sellersprite_integrated_runner_v0.3.8.2_zh_excel.user.js");
const candidate = loadCore("sellersprite_integrated_runner_v0.3.10_fast_loop.user.js");
const disabled = loadCore("sellersprite_integrated_runner_v0.3.10_fast_loop.user.js", (source) =>
  source.replace("var ENABLE_FAST_LOOP_CONTROL = true;", "var ENABLE_FAST_LOOP_CONTROL = false;"),
);

assert.ok(candidate.core);
assert.equal(candidate.core.fastLoopControlEnabled, true);
assert.equal(candidate.core.fastLoopCheckpointBridgeEnabled, true);
assert.equal(candidate.core.singleRunnerLeaseEnabled, true);
assert.equal(candidate.core.fastLoopControlVersion, "fast-loop-control-v1");
assert.equal(candidate.core.transientFailureCircuitLimit, 3);

for (const functionName of [
  "buildDimensions",
  "buildPriceTrend",
  "classifyPriceSamples",
  "normalizeAsin",
  "parsePriceTooltip",
  "parseTrafficCollector",
  "evaluateTrafficGate",
  "collectorHasKnownTrafficFailure",
  "legacyCollectorRetryReason",
  "collectorRetryReason",
  "shouldRetryCollector",
  "evaluateDimensionsGate",
  "evaluatePriceGate",
  "currentPriceFromSamples",
  "isQualifiedResult",
  "summarizeResults",
  "buildRunnerGateLogRow",
  "buildHistorySkipGateLogRow",
  "buildRunnerTimingLogRow",
  "buildHistorySkipTimingLogRow",
  "attachRunnerTelemetry",
  "rowsToTsv",
  "uniqueAsins",
  "filterHistoricalQueue",
  "valueAfterLabel",
]) {
  assert.equal(candidate.core[functionName].toString(), baseline.core[functionName].toString(), `${functionName} changed`);
}

function transient(asin) {
  return {
    targetAsin: asin,
    status: "no_data",
    rejectionStage: "traffic",
    rejectionRule: "traffic_error",
    telemetry: { timing: { retryReason: "tooltip_not_ready" } },
  };
}

assert.equal(candidate.core.transientTrafficFailureReason(transient("B0AAAA0001")), "tooltip_not_ready");
assert.equal(candidate.core.transientTrafficFailureReason({
  targetAsin: "B0AAAA0001",
  status: "ok",
  rejectionStage: "traffic",
  rejectionRule: "traffic_recent4_min_below_70",
}), "");
assert.equal(candidate.core.transientTrafficFailureReason({
  targetAsin: "B0AAAA0001",
  asinMismatch: true,
  status: "no_data",
  rejectionRule: "traffic_error",
}), "");

const circuitState = { status: "running", transientTrafficFailureStreak: 0, transientTrafficFailureAsins: [] };
assert.equal(candidate.core.updateTransientFailureCircuit(circuitState, transient("B0AAAA0001"), 3).opened, false);
assert.equal(candidate.core.updateTransientFailureCircuit(circuitState, transient("B0AAAA0002"), 3).opened, false);
const opened = candidate.core.updateTransientFailureCircuit(circuitState, transient("B0AAAA0003"), 3);
assert.equal(opened.opened, true);
assert.equal(circuitState.status, "paused");
assert.equal(circuitState.currentStep, "circuit_open");
assert.deepEqual(Array.from(circuitState.transientTrafficFailureAsins), ["B0AAAA0001", "B0AAAA0002", "B0AAAA0003"]);
candidate.core.updateTransientFailureCircuit(circuitState, { status: "ok", strictDecision: "reject" }, 3);
assert.equal(circuitState.transientTrafficFailureStreak, 0);

const stopState = {
  targetQualified: 10,
  requestedFinalTargetAtStart: 10,
  results: Array.from({ length: 10 }, () => ({ strictDecision: "pass" })),
  offlineStrictQualifiedCount: 9,
};
assert.equal(candidate.core.stopDecision(stopState).stop, false, "browser passes cannot stop the fast loop");
stopState.offlineStrictQualifiedCount = 10;
assert.equal(candidate.core.stopDecision(stopState).reason, "offline_strict_target_reached");
assert.equal(disabled.core.stopDecision({ ...stopState, offlineStrictQualifiedCount: 9 }).reason, "target_reached");

const response = candidate.core.validateFastLoopCheckpointResponse({
  schemaVersion: "sellerSpriteFastLoopCheckpointResponse/v1",
  finalAuthority: false,
  productionHistoryUpdated: false,
  target: 10,
  qualifiedCount: 7,
  remainingTarget: 3,
  targetReached: false,
  attemptedCount: 65,
  checkpointId: "b001-r0065-test",
}, 10);
assert.equal(response.qualifiedCount, 7);
assert.equal(response.remainingTarget, 3);
assert.throws(() => candidate.core.validateFastLoopCheckpointResponse({
  schemaVersion: "sellerSpriteFastLoopCheckpointResponse/v1",
  finalAuthority: true,
  productionHistoryUpdated: false,
  target: 10,
  qualifiedCount: 10,
  remainingTarget: 0,
  targetReached: true,
}, 10), /越过/);

assert.equal(candidate.core.runnerLeaseDecision({}, "tab-a", 1000, 20000).allowed, true);
assert.equal(candidate.core.runnerLeaseDecision({ ownerId: "tab-b", expiresAtMs: 5000 }, "tab-a", 1000, 20000).allowed, false);
assert.equal(candidate.core.runnerLeaseDecision({ ownerId: "tab-b", expiresAtMs: 999 }, "tab-a", 1000, 20000).allowed, true);
assert.equal(candidate.core.runnerLeaseDecision({ ownerId: "tab-a", expiresAtMs: 5000 }, "tab-a", 1000, 20000).ownedByCaller, true);

let historyWrites = 0;
candidate.core.commitCompletedRow(
  { queue: ["B0AAAA0001"], results: [null], currentIndex: 0 },
  0,
  { targetAsin: "B0AAAA0001", strictDecision: "pass", finishedAt: "2026-07-31T00:00:00Z" },
  () => {},
  () => { historyWrites += 1; return { asins: {} }; },
  () => ({ asins: {} }),
);
assert.equal(historyWrites, 0, "browser-only pass must not enter strict history");

assert.match(candidate.source, /@version\s+0\.3\.10/);
assert.match(candidate.source, /\/api\/v1\/checkpoint/);
assert.match(candidate.source, /FAST_LOOP_CONTROL_VERSION/);
assert.match(candidate.source, /setTimeout\(exportAcceptedExcel, 0\)/);

console.log("SellerSprite fast-loop Runner 0.3.10: PASS");
