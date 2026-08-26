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
  return { core: sandbox.globalThis.SSTrafficCollectorCore, source };
}

const baseline = loadCore("sellersprite_traffic_collector_v0.4.4.user.js");
const tier0 = loadCore("sellersprite_traffic_collector_v0.4.5.user.js");

assert.ok(baseline.core);
assert.ok(tier0.core);
assert.equal(tier0.core.telemetryEnabled, true);
assert.equal(tier0.core.maxRecentWeeks, baseline.core.maxRecentWeeks);
assert.equal(tier0.core.minRequiredWeeks, baseline.core.minRequiredWeeks);
assert.equal(
  tier0.core.earlyTrafficFailureReason.toString(),
  baseline.core.earlyTrafficFailureReason.toString(),
  "Tier 0 must not change the traffic short-circuit decision function",
);

const trafficFixtures = [
  [],
  [{ weekSort: 202627, naturalSharePct: 69.99 }],
  [{ weekSort: 202627, naturalSharePct: 70 }],
  [
    { weekSort: 202627, naturalSharePct: 85 },
    { weekSort: 202626, naturalSharePct: 68 },
  ],
  [
    { weekSort: 202627, naturalSharePct: 85 },
    { weekSort: 202626, naturalSharePct: 72 },
    { weekSort: 202625, naturalSharePct: 75 },
  ],
];

for (const fixture of trafficFixtures) {
  assert.equal(
    tier0.core.earlyTrafficFailureReason(fixture),
    baseline.core.earlyTrafficFailureReason(fixture),
  );
}

const passResult = {
  asin: "B0AAAA0001",
  status: "ok",
  decision: "pass",
  pass70: true,
  weeksRead: 4,
  latest: { naturalSharePct: 82 },
  recent4AvgNaturalSharePct: 80,
  recent4MinNaturalSharePct: 75,
  method: "tooltip_scan_recent_4_weeks",
  collectorVersion: "0.4.5",
  collectedAt: "2026-07-13T00:00:01.000Z",
  runId: "run-pass",
};
const passGate = tier0.core.buildGateLogRow(passResult);
assert.equal(passGate.outcome, "pass");
assert.equal(passGate.gateC, "pass");
assert.equal(passGate.gateA, "not_evaluated_in_collector");
assert.equal(passGate.shortCircuitGate, "");

const failedGate = tier0.core.buildGateLogRow({
  ...passResult,
  status: "no_chart_loaded",
  decision: "review",
  pass70: false,
  weeksRead: 0,
  latest: null,
  recent4AvgNaturalSharePct: null,
  recent4MinNaturalSharePct: null,
});
assert.equal(failedGate.outcome, "reject");
assert.equal(failedGate.gateC, "reject");
assert.equal(failedGate.shortCircuitGate, "C");

const attached = { ...passResult };
tier0.core.attachTelemetry(attached, {
  startedAt: "2026-07-13T00:00:00.000Z",
  completedAt: "2026-07-13T00:00:01.000Z",
  chartWaitMs: 100,
  tooltipScanMs: 800,
  trafficChartMs: 900,
  totalMs: 1000,
});
assert.equal(attached.telemetry.gate.outcome, "pass");
assert.equal(attached.telemetry.timing.trafficChartMs, 900);
assert.equal(attached.telemetry.timing.detailPageMsReason, "measured_by_runner");

const gateTsv = tier0.core.rowsToTsv([attached.telemetry.gate], tier0.core.gateLogColumns);
const timingTsv = tier0.core.rowsToTsv([attached.telemetry.timing], tier0.core.timingLogColumns);
assert.equal(gateTsv.split("\n").length, 2);
assert.equal(timingTsv.split("\n").length, 2);
assert.ok(gateTsv.startsWith("collectedAt\tasin\tcollectorVersion\toutcome"));
assert.ok(timingTsv.includes("trafficChartMs"));

const disabled = loadCore("sellersprite_traffic_collector_v0.4.5.user.js", (source) =>
  source.replace("var ENABLE_TIER0_TELEMETRY = true;", "var ENABLE_TIER0_TELEMETRY = false;"),
);
const disabledResult = { ...passResult };
disabled.core.attachTelemetry(disabledResult, { totalMs: 1 });
assert.equal(disabled.core.telemetryEnabled, false);
assert.equal(disabledResult.telemetry, undefined, "disabled telemetry must not add result fields");

assert.ok(tier0.source.includes("Copy Gate TSV"));
assert.ok(tier0.source.includes("Copy Timing TSV"));
assert.ok(tier0.source.includes("@version      0.4.5"));

console.log("SellerSprite Traffic Collector 0.4.5 Tier 0 parity/telemetry tests: PASS");
