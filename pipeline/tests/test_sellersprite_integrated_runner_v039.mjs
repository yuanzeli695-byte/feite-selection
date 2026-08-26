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

const baseline = loadCore("sellersprite_integrated_runner_v0.3.8.user.js");
const next = loadCore("sellersprite_integrated_runner_v0.3.9.user.js");
const disabled = loadCore("sellersprite_integrated_runner_v0.3.9.user.js", (source) =>
  source.replace(
    "var ENABLE_P1_CUMULATIVE_TARGET_CONTROL = true;",
    "var ENABLE_P1_CUMULATIVE_TARGET_CONTROL = false;",
  ).replace(
    "var ENABLE_TIER0_GRANULAR_TELEMETRY = true;",
    "var ENABLE_TIER0_GRANULAR_TELEMETRY = false;",
  ).replace(
    "var ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL = true;",
    "var ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL = false;",
  ),
);

assert.ok(baseline.core);
assert.ok(next.core);
assert.equal(next.core.cumulativeTargetControlEnabled, true);
assert.equal(next.core.granularTelemetryEnabled, true);
assert.equal(next.core.targetControlVersion, "p1-cumulative-remaining-v1");
assert.equal(next.core.granularTelemetryVersion, "tier0.2-granular-v1");
assert.equal(next.core.collectorDeadlineProtocolEnabled, true);
assert.equal(next.core.collectorDeadlineProtocolName, "p2-collector-owned-deadline-v1");
assert.equal(next.core.collectorDeadlineProtocolVersion, "2");
assert.equal(next.core.p2PairSandboxHistoryEnabled, true);
assert.equal(next.core.productionStrictHistoryKey, "ssIntegratedRunner:v0.3:strict-qualified-history");
assert.equal(next.core.p2SandboxHistoryKey, "ssIntegratedRunner:v0.3:p2-paired-sandbox-history:on");
assert.equal(disabled.core.cumulativeTargetControlEnabled, false);
assert.equal(disabled.core.granularTelemetryEnabled, false);
assert.equal(disabled.core.collectorDeadlineProtocolEnabled, false);

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

const pendingState = {
  status: "paused",
  currentStep: "traffic",
  currentIndex: 1,
  queue: ["B0AAAA0001", "B0AAAA0002"],
  results: [{ strictDecision: "reject" }, null],
  pendingCollectorProtocolPauseCount: 2,
  pendingCollectorProtocolPauseReasons: ["watchdog_page_hidden_or_throttled"],
};
assert.deepEqual(JSON.parse(JSON.stringify(next.core.pendingRecoverySummary(pendingState))), {
  schemaVersion: "collectorProtocolPendingRecovery/v1",
  state: "pending-recovery",
  count: 1,
  asins: ["B0AAAA0002"],
  pauseAttempts: 2,
  reasons: ["watchdog_page_hidden_or_throttled"],
});
assert.equal(next.core.batchFinishDecision(pendingState).allow, false);
assert.equal(
  next.core.pendingRecoverySummary({ ...pendingState, pendingCollectorProtocolPauseCount: 0 }).state,
  "pending-recovery",
  "a manually paused unfinished row is also explicit pending recovery",
);
assert.equal(next.core.batchFinishDecision({ ...pendingState, status: "running" }).allow, true);

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

const compatibleSnapshot = {
  collectorVersion: "0.4.7",
  p2Enabled: "1",
  protocolVersion: "2",
  protocolName: "p2-collector-owned-deadline-v1",
  deadlineOwner: "collector",
};
assert.deepEqual(
  JSON.parse(JSON.stringify(next.core.collectorProtocolCompatibility(compatibleSnapshot))),
  { ok: true, reason: "" },
);
assert.equal(
  next.core.collectorProtocolCompatibility({ ...compatibleSnapshot, collectorVersion: "0.4.6" }).reason,
  "collector_version_mismatch",
);
assert.equal(
  next.core.collectorProtocolCompatibility({ ...compatibleSnapshot, deadlineOwner: "runner" }).reason,
  "collector_deadline_owner_mismatch",
);
assert.equal(
  next.core.collectorProtocolCompatibility({ ...compatibleSnapshot, p2Enabled: "0" }).reason,
  "collector_p2_flag_mismatch",
);

