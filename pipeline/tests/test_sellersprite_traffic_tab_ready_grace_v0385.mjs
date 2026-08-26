import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const baselineName = "sellersprite_integrated_runner_v0.3.8.2_zh_excel.user.js";
const candidateName = "sellersprite_integrated_runner_v0.3.8.5_zh_excel_8s_ready_candidate.user.js";

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

function loadFixture({ availableAtMs = null, blockerAtMs = null, enabled = true } = {}) {
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
    candidateName,
    enabled
      ? (source) => source
      : (source) => source.replace(
        "var ENABLE_TRAFFIC_TAB_READY_GRACE = true;",
        "var ENABLE_TRAFFIC_TAB_READY_GRACE = false;",
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
      return availableAtMs !== null && nowMs >= availableAtMs ? [tab] : [];
    },
  };
  loaded.sandbox.getComputedStyle = () => ({ display: "block", visibility: "visible" });
  return { ...loaded, clickCount: () => clickCount, nowMs: () => nowMs };
}

const baseline = loadCore(baselineName);
const candidate = loadCore(candidateName);
const candidateOff = loadCore(
  candidateName,
  (source) => source.replace(
    "var ENABLE_TRAFFIC_TAB_READY_GRACE = true;",
    "var ENABLE_TRAFFIC_TAB_READY_GRACE = false;",
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
    `0.3.8.2 invariant changed: ${functionName}`,
  );
}

assert.equal(candidate.core.trafficTabReadyGraceEnabled, true);
assert.equal(candidateOff.core.trafficTabReadyGraceEnabled, false);
assert.equal(candidate.core.trafficTabReadyGraceVersion, "traffic-tab-ready-grace-8s-v1");
assert.equal(candidate.core.trafficTabReadyGraceMs, 8000);
assert.match(candidate.source, /@version\s+0\.3\.8\.5/);
assert.match(candidate.source, /TRAFFIC_TAB_READY_GRACE_MS = 8000/);
assert.match(candidate.source, /await clickTrafficTabWithGrace\(\)/);
assert.doesNotMatch(candidate.source, /traffic_tab_same_row_reload/);
assert.doesNotMatch(candidate.source, /MAX_TRAFFIC_TAB_RELOADS/);
for (const column of [
  "trafficTabWaitStartedAtMs",
  "trafficTabGraceWaitMs",
  "trafficTabPollCount",
  "trafficTabGraceRecovered",
]) {
  assert.ok(candidate.core.granularTimingColumns.includes(column), `missing granular field: ${column}`);
}

const immediate = loadFixture({ availableAtMs: 0 });
const immediateResult = await immediate.core.clickTrafficTabWithGrace();
assert.deepEqual(
  {
    found: immediateResult.found,
    clickedAtMs: immediateResult.clickedAtMs,
    pollCount: immediateResult.pollCount,
    waitMs: immediateResult.waitMs,
  },
  { found: true, clickedAtMs: 0, pollCount: 1, waitMs: 0 },
);
assert.equal(immediate.clickCount(), 1);

const delayed = loadFixture({ availableAtMs: 2000 });
const delayedResult = await delayed.core.clickTrafficTabWithGrace();
assert.equal(delayedResult.found, true);
assert.equal(delayedResult.clickedAtMs, 2000);
assert.equal(delayedResult.pollCount, 21);
assert.equal(delayedResult.waitMs, 2000);

const late = loadFixture({ availableAtMs: 7900 });
const lateResult = await late.core.clickTrafficTabWithGrace();
assert.equal(lateResult.found, true);
assert.equal(lateResult.clickedAtMs, 7900);
assert.equal(lateResult.pollCount, 80);
assert.equal(lateResult.waitMs, 7900);

const missing = loadFixture();
const missingResult = await missing.core.clickTrafficTabWithGrace();
assert.equal(missingResult.found, false);
assert.equal(missingResult.clickedAtMs, null);
assert.equal(missingResult.pollCount, 80);
assert.equal(missingResult.waitMs, 8000);
assert.equal(missing.clickCount(), 0);

const blocked = loadFixture({ blockerAtMs: 100 });
await assert.rejects(
  blocked.core.clickTrafficTabWithGrace(),
  (error) => error.code === "SS_SELLERSPRITE_ACCESS_BLOCKED"
    && error.accessBlocker.code === "seller_sprite_login_required",
);
assert.equal(blocked.nowMs(), 100);
assert.equal(blocked.clickCount(), 0);

const disabled = loadFixture({ enabled: false });
const disabledResult = await disabled.core.clickTrafficTabWithGrace();
assert.equal(disabledResult.found, false);
assert.equal(disabledResult.pollCount, 1);
assert.equal(disabledResult.waitMs, 0, "feature flag OFF must reproduce the 0.3.8.2 immediate miss");

console.log("SellerSprite Runner 0.3.8.5 8-second readiness candidate: PASS");
