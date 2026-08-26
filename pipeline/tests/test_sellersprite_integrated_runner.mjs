import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = fs.readFileSync(path.join(root, "scripts", "sellersprite_integrated_runner_v0.3.0.user.js"), "utf8");
const sandbox = { console, globalThis: {} };
vm.runInNewContext(source, sandbox, { filename: "sellersprite_integrated_runner_v0.3.0.user.js" });
const core = sandbox.globalThis.SSIntegratedRunnerCore;

assert.ok(core, "core API should be exposed for tests");
assert.equal(source.includes("view: window"), false, "sandboxed MouseEvent must not receive the userscript window proxy");
assert.ok(source.includes("canvas.ownerDocument && canvas.ownerDocument.defaultView"), "price-chart events must use the page window realm");

const traffic = core.parseTrafficCollector(
  {
    status: "ok",
    decision: "pass",
    latest: { week: "2026-W26", naturalSharePct: 92.5 },
    recent4AvgNaturalSharePct: 88.2,
    recent4MinNaturalSharePct: 75.1,
    weeksRead: 5,
    pass70: true,
    collectedAt: "2026-07-11T00:00:00Z",
  },
  "B0AAAA0001",
  "B0AAAA0001",
);
assert.equal(traffic.latestNaturalSharePct, 92.5);
assert.equal(traffic.weeksRead, 5);
assert.equal(traffic.pass70, true);
assert.equal(core.evaluateTrafficGate(traffic, false).pass, true);
assert.equal(core.evaluateTrafficGate({ ...traffic, latestNaturalSharePct: 69.99 }, false).rule, "traffic_latest_below_70");
assert.equal(core.evaluateTrafficGate({ ...traffic, recent4AvgNaturalSharePct: 69.99 }, false).rule, "traffic_recent4_avg_below_70");
assert.equal(core.evaluateTrafficGate({ ...traffic, recent4MinNaturalSharePct: 69.99 }, false).rule, "traffic_recent4_min_below_70");
assert.equal(core.evaluateTrafficGate(traffic, true).rule, "asin_mismatch");
assert.equal(core.collectorHasKnownTrafficFailure({ status: "ok", weeksRead: 1, latest: { naturalSharePct: 65 } }), true);
assert.equal(core.collectorHasKnownTrafficFailure({ status: "ok", weeksRead: 2, latest: { naturalSharePct: 85 }, recent4MinNaturalSharePct: 68 }), true);
assert.equal(core.collectorHasKnownTrafficFailure({ status: "ok", weeksRead: 2, latest: { naturalSharePct: 85 }, recent4MinNaturalSharePct: 75 }), false);
assert.equal(core.evaluateDimensionsGate("").rule, "dimensions_missing");
assert.equal(core.evaluatePriceGate("volatile").rule, "price_trend_not_allowed");
assert.equal(core.evaluatePriceGate("rising").pass, true);
const resultSummary = core.summarizeResults([
  { strictDecision: "pass" },
  { strictDecision: "reject" },
  { status: "ok", latestNaturalSharePct: 90, recent4AvgNaturalSharePct: 85, recent4MinNaturalSharePct: 75, weeksRead: 4, dimensions: "10 x 8 inches", priceTrendClass: "stable" },
  null,
]);
assert.equal(resultSummary.completed, 3);
assert.equal(resultSummary.qualified, 2);
assert.equal(resultSummary.rejected, 1);
assert.ok(source.indexOf("updateCurrentStep(state, 'traffic'") < source.indexOf("updateCurrentStep(state, 'dimensions'"));
assert.ok(source.indexOf("if (!trafficGate.pass)") < source.lastIndexOf("priceTrend = await collectPriceTrend()"));
assert.ok(source.includes("target_reached"));

const priceTooltip = core.parsePriceTooltip(
  "2026-07-10 Buybox价格 $17.89 价格 $17.89 大类BSR 404,721",
);
assert.deepEqual(priceTooltip && { date: priceTooltip.date, price: priceTooltip.price }, { date: "2026-07-10", price: 17.89 });

assert.equal(core.classifyPriceSamples([
  { date: "2026-07-01", price: 20 },
  { date: "2026-07-05", price: 20.5 },
  { date: "2026-07-10", price: 20.2 },
]), "stable");
assert.equal(core.classifyPriceSamples([
  { date: "2026-07-01", price: 14 },
  { date: "2026-07-05", price: 15 },
  { date: "2026-07-10", price: 17 },
]), "rising");
assert.equal(core.classifyPriceSamples([
  { date: "2026-07-01", price: 30 },
  { date: "2026-07-05", price: 28 },
  { date: "2026-07-10", price: 24.68 },
]), "declining");
assert.equal(core.classifyPriceSamples([
  { date: "2026-07-01", price: 10 },
  { date: "2026-07-03", price: 17 },
  { date: "2026-07-05", price: 11 },
  { date: "2026-07-07", price: 18 },
  { date: "2026-07-10", price: 12 },
]), "volatile");

assert.equal(
  core.buildDimensions({ itemDimensions: "2 x 3 x 4 inches", packageWeight: "0.5 pounds" }),
  "商品尺寸 2 x 3 x 4 inches；包装重量 0.5 pounds",
);
assert.equal(core.valueAfterLabel("商品尺寸:", "商品尺寸"), "");
assert.equal(core.valueAfterLabel('商品尺寸:2"L x 3"W x 4"H', "商品尺寸"), '2"L x 3"W x 4"H');

console.log("SellerSprite Integrated Runner core tests: PASS");