const validationIdentity = next.core.collectorValidationIdentity(true, [{
  collectorVersion: "0.4.7",
  collectorP2Enabled: "1",
  protocolName: "p2-collector-owned-deadline-v1",
  protocolVersion: "2",
  deadlineOwner: "collector",
}]);
assert.deepEqual(JSON.parse(JSON.stringify(validationIdentity)), {
  runnerP2Enabled: true,
  collectorVersion: "0.4.7",
  collectorP2Enabled: true,
  protocolName: "p2-collector-owned-deadline-v1",
  protocolVersion: "2",
  deadlineOwner: "collector",
  attemptCount: 1,
  complete: true,
});
assert.equal(next.core.collectorValidationIdentity(false, []).complete, false);
assert.deepEqual(
  JSON.parse(JSON.stringify(next.core.strictHistorySnapshot({
    schemaVersion: "strictQualifiedHistory/v1",
    asins: { B0BBBBBBBB: {}, B0AAAAAAAA: {} },
  }))),
  {
    schemaVersion: "strictQualifiedHistorySnapshot/v1",
    sourceSchemaVersion: "strictQualifiedHistory/v1",
    asins: ["B0AAAAAAAA", "B0BBBBBBBB"],
  },
);

const runId = "p2-run-1";
const matchingSnapshot = {
  ...compatibleSnapshot,
  runId,
  deadlineRunId: runId,
  resultRunId: runId,
  resultReady: "1",
  phase: "result_ready",
  acceptedAtMs: 1_000,
  phaseStartAtMs: 10_000,
  heartbeatAtMs: 10_000,
  lastObservedAtMs: 10_000,
  clockAnomalyKind: "",
  clockAnomalyObservedAtMs: null,
  resultReadyAtMs: 10_000,
  hiddenObservedAtMs: null,
  visibilityState: "visible",
};
const matchingPayload = {
  runId,
  collectorVersion: "0.4.7",
  deadlineProtocol: {
    runId,
    protocolName: "p2-collector-owned-deadline-v1",
    protocolVersion: "2",
    deadlineOwner: "collector",
    phase: "result_ready",
    acceptedAtMs: 1_000,
    resultReadyAtMs: 10_000,
    lastObservedAtMs: 10_000,
    clockAnomalyKind: "",
    clockAnomalyObservedAtMs: null,
  },
};
assert.equal(next.core.matchingCollectorProtocolResult(matchingSnapshot, matchingPayload, runId), true);
assert.equal(next.core.matchingCollectorProtocolResult({ ...matchingSnapshot, resultRunId: "stale" }, matchingPayload, runId), false);
assert.equal(next.core.matchingCollectorProtocolResult(matchingSnapshot, { ...matchingPayload, runId: "stale" }, runId), false);
assert.equal(next.core.matchingCollectorProtocolResult(matchingSnapshot, { ...matchingPayload, collectorVersion: "0.4.6" }, runId), false);
assert.equal(
  next.core.matchingCollectorProtocolResult(
    matchingSnapshot,
    { ...matchingPayload, deadlineProtocol: { ...matchingPayload.deadlineProtocol, lastObservedAtMs: 9_999 } },
    runId,
  ),
  false,
  "payload and panel wall-clock evidence must match exactly",
);

