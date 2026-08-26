import fs from "node:fs/promises";
import path from "node:path";

const rawArgs = process.argv.slice(2);
let importMode = "strict-pass";
const modeIndex = rawArgs.indexOf("--mode");
if (modeIndex >= 0) {
  importMode = rawArgs[modeIndex + 1] || "";
  rawArgs.splice(modeIndex, 2);
}
if (!new Set(["strict-pass", "browser-qualified"]).has(importMode)) {
  throw new Error("--mode must be strict-pass or browser-qualified");
}
const [batchPath, candidatesPath, titlesPath, imagesDir, replayDir, runId, runDate] = rawArgs;
if (![batchPath, candidatesPath, titlesPath, imagesDir, replayDir, runId, runDate].every(Boolean)) {
  throw new Error("Usage: node direct_import_batch_to_replay.mjs <batch> <candidates> <titles> <images> <replay> <runId> <runDate> [--mode strict-pass|browser-qualified]");
}

const readJson = async (file) => JSON.parse(await fs.readFile(file, "utf8"));
const batch = await readJson(batchPath);
const candidates = await readJson(candidatesPath);
const titles = await readJson(titlesPath);
const candidateByAsin = new Map(candidates.map((candidate) => [String(candidate.asin || "").trim().toUpperCase(), candidate]));
const directPasses = (batch.results || []).filter((result) => result.qualified === true && (importMode === "browser-qualified" || result.strictDecision === "pass"));

if (!directPasses.length) throw new Error("No qualified strict-pass records in batch JSON");

const finalRows = directPasses.map((traffic) => {
  const asin = String(traffic.actualAsin || traffic.targetAsin || "").trim().toUpperCase();
  const candidate = candidateByAsin.get(asin);
  if (!candidate) throw new Error("Candidate not found for " + asin);
  const cnTitle = titles[asin];
  if (!cnTitle) throw new Error("Chinese title not found for " + asin);
  const imagePath = path.resolve(imagesDir, asin + ".png");
  return {
    asin,
    cnTitle,
    product: {
      asin,
      title: candidate.title || "",
      brand: candidate.brand || "",
      categoryPath: candidate.categoryPath || "",
      price: traffic.currentPrice ?? candidate.price ?? null,
      sourcePrice: candidate.price ?? null,
      currentPrice: traffic.currentPrice ?? candidate.price ?? null,
      priceSource: "batch_json_direct_import",
      rating: candidate.rating ?? null,
      reviews: candidate.reviews ?? null,
      monthlySales: candidate.monthlySales ?? null,
      parentMonthlySales: candidate.parentMonthlySales ?? null,
      launchDate: candidate.launchDate || "",
      launchAgeDays: candidate.launchAgeDays ?? null,
      variationsCount: candidate.variations ?? null,
      imageUrl: candidate.image || "",
      sourcePage: candidate.sourcePage || "",
      delivery: candidate.delivery || "",
      dimensions: traffic.dimensions || "",
      itemDimensions: traffic.itemDimensions || "",
      itemWeight: traffic.itemWeight || "",
      packageDimensions: traffic.packageDimensions || "",
      packageWeight: traffic.packageWeight || "",
      priceTrend: traffic.priceTrend || "",
      priceTrendClass: traffic.priceTrendClass || "",
      priceTrendWindow: traffic.priceTrendWindow || "",
      priceTrendSource: traffic.priceTrendSource || "",
      dimensionsSource: traffic.dimensionsSource || "",
      sellerSpriteUrl: candidate.sellerSpriteUrl || "",
      rawProduct: "",
    },
    traffic,
    warnings: [],
    tags: [],
    imagePath,
    amazonUrl: candidate.amazonUrl || traffic.url || ("https://www.amazon.com/dp/" + asin),
    source: {
      batchName: batch.batchName || "",
      operator: batch.operator || "",
      queueHash: batch.queueHash || "",
      row: traffic.row ?? null,
    },
  };
});

await fs.mkdir(replayDir, { recursive: true });
await fs.writeFile(path.join(replayDir, "final_candidates_data.json"), JSON.stringify(finalRows, null, 2) + "\n", "utf8");
await fs.writeFile(path.join(replayDir, "rejected_audit_data.json"), "[]\n", "utf8");
await fs.writeFile(path.join(replayDir, "run_summary.json"), JSON.stringify({
  runId,
  runDate,
  targetN: finalRows.length,
  qualifiedCount: finalRows.length,
  attempts: finalRows.length,
  rejectedCount: 0,
  completedTarget: true,
  directImport: true,
  importMode,
  sourceBatch: batch.batchName || "",
  sourceQueueHash: batch.queueHash || "",
}, null, 2) + "\n", "utf8");
console.log(JSON.stringify({ directImported: finalRows.length, asins: finalRows.map((row) => row.asin) }));
