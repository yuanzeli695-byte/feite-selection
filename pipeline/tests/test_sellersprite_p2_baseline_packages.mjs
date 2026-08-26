import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function source(fileName) {
  return fs.readFileSync(path.join(root, "scripts", fileName), "utf8");
}

function core(text, fileName, globalName, extras = {}) {
  const sandbox = { console, globalThis: {}, ...extras };
  vm.runInNewContext(text, sandbox, { filename: fileName });
  return sandbox.globalThis[globalName];
}

const collectorOnSource = source("sellersprite_traffic_collector_v0.4.7.user.js");
const collectorOffSource = source("sellersprite_traffic_collector_v0.4.7_p2off.user.js");
const runnerOnSource = source("sellersprite_integrated_runner_v0.3.9.user.js");
const runnerOffSource = source("sellersprite_integrated_runner_v0.3.9_p2off.user.js");

const collectorOn = core(collectorOnSource, "collector-on", "SSTrafficCollectorCore", {
  location: { href: "https://www.amazon.com/dp/B0AAAA0001?th=1" },
  URL,
});
const collectorOff = core(collectorOffSource, "collector-off", "SSTrafficCollectorCore", {
  location: { href: "https://www.amazon.com/dp/B0AAAA0001?th=1" },
  URL,
});
const runnerOn = core(runnerOnSource, "runner-on", "SSIntegratedRunnerCore");
const runnerOff = core(runnerOffSource, "runner-off", "SSIntegratedRunnerCore");

assert.equal(collectorOn.p2CollectorDeadlineEnabled, true);
assert.equal(collectorOff.p2CollectorDeadlineEnabled, false);
assert.equal(collectorOn.protocolVersion, "2");
assert.equal(collectorOff.protocolVersion, "1");
assert.equal(runnerOn.collectorDeadlineProtocolEnabled, true);
assert.equal(runnerOff.collectorDeadlineProtocolEnabled, false);
assert.equal(runnerOn.p2PairSandboxHistoryEnabled, true);
assert.equal(runnerOff.p2PairSandboxHistoryEnabled, true);
assert.equal(runnerOn.p2SandboxHistoryKey, "ssIntegratedRunner:v0.3:p2-paired-sandbox-history:on");
assert.equal(runnerOff.p2SandboxHistoryKey, "ssIntegratedRunner:v0.3:p2-paired-sandbox-history:off");
assert.ok(collectorOnSource.includes("SellerSprite Traffic Collector 0.4.7 [P2 candidate ON]"));
assert.ok(collectorOffSource.includes("SellerSprite Traffic Collector 0.4.7 [P2 baseline OFF]"));
assert.ok(runnerOnSource.includes("SellerSprite Integrated Runner 0.3.9 [P2 candidate ON]"));
assert.ok(runnerOffSource.includes("SellerSprite Integrated Runner 0.3.9 [P2 baseline OFF]"));

const normalizedCollectorOff = collectorOffSource
  .replace("SellerSprite Traffic Collector 0.4.7 [P2 baseline OFF]", "SellerSprite Traffic Collector 0.4.7 [P2 candidate ON]")
  .replace("@version      0.4.7-p2off", "@version      0.4.7")
  .replace("Paired-validation baseline with the P2 deadline protocol disabled.", "Adds a Collector-owned readiness deadline protocol without changing traffic parsing or gates.")
  .replace("var ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL = false;", "var ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL = true;")
  .replace("SellerSprite Traffic Collector ' + VERSION + ' P2 OFF", "SellerSprite Traffic Collector ' + VERSION + ' P2 ON");
assert.equal(normalizedCollectorOff, collectorOnSource, "Collector baseline package may differ only by metadata, flag, and visible OFF label");

const normalizedRunnerOff = runnerOffSource
  .replace("SellerSprite Integrated Runner 0.3.9 [P2 baseline OFF]", "SellerSprite Integrated Runner 0.3.9 [P2 candidate ON]")
  .replace("@version      0.3.9-p2off", "@version      0.3.9")
  .replace("Paired-validation baseline with the P2 deadline protocol disabled.", "P2 candidate: uses a Collector-owned deadline protocol while preserving strict gates and release authority.")
  .replace("var ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL = false;", "var ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL = true;")
  .replace("SellerSprite Integrated Runner ' + VERSION + ' P2 OFF", "SellerSprite Integrated Runner ' + VERSION + ' P2 ON");
assert.equal(normalizedRunnerOff, runnerOnSource, "Runner baseline package may differ only by metadata, flag, and visible OFF label");

assert.ok(!collectorOnSource.includes("@updateURL"));
assert.ok(!collectorOnSource.includes("@downloadURL"));
assert.ok(!collectorOffSource.includes("@updateURL"));
assert.ok(!collectorOffSource.includes("@downloadURL"));
assert.ok(!runnerOnSource.includes("@updateURL"));
assert.ok(!runnerOnSource.includes("@downloadURL"));
assert.ok(!runnerOffSource.includes("@updateURL"));
assert.ok(!runnerOffSource.includes("@downloadURL"));

console.log("SellerSprite P2 flag-off baseline packages: PASS");
