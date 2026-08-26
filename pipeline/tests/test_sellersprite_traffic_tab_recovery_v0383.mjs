import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function loadCore(fileName, transform = (source) => source, runtime = {}) {
  const filePath = path.join(root, "scripts", fileName);
  const source = transform(fs.readFileSync(filePath, "utf8"));
  const sandbox = {
    console,
    globalThis: {},
    location: { href: "https://www.amazon.com/dp/B0AAAA0001?th=1" },
    URL,
    ...runtime,
  };
  vm.runInNewContext(source, sandbox, { filename: fileName });
  return { core: sandbox.globalThis.SSIntegratedRunnerCore, sandbox, source };
}

function loadTrafficTabFixture({ availableAtMs = null, blockerAtMs = null, enabled = true, scanCostMs = 0 } = {}) {
  let nowMs = 0;
  let clickCount = 0;
  const visibleElement = (textContent = "") => ({
    textContent,
    children: [],
    click() { clickCount += 1; },
    getBoundingClientRect() { return { width: 120, height: 24 }; },
  });
  const tab = visibleElement("流量洞察");
  const loginBlocker = visibleElement("login required");
  class FakeDate extends Date {
    static now() { return nowMs; }
  }
  const loaded = loadCore(
    "sellersprite_integrated_runner_v0.3.8.3_zh_excel_p2_candidate.user.js",
    enabled
      ? (source) => source
      : (source) => source.replace(
        "var ENABLE_TIER2_TRAFFIC_TAB_RECOVERY = true;",
        "var ENABLE_TIER2_TRAFFIC_TAB_RECOVERY = false;",
      ),
    {
      Date: FakeDate,
      setTimeout(callback, delayMs = 0) {
        nowMs += Number(delayMs) || 0;
        queueMicrotask(callback);
        return nowMs;
      },
      clearTimeout() {},
    },
  );
  loaded.sandbox.document = {
    querySelector(selector) {
      if (selector === ".ext-sign-in-container"
          && blockerAtMs !== null
          && nowMs >= blockerAtMs) {
        return loginBlocker;
      }
      return null;
    },
    querySelectorAll() {
      if (availableAtMs !== null && nowMs >= availableAtMs) {
        nowMs += Number(scanCostMs) || 0;
        return [tab];
      }
      return [];
    },
  };
  loaded.sandbox.getComputedStyle = () => ({ display: "block", visibility: "visible" });
  return {
    ...loaded,
    clickCount: () => clickCount,
    nowMs: () => nowMs,
  };
}

const baseline = loadCore("sellersprite_integrated_runner_v0.3.8.2_zh_excel.user.js");
const candidate = loadCore("sellersprite_integrated_runner_v0.3.8.3_zh_excel_p2_candidate.user.js");
const candidateOff = loadCore(
  "sellersprite_integrated_runner_v0.3.8.3_zh_excel_p2_candidate.user.js",
  (source) => source.replace(
    "var ENABLE_TIER2_TRAFFIC_TAB_RECOVERY = true;",
    "var ENABLE_TIER2_TRAFFIC_TAB_RECOVERY = false;",
  ),
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
    candidate.core[functionName].toString(),
    baseline.core[functionName].toString(),
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
  "commitCompletedRow",
  "classifySellerSpriteAccessState",
  "applySellerSpriteAccessPause",
]) {
  assert.equal(
    candidate.core[functionName].toString(),
    baseline.core[functionName].toString(),
    `Runner invariant function changed: ${functionName}`,
  );
}

assert.equal(candidate.core.tier2TrafficTabRecoveryEnabled, true);
assert.equal(candidateOff.core.tier2TrafficTabRecoveryEnabled, false);
assert.equal(candidate.core.trafficTabRecoveryVersion, "tier2-traffic-tab-recovery-v1");
assert.equal(candidate.core.trafficTabReadyGraceMs, 2000);
assert.equal(candidate.core.maxTrafficTabReloads, 1);

const state = { results: [], status: "running" };
assert.equal(candidate.core.trafficTabRecoveryDecision(state, 4, "B0AAAA0001").action, "reload");
const marker = candidate.core.markTrafficTabRecovery(state, 4, "B0AAAA0001", 123456);
assert.equal(marker.attempts, 1);
assert.equal(marker.index, 4);
assert.equal(marker.asin, "B0AAAA0001");
assert.equal(candidate.core.trafficTabRecoveryDecision(state, 4, "B0AAAA0001").action, "pause");
assert.equal(candidate.core.trafficTabRecoveryDecision(state, 5, "B0BBBB0002").action, "reload");
assert.equal(candidateOff.core.trafficTabRecoveryDecision({}, 4, "B0AAAA0001").action, "pause");
candidate.core.applySellerSpriteAccessPause(
  state,
  4,
  "B0AAAA0001",
  { code: "seller_sprite_login_required", message: "login required" },
  123500,
);
assert.equal(
  candidate.core.trafficTabRecoveryDecision(state, 4, "B0AAAA0001").action,
  "pause",
  "a different access blocker must not reset the one-reload limit",
);
const operatorPause = {
  status: "paused",
  pauseId: "operator-pause-1",
  pausedAtMs: 123501,
  message: "manual pause",
  trafficTabRecovery: { index: 4, asin: "B0AAAA0001", attempts: 1 },
};
const operatorPauseBefore = JSON.stringify(operatorPause);
assert.equal(candidate.core.trafficTabAccessAction(operatorPause, 4, "B0AAAA0001").action, "preserve_pause");
assert.equal(JSON.stringify(operatorPause), operatorPauseBefore, "operator pause ownership must remain unchanged");
assert.equal(candidate.core.clearTrafficTabRecovery(state, 5, "B0BBBB0002"), false);
assert.equal(candidate.core.clearTrafficTabRecovery(state, 4, "B0AAAA0001"), true);
assert.equal("trafficTabRecovery" in state, false);

