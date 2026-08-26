#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const runDir = path.resolve(process.argv[2] || "");
const forceExitAfterBuild = process.env.SELLERSPRITE_WORKBOOK_FORCE_EXIT_V1 === "1";
if (!runDir) {
  console.error("Usage: node scripts/build_replay_workbooks.mjs <runDir>");
  process.exit(2);
}

const finalDataPath = path.join(runDir, "final_candidates_data.json");
const auditDataPath = path.join(runDir, "rejected_audit_data.json");
const summaryPath = path.join(runDir, "run_summary.json");
const finalDataBytes = await fs.readFile(finalDataPath);
const auditDataBytes = await fs.readFile(auditDataPath);
const summaryBytes = await fs.readFile(summaryPath);
const finalRows = JSON.parse(finalDataBytes.toString("utf8"));
const auditRows = JSON.parse(auditDataBytes.toString("utf8"));
const summary = JSON.parse(summaryBytes.toString("utf8"));
const finalDataSha256 = createHash("sha256").update(finalDataBytes).digest("hex");
const runSummarySha256 = createHash("sha256").update(summaryBytes).digest("hex");
const rulesPath = path.resolve(path.dirname(process.argv[1]), "../config/rules.json");
const rules = JSON.parse(await fs.readFile(rulesPath, "utf8"));
const allowedPriceTrendClasses = new Set(rules.allowedPriceTrendClasses || ["stable", "rising"]);
const unacceptedWorkbookLabelsEnabled = process.env.AMAZON_RUNNER_UNACCEPTED_LABELS_V1 !== "0";
const hasDirectImport = Object.prototype.hasOwnProperty.call(summary, "directImport");
const hasImportMode = Object.prototype.hasOwnProperty.call(summary, "importMode");
if (hasDirectImport && typeof summary.directImport !== "boolean") {
  throw new Error("directImport must be a boolean when present");
}
if (hasImportMode && summary.directImport !== true) {
  throw new Error("Any explicit importMode requires directImport=true");
}
if (summary.directImport === true && !hasImportMode) {
  throw new Error("Direct-import workbook requires an explicit supported importMode");
}
if (hasImportMode && !new Set(["browser-qualified", "strict-pass"]).has(summary.importMode)) {
  throw new Error("Direct-import workbook requires an explicit supported importMode");
}
const directImportUnaccepted = hasImportMode;
if (directImportUnaccepted && !unacceptedWorkbookLabelsEnabled) {
  throw new Error("Direct-import workbook output is disabled because unaccepted labeling is not enabled");
}
const candidateProfile = directImportUnaccepted
  ? {
      version: "runner-unaccepted-workbook-v1.0.0",
      sheetName: "Runner通过_未做A-F验收",
      title: "Amazon美国站 Runner 通过候选（未做最终 A-F 验收）",
      conclusionHeader: "验收状态",
      conclusion: "Runner通过，未做最终A-F验收",
      filePrefix: "runner_candidates_unaccepted",
      status: "runner_pass_unaccepted",
      acceptance: "not_run_by_user_mode",
    }
  : {
      version: "strict-final-workbook-v1",
      sheetName: "最终合格品",
      title: "Amazon美国站最终合格候选品",
      conclusionHeader: "严格结论",
      conclusion: "严格合格",
      filePrefix: "final_candidates",
      status: "strict_final_accepted",
      acceptance: "strict_acceptance_complete",
    };

const enrichmentProblems = finalRows.flatMap((row) => {
  const product = row.product || {};
  const problems = [];
  if (rules.dimensionsRequired && !safeText(product.dimensions)) problems.push(`${row.asin}: dimensions missing`);
  if (rules.priceTrendRequired && !safeText(product.priceTrend)) problems.push(`${row.asin}: price trend missing`);
  if (rules.priceTrendRequired && !safeText(product.priceTrendClass)) problems.push(`${row.asin}: price trend class missing`);
  if (safeText(product.priceTrendClass) && !allowedPriceTrendClasses.has(safeText(product.priceTrendClass).toLowerCase())) {
    problems.push(`${row.asin}: price trend class ${product.priceTrendClass} not allowed`);
  }
  return problems;
});
if (enrichmentProblems.length) {
  throw new Error(`Final workbook blocked by enrichment gate: ${enrichmentProblems.join("; ")}`);
}

