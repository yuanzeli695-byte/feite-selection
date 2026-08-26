#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { spawnSync } from "node:child_process";

const DEFAULT_ARTIFACT_TOOL = "C:/Users/13045/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/@oai/artifact-tool/dist/artifact_tool.mjs";
const ASIN_RE = /^[A-Z0-9]{10}$/;
const MAX_SOURCE_AGE_MS = 24 * 60 * 60 * 1000;

const SOURCE_GATE_RULES = [
  ["electric_electronic", /(?:electronics?|printer|ink|cartridge|laser|battery|rechargeable|usb|bluetooth|wifi|smart|digital|automatic|touchless|powered|pump|led|neon|solar|charger|power cord|power strip)/i],
  ["magnetic", /(?:^|[^a-z0-9])(magnet|magnetic)(?:$|[^a-z0-9])/i],
  ["chemical_consumable", /(?:liquid glue|school glue|paint|wood filler|cleaning|bleach|aerosol|pesticide|insecticide|repellent|sealer|sealant|glue|filter|ink refill|deodorizer)/i],
  ["food_ingestible", /(?:edible|supplements?|vitamins?|gummies|capsules?|drink mix)/i],
  ["apparel_wearable_jewelry", /(?:clothing|apparel|shirt|pants|dress|shoes?|necklace|earrings?|bracelet|jewelry|headband|hair clips?|wearable|lanyards?|backpack|aprons?)/i],
  ["safety_sensitive", /(?:personal protective equipment|safety glasses|paper cutter|guillotine|saw blades?|door locks?|deadbolt|lock box|medical|therapeutic|healing|treatment|diabetes|helmet|car seat|life jacket|weapon|firearm|rifle|gun|ammunition|taser|knife)/i],
  ["ip_character_or_published_content", /(?:merch|official licensed|cartoon character|marvel|disney|star wars|mickey|minnie|frozen|snoopy|super mario|pokemon|hello kitty|barbie|spider-?man|batman|superman|harry potter|nintendo|anime|k-?pop|photocards?|music album|quran|bible|devotional|one minute with god|book)/i],
];

function parseArgs(argv) {
  const out = {};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) throw new Error(`unexpected argument: ${token}`);
    const key = token.slice(2);
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) throw new Error(`missing value for --${key}`);
    out[key] = value;
    index += 1;
  }
  for (const key of ["input", "run-dir", "queue-name", "query-url", "source-page"]) {
    if (!out[key]) throw new Error(`--${key} is required`);
  }
  out["queue-size"] = Number(out["queue-size"] || 160);
  if (!Number.isInteger(out["queue-size"]) || out["queue-size"] < 1) {
    throw new Error("--queue-size must be a positive integer");
  }
  out["part-size"] = Number(out["part-size"] || 64);
  if (!Number.isInteger(out["part-size"]) || out["part-size"] < 1) {
    throw new Error("--part-size must be a positive integer");
  }
  return out;
}

function normalizeQueryUrl(rawUrl) {
  const url = new URL(rawUrl);
  if (url.protocol !== "https:" || !/(^|\.)sellersprite\.com$/i.test(url.hostname)) {
    throw new Error("query URL must be an HTTPS SellerSprite URL");
  }
  if (url.searchParams.get("market")?.toUpperCase() !== "US") {
    throw new Error("query URL market must be US");
  }
  const maxReviews = Number(url.searchParams.get("maxReviews"));
  if (!Number.isFinite(maxReviews) || maxReviews < 0 || maxReviews > 100) {
    throw new Error("query URL maxReviews must be between 0 and 100");
  }
  const nodeRaw = url.searchParams.get("nodeIdPaths");
  let nodeIds;
  try {
    nodeIds = JSON.parse(nodeRaw || "null");
  } catch {
    throw new Error("query URL nodeIdPaths must be a JSON array");
  }
  if (!Array.isArray(nodeIds) || !nodeIds.length || nodeIds.some((value) => !String(value).trim())) {
    throw new Error("query URL nodeIdPaths must be a nonempty JSON array");
  }
  return { url: url.toString(), nodeIds: nodeIds.map(String), maxReviews };
}

