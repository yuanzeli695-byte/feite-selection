import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import test from "node:test";

const require = createRequire(import.meta.url);
const ui = require("./static/category-repository-ui.js");

test("category import preview enforces the four-state defaults", () => {
  const preview = ui.normalizePreview({
    items: [
      { key: "line:1", status: "ready", input: "Fresh | 100" },
      { key: "line:2", status: "screened", input: "Seen | 200", matches: [{ completionCount: 2 }] },
      { key: "line:3", status: "ambiguous", input: "Shared" },
      { key: "line:4", status: "duplicate", input: "Fresh | 100", duplicateOf: "line:1:opaque-hash" },
      { key: "line:5", status: "in_pool", input: "Queued | 300" },
      { key: "line:6", status: "invalid", input: "Bad | no", error: "nodeIdPath 无效" },
      { status: "ready", input: "Missing backend key | 700" },
    ],
  });

  assert.deepEqual(preview.selectedKeys, ["line:1"]);
  assert.deepEqual(preview.items.map((item) => item.tone), ["green", "red", "yellow", "yellow", "yellow", "gray", "green"]);
  assert.deepEqual(preview.items.map((item) => item.selectable), [true, true, false, false, false, false, false]);
  assert.match(preview.items[1].statusDetail, /2 次完成筛选/);
  assert.equal(preview.items[3].statusDetail, "与第 1 行重复");
  assert.doesNotMatch(preview.items[3].statusDetail, /line:/);
  assert.match(preview.items[5].statusDetail, /nodeIdPath 无效/);
});

test("import selection only forwards selectable keys and marks explicit screened overrides", () => {
  const preview = ui.normalizePreview({
    items: [
      { key: "line:1", status: "ready" },
      { key: "line:2", status: "screened" },
      { key: "line:3", status: "in_pool" },
      { key: "line:4", status: "invalid" },
    ],
  });
  const selection = ui.buildImportSelection(preview.items, new Set(["line:1", "line:2", "line:3", "line:4", "unknown"]));

  assert.deepEqual(selection, {
    selectedKeys: ["line:1", "line:2"],
    overrideScreenedKeys: ["line:2"],
  });
});

test("repository categories are flattened into one row per completed batch", () => {
  const rows = ui.flattenRepository({
    marketplace: "Amazon US",
    scope: "console_completed_runner_unaccepted",
    items: [
      {
        key: "Amazon US|100",
        nodeIdPath: "100",
        displayName: "Kitchen",
        completionCount: 2,
        completions: [
          { batchId: "batch-old", batchName: "Older", completedAt: "2026-08-20T12:00:00Z", archived: true },
          { batchId: "batch-new", batchName: "Newer", completedAt: "2026-08-22T12:00:00Z", archived: false },
        ],
      },
    ],
  });

  assert.equal(rows.length, 2);
  assert.deepEqual(rows.map((row) => row.batchId), ["batch-new", "batch-old"]);
  assert.equal(rows[1].archived, true);
  assert.equal(rows[0].scopeLabel, "Runner 已筛选，未做 A-F 最终验收");
});

test("import result summary reports selected rows that did not import", () => {
  assert.deepEqual(ui.importResultSummary({ addedCount: 1, selectedCount: 3 }), {
    added: 1,
    selected: 3,
    skipped: 2,
    text: "已导入 1 个类目，另有 2 行未导入",
    tone: "warn",
  });
  assert.deepEqual(ui.importResultSummary({ addedCount: 1, selectedCount: 1, skippedCount: 4 }), {
    added: 1,
    selected: 1,
    skipped: 4,
    text: "已导入 1 个类目，另有 4 行未导入",
    tone: "warn",
  });
  assert.equal(ui.importResultSummary({
    addedCount: 1,
    outcomes: [{ outcome: "imported" }, { outcome: "skipped" }],
  }).skipped, 1);
  assert.equal(ui.importResultSummary({ addedCount: 2, selectedCount: 2 }).tone, "good");
});

test("an older import response only clears the exact value that was submitted", () => {
  assert.equal(ui.shouldClearSubmittedInput("A | 100", "A | 100"), true);
  assert.equal(ui.shouldClearSubmittedInput("B | 200", "A | 100"), false);
  assert.equal(ui.shouldClearSubmittedInput("A | 100\n", "A | 100"), false);
});

test("unknown repository scope fails closed instead of claiming the Runner scope", () => {
  const [row] = ui.flattenRepository({
    scope: "future_or_missing_scope",
    items: [{ nodeIdPath: "900", completions: [{ batchId: "batch-unknown" }] }],
  });

  assert.equal(row.scope, "future_or_missing_scope");
  assert.equal(row.scopeLabel, "口径未知");
});

test("batch archive selection trusts backend eligibility and prunes active or stale ids", () => {
  const batches = [
    { id: "completed", archiveEligible: true },
    { id: "stopped", archiveEligible: true },
    { id: "running", archiveEligible: false, archiveBlockedReason: "Runner 正在执行" },
    { id: "legacy" },
  ];

  assert.deepEqual(ui.archiveableBatchIds(batches), ["completed", "stopped"]);
  assert.deepEqual([...ui.pruneBatchArchiveSelection(batches, new Set(["completed", "running", "missing"]))], ["completed"]);
  assert.equal(ui.batchArchiveEligibility(batches[2]).eligible, false);
  assert.equal(ui.batchArchiveEligibility(batches[2]).reason, "Runner 正在执行");
  assert.equal(ui.batchArchiveEligibility(batches[3]).eligible, false);
});

