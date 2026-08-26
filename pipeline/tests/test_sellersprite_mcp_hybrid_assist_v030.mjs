import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const fileName = "sellersprite_mcp_hybrid_assist_v0.3.0.user.js";
const source = fs.readFileSync(path.join(root, "scripts", fileName), "utf8");
const sandbox = { console, globalThis: {}, URL };
vm.runInNewContext(source, sandbox, { filename: fileName });
const core = sandbox.globalThis.SSMcpHybridAssistCore;
const plain = (value) => JSON.parse(JSON.stringify(value));

assert.ok(core);
assert.equal(core.version, "0.3.0");
assert.equal(core.mode, "shadow-assist");
assert.equal(core.featureFlag, "ENABLE_MCP_HYBRID_ASSIST_V0_3_0");
assert.equal(core.eventProtocol, "runner-adapter/v2");
assert.equal(core.minBridgeVersion, "0.3.0");
assert.equal(core.buildFlags.requiredAuditRelayV1, true);
assert.equal(core.normalizeRequestId(" runner-adapter:123:abc "), "runner-adapter:123:abc");
assert.equal(core.normalizeRequestId("bad request id"), "");
assert.equal(core.versionAtLeast("0.3.0", "0.3.0"), true);
assert.equal(core.versionAtLeast("0.4.0", "0.3.0"), true);
assert.equal(core.versionAtLeast("0.2.9", "0.3.0"), false);

const validHealth = {
  schemaVersion: "sellerSpriteMcpHybridResponse/v1",
  ok: true,
  version: "0.3.0",
  runId: "run-1",
  mode: "shadow",
  outboundMcpEnabled: false,
  finalAuthority: false,
};
assert.deepEqual(plain(core.validateBridgeHealth(validHealth)), {
  version: "0.3.0",
  runId: "run-1",
  policyVersion: "",
  policySha256: "",
  testMode: false,
  finalAuthority: false,
});
assert.throws(
  () => core.validateBridgeHealth({ ...validHealth, version: "0.2.9" }),
  /0\.3\.0 or newer/,
);
assert.throws(
  () => core.validateBridgeHealth({ ...validHealth, finalAuthority: true }),
  /authority boundary/,
);

const nowMs = Date.parse("2026-07-29T00:00:00Z");
const mergedRow = {
  asin: "B0AAAA0001",
  finalAuthority: false,
  usableForRanking: true,
  browserFallbackRequired: true,
  mergedRanking: {
    schemaVersion: "sellerSpriteMcpMergedRanking/v1",
    fields: { price: 19.99, rating: 4.8, reviews: 10, dimensions: "10 x 8 in" },
    fieldSources: {
      price: {
        evidenceId: "ev-1",
        tool: "keepa_info",
        capturedAt: "2026-07-28T22:00:00Z",
        expiresAt: "2026-07-29T04:00:00Z",
        sourcePath: "fields.price",
        semantics: "current_price",
      },
      rating: {
        evidenceId: "ev-1",
        tool: "keepa_info",
        capturedAt: "2026-07-28T22:00:00Z",
        expiresAt: "2026-07-29T04:00:00Z",
        sourcePath: "fields.rating",
        semantics: "rating",
      },
      reviews: {
        evidenceId: "ev-1",
        tool: "keepa_info",
        capturedAt: "2026-07-28T22:00:00Z",
        expiresAt: "2026-07-29T04:00:00Z",
        sourcePath: "fields.reviews",
        semantics: "reviews",
      },
      dimensions: {
        evidenceId: "ev-1",
        tool: "keepa_info",
        capturedAt: "2026-07-28T22:00:00Z",
        expiresAt: "2026-07-29T04:00:00Z",
        sourcePath: "fields.dimensions",
        semantics: "dimensions_advisory",
      },
    },
    usableForRanking: true,
    browserFallbackRequired: true,
    reasonCodes: [],
    evidenceIds: ["ev-1"],
    capturedAt: "2026-07-28T22:00:00Z",
    expiresAt: "2026-07-29T04:00:00Z",
    usableForFinal: false,
    finalAuthority: false,
  },
};
const normalizedMerged = core.normalizeLookupRow(mergedRow, "B0AAAA0001", nowMs);
assert.equal(normalizedMerged.usableForRanking, true);
assert.equal(normalizedMerged.browserFallbackRequired, true);
assert.equal(normalizedMerged.source, "mergedRanking");
assert.equal(normalizedMerged.fields.price, 19.99);
assert.equal(normalizedMerged.fieldSources.price.tool, "keepa_info");
assert.equal(normalizedMerged.finalAuthority, false);