function text(value) {
  return value == null ? "" : String(value).trim();
}

function number(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  const match = text(value).replace(/,/g, "").match(/-?\d+(?:\.\d+)?/);
  return match ? Number(match[0]) : null;
}

function normalizeDate(value) {
  if (value instanceof Date && !Number.isNaN(value.valueOf())) return value.toISOString().slice(0, 10);
  const raw = text(value);
  const match = raw.match(/\d{4}-\d{2}-\d{2}/);
  return match ? match[0] : raw;
}

function sha256(data) {
  return crypto.createHash("sha256").update(data).digest("hex");
}

function sourceGateHit(row) {
  const blob = [row.title, row.brand, row.categoryPath].filter(Boolean).join(" ");
  return SOURCE_GATE_RULES.find(([, pattern]) => pattern.test(blob))?.[0] || null;
}

function mapRows(values, queryUrl, sourcePage) {
  if (!Array.isArray(values) || values.length < 2) throw new Error("source workbook has no data rows");
  const headers = values[0].map(text);
  const required = [
    "ASIN", "品牌", "商品标题", "商品详情页链接", "商品主图", "类目路径", "月销量",
    "子体销量", "变体数", "价格($)", "评分数", "评分", "上架时间", "配送方式",
  ];
  const missing = required.filter((name) => !headers.includes(name));
  if (missing.length) throw new Error(`source workbook missing columns: ${missing.join(", ")}`);
  const index = Object.fromEntries(headers.map((name, position) => [name, position]));
  const normalized = [];
  const rejected = [];
  for (let rowIndex = 1; rowIndex < values.length; rowIndex += 1) {
    const source = values[rowIndex];
    const asin = text(source[index.ASIN]).toUpperCase();
    const row = {
      asin,
      brand: text(source[index["品牌"]]),
      seller: text(source[index["BuyBox卖家"]]),
      title: text(source[index["商品标题"]]),
      amazonUrl: text(source[index["商品详情页链接"]]) || `https://www.amazon.com/dp/${asin}`,
      image: text(source[index["商品主图"]]),
      categoryPath: text(source[index["类目路径"]]),
      monthlySales: number(source[index["月销量"]]),
      parentSales: number(source[index["月销量"]]),
      childSales: number(source[index["子体销量"]]),
      variations: number(source[index["变体数"]]),
      variationsCount: number(source[index["变体数"]]),
      price: number(source[index["价格($)"]]),
      reviews: number(source[index["评分数"]]),
      rating: number(source[index["评分"]]),
      launchDate: normalizeDate(source[index["上架时间"]]),
      launchAgeDays: number(source[index["上架天数"]]),
      delivery: text(source[index["配送方式"]]),
      sourceRawWeight: text(source[index["商品重量"]]),
      sourceRawDimensions: text(source[index["商品尺寸"]]),
      sourceRawPackageWeight: text(source[index["包装重量"]]),
      sourceRawPackageDimensions: text(source[index["包装尺寸"]]),
      sourcePage,
      sourceRow: rowIndex,
      sellerSpriteUrl: queryUrl,
      sourceExportType: "SellerSprite Product Research XLSX",
    };
    const invalid = [];
    if (!ASIN_RE.test(asin)) invalid.push("asin");
    for (const field of ["title", "amazonUrl", "image", "categoryPath", "launchDate"]) {
      if (!row[field]) invalid.push(field);
    }
    for (const field of ["monthlySales", "variations", "price", "reviews", "rating"]) {
      if (!Number.isFinite(row[field])) invalid.push(field);
    }
    if (invalid.length) {
      rejected.push({ asin, sourceRow: rowIndex, stage: "xlsx_normalization", reason: `invalid fields: ${invalid.join(", ")}` });
      continue;
    }
    const gateRule = sourceGateHit(row);
    if (gateRule) {
      rejected.push({ asin, sourceRow: rowIndex, stage: "source_gate_a", reason: gateRule, title: row.title, categoryPath: row.categoryPath });
      continue;
    }
    normalized.push(row);
  }
  return { headers, normalized, rejected };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const inputPath = path.resolve(args.input);
  const runDir = path.resolve(args["run-dir"]);
  const queueName = args["queue-name"];
  const importDir = path.join(runDir, `excel_import_${queueName}`);
  const sourceDir = path.join(importDir, "normalized_source");
  const outputDir = path.join(importDir, "candidate_pool");
  const query = normalizeQueryUrl(args["query-url"]);
  const stat = await fs.stat(inputPath);
  const ageMs = Date.now() - stat.mtimeMs;
  if (ageMs < -5 * 60 * 1000 || ageMs > MAX_SOURCE_AGE_MS) {
    throw new Error(`source workbook must be no more than 24 hours old; ageMs=${Math.round(ageMs)}`);
  }

  const artifactModule = process.env.CODEX_ARTIFACT_TOOL_MODULE || DEFAULT_ARTIFACT_TOOL;
  const { FileBlob, SpreadsheetFile } = await import(pathToFileURL(artifactModule).href);
  const input = await FileBlob.load(inputPath);
  const workbook = await SpreadsheetFile.importXlsx(input);
  const sheet = workbook.worksheets.getItemAt(0);
  const values = sheet.getUsedRange().values;
  const mapped = mapRows(values, query.url, args["source-page"]);
  if (!mapped.normalized.length) throw new Error("no rows survived XLSX normalization and the downward-only source gate");

  await fs.mkdir(sourceDir, { recursive: true });
  await fs.mkdir(outputDir, { recursive: true });
  const queryName = "query_excel_export.json";
  const queryPath = path.join(sourceDir, queryName);
  const queryJson = `${JSON.stringify(mapped.normalized, null, 2)}\n`;
  await fs.writeFile(queryPath, queryJson, "utf8");
  const capturedAt = stat.mtime.toISOString();
  const manifest = {
    schemaVersion: "sellerSpriteCandidateSourceManifest/v1",
    capturedAt,
    market: "US",
    preset: { name: "amazon-us-strict-v1-excel-export" },
    categoryScope: {
      name: `SellerSprite XLSX export: ${args["source-page"]}`,
      nodeIdPaths: query.nodeIds,
    },
    inputs: [{ path: queryName, sha256: sha256(Buffer.from(queryJson, "utf8")), queryUrl: query.url }],
  };
  const manifestPath = path.join(importDir, "source_manifest.json");
  await fs.writeFile(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");

  const ruleCounts = {};
  for (const row of mapped.rejected) {
    ruleCounts[row.reason] = (ruleCounts[row.reason] || 0) + 1;
  }
  const importSummary = {
    schemaVersion: "sellerSpriteXlsxImport/v1",
    inputPath,
    inputSha256: sha256(await fs.readFile(inputPath)),
    capturedAt,
    sheetName: sheet.name,
    sourceRows: values.length - 1,
    normalizedRows: mapped.normalized.length,
    rejectedRows: mapped.rejected.length,
    rejectionCounts: ruleCounts,
    embeddedImageCount: sheet.images?.items?.length ?? sheet.images?.length ?? null,
    imageUrlRows: mapped.normalized.filter((row) => row.image).length,
    queryUrl: query.url,
    sourcePage: args["source-page"],
    finalAuthority: false,
  };
  await fs.writeFile(path.join(importDir, "xlsx_import_summary.json"), `${JSON.stringify(importSummary, null, 2)}\n`, "utf8");
  await fs.writeFile(path.join(importDir, "xlsx_import_rejected.json"), `${JSON.stringify(mapped.rejected, null, 2)}\n`, "utf8");

  const projectRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/(?:[A-Za-z]:)/, (match) => match.slice(1))), "..");
  const python = args.python || "python";
  const prepareArgs = [
    path.join(projectRoot, "scripts", "prepare_strict_candidate_pool.py"),
    "--input-dir", sourceDir,
    "--source-manifest", manifestPath,
    "--project-root", projectRoot,
    "--output-dir", outputDir,
    "--queue-name", queueName,
    "--queue-size", String(args["queue-size"]),
    "--run-date", args["run-date"] || new Date().toISOString().slice(0, 10),
    "--max-per-source", String(args["queue-size"]),
    "--max-per-brand", args["max-per-brand"] || "2",
    "--allow-missing-parent-child-sales",
  ];
  if (args.attempted) prepareArgs.push("--attempted", path.resolve(args.attempted));
  const queueSizeArgIndex = prepareArgs.indexOf("--queue-size") + 1;
  let result = spawnSync(python, prepareArgs, { encoding: "utf8", windowsHide: true });
  let actualRequestedSize = args["queue-size"];
  const failureText = `${result.stderr || ""}\n${result.stdout || ""}`;
  const shortQueueMatch = failureText.match(/only (\d+) candidates available for requested queue size \d+/);
  if (result.status !== 0 && shortQueueMatch && Number(shortQueueMatch[1]) > 0) {
    actualRequestedSize = Number(shortQueueMatch[1]);
    prepareArgs[queueSizeArgIndex] = String(actualRequestedSize);
    result = spawnSync(python, prepareArgs, { encoding: "utf8", windowsHide: true });
  }
  await fs.writeFile(path.join(importDir, "prepare_stdout.txt"), result.stdout || "", "utf8");
  await fs.writeFile(path.join(importDir, "prepare_stderr.txt"), result.stderr || "", "utf8");
  if (result.status !== 0) {
    throw new Error(`strict candidate preparation failed (${result.status}): ${(result.stderr || result.stdout || "").trim()}`);
  }

  const queuePath = path.join(outputDir, `asin_queue_${queueName}.txt`);
  const queueJsonPath = path.join(outputDir, `${queueName}.json`);
  await fs.copyFile(queuePath, path.join(importDir, "runner_queue.txt"));
  await fs.copyFile(queueJsonPath, path.join(importDir, "runner_queue.json"));
  const queueAsins = (await fs.readFile(queuePath, "utf8")).split(/\r?\n/).filter(Boolean);
  const queueRows = JSON.parse(await fs.readFile(queueJsonPath, "utf8"));
  const parts = [];
  for (let offset = 0; offset < queueAsins.length; offset += args["part-size"]) {
    const partNumber = Math.floor(offset / args["part-size"]) + 1;
    const partLabel = String(partNumber).padStart(2, "0");
    const partAsins = queueAsins.slice(offset, offset + args["part-size"]);
    const asinSet = new Set(partAsins);
    const partRows = queueRows.filter((row) => asinSet.has(row.asin));
    const partTxt = path.join(importDir, `runner_queue_part_${partLabel}.txt`);
    const partJson = path.join(importDir, `runner_queue_part_${partLabel}.json`);
    await fs.writeFile(partTxt, `${partAsins.join("\n")}\n`, "ascii");
    await fs.writeFile(partJson, `${JSON.stringify(partRows, null, 2)}\n`, "utf8");
    parts.push({ part: partNumber, rows: partAsins.length, txt: partTxt, json: partJson });
  }
  console.log(JSON.stringify({
    ...importSummary,
    requestedQueueSize: args["queue-size"],
    preparedQueueSize: actualRequestedSize,
    queueSize: queueAsins.length,
    queueShortfall: Math.max(0, args["queue-size"] - queueAsins.length),
    queuePath: path.join(importDir, "runner_queue.txt"),
    queueJsonPath: path.join(importDir, "runner_queue.json"),
    partSize: args["part-size"],
    parts,
  }, null, 2));
}

main().catch((error) => {
  console.error(error?.stack || String(error));
  process.exitCode = 1;
});
