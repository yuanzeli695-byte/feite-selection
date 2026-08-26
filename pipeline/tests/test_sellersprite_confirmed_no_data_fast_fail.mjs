import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const collectorName = "sellersprite_traffic_collector_v0.4.6.4_zh_no_data_fast_fail.user.js";
const runnerName = "sellersprite_integrated_runner_v0.3.8.7_zh_no_data_fast_fail.user.js";

function loadCore(fileName, globalName, transform = (source) => source, runtime = {}) {
  const source = transform(fs.readFileSync(path.join(root, "scripts", fileName), "utf8"));
  const sandbox = {
    console,
    globalThis: {},
    location: { href: "https://www.amazon.com/dp/B0AAAA0001?th=1" },
    URL,
    ...runtime,
  };
  vm.runInNewContext(source, sandbox, { filename: fileName });
  return { core: sandbox.globalThis[globalName], sandbox, source };
}

function visibleNode(text, className = "") {
  return {
    innerText: text,
    textContent: text,
    tagName: "DIV",
    className,
    parentElement: null,
    querySelectorAll() { return []; },
    getBoundingClientRect() { return { x: 0, y: 0, width: 120, height: 24 }; },
  };
}

function collectorFixture({ text = "没有数据", removeAfterDelay = false, enabled = true } = {}) {
  let nowMs = 0;
  let present = true;
  class FakeDate extends Date {
    static now() { return nowMs; }
  }
  const emptyState = visibleNode(text, "ss-empty-state");
  const chart = visibleNode("", "echarts-trends-box");
  chart.querySelectorAll = () => (present ? [emptyState] : []);
  const parent = visibleNode("");
  parent.querySelectorAll = () => (present ? [emptyState] : []);
  chart.parentElement = parent;
  const loaded = loadCore(
    collectorName,
    "SSTrafficCollectorCore",
    enabled
      ? (source) => source
      : (source) => source.replace(
        "var ENABLE_CONFIRMED_NO_DATA_FAST_FAIL = true;",
        "var ENABLE_CONFIRMED_NO_DATA_FAST_FAIL = false;",
      ),
    {
      Date: FakeDate,
      setTimeout(callback, delayMs = 0) {
        nowMs += Number(delayMs) || 0;
        if (removeAfterDelay) present = false;
        queueMicrotask(callback);
        return nowMs;
      },
      clearTimeout() {},
    },
  );
  loaded.sandbox.document = {
    body: { innerText: "SellerSprite 自然流量" },
    querySelectorAll(selector) { return selector === ".echarts-trends-box" ? [chart] : []; },
    querySelector() { return null; },
  };
  loaded.sandbox.getComputedStyle = () => ({ display: "block", visibility: "visible" });
  return { ...loaded, nowMs: () => nowMs };
}

const collector = collectorFixture();
assert.equal(collector.core.confirmedNoDataFastFailEnabled, true);
assert.equal(collector.core.confirmedNoDataFastFailVersion, "confirmed-no-data-fast-fail-v1");
assert.equal(collector.core.noDataConfirmMs, 600);
assert.equal(collector.core.explicitNoDataPhrase(" 暂无数据。 "), true);
assert.equal(collector.core.explicitNoDataPhrase("No data"), true);
assert.equal(collector.core.explicitNoDataPhrase("库存没有数据"), false);
assert.equal(collector.core.explicitNoDataPhrase("No data available"), false);

const evidence = await collector.core.confirmExplicitNoData();
assert.equal(evidence.normalizedText, "没有数据");
assert.equal(evidence.stableMs, 600);
const result = collector.core.confirmedNoDataResult(evidence);
assert.equal(result.status, "no_data_confirmed");
assert.equal(result.decision, "fail");
assert.equal(result.pass70, false);
assert.equal(result.retryable, false);
assert.equal(result.shortCircuitReason, "seller_sprite_explicit_no_data");
assert.equal(result.details.length, 0);
assert.equal(result.method, "explicit_no_data_fast_fail");

const transient = collectorFixture({ removeAfterDelay: true });
assert.equal(await transient.core.confirmExplicitNoData(), null, "one transient empty marker is not confirmed");

const unrelated = collectorFixture({ text: "库存没有数据" });
assert.equal(unrelated.core.findExplicitNoDataEvidence(), null, "non-exact text must not trigger");

const disabled = collectorFixture({ enabled: false });
assert.equal(disabled.core.confirmedNoDataFastFailEnabled, false);
assert.equal(disabled.core.findExplicitNoDataEvidence(), null);

const runner = loadCore(runnerName, "SSIntegratedRunnerCore");
const previousCollector = loadCore(
  "sellersprite_traffic_collector_v0.4.6.3_zh_aggregate.user.js",
  "SSTrafficCollectorCore",
);
const previousRunner = loadCore(
  "sellersprite_integrated_runner_v0.3.8.6_zh_excel_aggregate.user.js",
  "SSIntegratedRunnerCore",
);
const payload = {
  status: "no_data_confirmed",
  decision: "fail",
  retryable: false,
  details: [],
  weeksRead: 0,
  aggregateWeeksRead: 0,
};
assert.equal(runner.core.confirmedNoDataFastFailEnabled, true);
assert.equal(runner.core.confirmedNoDataFastFailVersion, "confirmed-no-data-fast-fail-v1");
assert.equal(runner.core.collectorHasKnownTrafficFailure(payload), true);
assert.equal(runner.core.collectorRetryReason(payload), "");
assert.equal(runner.core.shouldRetryCollector(payload), false);
assert.equal(
  runner.core.shouldRetryCollector({ status: "no_data", decision: "review", details: [], weeksRead: 0 }),
  true,
  "ambiguous empty data keeps the existing single-retry behavior",
);
const parsed = runner.core.parseTrafficCollector(payload, "B0AAAA0001", "B0AAAA0001");
const gate = runner.core.evaluateTrafficGate(parsed, false);
assert.equal(gate.pass, false);
assert.equal(gate.rule, "traffic_no_data_confirmed");

const normalDetails = [
  { week: "2026-W31", weekSort: 202631, totalTraffic: 100, naturalTraffic: 80, naturalSharePct: 80 },
  { week: "2026-W30", weekSort: 202630, totalTraffic: 100, naturalTraffic: 70, naturalSharePct: 70 },
  { week: "2026-W29", weekSort: 202629, totalTraffic: 100, naturalTraffic: 60, naturalSharePct: 60 },
];
const currentNormal = collector.core.summarize(structuredClone(normalDetails), "fixture");
const previousNormal = previousCollector.core.summarize(structuredClone(normalDetails), "fixture");
delete currentNormal.collectedAt;
delete previousNormal.collectedAt;
assert.equal(
  JSON.stringify(currentNormal),
  JSON.stringify(previousNormal),
  "normal aggregate traffic evidence must remain byte-equivalent",
);
for (const functionName of [
  "buildDimensions",
  "buildPriceTrend",
  "classifyPriceSamples",
  "parsePriceTooltip",
  "evaluateDimensionsGate",
  "evaluatePriceGate",
  "currentPriceFromSamples",
  "isQualifiedResult",
]) {
  assert.equal(
    runner.core[functionName].toString(),
    previousRunner.core[functionName].toString(),
    `unrelated Runner function changed: ${functionName}`,
  );
}

assert.match(collector.source, /@version\s+0\.4\.6\.4/);
assert.match(runner.source, /@version\s+0\.3\.8\.7/);
console.log("SellerSprite confirmed no-data fast fail: PASS");