assert.match(candidate.source, /@version\s+0\.3\.8\.3/);
assert.match(candidate.source, /await clickTrafficTabWithGrace\(\)/);
assert.match(candidate.source, /clickExactText\('流量洞察'\)/);
assert.match(candidate.source, /TRAFFIC_TAB_READY_GRACE_MS = 2000/);
assert.match(candidate.source, /traffic_tab_same_row_reload/);
assert.match(candidate.source, /traffic_tab_reload_exhausted/);
assert.match(candidate.source, /trafficTabReady\.found && trafficTabReady\.pollCount > 1/);
assert.match(candidate.source, /saveBatch\(state\);\s+finalizeActiveGranular\('traffic_tab_same_row_reload'/s);
assert.match(candidate.source, /clearTrafficTabRecovery\(state, index, targetAsin\)/);
assert.match(candidate.source, /traffic_tab_recovery_cancelled_by_pause/);
for (const column of [
  "trafficTabWaitStartedAtMs",
  "trafficTabGraceWaitMs",
  "trafficTabPollCount",
  "trafficTabGraceRecovered",
]) {
  assert.ok(candidate.core.granularTimingColumns.includes(column), `missing granular field: ${column}`);
}

const immediate = loadTrafficTabFixture({ availableAtMs: 0 });
const immediateResult = await immediate.core.clickTrafficTabWithGrace();
assert.deepEqual(
  {
    found: immediateResult.found,
    waitStartedAtMs: immediateResult.waitStartedAtMs,
    clickedAtMs: immediateResult.clickedAtMs,
    pollCount: immediateResult.pollCount,
    waitMs: immediateResult.waitMs,
  },
  { found: true, waitStartedAtMs: 0, clickedAtMs: 0, pollCount: 1, waitMs: 0 },
);
assert.equal(immediate.clickCount(), 1);

const slowFirstScan = loadTrafficTabFixture({ availableAtMs: 0, scanCostMs: 150 });
const slowFirstScanResult = await slowFirstScan.core.clickTrafficTabWithGrace();
assert.equal(slowFirstScanResult.clickedAtMs, 150, "click time must be recorded after the successful DOM scan");
assert.equal(slowFirstScanResult.waitMs, 150);
assert.equal(slowFirstScanResult.pollCount, 1, "a slow first scan is not a grace recovery");

const delayed = loadTrafficTabFixture({ availableAtMs: 100 });
const delayedResult = await delayed.core.clickTrafficTabWithGrace();
assert.equal(delayedResult.found, true);
assert.equal(delayedResult.clickedAtMs, 100);
assert.equal(delayedResult.pollCount, 2);
assert.equal(delayedResult.waitMs, 100);
assert.equal(delayed.clickCount(), 1);

const late = loadTrafficTabFixture({ availableAtMs: 1900 });
const lateResult = await late.core.clickTrafficTabWithGrace();
assert.equal(lateResult.found, true);
assert.equal(lateResult.clickedAtMs, 1900);
assert.equal(lateResult.pollCount, 20);
assert.equal(lateResult.waitMs, 1900);

const missing = loadTrafficTabFixture();
const missingResult = await missing.core.clickTrafficTabWithGrace();
assert.equal(missingResult.found, false);
assert.equal(missingResult.clickedAtMs, null);
assert.equal(missingResult.pollCount, 20);
assert.equal(missingResult.waitMs, 2000);
assert.equal(missing.clickCount(), 0);

const blocked = loadTrafficTabFixture({ blockerAtMs: 100 });
await assert.rejects(
  blocked.core.clickTrafficTabWithGrace(),
  (error) => error.code === "SS_SELLERSPRITE_ACCESS_BLOCKED"
    && error.accessBlocker.code === "seller_sprite_login_required",
);
assert.equal(blocked.nowMs(), 100);
assert.equal(blocked.clickCount(), 0);

const disabled = loadTrafficTabFixture({ enabled: false });
const disabledResult = await disabled.core.clickTrafficTabWithGrace();
assert.equal(disabledResult.found, false);
assert.equal(disabledResult.pollCount, 1);
assert.equal(disabledResult.waitMs, 0, "feature flag OFF must reproduce the immediate baseline miss");

console.log("SellerSprite Runner 0.3.8.3 traffic-tab recovery candidate: PASS");