function colName(index) {
  let n = index;
  let out = "";
  while (n > 0) {
    const r = (n - 1) % 26;
    out = String.fromCharCode(65 + r) + out;
    n = Math.floor((n - 1) / 26);
  }
  return out;
}

function pct(v) {
  return typeof v === "number" ? v / 100 : null;
}

function money(v) {
  return typeof v === "number" ? v : null;
}

function safeText(v) {
  return String(v ?? "").replace(/\s+/g, " ").trim();
}

async function dataUrlFor(filePath) {
  if (!filePath) return "";
  const projectRoot = path.resolve(runDir, "..", "..");
  const candidates = path.isAbsolute(filePath)
    ? [filePath]
    : [filePath, path.resolve(runDir, filePath), path.resolve(projectRoot, filePath)];
  let resolvedPath = candidates[0];
  for (const candidate of candidates) {
    try {
      await fs.access(candidate);
      resolvedPath = candidate;
      break;
    } catch {}
  }
  const bytes = await fs.readFile(resolvedPath);
  const ext = path.extname(resolvedPath).slice(1).toLowerCase() || "png";
  const mime = ext === "jpg" || ext === "jpeg" ? "image/jpeg" : `image/${ext}`;
  return `data:${mime};base64,${bytes.toString("base64")}`;
}

function applyCommonTableStyle(sheet, range, tableName, style = "TableStyleMedium2") {
  const table = sheet.tables.add(range, true, tableName);
  table.style = style;
  table.showFilterButton = true;
  return table;
}

