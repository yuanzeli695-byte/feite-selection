import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const fixtures = JSON.parse(
  fs.readFileSync(path.join(root, "tests", "fixtures", "sellersprite_tier2_tooltips.json"), "utf8"),
);

function loadCore(fileName, transform) {
  let source = fs.readFileSync(path.join(root, "scripts", fileName), "utf8");
  if (transform) source = transform(source);
  const sandbox = {
    console,
    globalThis: {},
    location: { href: "https://www.amazon.com/dp/B0AAAA0001?th=1" },
    URL,
  };
  vm.runInNewContext(source, sandbox, { filename: fileName });
  return { core: sandbox.globalThis.SSTrafficCollectorCore, source };
}

function exposeBaselineParser(source) {
  return source.replace(
    "globalThis.SSTrafficCollectorCore = Object.freeze({",
    "globalThis.SSTrafficCollectorCore = Object.freeze({\n    parseTip: parseTip,\n    summarize: summarize,",
  );
}

function comparable(value) {
  return JSON.stringify(value);
}

const baseline = loadCore("sellersprite_traffic_collector_v0.4.5.user.js", exposeBaselineParser);
const tier2 = loadCore("sellersprite_traffic_collector_v0.4.6.user.js");
const disabled = loadCore("sellersprite_traffic_collector_v0.4.6.user.js", (source) =>
  source.replace(
    "var ENABLE_TIER2_1_ZERO_SHARE_DERIVATION = true;",
    "var ENABLE_TIER2_1_ZERO_SHARE_DERIVATION = false;",
  ),
);

assert.ok(baseline.core?.parseTip);
assert.ok(tier2.core?.parseTip);
assert.equal(tier2.core.tier21ZeroShareEnabled, true);
assert.equal(tier2.core.tier2ReaderVersion, "tier2.1-zero-share-v1");
assert.equal(disabled.core.tier21ZeroShareEnabled, false);

for (const fixture of fixtures) {
  const parsed = tier2.core.parseTip(fixture.rawText);
  assert.equal(parsed.totalTraffic, fixture.expected.totalTraffic, `${fixture.id}: total traffic`);
  assert.equal(parsed.naturalTraffic, fixture.expected.naturalTraffic, `${fixture.id}: natural traffic`);
  assert.equal(parsed.naturalSharePct, fixture.expected.naturalSharePct, `${fixture.id}: natural share`);
  assert.equal(parsed.naturalShareDerived, fixture.expected.naturalShareDerived, `${fixture.id}: derivation audit`);

  const baselineParsed = baseline.core.parseTip(fixture.rawText);
  const disabledParsed = disabled.core.parseTip(fixture.rawText);
  assert.equal(
    comparable(disabledParsed),
    comparable(baselineParsed),
    `${fixture.id}: disabling Tier 2.1 must restore 0.4.5 parser output`,
  );
}

const zeroFixture = fixtures.find((fixture) => fixture.shape === "explicit_zero");
const zeroBaseline = baseline.core.parseTip(zeroFixture.rawText);
const zeroTier2 = tier2.core.parseTip(zeroFixture.rawText);
assert.equal(zeroBaseline.naturalSharePct, null);
assert.equal(zeroTier2.naturalSharePct, 0);
assert.equal(zeroTier2.naturalShareSource, "derived_explicit_zero_over_positive_total");
assert.equal(tier2.core.earlyTrafficFailureReason([zeroTier2]), "traffic_latest_below_70");

const dashFixture = fixtures.find((fixture) => fixture.shape === "dash_missing");
const dashTier2 = tier2.core.parseTip(dashFixture.rawText);
assert.equal(dashTier2.naturalTraffic, null, "-- must not be parsed from the delta value");
assert.equal(dashTier2.naturalSharePct, null);
assert.equal(dashTier2.naturalShareSource, "missing");

const zeroTotalFixture = fixtures.find((fixture) => fixture.shape === "share_missing_total_zero");
const zeroTotalTier2 = tier2.core.parseTip(zeroTotalFixture.rawText);
assert.equal(zeroTotalTier2.totalTraffic, 0);
assert.equal(zeroTotalTier2.naturalTraffic, 0);
assert.equal(zeroTotalTier2.naturalSharePct, null, "0/0 must remain missing");

const ambiguous = tier2.core.parseTip(
  "2026第26周(06/21~06/27)\n总流量\n100\n自然流量\n0?\nSP广告流量\n100\n占比100%",
);
assert.equal(ambiguous.naturalTraffic, null);
assert.equal(ambiguous.naturalSharePct, null);
assert.equal(ambiguous.naturalShareDerived, false);

const summary = tier2.core.summarize([
  tier2.core.parseTip(zeroFixture.rawText),
  { week: "2026第24周", weekSort: 202624, naturalSharePct: 80 },
  { week: "2026第25周", weekSort: 202625, naturalSharePct: 85 },
], "tier2_fixture_summary");
assert.equal(summary.weeksRead, 3, "derived zero is a valid read week");
assert.equal(summary.recent4MinNaturalSharePct, 0);
assert.equal(summary.pass70, false);
assert.equal(summary.decision, "fail");

assert.ok(tier2.source.includes("@version      0.4.6"));
assert.ok(tier2.source.includes("ENABLE_TIER2_1_ZERO_SHARE_DERIVATION"));

console.log("SellerSprite Traffic Collector 0.4.6 Tier 2.1 tests: PASS");
