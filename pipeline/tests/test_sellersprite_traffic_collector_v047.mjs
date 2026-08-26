import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const fixtures = JSON.parse(
  fs.readFileSync(path.join(root, "tests", "fixtures", "sellersprite_tier2_tooltips.json"), "utf8"),
);

function exposeScanTooltip(source) {
  return source.replace(
    "globalThis.SSTrafficCollectorCore = Object.freeze({",
    "globalThis.SSTrafficCollectorCore = Object.freeze({\n    scanTooltip: scanTooltip,\n    waitForChart: waitForChart,",
  );
}

function loadCore(fileName, transform) {
  let source = fs.readFileSync(path.join(root, "scripts", fileName), "utf8");
  source = exposeScanTooltip(source);
  if (transform) source = transform(source);
  const sandbox = {
    console,
    globalThis: {},
    location: { href: "https://www.amazon.com/dp/B0AAAA0001?th=1" },
    URL,
  };
  vm.runInNewContext(source, sandbox, { filename: fileName });
  return { core: sandbox.globalThis.SSTrafficCollectorCore, source, sandbox };
}

function comparable(value) {
  return JSON.stringify(value);
}

const legacy = loadCore("sellersprite_traffic_collector_v0.4.6.user.js");
const candidate = loadCore("sellersprite_traffic_collector_v0.4.7.user.js");
const disabled = loadCore("sellersprite_traffic_collector_v0.4.7.user.js", (source) =>
  source.replace(
    "var ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL = true;",
    "var ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL = false;",
  ),
);

assert.ok(legacy.core);
assert.ok(candidate.core);
assert.equal(candidate.core.p2CollectorDeadlineEnabled, true);
assert.equal(candidate.core.p2DeadlineProtocolVersion, "p2-collector-owned-deadline-v1");
assert.equal(candidate.core.p2DeadlineOwner, "collector");
assert.equal(candidate.core.p2ChartReadyBudgetMs, 60000);
assert.equal(candidate.core.p2TooltipScanWatchdogMs, 45000);
assert.equal(candidate.core.protocolVersion, "2");
assert.equal(disabled.core.p2CollectorDeadlineEnabled, false);
assert.equal(disabled.core.protocolVersion, "1");
assert.equal(disabled.core.protocolName, "legacy_status_text_v1");
assert.equal(disabled.core.deadlineOwner, "runner");

const invariantFunctions = [
  "parseTip",
  "summarize",
  "explicitMetricValue",
  "earlyTrafficFailureReason",
  "buildGateLogRow",
  "buildTimingLogRow",
  "attachTelemetry",
  "rowsToTsv",
  "scanTooltip",
];
for (const name of invariantFunctions) {
  assert.equal(
    candidate.core[name].toString(),
    legacy.core[name].toString(),
    `${name} must remain byte-identical to Collector 0.4.6`,
  );
  assert.equal(
    disabled.core[name].toString(),
    legacy.core[name].toString(),
    `${name} must remain legacy-identical with the P2 flag off`,
  );
}

for (const fixture of fixtures) {
  assert.equal(
    comparable(candidate.core.parseTip(fixture.rawText)),
    comparable(legacy.core.parseTip(fixture.rawText)),
    `${fixture.id}: candidate parser output must equal 0.4.6`,
  );
  assert.equal(
    comparable(disabled.core.parseTip(fixture.rawText)),
    comparable(legacy.core.parseTip(fixture.rawText)),
    `${fixture.id}: flag-off parser output must equal 0.4.6`,
  );
}

