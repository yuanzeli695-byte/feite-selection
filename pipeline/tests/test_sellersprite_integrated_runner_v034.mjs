import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = fs.readFileSync(path.join(root, "scripts", "sellersprite_integrated_runner_v0.3.4.user.js"), "utf8");
const sandbox = { console, globalThis: {} };
vm.runInNewContext(source, sandbox, { filename: "sellersprite_integrated_runner_v0.3.4.user.js" });
const core = sandbox.globalThis.SSIntegratedRunnerCore;

assert.ok(core, "core API should be exposed for tests");
assert.equal(core.evaluatePriceGate("stable", 19.99).pass, true);
assert.equal(core.evaluatePriceGate("rising", 50).pass, true);
assert.equal(core.evaluatePriceGate("stable", 50.01).rule, "price_current_out_of_range");
assert.equal(core.evaluatePriceGate("stable", 9.89).rule, "price_current_out_of_range");
assert.equal(core.evaluatePriceGate("stable", null).rule, "price_current_missing");

const trend = core.buildPriceTrend([
  { date: "2026-07-01", price: 15 },
  { date: "2026-07-05", price: 15.2 },
  { date: "2026-07-10", price: 15.1 },
]);
assert.equal(trend.currentPrice, 15.1);
assert.equal(trend.priceMin, 15);
assert.equal(trend.priceMax, 15.2);
assert.equal(
  core.isQualifiedResult({
    status: "ok",
    latestNaturalSharePct: 90,
    recent4AvgNaturalSharePct: 85,
    recent4MinNaturalSharePct: 75,
    weeksRead: 4,
    dimensions: "10 x 8 inches",
    priceTrendClass: "stable",
    priceSamples: [{ date: "2026-07-10", price: 55 }],
  }),
  false,
);

console.log("SellerSprite Integrated Runner 0.3.4 price-gate tests: PASS");
