import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function loadCore(fileName, globalName, sandboxExtras = {}) {
  const source = fs.readFileSync(path.join(root, "scripts", fileName), "utf8");
  const sandbox = {
    console,
    globalThis: {},
    ...sandboxExtras,
  };
  vm.runInNewContext(source, sandbox, { filename: fileName });
  return { core: sandbox.globalThis[globalName], source };
}

const collector = loadCore(
  "sellersprite_traffic_collector_v0.4.7.user.js",
  "SSTrafficCollectorCore",
  { location: { href: "https://www.amazon.com/dp/B0AAAA0001?th=1" }, URL },
);
const runner = loadCore(
  "sellersprite_integrated_runner_v0.3.9.user.js",
  "SSIntegratedRunnerCore",
);

assert.ok(collector.core);
assert.ok(runner.core);

const acceptedAtMs = 1_000_000;
const runId = "paired-run-1";
const protocol = collector.core.createCollectorDeadlineState(runId, acceptedAtMs, 60_000);
let attributes = collector.core.collectorDeadlineAttributes(protocol);

const acceptedSnapshot = {
  collectorVersion: attributes["data-ss-collector-version"],
  p2Enabled: collector.core.p2CollectorDeadlineEnabled ? "1" : "0",
  protocolVersion: "2",
  protocolName: attributes["data-ss-protocol-name"],
  deadlineOwner: attributes["data-ss-deadline-owner"],
  runId,
  deadlineRunId: attributes["data-ss-deadline-run-id"],
  resultRunId: "",
  resultReady: "0",
  running: "1",
  phase: attributes["data-ss-deadline-phase"],
  acceptedAtMs,
  phaseStartAtMs: Number(attributes["data-ss-deadline-phase-started-at-ms"]),
  phaseDeadlineAtMs: Number(attributes["data-ss-deadline-at-ms"]),
  heartbeatAtMs: Number(attributes["data-ss-deadline-heartbeat-at-ms"]),
  lastObservedAtMs: Number(attributes["data-ss-deadline-last-observed-at-ms"]),
  clockAnomalyKind: attributes["data-ss-clock-anomaly-kind"],
  clockAnomalyObservedAtMs: attributes["data-ss-clock-anomaly-observed-at-ms"] === ""
    ? null
    : Number(attributes["data-ss-clock-anomaly-observed-at-ms"]),
  hiddenObservedAtMs: null,
  visibilityState: "visible",
};
assert.deepEqual(
  JSON.parse(JSON.stringify(runner.core.collectorProtocolCompatibility(acceptedSnapshot))),
  { ok: true, reason: "" },
);
assert.equal(acceptedSnapshot.phase, "chart_wait");
assert.equal(acceptedSnapshot.phaseDeadlineAtMs, acceptedAtMs + 60_000);
assert.equal(
  collector.core.collectorDeadlineReached(acceptedSnapshot.phaseDeadlineAtMs, acceptedAtMs, 60_000, acceptedAtMs + 59_900),
  false,
);
assert.equal(
  collector.core.collectorDeadlineReached(acceptedSnapshot.phaseDeadlineAtMs, acceptedAtMs, 60_000, acceptedAtMs + 60_100),
  true,
);

const chartReadyAtMs = acceptedAtMs + 15_100;
collector.core.advanceCollectorDeadlineState(protocol, "tooltip_scan", chartReadyAtMs, "");
attributes = collector.core.collectorDeadlineAttributes(protocol);
assert.equal(attributes["data-ss-deadline-phase"], "tooltip_scan");
assert.equal(Number(attributes["data-ss-deadline-at-ms"]), chartReadyAtMs + 45_000);
assert.equal(
  runner.core.classifyCollectorWatchdog(
    { phase: "tooltip_scan", heartbeatAtMs: chartReadyAtMs + 44_500, visibilityState: "visible", hiddenObservedAtMs: null },
    chartReadyAtMs + 45_100,
    "visible",
  ),
  "tooltip_scan_watchdog_exceeded_active",
);

