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

function comparable(value) {
  return JSON.stringify(value);
}

const baseline = loadCore("sellersprite_integrated_runner_v0.3.5.user.js");
const tier0 = loadCore("sellersprite_integrated_runner_v0.3.6.user.js");

assert.ok(baseline.core);
assert.ok(tier0.core);
assert.equal(tier0.core.telemetryEnabled, true);

for (const functionName of [
  "evaluateTrafficGate",
  "evaluateDimensionsGate",
  "evaluatePriceGate",
  "isQualifiedResult",
  "collectorHasKnownTrafficFailure",
]) {
  assert.equal(
    tier0.core[functionName].toString(),
    baseline.core[functionName].toString(),
    `Tier 0 must not change ${functionName}`,
  );
}

const trafficFixtures = [
  [{ status: "ok", weeksRead: 4, latestNaturalSharePct: 80, recent4AvgNaturalSharePct: 78, recent4MinNaturalSharePct: 72 }, false],
  [{ status: "error", weeksRead: 0, note: "timeout" }, false],
  [{ status: "ok", weeksRead: 2, latestNaturalSharePct: 80, recent4AvgNaturalSharePct: 78, recent4MinNaturalSharePct: 72 }, false],
  [{ status: "ok", weeksRead: 4, latestNaturalSharePct: 69.99, recent4AvgNaturalSharePct: 78, recent4MinNaturalSharePct: 72 }, false],
  [{ status: "ok", weeksRead: 4, latestNaturalSharePct: 80, recent4AvgNaturalSharePct: 69.99, recent4MinNaturalSharePct: 72 }, false],
  [{ status: "ok", weeksRead: 4, latestNaturalSharePct: 80, recent4AvgNaturalSharePct: 78, recent4MinNaturalSharePct: 69.99 }, false],
  [{ status: "ok", weeksRead: 4, latestNaturalSharePct: 80, recent4AvgNaturalSharePct: 78, recent4MinNaturalSharePct: 72 }, true],
];

for (const args of trafficFixtures) {
  assert.equal(
    comparable(tier0.core.evaluateTrafficGate(...args)),
    comparable(baseline.core.evaluateTrafficGate(...args)),
  );
}

for (const dimensions of ["", "10 x 8 x 2 inches", "0.5 pounds"]) {
  assert.equal(
    comparable(tier0.core.evaluateDimensionsGate(dimensions)),
    comparable(baseline.core.evaluateDimensionsGate(dimensions)),
  );
}

for (const args of [
  ["stable", 9.9],
  ["rising", 50],
  ["stable", 9.89],
  ["stable", 50.01],
  ["declining", 19.99],
  ["volatile", 19.99],
  ["no_data", null],
]) {
  assert.equal(
    comparable(tier0.core.evaluatePriceGate(...args)),
    comparable(baseline.core.evaluatePriceGate(...args)),
  );
}

const qualificationFixtures = [
  {
    status: "ok",
    weeksRead: 4,
    latestNaturalSharePct: 80,
    recent4AvgNaturalSharePct: 78,
    recent4MinNaturalSharePct: 72,
    dimensions: "10 x 8 x 2 inches",
    priceTrendClass: "stable",
    currentPrice: 19.99,
  },
  {
    status: "ok",
    weeksRead: 4,
    latestNaturalSharePct: 80,
    recent4AvgNaturalSharePct: 78,
    recent4MinNaturalSharePct: 69.99,
    dimensions: "10 x 8 x 2 inches",
    priceTrendClass: "stable",
    currentPrice: 19.99,
  },
  {
    status: "ok",
    weeksRead: 4,
    latestNaturalSharePct: 80,
    recent4AvgNaturalSharePct: 78,
    recent4MinNaturalSharePct: 72,
    dimensions: "",
    priceTrendClass: "stable",
    currentPrice: 19.99,
  },
];

for (const fixture of qualificationFixtures) {
  assert.equal(tier0.core.isQualifiedResult(fixture), baseline.core.isQualifiedResult(fixture));
}