assert.equal(next.core.collectorProtocolPreflightDecision({ ...compatibleSnapshot, running: "0" }).action, "click");
assert.equal(next.core.collectorProtocolPreflightDecision({ ...compatibleSnapshot, running: "1" }).reason, "collector_already_running");
assert.equal(
  next.core.collectorProtocolAcceptanceDecision(
    { runId: "old" },
    { ...compatibleSnapshot, runId, deadlineRunId: runId, running: "1", resultReady: "0", phase: "chart_wait", acceptedAtMs: 1000, phaseStartAtMs: 1000, phaseDeadlineAtMs: 61000, heartbeatAtMs: 1000, lastObservedAtMs: 1000, clockAnomalyKind: "", clockAnomalyObservedAtMs: null },
  ).action,
  "accepted",
);
assert.equal(
  next.core.collectorProtocolAcceptanceDecision(
    { runId },
    { ...compatibleSnapshot, runId, deadlineRunId: runId, running: "1", resultReady: "0", phase: "chart_wait", acceptedAtMs: 1000, phaseStartAtMs: 1000, phaseDeadlineAtMs: 61000, heartbeatAtMs: 1000, lastObservedAtMs: 1000, clockAnomalyKind: "", clockAnomalyObservedAtMs: null },
  ).reason,
  "collector_run_id_not_advanced",
);
assert.equal(
  next.core.collectorProtocolAcceptanceDecision(
    { runId: "old" },
    { ...compatibleSnapshot, runId, deadlineRunId: runId, running: "1", resultReady: "0", phase: "chart_wait", acceptedAtMs: 1000, phaseStartAtMs: 1000, phaseDeadlineAtMs: 61000, heartbeatAtMs: 1001, lastObservedAtMs: 1001, clockAnomalyKind: "", clockAnomalyObservedAtMs: null },
    1002,
  ).action,
  "accepted",
  "a normal heartbeat after acceptance must not be misclassified as a backward clock jump",
);
assert.equal(
  next.core.collectorProtocolAcceptanceDecision(
    { runId: "old" },
    { ...compatibleSnapshot, runId, deadlineRunId: runId, running: "1", resultReady: "0", phase: "chart_wait", acceptedAtMs: 1000, phaseStartAtMs: 1000, phaseDeadlineAtMs: 61000, heartbeatAtMs: 1001, lastObservedAtMs: 1001, clockAnomalyKind: "", clockAnomalyObservedAtMs: null },
    999,
  ).reason,
  "watchdog_wall_clock_backward",
  "a current wall clock earlier than accepted metadata must pause",
);

const waitingChartSnapshot = {
  ...matchingSnapshot,
  resultReady: "0",
  resultRunId: "",
  running: "1",
  phase: "chart_wait",
  phaseDeadlineAtMs: 61_000,
  phaseStartAtMs: 1_000,
  heartbeatAtMs: 15_500,
  lastObservedAtMs: 15_500,
  hiddenObservedAtMs: null,
  visibilityState: "visible",
};
assert.equal(next.core.collectorProtocolPollDecision(waitingChartSnapshot, null, runId, 15_900, "visible").action, "wait");
assert.equal(next.core.collectorProtocolPollDecision(waitingChartSnapshot, null, runId, 16_100, "visible").action, "wait");
const waitingChartNearDeadline = { ...waitingChartSnapshot, heartbeatAtMs: 65_500, lastObservedAtMs: 65_500 };
assert.equal(next.core.collectorProtocolPollDecision(waitingChartNearDeadline, null, runId, 65_999, "visible").action, "wait");
assert.equal(
  next.core.collectorProtocolPollDecision(waitingChartNearDeadline, null, runId, 66_001, "visible").reason,
  "watchdog_chart_deadline_unresolved_active",
);

const waitingScanSnapshot = {
  ...waitingChartSnapshot,
  phase: "tooltip_scan",
  phaseDeadlineAtMs: 46_000,
  heartbeatAtMs: 45_900,
  lastObservedAtMs: 45_900,
};
assert.equal(next.core.collectorProtocolPollDecision(waitingScanSnapshot, null, runId, 45_900, "visible").action, "wait");
assert.equal(
  next.core.collectorProtocolPollDecision(waitingScanSnapshot, null, runId, 46_100, "visible").reason,
  "watchdog_tooltip_scan_watchdog_exceeded_active",
);
assert.equal(
  next.core.collectorProtocolPollDecision({ ...waitingScanSnapshot, hiddenObservedAtMs: 30_000 }, null, runId, 46_100, "visible").reason,
  "watchdog_page_hidden_or_throttled",
);
assert.equal(next.core.collectorProtocolPollDecision(matchingSnapshot, matchingPayload, runId, 10_000, "visible").action, "payload");