const resultReadyAtMs = chartReadyAtMs + 20_000;
collector.core.advanceCollectorDeadlineState(protocol, "result_ready", resultReadyAtMs, "ok");
attributes = collector.core.collectorDeadlineAttributes(protocol);
const payload = {
  runId,
  collectorVersion: "0.4.7",
  status: "ok",
  deadlineProtocol: collector.core.collectorDeadlinePayload(protocol),
};
const resultSnapshot = {
  ...acceptedSnapshot,
  deadlineRunId: attributes["data-ss-deadline-run-id"],
  resultRunId: runId,
  resultReady: "1",
  running: "1",
  phase: attributes["data-ss-deadline-phase"],
  phaseStartAtMs: Number(attributes["data-ss-deadline-phase-started-at-ms"]),
  heartbeatAtMs: Number(attributes["data-ss-deadline-heartbeat-at-ms"]),
  lastObservedAtMs: Number(attributes["data-ss-deadline-last-observed-at-ms"]),
  clockAnomalyKind: attributes["data-ss-clock-anomaly-kind"],
  clockAnomalyObservedAtMs: attributes["data-ss-clock-anomaly-observed-at-ms"] === ""
    ? null
    : Number(attributes["data-ss-clock-anomaly-observed-at-ms"]),
  resultReadyAtMs: Number(attributes["data-ss-deadline-result-ready-at-ms"]),
};
assert.equal(runner.core.matchingCollectorProtocolResult(resultSnapshot, payload, runId), true);
assert.equal(
  runner.core.matchingCollectorProtocolResult({ ...resultSnapshot, deadlineRunId: "stale" }, payload, runId),
  false,
);
assert.equal(
  runner.core.matchingCollectorProtocolResult(resultSnapshot, { ...payload, runId: "stale" }, runId),
  false,
);
assert.equal(
  runner.core.collectorProtocolPollDecision(
    { ...resultSnapshot, hiddenObservedAtMs: acceptedAtMs + 20_000 },
    payload,
    runId,
    resultReadyAtMs,
    "visible",
  ).action,
  "pause",
  "a hidden result-ready payload is quarantined and never accepted",
);
assert.equal(
  runner.core.collectorProtocolPollDecision(
    { ...resultSnapshot, visibilityState: "hidden", hiddenObservedAtMs: null },
    payload,
    runId,
    resultReadyAtMs,
    "visible",
  ).reason,
  "watchdog_page_hidden_or_throttled",
);

collector.core.heartbeatCollectorDeadlineState(protocol, resultReadyAtMs + 100);
collector.core.heartbeatCollectorDeadlineState(protocol, resultReadyAtMs + 99);
attributes = collector.core.collectorDeadlineAttributes(protocol);
const backwardPayload = {
  ...payload,
  deadlineProtocol: collector.core.collectorDeadlinePayload(protocol),
};
const backwardResultSnapshot = {
  ...resultSnapshot,
  phaseStartAtMs: Number(attributes["data-ss-deadline-phase-started-at-ms"]),
  heartbeatAtMs: Number(attributes["data-ss-deadline-heartbeat-at-ms"]),
  lastObservedAtMs: Number(attributes["data-ss-deadline-last-observed-at-ms"]),
  clockAnomalyKind: attributes["data-ss-clock-anomaly-kind"],
  clockAnomalyObservedAtMs: Number(attributes["data-ss-clock-anomaly-observed-at-ms"]),
};
assert.equal(backwardResultSnapshot.clockAnomalyKind, "wall_clock_backward");
assert.equal(runner.core.matchingCollectorProtocolResult(backwardResultSnapshot, backwardPayload, runId), false);
assert.deepEqual(
  JSON.parse(JSON.stringify(runner.core.collectorProtocolPollDecision(
    backwardResultSnapshot,
    backwardPayload,
    runId,
    resultReadyAtMs + 100,
    "visible",
  ))),
  { action: "pause", reason: "watchdog_wall_clock_backward", watchdogClassification: "wall_clock_backward" },
  "Collector-detected backward wall-clock jumps are quarantined before Runner payload acceptance",
);

assert.equal(
  runner.core.classifyCollectorWatchdog(
    { phase: "chart_wait", heartbeatAtMs: acceptedAtMs + 59_000, hiddenObservedAtMs: acceptedAtMs + 20_000, visibilityState: "visible" },
    acceptedAtMs + 61_000,
    "visible",
  ),
  "page_hidden_or_throttled",
);

assert.ok(runner.source.includes("if (!ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL)"));
assert.ok(runner.source.includes("}, 15000, 250);"));
assert.ok(runner.source.includes("}, 5000, 100);"));
assert.ok(runner.source.includes("}, 45000, 250);"));
assert.ok(runner.source.includes("collector_result_identity_mismatch"));
assert.ok(runner.source.includes("collector_protocol_pause"));
assert.ok(collector.source.includes("heartbeatTimer = setInterval"));
assert.ok(collector.source.includes("data-ss-deadline-last-observed-at-ms"));
assert.ok(collector.source.includes("data-ss-clock-anomaly-kind"));
assert.ok(collector.source.includes("data-ss-clock-anomaly-observed-at-ms"));

console.log("SellerSprite Collector 0.4.7 / Runner 0.3.9 deadline protocol integration: PASS");
