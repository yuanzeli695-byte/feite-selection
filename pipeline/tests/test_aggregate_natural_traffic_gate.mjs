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

const collector = loadCore(
  "sellersprite_traffic_collector_v0.4.6.3_zh_aggregate.user.js",
  "SSTrafficCollectorCore",
);
const runner = loadCore(
  "sellersprite_integrated_runner_v0.3.8.6_zh_excel_aggregate.user.js",
  "SSIntegratedRunnerCore",
);

const details = [
  { week: "2026-W31", weekSort: 202631, totalTraffic: 1000, naturalTraffic: 800, naturalSharePct: 80 },
  { week: "2026-W30", weekSort: 202630, totalTraffic: 100, naturalTraffic: 40, naturalSharePct: 40 },
  { week: "2026-W29", weekSort: 202629, totalTraffic: 100, naturalTraffic: 100, naturalSharePct: 100 },
];
const summary = collector.core.summarize(details, "fixture");
assert.equal(summary.aggregateNaturalTraffic, 940);
assert.equal(summary.aggregateTotalTraffic, 1200);
assert.equal(summary.aggregateWeeksRead, 3);
assert.equal(summary.aggregateNaturalSharePct, 940 / 1200 * 100);
assert.equal(summary.recent4MinNaturalSharePct, 40);
assert.equal(summary.pass70, true, "a low individual week must not fail an aggregate >=70% result");
assert.equal(summary.decision, "pass");

const parsed = runner.core.parseTrafficCollector(summary, "B0AAAA0001", "B0AAAA0001");
assert.equal(parsed.aggregateNaturalSharePct, 940 / 1200 * 100);
assert.equal(parsed.trafficDetails.length, 3);
assert.equal(runner.core.evaluateTrafficGate(parsed, false).pass, true);

const below = collector.core.summarize([
  { week: "2026-W31", weekSort: 202631, totalTraffic: 100, naturalTraffic: 80, naturalSharePct: 80 },
  { week: "2026-W30", weekSort: 202630, totalTraffic: 100, naturalTraffic: 50, naturalSharePct: 50 },
  { week: "2026-W29", weekSort: 202629, totalTraffic: 100, naturalTraffic: 60, naturalSharePct: 60 },
], "fixture");
assert.equal(below.pass70, false);
assert.equal(runner.core.evaluateTrafficGate(
  runner.core.parseTrafficCollector(below, "B0AAAA0001", "B0AAAA0001"),
  false,
).rule, "traffic_aggregate_below_70");

const insufficient = collector.core.summarize(details.slice(0, 2), "fixture");
assert.equal(insufficient.pass70, false);
assert.equal(insufficient.decision, "sample_low_review");

const boundary = collector.core.summarize([
  { week: "2026-W31", weekSort: 202631, totalTraffic: 100, naturalTraffic: 70, naturalSharePct: 70 },
  { week: "2026-W30", weekSort: 202630, totalTraffic: 100, naturalTraffic: 70, naturalSharePct: 70 },
  { week: "2026-W29", weekSort: 202629, totalTraffic: 100, naturalTraffic: 70, naturalSharePct: 70 },
], "fixture");
assert.equal(boundary.aggregateNaturalSharePct, 70);
assert.equal(boundary.pass70, true, "70% is inclusive");

const invalid = collector.core.summarize([
  ...details.slice(0, 2),
  { week: "2026-W29", weekSort: 202629, totalTraffic: 100, naturalTraffic: 101, naturalSharePct: 101 },
], "fixture");
assert.equal(invalid.aggregateWeeksRead, 2);
assert.equal(invalid.pass70, false, "invalid raw traffic cannot satisfy the three-week floor");

assert.equal(collector.core.aggregateNaturalTrafficGateEnabled, true);
assert.equal(runner.core.aggregateNaturalTrafficGateEnabled, true);
assert.match(collector.source, /@version\s+0\.4\.6\.3/);
assert.match(runner.source, /@version\s+0\.3\.8\.6/);

console.log("Aggregate natural traffic gate: PASS");
