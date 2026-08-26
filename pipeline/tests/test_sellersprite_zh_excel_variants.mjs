import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const candidateRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const projectRoot = process.env.AMAZON_PRODUCTS_ROOT || "C:/Users/13045/Desktop/amazon_products";

function loadCore(filePath, globalName) {
  const source = fs.readFileSync(filePath, "utf8");
  const sandbox = {
    console,
    globalThis: {},
    location: { href: "https://www.amazon.com/dp/B0AAAA0001?th=1" },
    URL,
  };
  vm.runInNewContext(source, sandbox, { filename: filePath });
  return { core: sandbox.globalThis[globalName], source };
}

const collectorBaseline = loadCore(
  path.join(projectRoot, "scripts", "sellersprite_traffic_collector_v0.4.6.user.js"),
  "SSTrafficCollectorCore",
);
const collectorZh = loadCore(
  path.join(candidateRoot, "scripts", "sellersprite_traffic_collector_v0.4.6_zh.user.js"),
  "SSTrafficCollectorCore",
);
const runnerBaseline = loadCore(
  path.join(projectRoot, "scripts", "sellersprite_integrated_runner_v0.3.7.user.js"),
  "SSIntegratedRunnerCore",
);
const runnerZh = loadCore(
  path.join(candidateRoot, "scripts", "sellersprite_integrated_runner_v0.3.7_zh_excel.user.js"),
  "SSIntegratedRunnerCore",
);

for (const functionName of [
  "parseTip",
  "summarize",
  "explicitMetricValue",
  "earlyTrafficFailureReason",
  "buildGateLogRow",
  "buildTimingLogRow",
  "attachTelemetry",
  "rowsToTsv",
]) {
  assert.equal(
    collectorZh.core[functionName].toString(),
    collectorBaseline.core[functionName].toString(),
    `Collector hard-gate/telemetry function changed: ${functionName}`,
  );
}
assert.deepEqual(
  JSON.parse(JSON.stringify(collectorZh.core.gateLogColumns)),
  JSON.parse(JSON.stringify(collectorBaseline.core.gateLogColumns)),
);
assert.deepEqual(
  JSON.parse(JSON.stringify(collectorZh.core.timingLogColumns)),
  JSON.parse(JSON.stringify(collectorBaseline.core.timingLogColumns)),
);

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
    runnerZh.core[functionName].toString(),
    runnerBaseline.core[functionName].toString(),
    `Runner hard-gate/telemetry function changed: ${functionName}`,
  );
}
assert.deepEqual(
  JSON.parse(JSON.stringify(runnerZh.core.gateLogColumns)),
  JSON.parse(JSON.stringify(runnerBaseline.core.gateLogColumns)),
);
assert.deepEqual(
  JSON.parse(JSON.stringify(runnerZh.core.timingLogColumns)),
  JSON.parse(JSON.stringify(runnerBaseline.core.timingLogColumns)),
);

const trafficFixtures = [
  {
    status: "ok",
    weeksRead: 3,
    latestNaturalSharePct: 75,
    recent4AvgNaturalSharePct: 80,
    recent4MinNaturalSharePct: 71,
  },
  {
    status: "ok",
    weeksRead: 2,
    latestNaturalSharePct: 90,
    recent4AvgNaturalSharePct: 90,
    recent4MinNaturalSharePct: 90,
  },
  {
    status: "ok",
    weeksRead: 4,
    latestNaturalSharePct: 69,
    recent4AvgNaturalSharePct: 80,
    recent4MinNaturalSharePct: 69,
  },
];
for (const fixture of trafficFixtures) {
  assert.deepEqual(
    JSON.parse(JSON.stringify(runnerZh.core.evaluateTrafficGate(fixture, false))),
    JSON.parse(JSON.stringify(runnerBaseline.core.evaluateTrafficGate(fixture, false))),
  );
}

assert.match(collectorZh.source, /卖家精灵流量采集器 0\.4\.6 中文版/);
assert.match(collectorZh.source, /data-ss-running/);
assert.match(collectorZh.source, /data-ss-result-ready/);
assert.match(runnerZh.source, /卖家精灵一体化选品 0\.3\.7 中文 Excel 版/);
assert.match(runnerZh.source, /一键生成待验收 Excel/);
assert.match(runnerZh.source, /panel\.getAttribute\('data-ss-running'\) === '1'/);
assert.match(runnerZh.source, /panel\.getAttribute\('data-ss-result-ready'\) === '1'/);
assert.doesNotMatch(runnerZh.source, /\/Collecting\/i\.test/);
assert.match(runnerZh.source, /state\.status !== 'done'/);
assert.match(runnerZh.source, /payload\.accepted !== true \|\| payload\.machineAcceptancePassed !== true/);
assert.match(runnerZh.source, /url\.hostname !== '127\.0\.0\.1' && url\.hostname !== 'localhost'/);
assert.match(runnerZh.source, /return 'http:\/\/127\.0\.0\.1' \+ \(url\.port \? ':' \+ url\.port : ''\)/);
assert.match(runnerZh.source, /productionHistoryUpdated/);
assert.match(runnerZh.source, /@grant\s+GM_xmlhttpRequest/);
assert.match(runnerZh.source, /@grant\s+GM_download/);
assert.match(runnerZh.source, /sellerSpriteIntegratedBatch\/v0\.3\.0/);

console.log("SellerSprite Chinese UI + accepted Excel variants: PASS");