const explicitClockAnomalySnapshot = {
  ...matchingSnapshot,
  clockAnomalyKind: "wall_clock_backward",
  clockAnomalyObservedAtMs: 9_999,
};
const explicitClockAnomalyPayload = {
  ...matchingPayload,
  deadlineProtocol: {
    ...matchingPayload.deadlineProtocol,
    clockAnomalyKind: "wall_clock_backward",
    clockAnomalyObservedAtMs: 9_999,
  },
};
assert.equal(next.core.matchingCollectorProtocolResult(explicitClockAnomalySnapshot, explicitClockAnomalyPayload, runId), false);
assert.deepEqual(
  JSON.parse(JSON.stringify(next.core.collectorProtocolPollDecision(
    explicitClockAnomalySnapshot,
    explicitClockAnomalyPayload,
    runId,
    10_000,
    "visible",
  ))),
  { action: "pause", reason: "watchdog_wall_clock_backward", watchdogClassification: "wall_clock_backward" },
  "explicit Collector clock anomalies must pause before payload acceptance",
);
assert.deepEqual(
  JSON.parse(JSON.stringify(next.core.collectorProtocolPollDecision(
    { ...matchingSnapshot, lastObservedAtMs: 10_001 },
    matchingPayload,
    runId,
    10_000,
    "visible",
  ))),
  { action: "pause", reason: "watchdog_wall_clock_backward", watchdogClassification: "wall_clock_backward" },
  "a backward NTP step inferred from now < lastObservedAtMs must never return payload",
);
assert.equal(
  next.core.collectorProtocolAcceptanceDecision(
    { runId: "old" },
    { ...compatibleSnapshot, runId, deadlineRunId: runId, running: "1", resultReady: "0", phase: "chart_wait", acceptedAtMs: 1000, phaseStartAtMs: 1000, phaseDeadlineAtMs: 61000, heartbeatAtMs: 1000, lastObservedAtMs: 999, clockAnomalyKind: "", clockAnomalyObservedAtMs: null },
  ).reason,
  "watchdog_wall_clock_backward",
  "a synchronously accepted run with a regressed clock cannot be accepted",
);
assert.equal(
  next.core.collectorProtocolPollDecision({ ...matchingSnapshot, hiddenObservedAtMs: 9_000 }, matchingPayload, runId, 10_000, "visible").reason,
  "watchdog_page_hidden_or_throttled",
);
assert.equal(
  next.core.collectorProtocolPollDecision({ ...matchingSnapshot, visibilityState: "hidden" }, matchingPayload, runId, 10_000, "visible").reason,
  "watchdog_page_hidden_or_throttled",
);
assert.equal(
  next.core.collectorProtocolPollDecision(matchingSnapshot, matchingPayload, runId, 10_000, "hidden").reason,
  "watchdog_page_hidden_or_throttled",
);
assert.equal(
  next.core.collectorProtocolPollDecision({ ...waitingChartSnapshot, running: "0" }, null, runId, 16_000, "visible").reason,
  "collector_stopped_without_result",
);

const rawCollectorPayload = {
  runId,
  status: "ok",
  details: [{ weekSort: 202627, totalTraffic: 100, naturalTraffic: 80, naturalSharePct: 80 }],
};
const capturedCollectorPayload = next.core.collectorEvidenceSnapshot(rawCollectorPayload);
assert.deepEqual(JSON.parse(JSON.stringify(capturedCollectorPayload)), rawCollectorPayload);
rawCollectorPayload.details[0].naturalTraffic = 0;
assert.equal(capturedCollectorPayload.details[0].naturalTraffic, 80, "capture must be detached from the live payload");

const attemptEvidence = next.core.collectorAttemptEvidence(rawCollectorPayload, null, {
  collectorRunId: runId,
  outcome: "payload",
  payloadAccepted: true,
});
assert.equal(attemptEvidence.outcome, "payload");
assert.equal(attemptEvidence.payload.runId, runId);
assert.equal(attemptEvidence.attemptSnapshot.payloadAccepted, true);

const recoveredState = {
  pendingCollectorProtocolPauseCount: 1,
  pendingCollectorProtocolPauseReasons: ["watchdog_page_hidden_or_throttled"],
  pendingCollectorProtocolStaleRunIds: ["stale-run"],
  pendingCollectorProtocolAttemptEvidence: [{ outcome: "error", error: "paused" }],
};
const recoveredEvidence = next.core.buildProtocolRecoveryEvidence(
  recoveredState,
  matchingPayload,
  [{ collectorRunId: runId, outcome: "payload", payloadAccepted: true }],
);
assert.equal(recoveredEvidence.pendingRecoveryState, "recovered");
assert.equal(recoveredEvidence.freshRunIdVerified, true);
assert.equal(recoveredEvidence.runIdentityConsistent, true);
assert.deepEqual(JSON.parse(JSON.stringify(recoveredEvidence.staleRunIds)), ["stale-run"]);
assert.equal(
  next.core.buildProtocolRecoveryEvidence(
    { ...recoveredState, pendingCollectorProtocolStaleRunIds: [runId] },
    matchingPayload,
    [{ collectorRunId: runId, outcome: "payload", payloadAccepted: true }],
  ).pendingRecoveryState,
  "invalid",
);