const missingMergedAuthority = core.normalizeLookupRow({
  ...mergedRow,
  mergedRanking: { ...mergedRow.mergedRanking, finalAuthority: undefined },
}, "B0AAAA0001", nowMs);
assert.equal(missingMergedAuthority.usableForRanking, false);

const overTtlMerged = core.normalizeLookupRow({
  ...mergedRow,
  mergedRanking: {
    ...mergedRow.mergedRanking,
    fieldSources: {
      ...mergedRow.mergedRanking.fieldSources,
      price: {
        ...mergedRow.mergedRanking.fieldSources.price,
        capturedAt: "2026-07-28T00:00:00Z",
        expiresAt: "2026-07-29T04:00:00Z",
      },
    },
  },
}, "B0AAAA0001", nowMs);
assert.equal(overTtlMerged.fields.price, undefined);
assert.equal(overTtlMerged.browserFallbackRequired, true);

const invalidMerged = core.normalizeLookupRow({
  ...mergedRow,
  mergedRanking: { ...mergedRow.mergedRanking, reasonCodes: ["stale_evidence"] },
  results: [{
    usableForRanking: true,
    usableForFinal: false,
    evidence: {
      targetAsin: "B0AAAA0001",
      actualAsin: "B0AAAA0001",
      finalAuthority: false,
      fields: { price: 19.99 },
    },
  }],
}, "B0AAAA0001", nowMs);
assert.equal(invalidMerged.usableForRanking, false);
assert.equal(invalidMerged.reason, "invalid_merged_ranking");

const legacyRow = {
  asin: "B0AAAA0002",
  finalAuthority: false,
  browserFallbackRequired: true,
  results: [{
    usableForRanking: true,
    browserFallbackRequired: true,
    usableForFinal: false,
    evidence: {
      evidenceId: "legacy-1",
      tool: { name: "keepa_info" },
      targetAsin: "B0AAAA0002",
      actualAsin: "B0AAAA0002",
      capturedAt: "2026-07-28T22:00:00Z",
      expiresAt: "2026-07-29T04:00:00Z",
      finalAuthority: false,
      fields: { price: 12.99, reviews: 20 },
      fieldProvenance: {
        price: { sourceTool: "keepa_info", sourcePath: "fields.price", semantics: "current_price" },
        reviews: { sourceTool: "keepa_info", sourcePath: "fields.reviews", semantics: "review_count" },
      },
    },
  }, {
    usableForRanking: true,
    usableForFinal: false,
    reasonCodes: ["asin_mismatch"],
    evidence: {
      targetAsin: "B0AAAA0002",
      actualAsin: "B0AAAA0003",
      finalAuthority: false,
      fields: { rating: 5 },
    },
  }],
};
const normalizedLegacy = core.normalizeLookupRow(legacyRow, "B0AAAA0002", nowMs);
assert.equal(normalizedLegacy.usableForRanking, true);
assert.equal(normalizedLegacy.source, "legacyResults");
assert.deepEqual(plain(normalizedLegacy.fields), { price: 12.99, reviews: 20 });
assert.equal(normalizedLegacy.fieldSources.price.tool, "keepa_info");

const badLegacyProvenance = JSON.parse(JSON.stringify(legacyRow));
badLegacyProvenance.results[0].evidence.fieldProvenance.price.sourceTool = "asin_detail";
badLegacyProvenance.results[0].evidence.fieldProvenance.reviews.sourceAsin = "B0AAAA0003";
const rejectedLegacyProvenance = core.normalizeLookupRow(
  badLegacyProvenance,
  "B0AAAA0002",
  nowMs,
);
assert.equal(rejectedLegacyProvenance.usableForRanking, false);
assert.equal(rejectedLegacyProvenance.browserFallbackRequired, true);

const shadowOnly = core.normalizeLookupRow({
  asin: "B0AAAA0003",
  finalAuthority: false,
  results: [{
    usableForShadow: true,
    usableForFinal: false,
    evidence: {
      targetAsin: "B0AAAA0003",
      actualAsin: "B0AAAA0003",
      finalAuthority: false,
      fields: { price: 12.99 },
    },
  }],
}, "B0AAAA0003", nowMs);
assert.equal(shadowOnly.usableForRanking, false);
assert.equal(shadowOnly.browserFallbackRequired, true);

