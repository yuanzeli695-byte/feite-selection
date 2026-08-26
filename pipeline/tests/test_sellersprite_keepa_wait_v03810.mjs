import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const candidateName = "sellersprite_integrated_runner_v0.3.8.10_zh_keepa_20s.user.js";
const baselineName = "sellersprite_integrated_runner_v0.3.8.7_zh_no_data_fast_fail.user.js";

function loadCore(fileName, transform = (source) => source, runtime = {}) {
  const source = transform(fs.readFileSync(path.join(root, "scripts", fileName), "utf8"));
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

function keepaFixture({ canvasAtMs = 0, tooltipAtMs = 0 } = {}) {
  let nowMs = 0;
  let retries = 0;
  class FakeDate extends Date {
    static now() { return nowMs; }
  }
  class FakeMouseEvent {
    constructor(type, init) {
      this.type = type;
      Object.assign(this, init);
    }
  }
  const canvas = {
    width: 900,
    height: 320,
    ownerDocument: { defaultView: { MouseEvent: FakeMouseEvent, PointerEvent: FakeMouseEvent } },
    dispatchEvent() {},
    getBoundingClientRect() { return { left: 0, top: 0, width: 900, height: 320 }; },
  };
  const tooltip = {
    textContent: "2026-07-12 Buybox价格 $13.99",
    getBoundingClientRect() { return { width: 180, height: 90 }; },
  };
  const module = {
    querySelectorAll(selector) {
      if (selector === "canvas") return nowMs >= canvasAtMs ? [canvas] : [];
      if (selector === "div") return nowMs >= tooltipAtMs ? [tooltip] : [];
      return [];
    },
  };
  const loaded = loadCore(candidateName, (source) => source, {
    Date: FakeDate,
    MouseEvent: FakeMouseEvent,
    PointerEvent: FakeMouseEvent,
    setTimeout(callback, delayMs = 0) {
      nowMs += Number(delayMs) || 0;
      queueMicrotask(callback);
      return nowMs;
    },
    clearTimeout() {},
  });
  loaded.sandbox.document = {
    querySelector(selector) { return selector === ".keepa-module" ? module : null; },
  };
  loaded.sandbox.getComputedStyle = (element) => ({
    display: "block",
    visibility: "visible",
    position: element === tooltip ? "absolute" : "static",
    zIndex: element === tooltip ? "10" : "0",
  });
  return {
    ...loaded,
    module,
    nowMs: () => nowMs,
    retry: async () => { retries += 1; },
    retries: () => retries,
  };
}

const immediate = keepaFixture();
const immediateReady = await immediate.core.waitForKeepaChartReady(immediate.module, immediate.retry);
assert.equal(immediateReady.seedSample.price, 13.99);
assert.equal(immediateReady.retryCount, 0);
assert.equal(immediate.retries(), 0);

const delayedCanvas = keepaFixture({ canvasAtMs: 8000, tooltipAtMs: 8000 });
const delayedCanvasReady = await delayedCanvas.core.waitForKeepaChartReady(
  delayedCanvas.module,
  delayedCanvas.retry,
);
assert.equal(delayedCanvasReady.seedSample.price, 13.99);
assert.equal(delayedCanvasReady.retryCount, 1);
assert.equal(delayedCanvas.retries(), 1);
assert.ok(delayedCanvasReady.waitMs >= 8000 && delayedCanvasReady.waitMs < 10000);

const delayedTooltip = keepaFixture({ canvasAtMs: 0, tooltipAtMs: 8000 });
const delayedTooltipReady = await delayedTooltip.core.waitForKeepaChartReady(
  delayedTooltip.module,
  delayedTooltip.retry,
);
assert.equal(delayedTooltipReady.seedSample.price, 13.99);
assert.equal(delayedTooltipReady.retryCount, 1);
assert.equal(delayedTooltip.retries(), 1);
assert.ok(delayedTooltipReady.waitMs >= 8000 && delayedTooltipReady.waitMs < 10000);

const lateChart = keepaFixture({ canvasAtMs: 15000, tooltipAtMs: 15000 });
const lateChartReady = await lateChart.core.waitForKeepaChartReady(lateChart.module, lateChart.retry);
assert.equal(lateChartReady.seedSample.price, 13.99);
assert.equal(lateChartReady.retryCount, 1);
assert.equal(lateChart.retries(), 1);
assert.ok(lateChartReady.waitMs >= 15000 && lateChartReady.waitMs < 20000);

const missingTooltip = keepaFixture({ canvasAtMs: 0, tooltipAtMs: Number.POSITIVE_INFINITY });
const missingTooltipResult = await missingTooltip.core.waitForKeepaChartReady(
  missingTooltip.module,
  missingTooltip.retry,
);
assert.equal(missingTooltipResult.seedSample, null);
assert.equal(missingTooltipResult.sawCanvas, true);
assert.equal(missingTooltipResult.retryCount, 1);
assert.equal(missingTooltip.retries(), 1);
assert.ok(missingTooltipResult.waitMs >= 20000);

const missingCanvas = keepaFixture({
  canvasAtMs: Number.POSITIVE_INFINITY,
  tooltipAtMs: Number.POSITIVE_INFINITY,
});
const missingCanvasResult = await missingCanvas.core.waitForKeepaChartReady(
  missingCanvas.module,
  missingCanvas.retry,
);
assert.equal(missingCanvasResult.canvas, null);
assert.equal(missingCanvasResult.sawCanvas, false);
assert.equal(missingCanvasResult.retryCount, 1);
assert.equal(missingCanvas.retries(), 1);

const candidate = loadCore(candidateName);
const baseline = loadCore(baselineName);
assert.equal(candidate.core.keepaChartReadyEnabled, true);
assert.equal(candidate.core.keepaChartReadyVersion, "keepa-chart-ready-20s-v2");
assert.equal(candidate.core.keepaChartReadyTimeoutMs, 20000);
assert.equal(candidate.core.keepaChartReadyRetryAtMs, 5000);
assert.equal(candidate.core.keepaParentClickEnabled, true);
assert.equal(candidate.core.keepaParentClickVersion, "keepa-parent-click-v1");
assert.equal(candidate.core.keepaTabReadyTimeoutMs, 8000);
assert.match(candidate.source, /@version\s+0\.3\.8\.10/);
assert.match(candidate.source, /keepa_tooltip_not_ready/);
assert.match(candidate.source, /keepaModuleIsLoading\(currentModule\)/);
assert.match(candidate.source, /clickKeepaTab\(document\)/);
assert.doesNotMatch(candidate.source, /if \(!canvas\) return buildPriceTrend\(\[\]\)/);

let parentClicks = 0;
const keepaLabel = {
  textContent: "Keepa插件替代",
  children: [],
  parentElement: null,
  closest(selector) { return selector === ".list" ? keepaParent : null; },
  getBoundingClientRect() { return { width: 80, height: 20 }; },
};
const keepaParent = {
  className: "list",
  children: [keepaLabel],
  textContent: "Keepa插件替代",
  getBoundingClientRect() { return { width: 100, height: 24 }; },
  click() { parentClicks += 1; },
};
keepaLabel.parentElement = keepaParent;
candidate.sandbox.document = {
  querySelectorAll() { return [keepaLabel, keepaParent]; },
};
candidate.sandbox.getComputedStyle = () => ({ display: "block", visibility: "visible" });
assert.equal(candidate.core.keepaTabTarget(candidate.sandbox.document), keepaParent);
assert.equal(candidate.core.clickKeepaTab(candidate.sandbox.document), true);
assert.equal(parentClicks, 1);

for (const functionName of [
  "buildDimensions",
  "buildPriceTrend",
  "classifyPriceSamples",
  "parsePriceTooltip",
  "evaluateTrafficGate",
  "evaluateDimensionsGate",
  "evaluatePriceGate",
  "currentPriceFromSamples",
  "isQualifiedResult",
]) {
  assert.equal(
    candidate.core[functionName].toString(),
    baseline.core[functionName].toString(),
    `hard-gate function changed: ${functionName}`,
  );
}

console.log("SellerSprite Keepa 20-second readiness 0.3.8.10: PASS");
