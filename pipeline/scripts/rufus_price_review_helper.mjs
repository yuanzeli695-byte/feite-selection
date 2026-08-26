import fs from "node:fs/promises";
import path from "node:path";

const STOP_WORDS = new Set([
  "with", "for", "and", "the", "from", "this", "that", "pack", "set",
  "home", "kitchen", "organizer", "holder", "storage", "compatible",
  "replacement", "accessories",
]);

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function classifySentence(sentence) {
  const text = String(sentence || "").replace(/\s+/g, " ").trim();
  const amounts = [...text.matchAll(/\$\s*([0-9]+(?:\.[0-9]{1,2})?)/g)]
    .map((match) => Number(match[1]));

  if (/\bsteady\b|\bstable\b/i.test(text)) {
    const price = amounts.length ? amounts.at(-1) : null;
    return {
      priceTrendClass: "stable",
      minimum: price,
      maximum: price,
      current: price,
      spreadPct: 0,
      currentPosition: null,
    };
  }

  const range = text.match(
    /ranged\s+from\s+\$\s*([0-9]+(?:\.[0-9]{1,2})?)\s+to\s+\$\s*([0-9]+(?:\.[0-9]{1,2})?)/i,
  );
  const currentMatch = text.match(
    /current\s+price\s+is\s+\$\s*([0-9]+(?:\.[0-9]{1,2})?)/i,
  );
  if (!range) {
    return {
      priceTrendClass: "no_data",
      minimum: null,
      maximum: null,
      current: amounts.length ? amounts.at(-1) : null,
      spreadPct: null,
      currentPosition: null,
    };
  }

  const minimum = Number(range[1]);
  const maximum = Number(range[2]);
  const current = currentMatch ? Number(currentMatch[1]) : amounts.at(-1);
  const spreadPct = minimum > 0 ? (maximum - minimum) / minimum : null;
  const currentPosition = maximum > minimum
    ? (current - minimum) / (maximum - minimum)
    : null;

  let priceTrendClass = "volatile";
  if (spreadPct != null && spreadPct <= 0.2) {
    priceTrendClass = "stable";
  } else if (
    /highest|increased|rose|up\b/i.test(text)
    || (currentPosition != null && currentPosition >= 0.75)
  ) {
    priceTrendClass = "rising";
  } else if (
    /lowest|decreased|dropped|down\b/i.test(text)
    || (currentPosition != null && currentPosition <= 0.25)
  ) {
    priceTrendClass = "declining";
  }

  return {
    priceTrendClass,
    minimum,
    maximum,
    current,
    spreadPct,
    currentPosition,
  };
}

function chineseTrend(classification) {
  const {
    priceTrendClass,
    minimum,
    maximum,
    current,
  } = classification;
  if (priceTrendClass === "stable") {
    if (minimum != null && maximum === minimum) {
      return `近30天价格稳定在 $${current.toFixed(2)}。`;
    }
    return `近30天价格区间 $${minimum.toFixed(2)}-$${maximum.toFixed(2)}，当前 $${current.toFixed(2)}，整体波动有限，判定稳定。`;
  }
  if (priceTrendClass === "rising") {
    return `近30天价格区间 $${minimum.toFixed(2)}-$${maximum.toFixed(2)}，当前 $${current.toFixed(2)}，处于区间高位或上涨趋势。`;
  }
  if (priceTrendClass === "declining") {
    return `近30天价格区间 $${minimum.toFixed(2)}-$${maximum.toFixed(2)}，当前 $${current.toFixed(2)}，处于区间低位，判定下降趋势。`;
  }
  if (priceTrendClass === "volatile") {
    return `近30天价格区间 $${minimum.toFixed(2)}-$${maximum.toFixed(2)}，当前 $${current.toFixed(2)}，价格波动较大。`;
  }
  return "近30天价格趋势数据不足。";
}

async function loadCandidateMap(runDir) {
  const map = new Map();
  const inputDir = path.join(runDir, "candidate_inputs");
  const files = (await fs.readdir(inputDir))
    .filter((name) => /^batch\d+_integrated\.json$/i.test(name))
    .sort();
  for (const fileName of files) {
    const filePath = path.join(inputDir, fileName);
    const rows = JSON.parse(await fs.readFile(filePath, "utf8"));
    for (const row of rows) map.set(row.asin, row);
  }
  return map;
}