const baseResult = {
  targetAsin: "B0AAAA0001",
  status: "ok",
  weeksRead: 4,
  latestNaturalSharePct: 82,
  recent4AvgNaturalSharePct: 80,
  recent4MinNaturalSharePct: 75,
  dimensions: "10 x 8 x 2 inches",
  dimensionsSource: "SellerSprite/Amazon",
  currentPrice: 19.99,
  priceTrendClass: "stable",
  startedAt: "2026-07-13T00:00:00.000Z",
  finishedAt: "2026-07-13T00:00:05.000Z",
  url: "https://www.amazon.com/dp/B0AAAA0001",
  skippedSteps: [],
};
const context = { batchName: "tier0-test", queueHash: "12345678", generatedAt: "2026-07-13T00:00:00.000Z" };

const passGate = tier0.core.buildRunnerGateLogRow({ ...baseResult, strictDecision: "pass" }, context);
assert.equal(passGate.outcome, "pass");
assert.equal(passGate.gateC, "pass");
assert.equal(passGate.gateD, "pass");
assert.equal(passGate.gateE, "pass");
assert.equal(passGate.gateA, "not_evaluated_in_runner");

const trafficReject = tier0.core.buildRunnerGateLogRow({
  ...baseResult,
  strictDecision: "reject",
  rejectionStage: "traffic",
  rejectionRule: "traffic_recent4_min_below_70",
  rejectionReason: "69.99% < 70%",
  skippedSteps: ["dimensions", "price"],
}, context);
assert.equal(trafficReject.outcome, "reject");
assert.equal(trafficReject.shortCircuitGate, "C");
assert.equal(trafficReject.gateC, "reject");
assert.equal(trafficReject.gateD, "not_run");

const dimensionsReject = tier0.core.buildRunnerGateLogRow({
  ...baseResult,
  strictDecision: "reject",
  rejectionStage: "dimensions",
  rejectionRule: "dimensions_missing",
}, context);
assert.equal(dimensionsReject.shortCircuitGate, "D");
assert.equal(dimensionsReject.gateC, "pass");
assert.equal(dimensionsReject.gateD, "reject");

const historySkip = tier0.core.buildHistorySkipGateLogRow("B0BBBB0002", context);
assert.equal(historySkip.outcome, "skip");
assert.equal(historySkip.gateC, "not_run_history_skip");
assert.notEqual(historySkip.outcome, "pass");

const attached = { ...baseResult, strictDecision: "pass" };
tier0.core.attachRunnerTelemetry(attached, {
  detailPageMs: 900,
  trafficChartMs: 2100,
  dimensionsMs: 100,
  priceChartMs: 1400,
  retryCount: 1,
  totalMs: 5000,
}, context);
assert.equal(attached.telemetry.gate.outcome, "pass");
assert.equal(attached.telemetry.timing.retryCount, 1);
assert.equal(attached.telemetry.timing.trafficChartMs, 2100);

const gateTsv = tier0.core.rowsToTsv([trafficReject, historySkip], tier0.core.gateLogColumns);
const timingTsv = tier0.core.rowsToTsv([attached.telemetry.timing], tier0.core.timingLogColumns);
assert.equal(gateTsv.split("\n").length, 3);
assert.equal(timingTsv.split("\n").length, 2);
assert.ok(gateTsv.startsWith("finishedAt\tbatchName\tqueueHash\tasin"));

const disabled = loadCore("sellersprite_integrated_runner_v0.3.6.user.js", (source) =>
  source.replace("var ENABLE_TIER0_TELEMETRY = true;", "var ENABLE_TIER0_TELEMETRY = false;"),
);
const disabledResult = { ...baseResult, strictDecision: "pass" };
disabled.core.attachRunnerTelemetry(disabledResult, { totalMs: 1 }, context);
assert.equal(disabled.core.telemetryEnabled, false);
assert.equal(disabledResult.telemetry, undefined, "disabled telemetry must not add result fields");

assert.ok(tier0.source.includes("Copy gate log TSV"));
assert.ok(tier0.source.includes("Copy timing log TSV"));
assert.ok(tier0.source.includes("@version      0.3.6"));

console.log("SellerSprite Integrated Runner 0.3.6 Tier 0 parity/telemetry tests: PASS");
