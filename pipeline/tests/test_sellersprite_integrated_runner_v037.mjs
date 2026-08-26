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

const baseline = loadCore("sellersprite_integrated_runner_v0.3.6.user.js");
const tier2 = loadCore("sellersprite_integrated_runner_v0.3.7.user.js");
const disabled = loadCore("sellersprite_integrated_runner_v0.3.7.user.js", (source) =>
  source.replace(
    "var ENABLE_TIER2_2_CONDITIONAL_RETRY = true;",
    "var ENABLE_TIER2_2_CONDITIONAL_RETRY = false;",
  ),
);

assert.ok(baseline.core);
assert.ok(tier2.core);
assert.equal(tier2.core.tier22ConditionalRetryEnabled, true);
assert.equal(tier2.core.tier2RetryVersion, "tier2.2-conditional-retry-v1");
assert.equal(tier2.core.maxCollectorRetries, 1);
assert.equal(disabled.core.tier22ConditionalRetryEnabled, false);

for (const functionName of [
  "evaluateTrafficGate",
  "evaluateDimensionsGate",
  "evaluatePriceGate",
  "isQualifiedResult",
  "collectorHasKnownTrafficFailure",
]) {
  assert.equal(
    tier2.core[functionName].toString(),
    baseline.core[functionName].toString(),
    `Tier 2 must not change hard-gate function ${functionName}`,
  );
}

const fixtures = [
  {
    name: "known low traffic",
    payload: { status: "ok", weeksRead: 1, latest: { naturalSharePct: 0 }, shortCircuited: true },
    retry: false,
    reason: "",
  },
  {
    name: "partial valid sample",
    payload: { status: "ok", weeksRead: 1, details: [{ naturalSharePct: 85 }] },
    retry: false,
    reason: "",
  },
  {
    name: "chart not ready",
    payload: { status: "no_chart_loaded", weeksRead: 0, details: [] },
    retry: true,
    reason: "chart_not_ready",
  },
  {
    name: "tooltip not ready",
    payload: { status: "no_data", weeksRead: 0, details: [] },
    retry: true,
    reason: "tooltip_not_ready",
  },
  {
    name: "collector exception",
    payload: { status: "error", weeksRead: 0, details: [], method: "collector_exception" },
    retry: false,
    reason: "",
  },
  {
    name: "explicit future readiness signal",
    payload: { status: "error", weeksRead: 0, retryable: true, retryReason: "chart_dom_pending" },
    retry: true,
    reason: "chart_dom_pending",
  },
  {
    name: "complete pass sample",
    payload: { status: "ok", weeksRead: 4, latest: { naturalSharePct: 80 }, recent4AvgNaturalSharePct: 78, recent4MinNaturalSharePct: 72 },
    retry: false,
    reason: "",
  },
];

for (const fixture of fixtures) {
  assert.equal(tier2.core.shouldRetryCollector(fixture.payload), fixture.retry, fixture.name);
  assert.equal(tier2.core.collectorRetryReason(fixture.payload), fixture.reason, `${fixture.name}: reason`);
}

for (const fixture of fixtures) {
  const expectedLegacy = Boolean(tier2.core.legacyCollectorRetryReason(fixture.payload));
  assert.equal(
    disabled.core.shouldRetryCollector(fixture.payload),
    expectedLegacy,
    `${fixture.name}: disabling Tier 2.2 must restore legacy retry policy`,
  );
}

assert.equal(
  tier2.core.evaluateTrafficGate(
    { status: "ok", weeksRead: 3, latestNaturalSharePct: 0, recent4AvgNaturalSharePct: 80, recent4MinNaturalSharePct: 0 },
    false,
  ).rule,
  "traffic_latest_below_70",
);

const timing = tier2.core.buildRunnerTimingLogRow(
  {
    targetAsin: "B0AAAA0001",
    collectorVersion: "0.4.6",
    startedAt: "2026-07-13T00:00:00.000Z",
    finishedAt: "2026-07-13T00:00:10.000Z",
  },
  {
    trafficChartMs: 5000,
    retryCount: 1,
    retryDecision: "retry",
    retryReason: "chart_not_ready",
    totalMs: 10000,
  },
  { batchName: "tier2-test", queueHash: "12345678" },
);
assert.equal(timing.retryCount, 1);
assert.equal(timing.retryDecision, "retry");
assert.equal(timing.retryReason, "chart_not_ready");
assert.ok(tier2.core.timingLogColumns.includes("retryDecision"));
assert.ok(tier2.core.timingLogColumns.includes("retryReason"));

assert.ok(tier2.source.includes("@version      0.3.7"));
assert.ok(tier2.source.includes("Running Traffic Collector 0.4.6."));

console.log("SellerSprite Integrated Runner 0.3.7 Tier 2.2 tests: PASS");
