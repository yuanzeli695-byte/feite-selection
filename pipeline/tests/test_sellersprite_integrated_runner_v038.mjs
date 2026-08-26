import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function loadCore(fileName, transform) {
  let source = fs.readFileSync(path.join(root, "scripts", fileName), "utf8");
  if (transform) source = transform(source);
  const sandbox = { console, globalThis: {} };
  vm.runInNewContext(source, sandbox, { filename: fileName });
  return { core: sandbox.globalThis.SSIntegratedRunnerCore, source };
}

const baseline = loadCore("sellersprite_integrated_runner_v0.3.7.user.js");
const next = loadCore("sellersprite_integrated_runner_v0.3.8.user.js");
const disabled = loadCore("sellersprite_integrated_runner_v0.3.8.user.js", (source) =>
  source.replace(
    "var ENABLE_P1_CUMULATIVE_TARGET_CONTROL = true;",
    "var ENABLE_P1_CUMULATIVE_TARGET_CONTROL = false;",
  ).replace(
    "var ENABLE_TIER0_GRANULAR_TELEMETRY = true;",
    "var ENABLE_TIER0_GRANULAR_TELEMETRY = false;",
  ),
);

assert.ok(baseline.core);
assert.ok(next.core);
assert.equal(next.core.cumulativeTargetControlEnabled, true);
assert.equal(next.core.granularTelemetryEnabled, true);
assert.equal(next.core.targetControlVersion, "p1-cumulative-remaining-v1");
assert.equal(next.core.granularTelemetryVersion, "tier0.2-granular-v1");
assert.equal(disabled.core.cumulativeTargetControlEnabled, false);
assert.equal(disabled.core.granularTelemetryEnabled, false);

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
  assert.equal(
    next.core[functionName].toString(),
    baseline.core[functionName].toString(),
    `${functionName} must remain unchanged in P1`,
  );
}

assert.equal(JSON.stringify(next.core.timingLogColumns), JSON.stringify(baseline.core.timingLogColumns));
assert.ok(next.core.granularTimingColumns.includes("persistenceTotalMs"));
assert.ok(next.core.granularTimingColumns.includes("collectorAttempts"));
assert.ok(next.core.controlEventColumns.includes("pauseDurationMs"));

const legacy = { targetQualified: 20, results: [{ strictDecision: "reject" }] };
assert.equal(next.core.effectiveStopBudget(legacy), 20);
assert.equal(next.core.stopDecision(legacy).stop, false);

const cumulative = {
  targetQualified: 10,
  requestedFinalTargetAtStart: 10,
  remainingTargetAtStart: 2,
  targetControlVersion: "p1-cumulative-remaining-v1",
  results: [{ strictDecision: "pass" }, { strictDecision: "reject" }],
};
assert.equal(next.core.effectiveStopBudget(cumulative), 2);
assert.equal(next.core.browserPassesThisBatch(cumulative), 1);
assert.equal(next.core.stopDecision(cumulative).stop, false);
cumulative.results.push({ strictDecision: "pass" });
assert.equal(next.core.stopDecision(cumulative).reason, "target_reached");
assert.equal(next.core.stopDecision(cumulative).action, "stop_after_current_row");

const zero = { targetQualified: 10, requestedFinalTargetAtStart: 10, remainingTargetAtStart: 0, targetControlVersion: "p1-cumulative-remaining-v1", results: [] };
assert.equal(next.core.stopDecision(zero).reason, "target_already_reached");

const requested = next.core.requestStopAfterCurrentRow({ targetQualified: 2, results: [] }, "operator_test");
assert.equal(requested.stopAfterCurrentRowRequested, true);
assert.equal(requested.stopAction, "operator_test");
assert.equal(next.core.stopDecision(requested).reason, "operator_stop_after_current_row");

const invalid = { targetQualified: 2, targetControlVersion: "p1-cumulative-remaining-v1", remainingTargetAtStart: "bad", results: [] };
assert.equal(next.core.stopDecision(invalid).reason, "invalid_target_control");

const flagOff = {
  targetQualified: 10,
  requestedFinalTargetAtStart: 10,
  remainingTargetAtStart: 1,
  targetControlVersion: "p1-cumulative-remaining-v1",
  results: [],
};
assert.equal(disabled.core.normalizeTargetControl(flagOff).mode, "legacy_batch");
assert.equal(disabled.core.effectiveStopBudget(flagOff), 10);

const inFlightState = {
  queueHash: "control-hash",
  status: "running",
  stopAfterCurrentRowRequested: false,
  stopAction: "",
  currentStep: "traffic",
};
next.core.mergeLatestControlState(inFlightState, {
  queueHash: "control-hash",
  status: "paused",
  stopAfterCurrentRowRequested: true,
  stopAction: "operator_stop_after_current_row",
  pauseId: "pause-1",
});
assert.equal(inFlightState.status, "paused");
assert.equal(inFlightState.stopAfterCurrentRowRequested, true);
assert.equal(inFlightState.stopAction, "operator_stop_after_current_row");
assert.equal(inFlightState.currentStep, "traffic");

const fallbackSidecar = {
  schemaVersion: "sellerSpriteGranularTelemetry/v1",
  queueHash: "abc123",
  batchCreatedAt: "2026-07-15T00:00:00Z",
  rowsByIndex: {},
  controlEvents: [],
};
const latestSidecar = {
  schemaVersion: "sellerSpriteGranularTelemetry/v1",
  queueHash: "abc123",
  batchCreatedAt: "2026-07-15T00:00:00Z",
  rowsByIndex: {},
  controlEvents: [{ event: "pause_requested" }],
};
const mergedSidecar = next.core.mergeGranularRowSidecar(latestSidecar, fallbackSidecar, 3, { asin: "B0TEST0001" });
assert.equal(mergedSidecar.controlEvents.length, 1);
assert.equal(mergedSidecar.rowsByIndex["3"].asin, "B0TEST0001");
const staleSidecar = { ...latestSidecar, batchCreatedAt: "2026-07-14T00:00:00Z" };
const isolatedSidecar = next.core.mergeGranularRowSidecar(staleSidecar, fallbackSidecar, 4, { asin: "B0TEST0002" });
assert.equal(isolatedSidecar, fallbackSidecar);
assert.equal(isolatedSidecar.rowsByIndex["4"].asin, "B0TEST0002");

assert.ok(next.source.includes("@version      0.3.8"));
assert.ok(next.source.includes("ENABLE_P1_CUMULATIVE_TARGET_CONTROL"));
assert.ok(next.source.includes("Stop after current row"));
assert.ok(next.source.includes("state.targetQualified = targetControl.requestedFinalTargetAtStart"));
assert.ok(next.source.includes("mergeGranularRowSidecar(latestSidecar"));
assert.ok(next.source.includes("mergeLatestControlState(state, loadBatch(state.queueHash))"));
assert.ok(next.source.includes("clearGranularSidecar(hash)"));
assert.match(next.source, /function saveGranularSidecar[\s\S]*?catch \(error\)/);
assert.ok(next.source.includes("}, 18000, 250);"));
assert.ok(next.source.includes("}, 15000, 250);"));
assert.ok(next.source.includes("}, 5000, 100);"));
assert.ok(next.source.includes("}, 45000, 250);"));
assert.ok(next.source.includes("await sleep(600);"));

console.log("SellerSprite Integrated Runner 0.3.8 P1 tests: PASS");
