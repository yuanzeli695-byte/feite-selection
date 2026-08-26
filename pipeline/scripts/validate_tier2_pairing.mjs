import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const inputPath = path.resolve(root, process.argv[2] || "runs/new_20260710_batch2/batch_batch2.json");
const outputDir = path.resolve(root, process.argv[3] || "runs/tier2_pair_validation_20260713");
const sampleTarget = Number(process.argv[4] || 30);

function loadCore(fileName, globalName, transform) {
  let source = fs.readFileSync(path.join(root, "scripts", fileName), "utf8");
  if (transform) source = transform(source);
  const sandbox = {
    console,
    globalThis: {},
    location: { href: "https://www.amazon.com/dp/B0AAAA0001?th=1" },
    URL,
  };
  vm.runInNewContext(source, sandbox, { filename: fileName });
  return sandbox.globalThis[globalName];
}

function exposeCollectorParser(source) {
  return source.replace(
    "globalThis.SSTrafficCollectorCore = Object.freeze({",
    "globalThis.SSTrafficCollectorCore = Object.freeze({\n    parseTip: parseTip,\n    summarize: summarize,",
  );
}

function numberOrNull(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function sameNumber(left, right) {
  const a = numberOrNull(left);
  const b = numberOrNull(right);
  return a === b || (a !== null && b !== null && Math.abs(a - b) < 1e-9);
}

function outcome(gate) {
  return gate.pass ? "pass" : "reject";
}

function legacyShouldRetry(runner, payload) {
  return (payload.status !== "ok" || Number(payload.weeksRead || 0) < 3)
    && !runner.collectorHasKnownTrafficFailure(payload);
}

const collector045 = loadCore(
  "sellersprite_traffic_collector_v0.4.5.user.js",
  "SSTrafficCollectorCore",
  exposeCollectorParser,
);
const collector046 = loadCore(
  "sellersprite_traffic_collector_v0.4.6.user.js",
  "SSTrafficCollectorCore",
);
const runner036 = loadCore(
  "sellersprite_integrated_runner_v0.3.6.user.js",
  "SSIntegratedRunnerCore",
);
const runner037 = loadCore(
  "sellersprite_integrated_runner_v0.3.7.user.js",
  "SSIntegratedRunnerCore",
);

const batch = JSON.parse(fs.readFileSync(inputPath, "utf8"));
const selected = [];
const seen = new Set();
for (const result of batch.results || []) {
  const asin = String(result.targetAsin || result.actualAsin || "").toUpperCase();
  const rawDetails = (result.fullResult?.details || []).filter((detail) => typeof detail.rawText === "string");
  if (!asin || seen.has(asin) || rawDetails.length === 0) continue;
  seen.add(asin);
  selected.push({ asin, rawDetails });
  if (selected.length >= sampleTarget) break;
}

if (selected.length < sampleTarget) {
  throw new Error(`Need ${sampleTarget} distinct real ASINs with raw tooltips; found ${selected.length}`);
}

const rows = [];
let unexpectedFieldDifferenceCount = 0;
let derivedZeroWeekCount = 0;
let strictMissingCorrectionCount = 0;

for (const item of selected) {
  const oldDetails = item.rawDetails.map((detail) => collector045.parseTip(detail.rawText));
  const newDetails = item.rawDetails.map((detail) => collector046.parseTip(detail.rawText));
  const detailDiffs = [];

  for (let index = 0; index < oldDetails.length; index += 1) {
    const oldDetail = oldDetails[index];
    const newDetail = newDetails[index];
    const differences = [];

    if (!sameNumber(oldDetail.totalTraffic, newDetail.totalTraffic)) {
      const conservativeMissing = numberOrNull(oldDetail.totalTraffic) !== null && newDetail.totalTraffic === null;
      differences.push({ field: "totalTraffic", old: oldDetail.totalTraffic, new: newDetail.totalTraffic, allowed: conservativeMissing });
      if (conservativeMissing) strictMissingCorrectionCount += 1;
    }
    if (!sameNumber(oldDetail.naturalTraffic, newDetail.naturalTraffic)) {
      const conservativeMissing = numberOrNull(oldDetail.naturalTraffic) !== null && newDetail.naturalTraffic === null;
      differences.push({ field: "naturalTraffic", old: oldDetail.naturalTraffic, new: newDetail.naturalTraffic, allowed: conservativeMissing });
      if (conservativeMissing) strictMissingCorrectionCount += 1;
    }
    if (!sameNumber(oldDetail.naturalSharePct, newDetail.naturalSharePct)) {
      const guardedZero = oldDetail.naturalSharePct === null
        && newDetail.naturalSharePct === 0
        && newDetail.naturalShareDerived === true;
      differences.push({ field: "naturalSharePct", old: oldDetail.naturalSharePct, new: newDetail.naturalSharePct, allowed: guardedZero });
      if (guardedZero) derivedZeroWeekCount += 1;
    }

    const unexpected = differences.filter((difference) => !difference.allowed);
    unexpectedFieldDifferenceCount += unexpected.length;
    if (differences.length) {
      detailDiffs.push({
        week: newDetail.week || oldDetail.week || "",
        differences,
      });
    }
  }

  const oldSummary = collector045.summarize(oldDetails, "paired_real_tooltip_replay_045");
  const newSummary = collector046.summarize(newDetails, "paired_real_tooltip_replay_046");
  oldSummary.asin = item.asin;
  newSummary.asin = item.asin;
  oldSummary.collectorVersion = "0.4.5";
  newSummary.collectorVersion = "0.4.6";

  const oldTraffic = runner036.parseTrafficCollector(oldSummary, item.asin, item.asin);
  const newTraffic = runner037.parseTrafficCollector(newSummary, item.asin, item.asin);
  const oldGate = runner036.evaluateTrafficGate(oldTraffic, false);
  const newGate = runner037.evaluateTrafficGate(newTraffic, false);
  const oldRetry = legacyShouldRetry(runner036, oldSummary);
  const newRetry = runner037.shouldRetryCollector(newSummary);

  rows.push({
    asin: item.asin,
    rawTooltipWeeks: item.rawDetails.length,
    old: {
      status: oldSummary.status,
      decision: oldSummary.decision,
      weeksRead: oldSummary.weeksRead,
      latestNaturalSharePct: oldTraffic.latestNaturalSharePct,
      recent4AvgNaturalSharePct: oldTraffic.recent4AvgNaturalSharePct,
      recent4MinNaturalSharePct: oldTraffic.recent4MinNaturalSharePct,
      gateOutcome: outcome(oldGate),
      gateRule: oldGate.rule,
      retry: oldRetry,
    },
    new: {
      status: newSummary.status,
      decision: newSummary.decision,
      weeksRead: newSummary.weeksRead,
      latestNaturalSharePct: newTraffic.latestNaturalSharePct,
      recent4AvgNaturalSharePct: newTraffic.recent4AvgNaturalSharePct,
      recent4MinNaturalSharePct: newTraffic.recent4MinNaturalSharePct,
      gateOutcome: outcome(newGate),
      gateRule: newGate.rule,
      retry: newRetry,
    },
    outcomeMatch: outcome(oldGate) === outcome(newGate),
    falsePositive: outcome(oldGate) === "reject" && outcome(newGate) === "pass",
    conservativeDifference: outcome(oldGate) === "pass" && outcome(newGate) === "reject",
    detailDiffs,
  });
}

const outcomeMismatchCount = rows.filter((row) => !row.outcomeMatch).length;
const falsePositiveCount = rows.filter((row) => row.falsePositive).length;
const conservativeOutcomeDifferenceCount = rows.filter((row) => row.conservativeDifference).length;
const oldRetryCount = rows.filter((row) => row.old.retry).length;
const newRetryCount = rows.filter((row) => row.new.retry).length;
const passed = selected.length >= 30
  && outcomeMismatchCount === 0
  && falsePositiveCount === 0
  && unexpectedFieldDifferenceCount === 0
  && newRetryCount <= oldRetryCount;

const summary = {
  schemaVersion: "sellerSpriteTier2PairValidation/v1",
  generatedAt: new Date().toISOString(),
  sourceBatch: path.relative(root, inputPath).replaceAll("\\", "/"),
  sourceSchemaVersion: batch.schemaVersion || "",
  sampleTarget,
  sampleCount: selected.length,
  collectorVersions: { old: "0.4.5", new: "0.4.6" },
  runnerVersions: { old: "0.3.6", new: "0.3.7" },
  exactOutcomeMatchCount: rows.length - outcomeMismatchCount,
  outcomeMismatchCount,
  falsePositiveCount,
  conservativeOutcomeDifferenceCount,
  unexpectedFieldDifferenceCount,
  derivedZeroWeekCount,
  strictMissingCorrectionCount,
  oldRetryCount,
  newRetryCount,
  retryReduction: oldRetryCount - newRetryCount,
  passed,
  rows,
};

fs.mkdirSync(outputDir, { recursive: true });
fs.writeFileSync(path.join(outputDir, "pair_validation_summary.json"), `${JSON.stringify(summary, null, 2)}\n`, "utf8");

const report = [
  "# Tier 2.1 + 2.2 真实 ASIN 配对验证",
  "",
  `- 真实数据源：\`${summary.sourceBatch}\``,
  `- 配对样本：${summary.sampleCount} 个不同 ASIN`,
  `- C 关结果完全一致：${summary.exactOutcomeMatchCount}/${summary.sampleCount}`,
  `- 结果不一致：${summary.outcomeMismatchCount}`,
  `- 假阳性：${summary.falsePositiveCount}`,
  `- 非预期字段差异：${summary.unexpectedFieldDifferenceCount}`,
  `- 明确零值推导周：${summary.derivedZeroWeekCount}`,
  `- 严格缺失纠正：${summary.strictMissingCorrectionCount}`,
  `- 旧重试数：${summary.oldRetryCount}`,
  `- 新重试数：${summary.newRetryCount}`,
  `- 重试减少：${summary.retryReduction}`,
  `- 验证结论：${summary.passed ? "PASS" : "FAIL"}`,
  "",
  "## 判定边界",
  "",
  "- 同一份真实 SellerSprite rawText 同时交给 0.4.5 和 0.4.6，排除页面加载与鼠标悬停波动。",
  "- 只有 totalTraffic > 0 且自然流量字面值为 0 时，0.4.6 才推导 0%。",
  "- `--`、歧义值和 0/0 保持缺失；任何旧拒绝变新通过都会使本验证失败。",
  "- Runner 0.3.7 只对明确未就绪状态重试一次，硬门槛函数与 0.3.6 保持一致。",
  "",
].join("\n");
fs.writeFileSync(path.join(outputDir, "pair_validation_report.md"), report, "utf8");

console.log(JSON.stringify({
  sampleCount: summary.sampleCount,
  exactOutcomeMatchCount: summary.exactOutcomeMatchCount,
  falsePositiveCount: summary.falsePositiveCount,
  unexpectedFieldDifferenceCount: summary.unexpectedFieldDifferenceCount,
  derivedZeroWeekCount: summary.derivedZeroWeekCount,
  oldRetryCount: summary.oldRetryCount,
  newRetryCount: summary.newRetryCount,
  passed: summary.passed,
}, null, 2));

if (!summary.passed) process.exitCode = 1;