const acceptedAtMs = 1_000_000;
const accepted = candidate.core.createCollectorDeadlineState("run-1", acceptedAtMs, 60000);
assert.equal(accepted.owner, "collector");
assert.equal(accepted.runId, "run-1");
assert.equal(accepted.phase, "chart_wait");
assert.equal(accepted.phaseDeadlineKind, "hard_readiness");
assert.equal(accepted.phaseStartedAtMs, acceptedAtMs);
assert.equal(accepted.phaseDeadlineAtMs, acceptedAtMs + 60000);
assert.equal(accepted.chartReadyDeadlineAtMs, acceptedAtMs + 60000);
assert.equal(accepted.protocolName, "p2-collector-owned-deadline-v1");
assert.equal(accepted.domProtocolVersion, "2");
assert.equal(accepted.heartbeatAtMs, acceptedAtMs);
assert.equal(accepted.lastObservedAtMs, acceptedAtMs);
assert.equal(accepted.clockAnomalyKind, "");
assert.equal(accepted.clockAnomalyObservedAtMs, null);
assert.equal(accepted.hiddenObservedAtMs, null);
assert.equal(
  candidate.core.collectorDeadlineReached(accepted.phaseDeadlineAtMs, acceptedAtMs, 60000, acceptedAtMs + 59999),
  false,
);
assert.equal(
  candidate.core.collectorDeadlineReached(accepted.phaseDeadlineAtMs, acceptedAtMs, 60000, acceptedAtMs + 60000),
  true,
);
assert.equal(
  candidate.core.collectorDeadlineReached(null, acceptedAtMs, 60000, acceptedAtMs + 59999),
  false,
);
assert.equal(
  candidate.core.collectorDeadlineReached(null, acceptedAtMs, 60000, acceptedAtMs + 60000),
  true,
  "flag-off fallback preserves the legacy relative 60 second boundary",
);
assert.equal(
  candidate.core.collectorDeadlineReached(acceptedAtMs + 60000, acceptedAtMs, 60000, acceptedAtMs - 1),
  true,
  "a backward wall-clock jump is a hard deadline condition under P2",
);
assert.equal(
  disabled.core.collectorDeadlineReached(acceptedAtMs + 60000, acceptedAtMs, 60000, acceptedAtMs - 1),
  false,
  "the backward-clock guard is isolated behind the P2 flag",
);

let attributes = candidate.core.collectorDeadlineAttributes(accepted);
assert.equal(attributes["data-ss-collector-version"], "0.4.7");
assert.equal(attributes["data-ss-protocol-name"], "p2-collector-owned-deadline-v1");
assert.equal(attributes["data-ss-deadline-protocol-version"], "p2-collector-owned-deadline-v1");
assert.equal(attributes["data-ss-deadline-owner"], "collector");
assert.equal(attributes["data-ss-deadline-run-id"], "run-1");
assert.equal(attributes["data-ss-deadline-phase"], "chart_wait");
assert.equal(attributes["data-ss-deadline-at-ms"], String(acceptedAtMs + 60000));
assert.equal(attributes["data-ss-deadline-chart-ready-deadline-at-ms"], String(acceptedAtMs + 60000));
assert.equal(attributes["data-ss-deadline-last-observed-at-ms"], String(acceptedAtMs));
assert.equal(attributes["data-ss-clock-anomaly-kind"], "");
assert.equal(attributes["data-ss-clock-anomaly-observed-at-ms"], "");
assert.equal(attributes["data-ss-hidden-observed-at-ms"], "");

candidate.core.heartbeatCollectorDeadlineState(accepted, acceptedAtMs + 1000);
assert.equal(accepted.heartbeatAtMs, acceptedAtMs + 1000);
assert.equal(accepted.lastObservedAtMs, acceptedAtMs + 1000);
assert.equal(accepted.phaseDeadlineAtMs, acceptedAtMs + 60000, "heartbeat cannot extend readiness");

const chartReadyAtMs = acceptedAtMs + 15001;
candidate.core.advanceCollectorDeadlineState(accepted, "tooltip_scan", chartReadyAtMs, "");
assert.equal(accepted.phase, "tooltip_scan");
assert.equal(accepted.phaseDeadlineKind, "observer_watchdog");
assert.equal(accepted.chartReadyAtMs, chartReadyAtMs);
assert.equal(accepted.chartReadyDeadlineExceededByMs, 0);
assert.equal(accepted.phaseDeadlineAtMs, chartReadyAtMs + 45000);