const batchPayload = {
  schemaVersion: "sellerSpriteMcpHybridResponse/v1",
  ok: true,
  finalAuthority: false,
  result: {
    schemaVersion: "sellerSpriteMcpBatchLookup/v1",
    finalAuthority: false,
    rows: [mergedRow, legacyRow],
  },
};
const batch = core.normalizeBatchResponse(batchPayload, ["B0AAAA0001", "B0AAAA0002"], nowMs);
assert.equal(batch.ok, true);
assert.equal(batch.rows.length, 2);
assert.equal(batch.rows[0].source, "mergedRanking");
assert.equal(batch.rows[1].source, "legacyResults");

const evidenceByAsin = {
  B0AAAA0001: normalizedMerged,
  B0AAAA0002: normalizedLegacy,
};
const smallAuto = core.rankQueue(
  ["B0AAAA0002", "B0AAAA0001"],
  evidenceByAsin,
  "auto",
  { balancedExplicit: false },
);
assert.equal(smallAuto.mode, "focus5");
assert.deepEqual(plain(smallAuto.ranked), ["B0AAAA0001", "B0AAAA0002"]);
assert.equal(smallAuto.multisetUnchanged, true);

const ten = Array.from({ length: 10 }, (_, index) => `B0AAA${String(index).padStart(5, "0")}`);
const largeAuto = core.rankQueue(ten, {}, "auto", { balancedExplicit: false });
assert.equal(largeAuto.mode, "original");
assert.deepEqual(plain(largeAuto.ranked), ten);
const balancedWithoutOptIn = core.rankQueue(
  ["B0AAAA0002", "B0AAAA0001"],
  evidenceByAsin,
  "balanced",
  { balancedExplicit: false },
);
assert.equal(balancedWithoutOptIn.mode, "original");
const balancedExplicit = core.rankQueue(
  ["B0AAAA0002", "B0AAAA0001"],
  evidenceByAsin,
  "balanced",
  { balancedExplicit: true },
);
assert.equal(balancedExplicit.mode, "balanced");
assert.deepEqual(plain(balancedExplicit.ranked), ["B0AAAA0001", "B0AAAA0002"]);

const breakdown = core.scoreBreakdown({
  price: 20,
  rating: 4.5,
  reviews: 10,
  dimensions: "x",
  priceTrendClass: "stable",
});
assert.equal(breakdown.price + breakdown.rating + breakdown.reviews, 8);
assert.equal(breakdown.dimensions + breakdown.priceTrend, 0.5);
assert.equal(core.buildAdvisory(normalizedMerged).allowedAction, "reorder_only");
assert.equal(core.buildAdvisory(normalizedMerged).gateCProvided, false);

const receiptPayload = {
  schemaVersion: "sellerSpriteMcpHybridResponse/v1",
  ok: true,
  finalAuthority: false,
  result: {
    schemaVersion: "sellerSpriteMcpAuditReceipt/v1",
    requestId: "runner-adapter:1:abc",
    auditId: "apply:abc:def",
    persisted: true,
    idempotent: false,
    finalAuthority: false,
  },
};
assert.deepEqual(plain(core.buildAuditRequest(
  "queue_applied",
  { finalAuthority: true, count: 2 },
  "runner-adapter:1:abc",
  "apply:abc:def",
)), {
  schemaVersion: "sellerSpriteMcpAuditEvent/v1",
  requestId: "runner-adapter:1:abc",
  auditId: "apply:abc:def",
  eventType: "queue_applied",
  payload: { finalAuthority: false, count: 2 },
});
assert.throws(
  () => core.buildAuditRequest("Bad Event", {}, "runner-adapter:1:abc", "apply:abc:def"),
  /invalid/,
);
assert.equal(core.validateAuditReceipt(receiptPayload, {
  requestId: "runner-adapter:1:abc",
  auditId: "apply:abc:def",
}).persisted, true);
assert.throws(
  () => core.validateAuditReceipt(receiptPayload, {
    requestId: "runner-adapter:old",
    auditId: "apply:abc:def",
  }),
  /invalid or stale/,
);

assert.equal(source.includes("localStorage"), false);
assert.equal(source.includes("strict-qualified-history"), false);
assert.equal(source.includes(".click("), false);
assert.match(source, /\/api\/v1\/health/);
assert.match(source, /\/api\/v1\/audit\/events/);
assert.match(source, /rankingAuditConfirmed = true/);
assert.match(source, /data-ss-mcp-feature-enabled/);
assert.match(source, /forbiddenActions: \['pass_gate'/);

console.log("SellerSprite MCP Hybrid Assist 0.3.0 tests: PASS");