async function buildFinalWorkbook() {
  const workbook = Workbook.create();
  const sheet = workbook.worksheets.add(candidateProfile.sheetName);
  sheet.showGridLines = false;
  const headers = [
    "序号",
    "ASIN",
    "主图",
    "中文品名",
    "商品标题（英文）",
    "品牌",
    "价格（USD）",
    "月销售额（USD）",
    "评分",
    "评论数",
    "子体月销",
    "父体月销",
    "上架日期",
    "上架天数",
    "变体数",
    "配送",
    "重量/尺寸",
    "价格趋势",
    "最新自然流量%",
    "近4周平均自然流量%",
    "近4周最低自然流量%",
    "总自然流量占比%",
    candidateProfile.conclusionHeader,
    "Amazon链接",
  ];
  const lastCol = colName(headers.length);
  const lastRow = 7 + finalRows.length;

  sheet.getRange(`A1:${lastCol}1`).merge();
  sheet.getRange("A1").values = [[candidateProfile.title]];
  sheet.getRange("A1").format = {
    fill: "#17365D",
    font: { bold: true, color: "#FFFFFF", size: 16 },
    horizontalAlignment: "center",
  };
  sheet.getRange(`A2:${lastCol}2`).merge();
  sheet.getRange("A2").values = [[
    directImportUnaccepted
      ? `runId=${summary.runId}; Runner通过=${summary.qualifiedCount}; attempts=${summary.attempts}. 本表未执行最终 A-F 严格验收，不是最终合格品，不得更新严格合格历史；月销售额仅显示源数据，不按售价×销量估算。`
      : `runId=${summary.runId}; target=${summary.targetN}; qualified=${summary.qualifiedCount}; attempts=${summary.attempts}; rejected=${summary.rejectedCount}. 本表只写入 state=QUALIFIED 的商品；月销售额仅显示源数据，不按售价×销量估算。`,
  ]];
  sheet.getRange("A2").format = {
    fill: "#EAF2F8",
    font: { color: "#1F2937", italic: true },
    wrapText: true,
  };
  sheet.getRange("A4:F5").values = [
    directImportUnaccepted
      ? ["目标候选", "Runner通过", "尝试数", "Runner拒绝", "最终A-F验收", "运行日期"]
      : ["目标数量", "实际合格", "尝试数", "剔除数", "是否凑够目标", "运行日期"],
    [
      summary.targetN,
      summary.qualifiedCount,
      summary.attempts,
      summary.rejectedCount,
      directImportUnaccepted ? "未执行" : (summary.completedTarget ? "是" : "否"),
      new Date(`${summary.runDate}T00:00:00`),
    ],
  ];
  sheet.getRange("A4:F4").format = {
    fill: "#D9EAF7",
    font: { bold: true, color: "#17365D" },
    horizontalAlignment: "center",
  };
  sheet.getRange("A5:F5").format = {
    fill: "#F8FBFD",
    font: { bold: true },
    horizontalAlignment: "center",
  };
  sheet.getRange("F5").format.numberFormat = "yyyy-mm-dd";

  const values = [
    headers,
    ...finalRows.map((row, index) => {
      const product = row.product || {};
      const traffic = row.traffic || {};
      return [
        index + 1,
        row.asin,
        "",
        row.cnTitle || product.title || row.asin,
        product.title || "",
        product.brand || "",
        money(product.price),
        null,
        product.rating ?? null,
        product.reviews ?? null,
        product.monthlySales ?? null,
        product.parentMonthlySales ?? null,
        product.launchDate ? new Date(`${product.launchDate}T00:00:00`) : null,
        product.launchAgeDays ?? null,
        product.variationsCount ?? null,
        product.delivery || "N/A",
        product.dimensions || "",
        product.priceTrend || "",
        pct(traffic.latestNaturalSharePct),
        pct(traffic.recent4AvgNaturalSharePct),
        pct(traffic.recent4MinNaturalSharePct),
        pct(traffic.aggregateNaturalSharePct),
        candidateProfile.conclusion,
        row.amazonUrl || `https://www.amazon.com/dp/${row.asin}?th=1`,
      ];
    }),
  ];
  sheet.getRange(`A7:${lastCol}${lastRow}`).values = values;
  applyCommonTableStyle(
    sheet,
    `A7:${lastCol}${lastRow}`,
    directImportUnaccepted ? "RunnerCandidatesUnaccepted" : "FinalCandidates",
    "TableStyleMedium2",
  );

  for (const [index, row] of finalRows.entries()) {
    const dataUrl = await dataUrlFor(row.imagePath);
    if (!dataUrl) continue;
    sheet.images.add({
      dataUrl,
      anchor: {
        from: { row: 7 + index, col: 2, rowOffsetPx: 6, colOffsetPx: 8 },
        extent: { widthPx: 88, heightPx: 88 },
      },
    });
  }

  sheet.getRange(`A7:${lastCol}7`).format = {
    fill: "#1F4E78",
    font: { bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    wrapText: true,
  };
  sheet.getRange(`G8:H${lastRow}`).format.numberFormat = "$#,##0.00";
  sheet.getRange(`I8:I${lastRow}`).format.numberFormat = "0.0";
  sheet.getRange(`J8:L${lastRow}`).format.numberFormat = "#,##0";
  sheet.getRange(`M8:M${lastRow}`).format.numberFormat = "yyyy-mm-dd";
  sheet.getRange(`N8:O${lastRow}`).format.numberFormat = "#,##0";
  sheet.getRange(`S8:V${lastRow}`).format.numberFormat = "0.00%";
  sheet.getRange(`A7:${lastCol}${lastRow}`).format.borders = { preset: "outside", style: "thin", color: "#9CA3AF" };
  sheet.getRange(`A:${lastCol}`).format.font = { name: "Microsoft YaHei", size: 10 };
  sheet.getRange(`D8:F${lastRow}`).format.wrapText = true;
  sheet.getRange(`P8:R${lastRow}`).format.wrapText = true;
  const widths = {
    A: 7, B: 14, C: 15, D: 28, E: 50, F: 18, G: 11, H: 14, I: 8, J: 10,
    K: 11, L: 11, M: 13, N: 10, O: 9, P: 24, Q: 24, R: 14, S: 15, T: 15,
    U: 15, V: 15, W: 12, X: 36,
  };
  for (const [col, width] of Object.entries(widths)) {
    sheet.getRange(`${col}:${col}`).format.columnWidth = width;
  }
  sheet.getRange("1:1").format.rowHeight = 28;
  sheet.getRange("2:2").format.rowHeight = 40;
  sheet.getRange("7:7").format.rowHeight = 42;
  if (finalRows.length) sheet.getRange(`8:${lastRow}`).format.rowHeight = 98;
  sheet.freezePanes.freezeRows(7);
  sheet.freezePanes.freezeColumns(3);

  const auditSheet = workbook.worksheets.add("审计数据");
  auditSheet.showGridLines = false;
  const auditHeaders = [
    "序号",
    "ASIN",
    "中文品名",
    "商品标题（英文）",
    "品牌",
    "价格（USD）",
    "月销售额（USD）",
    "评分",
    "评论数",
    "子体月销",
    "父体月销",
    "上架日期",
    "上架天数",
    "变体数",
    "配送",
    "重量/尺寸",
    "价格趋势",
    "最新自然流量%",
    "近4周平均自然流量%",
    "近4周最低自然流量%",
    "总自然流量占比%",
    "读取周数",
    "流量窗口",
    "采集状态",
    candidateProfile.conclusionHeader,
    "实际ASIN",
    "流量判定",
    "Amazon链接",
  ];
  const auditLastCol = colName(auditHeaders.length);
  const auditLastRow = 1 + finalRows.length;
  const auditValues = [
    auditHeaders,
    ...finalRows.map((row, index) => {
      const product = row.product || {};
      const traffic = row.traffic || {};
      return [
        index + 1,
        row.asin,
        row.cnTitle || product.title || row.asin,
        product.title || "",
        product.brand || "",
        money(product.price),
        money(product.monthlyRevenue),
        product.rating ?? null,
        product.reviews ?? null,
        product.monthlySales ?? null,
        product.parentMonthlySales ?? null,
        product.launchDate ? new Date(`${product.launchDate}T00:00:00`) : null,
        product.launchAgeDays ?? null,
        product.variationsCount ?? null,
        product.delivery || "N/A",
        product.dimensions || "",
        product.priceTrend || "",
        pct(traffic.latestNaturalSharePct),
        pct(traffic.recent4AvgNaturalSharePct),
        pct(traffic.recent4MinNaturalSharePct),
        pct(traffic.aggregateNaturalSharePct),
        traffic.weeksRead ?? null,
        traffic.trafficWindow || "",
        traffic.status === "ok" ? "正常" : safeText(traffic.status),
        candidateProfile.conclusion,
        traffic.actualAsin || row.asin,
        traffic.decision === "pass" ? "流量通过" : safeText(traffic.decision),
        row.amazonUrl || `https://www.amazon.com/dp/${row.asin}?th=1`,
      ];
    }),
  ];
  auditSheet.getRange(`A1:${auditLastCol}${auditLastRow}`).values = auditValues;
  applyCommonTableStyle(
    auditSheet,
    `A1:${auditLastCol}${auditLastRow}`,
    directImportUnaccepted ? "RunnerCandidateAudit" : "QualifiedAudit",
    "TableStyleMedium9",
  );
  auditSheet.getRange(`A1:${auditLastCol}1`).format = {
    fill: "#374151",
    font: { bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    wrapText: true,
  };
  auditSheet.getRange(`F2:G${auditLastRow}`).format.numberFormat = "$#,##0.00";
  auditSheet.getRange(`H2:H${auditLastRow}`).format.numberFormat = "0.0";
  auditSheet.getRange(`I2:K${auditLastRow}`).format.numberFormat = "#,##0";
  auditSheet.getRange(`L2:L${auditLastRow}`).format.numberFormat = "yyyy-mm-dd";
  auditSheet.getRange(`M2:N${auditLastRow}`).format.numberFormat = "#,##0";
  auditSheet.getRange(`R2:U${auditLastRow}`).format.numberFormat = "0.00%";
  auditSheet.getRange(`A:${auditLastCol}`).format.font = { name: "Microsoft YaHei", size: 10 };
  auditSheet.getRange(`C2:E${auditLastRow}`).format.wrapText = true;
  auditSheet.getRange(`P2:Q${auditLastRow}`).format.wrapText = true;
  auditSheet.getRange(`V2:${auditLastCol}${auditLastRow}`).format.wrapText = true;
  const auditWidths = {
    A: 7, B: 14, C: 28, D: 50, E: 18, F: 11, G: 14, H: 8, I: 10, J: 11,
    K: 11, L: 13, M: 10, N: 9, O: 14, P: 24, Q: 24, R: 15, S: 15, T: 15, U: 15,
    V: 10, W: 25, X: 12, Y: 14, Z: 13, AA: 13, AB: 36,
  };
  for (const [col, width] of Object.entries(auditWidths)) {
    auditSheet.getRange(`${col}:${col}`).format.columnWidth = width;
  }
  auditSheet.getRange("1:1").format.rowHeight = 42;
  if (finalRows.length) auditSheet.getRange(`2:${auditLastRow}`).format.rowHeight = 54;
  auditSheet.freezePanes.freezeRows(1);
  auditSheet.freezePanes.freezeColumns(2);

  const costSheet = workbook.worksheets.add("成本利润测算");
  costSheet.showGridLines = false;
  const costHeaders = [
    "序号",
    "ASIN",
    "中文品名",
    "当前售价（USD）",
    "美元兑人民币汇率（1 USD = X RMB）",
    "采购价（RMB）",
    "MOQ",
    "国内运费（RMB）",
    "供应商链接",
    "总成本（RMB）",
    "利润（RMB）",
    "毛利率",
    "ROI",
  ];
  const costLastCol = colName(costHeaders.length);
  const costLastRow = 5;
  costSheet.getRange(`A1:${costLastCol}1`).merge();
  costSheet.getRange("A1").values = [["成本利润测算（后续程序使用）"]];
  costSheet.getRange("A1").format = {
    fill: "#215E4B",
    font: { bold: true, color: "#FFFFFF", size: 15 },
    horizontalAlignment: "center",
  };
  costSheet.getRange(`A2:${costLastCol}2`).merge();
  costSheet.getRange("A2").values = [["本脚本不向本层写入任何商品或成本数据，也不计算总成本、利润、毛利率或 ROI。"]];
  costSheet.getRange("A2").format = {
    fill: "#E7F3EE",
    font: { color: "#24433A", italic: true },
    wrapText: true,
  };
  const costValues = [
    costHeaders,
    Array(costHeaders.length).fill(null),
  ];
  costSheet.getRange(`A4:${costLastCol}${costLastRow}`).values = costValues;
  applyCommonTableStyle(costSheet, `A4:${costLastCol}${costLastRow}`, "CostProfitTemplate", "TableStyleMedium4");
  costSheet.getRange(`A4:${costLastCol}4`).format = {
    fill: "#2F6F5E",
    font: { bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    wrapText: true,
  };
  costSheet.getRange(`E5:I${costLastRow}`).format.fill = "#FFF4CC";
  costSheet.getRange(`J5:M${costLastRow}`).format.fill = "#E8F0F7";
  costSheet.getRange(`D5:D${costLastRow}`).format.numberFormat = "$#,##0.00";
  costSheet.getRange(`E5:E${costLastRow}`).format.numberFormat = "0.0000";
  costSheet.getRange(`F5:F${costLastRow}`).format.numberFormat = '"¥"#,##0.00';
  costSheet.getRange(`G5:G${costLastRow}`).format.numberFormat = "#,##0";
  costSheet.getRange(`H5:H${costLastRow}`).format.numberFormat = '"¥"#,##0.00';
  costSheet.getRange(`J5:K${costLastRow}`).format.numberFormat = '"¥"#,##0.00';
  costSheet.getRange(`L5:M${costLastRow}`).format.numberFormat = "0.00%";
  costSheet.getRange(`A:${costLastCol}`).format.font = { name: "Microsoft YaHei", size: 10 };
  costSheet.getRange(`C5:C${costLastRow}`).format.wrapText = true;
  costSheet.getRange(`I5:I${costLastRow}`).format.wrapText = true;
  const costWidths = { A: 7, B: 14, C: 34, D: 14, E: 20, F: 14, G: 10, H: 16, I: 36, J: 15, K: 14, L: 12, M: 12 };
  for (const [col, width] of Object.entries(costWidths)) {
    costSheet.getRange(`${col}:${col}`).format.columnWidth = width;
  }
  costSheet.getRange("1:1").format.rowHeight = 28;
  costSheet.getRange("2:2").format.rowHeight = 36;
  costSheet.getRange("4:4").format.rowHeight = 42;
  costSheet.getRange(`5:${costLastRow}`).format.rowHeight = 42;
  costSheet.freezePanes.freezeRows(4);
  costSheet.freezePanes.freezeColumns(2);

  const inspect = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 50 },
    summary: "final formula error scan",
  });
  const previewPath = path.join(runDir, `${candidateProfile.filePrefix}_preview.png`);
  const focusPreviewPath = path.join(runDir, `${candidateProfile.filePrefix}_preview_focus.png`);
  const preview = await workbook.render({ sheetName: candidateProfile.sheetName, range: `A1:${lastCol}${lastRow}`, scale: 1, format: "png" });
  await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
  const focusPreview = await workbook.render({ sheetName: candidateProfile.sheetName, range: `A7:H${Math.min(lastRow, 12)}`, scale: 1, format: "png" });
  await fs.writeFile(focusPreviewPath, new Uint8Array(await focusPreview.arrayBuffer()));
  const qualifiedAuditPreview = await workbook.render({ sheetName: "审计数据", range: `A1:${auditLastCol}${Math.min(auditLastRow, 12)}`, scale: 1, format: "png" });
  await fs.writeFile(path.join(runDir, "qualified_audit_preview.png"), new Uint8Array(await qualifiedAuditPreview.arrayBuffer()));
  const costProfitPreview = await workbook.render({ sheetName: "成本利润测算", range: `A1:${costLastCol}${costLastRow}`, scale: 1, format: "png" });
  await fs.writeFile(path.join(runDir, "cost_profit_preview.png"), new Uint8Array(await costProfitPreview.arrayBuffer()));
  const output = await SpreadsheetFile.exportXlsx(workbook);
  const outputPath = path.join(runDir, `${candidateProfile.filePrefix}_${summary.runId}.xlsx`);
  await output.save(outputPath);
  const outputSha256 = createHash("sha256").update(await fs.readFile(outputPath)).digest("hex");
  return {
    outputPath,
    outputSha256,
    previewPath,
    focusPreviewPath,
    formulaScan: inspect.ndjson,
    qualifiedAuditPreview: path.join(runDir, "qualified_audit_preview.png"),
    costProfitPreview: path.join(runDir, "cost_profit_preview.png"),
  };
}