const resultReadyAtMs = chartReadyAtMs + 21000;
candidate.core.advanceCollectorDeadlineState(accepted, "result_ready", resultReadyAtMs, "ok");
assert.equal(accepted.phase, "result_ready");
assert.equal(accepted.phaseDeadlineKind, "terminal");
assert.equal(accepted.phaseDeadlineAtMs, null);
assert.equal(accepted.resultReadyAtMs, resultReadyAtMs);
assert.equal(accepted.terminalFromPhase, "tooltip_scan");
assert.equal(accepted.deadlineExceededByMs, 0);
assert.equal(accepted.terminalReason, "ok");
attributes = candidate.core.collectorDeadlineAttributes(accepted);
assert.equal(attributes["data-ss-deadline-at-ms"], "");
assert.equal(attributes["data-ss-deadline-result-ready-at-ms"], String(resultReadyAtMs));
assert.equal(attributes["data-ss-deadline-terminal-from-phase"], "tooltip_scan");
assert.equal(attributes["data-ss-deadline-exceeded-by-ms"], "0");
assert.equal(attributes["data-ss-deadline-terminal-reason"], "ok");
const deadlinePayload = candidate.core.collectorDeadlinePayload(accepted);
assert.equal(deadlinePayload.protocolName, "p2-collector-owned-deadline-v1");
assert.equal(deadlinePayload.protocolVersion, "2");
assert.equal(deadlinePayload.deadlineOwner, "collector");
assert.equal(deadlinePayload.runId, "run-1");
assert.equal(deadlinePayload.lastObservedAtMs, resultReadyAtMs);
assert.equal(deadlinePayload.clockAnomalyKind, "");
assert.equal(deadlinePayload.clockAnomalyObservedAtMs, null);

const backwardClock = candidate.core.createCollectorDeadlineState("clock-backward", acceptedAtMs, 60000);
assert.equal(candidate.core.observeCollectorWallClock(backwardClock, acceptedAtMs + 1000), false);
assert.equal(candidate.core.observeCollectorWallClock(backwardClock, acceptedAtMs + 999), true);
assert.equal(backwardClock.lastObservedAtMs, acceptedAtMs + 1000, "the trusted high-water mark cannot move backward");
assert.equal(backwardClock.clockAnomalyKind, "wall_clock_backward");
assert.equal(backwardClock.clockAnomalyObservedAtMs, acceptedAtMs + 999);
const backwardAttributes = candidate.core.collectorDeadlineAttributes(backwardClock);
assert.equal(backwardAttributes["data-ss-deadline-last-observed-at-ms"], String(acceptedAtMs + 1000));
assert.equal(backwardAttributes["data-ss-clock-anomaly-kind"], "wall_clock_backward");
assert.equal(backwardAttributes["data-ss-clock-anomaly-observed-at-ms"], String(acceptedAtMs + 999));
const backwardPayload = candidate.core.collectorDeadlinePayload(backwardClock);
assert.equal(backwardPayload.lastObservedAtMs, acceptedAtMs + 1000);
assert.equal(backwardPayload.clockAnomalyKind, "wall_clock_backward");
assert.equal(backwardPayload.clockAnomalyObservedAtMs, acceptedAtMs + 999);

const overrun = candidate.core.createCollectorDeadlineState("slow-1", acceptedAtMs, 60000);
candidate.core.advanceCollectorDeadlineState(overrun, "tooltip_scan", chartReadyAtMs, "");
candidate.core.advanceCollectorDeadlineState(overrun, "result_ready", chartReadyAtMs + 46000, "no_data");
assert.equal(overrun.terminalFromPhase, "tooltip_scan");
assert.equal(overrun.deadlineExceededByMs, 1000);

const lateChart = candidate.core.createCollectorDeadlineState("late-chart", acceptedAtMs, 60000);
candidate.core.advanceCollectorDeadlineState(lateChart, "tooltip_scan", acceptedAtMs + 61000, "");
assert.equal(lateChart.chartReadyDeadlineExceededByMs, 1000);
assert.equal(
  candidate.core.collectorDeadlineAttributes(lateChart)["data-ss-deadline-chart-ready-exceeded-by-ms"],
  "1000",
);

const automatic = candidate.core.createCollectorDeadlineState("auto-1", acceptedAtMs, 90000);
assert.equal(automatic.phaseDeadlineAtMs, acceptedAtMs + 90000, "existing ss-auto budget remains auditable");
assert.throws(
  () => candidate.core.createCollectorDeadlineState("bad", "not-a-time", 60000),
  /acceptedAtMs is invalid/,
);