test("unfinished batches can request graceful deletion and stay fenced while pending", () => {
  const requestable = {
    id: "running",
    overallStatus: "running",
    archiveEligible: false,
    archiveRequestEligible: true,
    archiveRequestBlockedReason: "",
  };
  const pending = {
    ...requestable,
    id: "pending",
    archiveRequest: { status: "waiting", phase: "waiting", lastError: "Bridge 等待 Runner 完成停止" },
  };
  const failed = {
    ...requestable,
    id: "failed",
    archiveRequest: { status: "failed", phase: "needs_attention", lastError: "删除收尾超时" },
  };

  assert.deepEqual(ui.batchArchiveEligibility(requestable), {
    eligible: true,
    reason: "将先停止任务，等待 Runner、Bridge 和本地租约收尾后移入仓库",
    mode: "request",
    requestStatus: "",
  });
  assert.equal(ui.batchArchiveEligibility(pending).eligible, false);
  assert.equal(ui.batchArchiveEligibility(pending).mode, "pending");
  assert.match(ui.batchArchiveEligibility(pending).reason, /Bridge/);
  assert.equal(ui.batchArchiveEligibility(failed).eligible, true);
  assert.equal(ui.batchArchiveEligibility(failed).mode, "request");
  assert.deepEqual(ui.archiveableBatchIds([requestable, pending, failed]), ["running", "failed"]);
  assert.deepEqual([...ui.pruneBatchArchiveSelection([requestable, pending], new Set(["running"]))], ["running"]);
});

test("frontend DOM and API contracts expose preview, recoverable delete, repository, and restore flows", () => {
  const html = readFileSync(new URL("./static/index.html", import.meta.url), "utf8");
  const app = readFileSync(new URL("./static/app.js", import.meta.url), "utf8");
  const styles = readFileSync(new URL("./static/styles.css", import.meta.url), "utf8");

  for (const id of [
    "categoryRepositoryButton", "categoryImportPreview", "categoryPreviewList",
    "batchSelectionBar", "batchSelectAll", "batchSelectedCount", "batchBulkDelete",
    "batchArchiveDialog", "categoryRepositoryDialog", "categoryRepositoryTable", "archivedBatchList",
  ]) assert.match(html, new RegExp(`id="${id}"`), `missing #${id}`);
  assert.ok(html.indexOf("category-repository-ui.js") < html.indexOf("app.js"));
  assert.match(app, /\/api\/category-pool\/preview/);
  assert.match(app, /\/api\/category-repository\?q=/);
  assert.match(app, /const endpoint = requestMode \? "\/api\/batches\/archive-request" : "\/api\/batches\/archive"/);
  assert.match(app, /\/api\/batches\/archive-request/);
  assert.match(app, /Idempotency-Key/);
  assert.match(app, /停止并删除/);
  assert.match(app, /archiveRequest\?\.status/);
  assert.match(app, /JSON\.stringify\(\{ batchIds \}\)/);
  assert.match(app, /categoryRepositoryUI\.batchArchiveEligibility\(batch\)/);
  assert.match(app, /原状态 \$\{escapeHtml\(statusLabels\[batch\.overallStatus\]/);
  assert.doesNotMatch(app, /batch\.overallStatus === "completed" \? `<button class="button quiet small run-archive"/);
  assert.match(app, /\/api\/batches\/\$\{batchId\}\/restore/);
  assert.match(app, /\/api\/batches\?archived=1/);
  assert.match(app, /body: JSON\.stringify\(\{ categories: source, \.\.\.selection \}\)/);
  assert.match(app, /const repositoryCount = state\.repository\.rows\.length/);
  assert.match(app, /const query = event\.currentTarget\.value;[\s\S]*setTimeout\(\(\) => loadCategoryRepository\(query\), 350\)/);
  assert.match(app, /\["ArrowLeft", "ArrowRight", "Home", "End"\]/);
  assert.match(app, /archived\.controller\?\.abort\(\);[\s\S]*requestId !== archived\.requestId/);
  assert.match(app, /shouldClearSubmittedInput\(input\.value, submittedValue\)/);
  assert.match(app, /if \(!inputUnchanged\) scheduleCategoryPreview\(true\)/);
  assert.match(html, /删除批次（可恢复）/);
  assert.match(html, /archiveRequestStatus/);
  assert.match(html, /Runner、Bridge 和本地任务租约/);
  assert.match(html, /已完成选品类目库/);
  assert.match(html, /已删除批次/);
  assert.doesNotMatch(`${html}\n${app}`, /归档/);
  assert.match(styles, /\.run-row\s*\{/);
  assert.match(styles, /\.batch-selection-bar\s*\{/);
  assert.match(styles, /\.repository-table-wrapper/);
  assert.match(styles, /@media \(max-width: 540px\)/);
});