function validateAnswer(candidate, sentence) {
  const title = String(candidate?.title || "").toLowerCase();
  const answer = String(sentence || "").toLowerCase();
  const words = [...new Set((title.match(/[a-z0-9]+/g) || [])
    .filter((word) => word.length >= 4 && !STOP_WORDS.has(word)))];
  const overlaps = words.filter((word) => answer.includes(word));
  const amounts = [...answer.matchAll(/\$\s*([0-9]+(?:\.[0-9]{1,2})?)/g)]
    .map((match) => Number(match[1]));
  const expectedPrice = Number(candidate?.price);
  const priceMatch = Number.isFinite(expectedPrice)
    && amounts.some((value) => Math.abs(value - expectedPrice) <= 0.02);
  return {
    valid: Boolean(sentence) && (overlaps.length >= 1 || priceMatch),
    overlaps,
    priceMatch,
    expectedPrice: candidate?.price ?? null,
    amounts,
  };
}

async function readAnswerRecords(tab) {
  return tab.playwright.evaluate(() => {
    const records = [];
    for (const container of document.querySelectorAll(
      "#nav-flyout-rufus [data-csa-c-nile-request-id]",
    )) {
      const id = container.getAttribute("data-csa-c-nile-request-id") || "";
      const values = [container, ...container.querySelectorAll("*")]
        .map((element) => (element.innerText || "").replace(/\s+/g, " ").trim())
        .filter((text) => text.startsWith("Over the past 30 days")
          && text.length >= 45
          && text.length < 700);
      const unique = [...new Set(values)].sort((left, right) => left.length - right.length);
      if (id && unique[0]) records.push({ id, text: unique[0] });
    }
    const byId = new Map();
    for (const record of records) {
      const prior = byId.get(record.id);
      if (!prior || record.text.length < prior.text.length) byId.set(record.id, record);
    }
    return [...byId.values()];
  }, undefined, { timeoutMs: 10000 }).catch(() => []);
}

async function loadCheckpoint(runDir) {
  const checkpointPath = path.join(runDir, "price_review_checkpoint.json");
  try {
    return JSON.parse(await fs.readFile(checkpointPath, "utf8"));
  } catch {
    return { schemaVersion: "priceReview/v1", results: {}, attempts: [] };
  }
}

async function saveCheckpoint(runDir, result) {
  const checkpointPath = path.join(runDir, "price_review_checkpoint.json");
  const checkpoint = await loadCheckpoint(runDir);
  const previous = checkpoint.results[result.asin];
  if (!previous || previous.priceTrendClass === "no_data" || result.priceTrendClass !== "no_data") {
    checkpoint.results[result.asin] = result;
  }
  checkpoint.attempts.push({
    asin: result.asin,
    collectedAt: result.collectedAt,
    priceTrendClass: result.priceTrendClass,
    error: result.error || "",
  });
  checkpoint.updatedAt = new Date().toISOString();
  const tempPath = `${checkpointPath}.tmp`;
  await fs.writeFile(tempPath, `${JSON.stringify(checkpoint, null, 2)}\n`, "utf8");
  await fs.rename(tempPath, checkpointPath);
}

function baseResult(asin, sourceUrl, pageTitle) {
  return {
    asin,
    status: "review",
    priceTrendClass: "no_data",
    priceTrendSentence: "",
    priceTrend: "近30天价格趋势数据不足。",
    minimum: null,
    maximum: null,
    current: null,
    spreadPct: null,
    currentPosition: null,
    priceTrendWindow: "近30天",
    priceTrendSource: "Amazon Price history / Rufus",
    sourceUrl,
    pageTitle,
    collectedAt: new Date().toISOString(),
  };
}

