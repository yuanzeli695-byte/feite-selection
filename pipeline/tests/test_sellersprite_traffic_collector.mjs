import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = fs.readFileSync(path.join(root, "scripts", "sellersprite_traffic_collector_v0.4.4.user.js"), "utf8");
const sandbox = { console, globalThis: {} };
vm.runInNewContext(source, sandbox, { filename: "sellersprite_traffic_collector_v0.4.4.user.js" });
const core = sandbox.globalThis.SSTrafficCollectorCore;

assert.ok(core, "collector core API should be exposed for tests");
assert.equal(core.maxRecentWeeks, 4);
assert.equal(core.minRequiredWeeks, 3);
assert.equal(
  core.earlyTrafficFailureReason([{ weekSort: 202627, naturalSharePct: 69.99 }]),
  "traffic_latest_below_70",
);
assert.equal(
  core.earlyTrafficFailureReason([
    { weekSort: 202627, naturalSharePct: 85 },
    { weekSort: 202626, naturalSharePct: 68 },
  ]),
  "traffic_recent4_min_below_70",
);
assert.equal(
  core.earlyTrafficFailureReason([
    { weekSort: 202627, naturalSharePct: 85 },
    { weekSort: 202626, naturalSharePct: 72 },
    { weekSort: 202625, naturalSharePct: 75 },
  ]),
  "",
);
assert.ok(source.includes("failed.shortCircuited = true"));
assert.ok(source.indexOf("if (earlyReason)") < source.indexOf("if (details.length >= MAX_RECENT_WEEKS)"));

console.log("SellerSprite Traffic Collector 0.4.4 baseline tests: PASS");