async function buildAuditWorkbook() {
  const workbook = Workbook.create();
  const sheet = workbook.worksheets.add("剔除审计");
  sheet.showGridLines = false;
  const headers = [
    "ASIN",
    "原英文标题",
    "剔除阶段",
    "规则代号",
    "剔除详情",
    "采集状态",
    "实际ASIN",
    "最新自然%",
    "近4周均值%",
    "近4周最低%",
    "总自然流量占比%",
    "读取周数",
    "流量窗口",
    "价格",
    "评分",
    "评论数",
    "子体月销",
    "父体月销",
    "上架日期",
    "上架天数",
    "变体数",
    "Amazon链接",
  ];
  const lastCol = colName(headers.length);
  const lastRow = Math.max(2, 1 + auditRows.length);
  const values = [
    headers,
    ...auditRows.map((row) => {
      const product = row.product || {};
      const traffic = row.traffic || {};
      return [
        row.asin || product.asin || "",
        product.title || "",
        row.stage || "",
        row.rejectRule || "",
        row.rejectDetail || "",
        traffic.status || "",
        traffic.actualAsin || "",
        traffic.latestNaturalSharePct ?? null,
        traffic.recent4AvgNaturalSharePct ?? null,
        traffic.recent4MinNaturalSharePct ?? null,
        traffic.aggregateNaturalSharePct ?? null,
        traffic.weeksRead ?? null,
        traffic.trafficWindow || "",
        product.price ?? null,
        product.rating ?? null,
        product.reviews ?? null,
        product.monthlySales ?? null,
        product.parentMonthlySales ?? null,
        product.launchDate ? new Date(`${product.launchDate}T00:00:00`) : null,
        product.launchAgeDays ?? null,
        product.variationsCount ?? null,
        product.asin ? `https://www.amazon.com/dp/${product.asin}?th=1` : "",
      ];
    }),
  ];
  sheet.getRange(`A1:${lastCol}${lastRow}`).values = values;
  applyCommonTableStyle(sheet, `A1:${lastCol}${lastRow}`, "RejectedAudit", "TableStyleMedium4");
  sheet.getRange(`A1:${lastCol}1`).format = {
    fill: "#374151",
    font: { bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    wrapText: true,
  };
  sheet.getRange(`H2:K${lastRow}`).format.numberFormat = "0.00";
  sheet.getRange(`N2:N${lastRow}`).format.numberFormat = "$#,##0.00";
  sheet.getRange(`O2:O${lastRow}`).format.numberFormat = "0.0";
  sheet.getRange(`P2:R${lastRow}`).format.numberFormat = "#,##0";
  sheet.getRange(`S2:S${lastRow}`).format.numberFormat = "yyyy-mm-dd";
  sheet.getRange(`T2:U${lastRow}`).format.numberFormat = "#,##0";
  sheet.getRange(`A:${lastCol}`).format.font = { name: "Microsoft YaHei", size: 10 };
  const widths = {
    A: 14, B: 62, C: 16, D: 28, E: 42, F: 12, G: 14, H: 12, I: 13, J: 13, K: 15, L: 10, M: 25,
    N: 10, O: 8, P: 10, Q: 11, R: 11, S: 13, T: 10, U: 9, V: 36,
  };
  for (const [col, width] of Object.entries(widths)) {
    sheet.getRange(`${col}:${col}`).format.columnWidth = width;
  }
  sheet.getRange(`B2:E${lastRow}`).format.wrapText = true;
  sheet.getRange(`M2:V${lastRow}`).format.wrapText = true;
  sheet.freezePanes.freezeRows(1);
  const preview = await workbook.render({ sheetName: "剔除审计", range: `A1:${lastCol}${Math.min(lastRow, 26)}`, scale: 1, format: "png" });
  await fs.writeFile(path.join(runDir, "rejected_audit_preview.png"), new Uint8Array(await preview.arrayBuffer()));
  const output = await SpreadsheetFile.exportXlsx(workbook);
  const outputPath = path.join(runDir, `rejected_audit_${summary.runId}.xlsx`);
  await output.save(outputPath);
  return { outputPath };
}

const finalResult = await buildFinalWorkbook();
const auditResult = await buildAuditWorkbook();
const buildReport = {
  workbookExitPolicy: forceExitAfterBuild ? "force_exit_after_awaited_build_v1" : "natural_event_loop",
  candidateProfileVersion: candidateProfile.version,
  candidateStatus: candidateProfile.status,
  acceptance: candidateProfile.acceptance,
  finalDataSha256,
  runSummarySha256,
  finalXlsx: finalResult.outputPath,
  finalXlsxSha256: finalResult.outputSha256,
  auditXlsx: auditResult.outputPath,
  finalPreview: finalResult.previewPath,
  finalFocusPreview: finalResult.focusPreviewPath,
  qualifiedAuditPreview: finalResult.qualifiedAuditPreview,
  costProfitPreview: finalResult.costProfitPreview,
  auditPreview: path.join(runDir, "rejected_audit_preview.png"),
  formulaScan: finalResult.formulaScan,
};
await fs.writeFile(path.join(runDir, "workbook_build_report.json"), JSON.stringify(buildReport, null, 2), "utf8");
console.log(JSON.stringify(buildReport, null, 2));
if (forceExitAfterBuild) process.exit(0);