const snapshot = candidate.core.collectorDeadlineSnapshot(accepted);
accepted.terminalReason = "changed-after-snapshot";
assert.equal(snapshot.terminalReason, "ok", "telemetry snapshot must be detached from mutable state");

assert.equal(disabled.core.createCollectorDeadlineState("run-off", acceptedAtMs, 60000), null);
assert.equal(comparable(disabled.core.collectorDeadlineAttributes(null)), "{}");

async function chartAtWallClock(loaded, readyAtMs) {
  let nowMs = 0;
  let chartAvailable = false;
  const chart = { getBoundingClientRect: () => ({ width: 600, height: 300 }) };
  loaded.sandbox.Date = { now: () => nowMs };
  loaded.sandbox.document = {
    querySelectorAll: () => (chartAvailable ? [chart] : []),
    getElementById: () => null,
  };
  loaded.sandbox.getComputedStyle = () => ({ display: "block", visibility: "visible" });
  loaded.sandbox.setTimeout = (callback) => {
    nowMs = readyAtMs;
    chartAvailable = true;
    callback();
  };
  return loaded.core.waitForChart(60000, 60000);
}

async function chartAfterBackwardWallClockJump(loaded) {
  let nowMs = acceptedAtMs;
  let chartAvailable = false;
  const chart = { getBoundingClientRect: () => ({ width: 600, height: 300 }) };
  loaded.sandbox.Date = { now: () => nowMs };
  loaded.sandbox.document = {
    querySelectorAll: () => (chartAvailable ? [chart] : []),
    getElementById: () => null,
  };
  loaded.sandbox.getComputedStyle = () => ({ display: "block", visibility: "visible" });
  loaded.sandbox.setTimeout = (callback) => {
    nowMs = acceptedAtMs - 1;
    chartAvailable = true;
    callback();
  };
  return loaded.core.waitForChart(60000, acceptedAtMs + 60000);
}

assert.ok(await chartAtWallClock(disabled, 60000), "flag off must preserve 0.4.6 chart-first boundary semantics");
assert.ok(await chartAtWallClock(legacy, 60000), "0.4.6 must accept a chart observed at its final boundary poll");
assert.equal(await chartAtWallClock(candidate, 60000), null, "flag on must enforce the hard deadline before chart acceptance");
assert.equal(await chartAtWallClock(candidate, 60001), null, "a chart first observed at 60,001ms must be rejected");
assert.equal(
  await chartAtWallClock(candidate, 700000),
  null,
  "a chart appearing only after a throttled 700s wall-clock jump must be rejected",
);
assert.equal(
  await chartAfterBackwardWallClockJump(candidate),
  null,
  "a chart exposed after a backward wall-clock jump must be quarantined, never returned",
);
assert.ok(
  await chartAfterBackwardWallClockJump(disabled),
  "the backward-clock quarantine remains isolated behind the P2 flag",
);
assert.ok(candidate.source.includes("@version      0.4.7"));
assert.ok(candidate.source.includes("ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL"));
assert.ok(candidate.source.includes("var P2_CHART_READY_BUDGET_MS = 60000;"));
assert.ok(candidate.source.includes("var P2_TOOLTIP_SCAN_WATCHDOG_MS = 45000;"));
assert.ok(candidate.source.includes("var chart = await waitForChart(chartReadyBudgetMs, chartDeadlineAtMs);"));
assert.ok(!candidate.source.includes("getChartElement() || (await waitForChart"));
assert.ok(candidate.source.includes("result.deadlineProtocol = collectorDeadlinePayload"));
assert.ok(candidate.source.includes("heartbeatTimer = setInterval"));
assert.ok(candidate.source.includes("data-ss-visibility-state"));
assert.ok(candidate.source.includes("data-ss-deadline-last-observed-at-ms"));
assert.ok(candidate.source.includes("data-ss-clock-anomaly-kind"));
assert.ok(candidate.source.includes("data-ss-clock-anomaly-observed-at-ms"));
assert.ok(candidate.source.includes('document.addEventListener("visibilitychange"'));

console.log("SellerSprite Traffic Collector 0.4.7 P2 deadline protocol tests: PASS");