export async function collectOne(browser, asin, runDir) {
  const candidateMap = await loadCandidateMap(runDir);
  const candidate = candidateMap.get(asin) || {};
  const sourceUrl = `https://www.amazon.com/dp/${asin}?th=1`;
  const tab = await browser.tabs.new();
  let result = baseResult(asin, sourceUrl, "");

  try {
    try {
      await tab.goto(sourceUrl);
    } catch {
      // A partial Amazon load can still expose the product and price controls.
    }
    await tab.playwright.waitForTimeout(4000);

    const pageState = await tab.playwright.evaluate(() => {
      const match = (location.pathname + location.href)
        .toUpperCase()
        .match(/B0[A-Z0-9]{8}/);
      return {
        actualAsin: match ? match[0] : "",
        pageTitle: (document.querySelector("#productTitle")?.textContent || "").trim(),
      };
    }, undefined, { timeoutMs: 10000 }).catch(() => ({ actualAsin: "", pageTitle: "" }));
    result.pageTitle = pageState.pageTitle;

    if (pageState.actualAsin && pageState.actualAsin !== asin) {
      result.error = `asin_mismatch:${pageState.actualAsin}`;
      return result;
    }

    const captchaClose = tab.playwright.locator(".header-class svg.close-btn");
    const closeCount = await captchaClose.count().catch(() => 0);
    if (closeCount === 1) {
      try { await captchaClose.click({ timeoutMs: 5000 }); } catch {}
    }

    const buyBoxButton = tab.playwright.locator("#rufus-price-ingress-bb .a-button-text");
    const centerButton = tab.playwright.locator("#rufus-price-ingress-cc .a-button-text");
    let chosen = null;
    if (await buyBoxButton.count().catch(() => 0) === 1) chosen = buyBoxButton;
    else if (await centerButton.count().catch(() => 0) === 1) chosen = centerButton;
    if (!chosen) {
      result.error = "price_history_button_missing";
      return result;
    }

    try {
      await chosen.click({ timeoutMs: 5000, force: true });
    } catch (error) {
      result.error = String(error);
      return result;
    }

    await tab.playwright.waitForTimeout(15000);
    const records = await readAnswerRecords(tab);
    let sentence = "";
    let requestId = "";
    if (records.length) ({ text: sentence, id: requestId } = records.at(-1));

    const validation = validateAnswer(candidate, sentence);
    if (!validation.valid) {
      result.priceTrendSentence = sentence;
      result.validation = validation;
      result.requestId = requestId;
      result.error = "answer_context_mismatch_or_missing";
      return result;
    }

    const classification = classifySentence(sentence);
    result = {
      ...result,
      ...classification,
      status: ["stable", "rising"].includes(classification.priceTrendClass)
        ? "ok"
        : "review",
      priceTrendSentence: sentence,
      priceTrend: chineseTrend(classification),
      requestId,
      validation,
      error: "",
      collectedAt: new Date().toISOString(),
    };
    return result;
  } finally {
    await saveCheckpoint(runDir, result);
    await Promise.race([tab.close().catch(() => {}), sleep(500)]);
  }
}

export async function seedCheckpoint(runDir, entries) {
  for (const entry of entries) {
    const classification = classifySentence(entry.priceTrendSentence);
    await saveCheckpoint(runDir, {
      asin: entry.asin,
      status: ["stable", "rising"].includes(classification.priceTrendClass)
        ? "ok"
        : "review",
      ...classification,
      priceTrendSentence: entry.priceTrendSentence,
      priceTrend: chineseTrend(classification),
      priceTrendWindow: "近30天",
      priceTrendSource: "Amazon Price history / Rufus",
      sourceUrl: `https://www.amazon.com/dp/${entry.asin}?th=1`,
      collectedAt: entry.collectedAt || new Date().toISOString(),
      validation: { valid: true, seededFromVerifiedRun: true },
      error: "",
    });
  }
  return loadCheckpoint(runDir);
}

export async function collectQueueSlice(browser, asins, runDir, maxStartMs = 25000) {
  const startedAt = Date.now();
  const results = [];
  for (const asin of asins) {
    if (results.length && Date.now() - startedAt >= maxStartMs) break;
    results.push(await collectOne(browser, asin, runDir));
  }
  return {
    elapsedMs: Date.now() - startedAt,
    completed: results.length,
    results,
  };
}

export { loadCheckpoint };