const historyIsolation = next.core.historyIsolationSnapshot(
  { schemaVersion: "strictQualifiedHistory/v1", asins: { B0AAAA0001: {} } },
  { schemaVersion: "strictQualifiedHistory/v1", asins: { B0AAAA0001: {} } },
);
assert.equal(historyIsolation.mode, "sandbox");
assert.equal(historyIsolation.p2Side, "on");
assert.equal(historyIsolation.productionWriteProtected, true);
assert.deepEqual(historyIsolation.productionSnapshot, historyIsolation.sandboxSeedSnapshot);

assert.equal(
  next.core.classifyCollectorWatchdog({ phase: "tooltip_scan", heartbeatAtMs: 9_000, visibilityState: "visible" }, 10_000, "visible"),
  "tooltip_scan_watchdog_exceeded_active",
);
assert.equal(
  next.core.classifyCollectorWatchdog({ phase: "chart_wait", heartbeatAtMs: 1_000, visibilityState: "visible" }, 10_000, "visible"),
  "collector_heartbeat_stale",
);
assert.equal(
  next.core.classifyCollectorWatchdog({ phase: "chart_wait", heartbeatAtMs: 9_000, visibilityState: "hidden" }, 10_000, "hidden"),
  "page_hidden_or_throttled",
);
assert.equal(
  next.core.classifyCollectorWatchdog({ phase: "chart_wait", heartbeatAtMs: 9_000, hiddenObservedAtMs: 8_000, visibilityState: "visible" }, 10_000, "visible"),
  "page_hidden_or_throttled",
);
assert.equal(
  next.core.classifyCollectorWatchdog({ phase: "chart_wait", acceptedAtMs: 9_000, phaseStartAtMs: 9_000, heartbeatAtMs: 10_001, lastObservedAtMs: 10_001, visibilityState: "visible" }, 10_000, "visible"),
  "wall_clock_backward",
);

assert.ok(next.source.includes("@version      0.3.9"));
assert.ok(next.source.includes("ENABLE_P1_CUMULATIVE_TARGET_CONTROL"));
assert.ok(next.source.includes("ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL"));
assert.ok(next.source.includes("p2-collector-owned-deadline-v1"));
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
assert.ok(next.source.includes("collector_run_id_not_advanced"));
assert.ok(next.source.includes("collector_result_identity_mismatch"));
assert.ok(next.source.includes("collector_protocol_pause"));
assert.ok(next.source.includes("resume_same_row_with_new_collector_run"));
assert.ok(next.source.includes("collectorEvidence: collectorEvidenceSnapshot(collectorPayload)"));
assert.ok(next.source.includes("collectorValidationIdentity:"));
assert.ok(next.source.includes("historySnapshotAtGeneration:"));
assert.ok(next.source.includes("Copy active sandbox history JSON"));
assert.ok(next.source.includes("Copy production history JSON"));
assert.ok(next.source.includes("p2_pair_production_history_write_blocked"));
assert.ok(!next.source.includes("writeJson(PRODUCTION_STRICT_HISTORY_KEY"));
assert.ok(next.source.includes("prepareP2SandboxHistoryForGenerate()"));
assert.ok(next.source.includes("firstAttemptEvidence: trafficTiming.firstAttemptEvidence"));
assert.ok(next.source.includes("retryRecoveryYield"));
assert.ok(next.source.includes("data-ss-deadline-last-observed-at-ms"));
assert.ok(next.source.includes("data-ss-clock-anomaly-kind"));
assert.ok(next.source.includes("data-ss-clock-anomaly-observed-at-ms"));

console.log("SellerSprite Integrated Runner 0.3.9 P2 deadline-protocol tests: PASS");
