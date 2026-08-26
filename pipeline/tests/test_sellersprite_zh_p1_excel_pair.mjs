import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function loadCore(fileName, globalName) {
  const filePath = path.join(root, "scripts", fileName);
  const source = fs.readFileSync(filePath, "utf8");
  const sandbox = {
    console,
    globalThis: {},
    location: { href: "https://www.amazon.com/dp/B0AAAA0001?th=1" },
    URL,
  };
  vm.runInNewContext(source, sandbox, { filename: fileName });
  return { core: sandbox.globalThis[globalName], source };
}

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

function sliceBetween(source, start, end) {
  const startIndex = source.indexOf(start);
  const endIndex = source.indexOf(end, startIndex);
  assert.notEqual(startIndex, -1, `Missing source marker: ${start}`);
  assert.notEqual(endIndex, -1, `Missing source marker: ${end}`);
  return source.slice(startIndex, endIndex);
}

function occurrences(source, token) {
  return source.split(token).length - 1;
}

const collectorBaseline = loadCore(
  "sellersprite_traffic_collector_v0.4.6.user.js",
  "SSTrafficCollectorCore",
);
const collectorCandidate = loadCore(
  "sellersprite_traffic_collector_v0.4.6_zh_p1.user.js",
  "SSTrafficCollectorCore",
);
const runnerBaseline = loadCore(
  "sellersprite_integrated_runner_v0.3.8.user.js",
  "SSIntegratedRunnerCore",
);
const runnerCandidate = loadCore(
  "sellersprite_integrated_runner_v0.3.8_zh_excel.user.js",
  "SSIntegratedRunnerCore",
);

assert.ok(collectorCandidate.core);
assert.ok(runnerCandidate.core);

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
    collectorCandidate.core[functionName].toString(),
    collectorBaseline.core[functionName].toString(),
    `Collector gate/telemetry function changed: ${functionName}`,
  );
}
assert.deepEqual(plain(collectorCandidate.core.gateLogColumns), plain(collectorBaseline.core.gateLogColumns));
assert.deepEqual(plain(collectorCandidate.core.timingLogColumns), plain(collectorBaseline.core.timingLogColumns));
assert.equal(collectorCandidate.core.tier21ZeroShareEnabled, collectorBaseline.core.tier21ZeroShareEnabled);
assert.equal(collectorCandidate.core.tier2ReaderVersion, collectorBaseline.core.tier2ReaderVersion);
assert.equal(collectorCandidate.core.maxRecentWeeks, collectorBaseline.core.maxRecentWeeks);
assert.equal(collectorCandidate.core.minRequiredWeeks, collectorBaseline.core.minRequiredWeeks);

const runnerGateFunctions = [
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
];
assert.equal(runnerGateFunctions.length, 25);
for (const functionName of runnerGateFunctions) {
  assert.equal(
    runnerCandidate.core[functionName].toString(),
    runnerBaseline.core[functionName].toString(),
    `Runner gate/log function changed: ${functionName}`,
  );
}

for (const functionName of [
  "normalizeTargetControl",
  "effectiveStopBudget",
  "browserPassesThisBatch",
  "stopDecision",
  "requestStopAfterCurrentRow",
  "mergeLatestControlState",
  "mergeGranularRowSidecar",
]) {
  assert.equal(
    runnerCandidate.core[functionName].toString(),
    runnerBaseline.core[functionName].toString(),
    `Runner P1 function changed: ${functionName}`,
  );
}
assert.deepEqual(plain(runnerCandidate.core.gateLogColumns), plain(runnerBaseline.core.gateLogColumns));
assert.deepEqual(plain(runnerCandidate.core.timingLogColumns), plain(runnerBaseline.core.timingLogColumns));
assert.deepEqual(plain(runnerCandidate.core.granularTimingColumns), plain(runnerBaseline.core.granularTimingColumns));
assert.deepEqual(plain(runnerCandidate.core.controlEventColumns), plain(runnerBaseline.core.controlEventColumns));
assert.equal(runnerCandidate.core.cumulativeTargetControlEnabled, true);
assert.equal(runnerCandidate.core.granularTelemetryEnabled, true);
assert.equal(runnerCandidate.core.targetControlVersion, "p1-cumulative-remaining-v1");
assert.equal(runnerCandidate.core.granularTelemetryVersion, "tier0.2-granular-v1");
assert.equal(runnerCandidate.core.maxCollectorRetries, 1);

assert.equal(
  sliceBetween(runnerCandidate.source, "async function runCollectorOnce", "\n  async function collectTraffic"),
  sliceBetween(runnerBaseline.source, "async function runCollectorOnce", "\n  async function collectTraffic"),
  "Runner Collector handshake/deadline implementation changed",
);
for (const token of [
  "}, 18000, 250);",
  "}, 15000, 250);",
  "}, 5000, 100);",
  "}, 45000, 250);",
  "await sleep(600);",
]) {
  assert.equal(
    occurrences(runnerCandidate.source, token),
    occurrences(runnerBaseline.source, token),
    `Runner timing token changed: ${token}`,
  );
  assert.ok(occurrences(runnerCandidate.source, token) > 0, `Runner timing token missing: ${token}`);
}

assert.match(collectorCandidate.source, /@name\s+卖家精灵流量采集器 0\.4\.6\.2 中文 P1 版/);
assert.match(collectorCandidate.source, /@version\s+0\.4\.6\.2/);
assert.match(collectorCandidate.source, /var VERSION = "0\.4\.6\.2";/);
assert.match(collectorCandidate.source, /正在采集（Collecting），请不要移动鼠标、切换标签或刷新页面。/);
assert.match(collectorCandidate.source, /data-ss-running/);
assert.match(collectorCandidate.source, /data-ss-result-ready/);

assert.match(runnerCandidate.source, /@version\s+0\.3\.8\.1/);
assert.match(runnerCandidate.source, /var VERSION = '0\.3\.8\.1';/);
assert.match(runnerCandidate.source, /\/Collecting\/i\.test/);
assert.match(runnerCandidate.source, /一键生成待验收 Excel/);
for (const label of [
  "本地批次",
  "批次名称",
  "操作人",
  "最终合格目标数",
  "候选 ASIN 队列",
  "生成批次",
  "清理孤立存储",
  "删除已完成批次",
]) {
  assert.ok(runnerCandidate.source.includes(label), `Runner Chinese UI label missing: ${label}`);
}
assert.match(runnerCandidate.source, /@grant\s+GM_xmlhttpRequest/);
assert.match(runnerCandidate.source, /@grant\s+GM_download/);
assert.match(runnerCandidate.source, /DEFAULT_EXCEL_BRIDGE_URL = 'http:\/\/127\.0\.0\.1:8765'/);
assert.match(runnerCandidate.source, /url\.hostname !== '127\.0\.0\.1' && url\.hostname !== 'localhost'/);
assert.match(runnerCandidate.source, /payload\.accepted !== true \|\| payload\.machineAcceptancePassed !== true/);
assert.match(runnerCandidate.source, /productionHistoryUpdated/);
assert.match(runnerCandidate.source, /state\.status !== 'done'/);
assert.match(runnerCandidate.source, /@name\s+卖家精灵一体化选品 0\.3\.8\.1 中文 Excel 版/);

console.log("SellerSprite Chinese P1 + accepted Excel candidate pair: PASS");
