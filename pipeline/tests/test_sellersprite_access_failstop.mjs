import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function loadCore(fileName, globalName) {
  const source = fs.readFileSync(path.join(root, "scripts", fileName), "utf8");
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

const runnerPrevious = loadCore(
  "sellersprite_integrated_runner_v0.3.8_zh_excel.user.js",
  "SSIntegratedRunnerCore",
);
const runnerCandidate = loadCore(
  "sellersprite_integrated_runner_v0.3.8.2_zh_excel.user.js",
  "SSIntegratedRunnerCore",
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
    runnerCandidate.core[functionName].toString(),
    runnerPrevious.core[functionName].toString(),
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
    runnerPrevious.core[functionName].toString(),
    `Runner P1 function changed: ${functionName}`,
  );
}

const loginBlocked = plain(runnerCandidate.core.classifySellerSpriteAccessState({ loginVisible: true }));
assert.equal(loginBlocked.code, "seller_sprite_login_required");
assert.match(loginBlocked.message, /未登录/);

const paidBlocked = plain(runnerCandidate.core.classifySellerSpriteAccessState({
  loginVisible: false,
  contentText: "仅限付费用户，升级套餐 后即可查看",
}));
assert.equal(paidBlocked.code, "seller_sprite_paid_plan_required");
assert.match(paidBlocked.message, /付费套餐/);

assert.equal(
  runnerCandidate.core.classifySellerSpriteAccessState({
    loginVisible: false,
    contentText: "流量图已加载",
  }),
  null,
);
const existingResults = [{ strictDecision: "reject" }];
const paused = runnerCandidate.core.applySellerSpriteAccessPause({
  status: "running",
  currentIndex: 4,
  currentStep: "traffic",
  results: existingResults,
}, 4, "B0AAAA0001", paidBlocked, 123456);
assert.equal(paused.status, "paused");
assert.equal(paused.currentIndex, 4);
assert.equal(paused.currentStep, "external_blocked");
assert.equal(paused.results, existingResults);
assert.equal(paused.externalBlockerCode, "seller_sprite_paid_plan_required");
assert.equal(paused.externalBlockerAsin, "B0AAAA0001");
assert.equal(paused.pauseId, "seller-sprite-access-123456");

assert.match(runnerCandidate.source, /@version\s+0\.3\.8\.2/);
assert.match(runnerCandidate.source, /recordControlEvent\(state, 'seller_sprite_access_blocked'/);
assert.match(runnerCandidate.source, /finalizeActiveGranular\('seller_sprite_access_blocked'/);
assert.match(runnerCandidate.source, /if \(chartReady\.accessBlocker\) throw sellerSpriteAccessError/);
assert.match(runnerCandidate.source, /seller_sprite_collector_unavailable/);
assert.match(runnerCandidate.source, /seller_sprite_traffic_tab_unavailable/);
assert.match(runnerCandidate.source, /seller_sprite_traffic_chart_unavailable/);

console.log("SellerSprite access fail-stop: PASS");
