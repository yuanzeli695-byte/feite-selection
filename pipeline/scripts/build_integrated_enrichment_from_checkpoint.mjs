import fs from "node:fs/promises";
import path from "node:path";

const runDir = path.resolve(process.argv[2] || "");
if (!runDir) throw new Error("Usage: node build_integrated_enrichment_from_checkpoint.mjs <run-dir>");

const batchDir = path.join(runDir, "batch_inputs");
const checkpointPath = path.join(runDir, "price_review_checkpoint.json");
const outputPath = path.join(runDir, "product_enrichment_dimensions_price.json");
const batchFiles = (await fs.readdir(batchDir))
  .filter((name) => /^batch\d+.*_integrated\.json$/i.test(name))
  .sort();

const dimensionsByAsin = new Map();
for (const fileName of batchFiles) {
  const payload = JSON.parse(await fs.readFile(path.join(batchDir, fileName), "utf8"));
  for (const row of payload.results || []) {
    const asin = row.targetAsin || row.asin;
    if (!asin || dimensionsByAsin.has(asin)) continue;
    dimensionsByAsin.set(asin, {
      dimensions: row.dimensions || "",
      itemDimensions: row.itemDimensions || "",
      itemWeight: row.itemWeight || "",
      packageDimensions: row.packageDimensions || "",
      packageWeight: row.packageWeight || "",
      dimensionsSource: row.dimensionsSource || "SellerSprite商品详情/Amazon详情",
    });
  }
}

const checkpoint = JSON.parse(await fs.readFile(checkpointPath, "utf8"));
const rows = Object.values(checkpoint.results || {}).map((price) => {
  const dimensions = dimensionsByAsin.get(price.asin) || {};
  const priceAllowed = ["stable", "rising"].includes(price.priceTrendClass);
  const dimensionsPresent = Boolean(String(dimensions.dimensions || "").trim());
  return {
    asin: price.asin,
    status: priceAllowed && dimensionsPresent ? "ok" : "review",
    ...dimensions,
    priceTrendClass: price.priceTrendClass || "no_data",
    priceTrendSentence: price.priceTrendSentence || "",
    priceTrend: price.priceTrend || "近30天价格趋势数据不足。",
    spreadPct: price.spreadPct ?? null,
    currentPosition: price.currentPosition ?? null,
    priceTrendWindow: price.priceTrendWindow || "近30天",
    priceTrendSource: price.priceTrendSource || "Amazon Price history / Rufus",
    sourceUrl: price.sourceUrl || `https://www.amazon.com/dp/${price.asin}?th=1`,
    collectedAt: price.collectedAt || checkpoint.updatedAt || new Date().toISOString(),
    error: price.error || "",
  };
});

await fs.writeFile(outputPath, `${JSON.stringify(rows, null, 2)}\n`, "utf8");
const summary = {
  outputPath,
  rows: rows.length,
  ok: rows.filter((row) => row.status === "ok").length,
  noDimensions: rows.filter((row) => !String(row.dimensions || "").trim()).length,
  priceRejected: rows.filter((row) => !["stable", "rising"].includes(row.priceTrendClass)).length,
};
console.log(JSON.stringify(summary, null, 2));
