import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function loadCore(fileName, globalName) {
  const source = fs.readFileSync(path.join(root, "scripts", fileName), "utf8");
  const sandbox = { console, globalThis: {}, URL, Event: class {} };
  vm.runInNewContext(source, sandbox, { filename: fileName });
  return sandbox.globalThis[globalName];
}

function sha256(fileName) {
  return crypto.createHash("sha256")
    .update(fs.readFileSync(path.join(root, "scripts", fileName)))
    .digest("hex")
    .toUpperCase();
}

const assist = loadCore(
  "sellersprite_mcp_hybrid_assist_v0.3.0.user.js",
  "SSMcpHybridAssistCore",
);
const adapter = loadCore(
  "sellersprite_mcp_hybrid_runner_adapter_v0.2.0.user.js",
  "SSMcpHybridRunnerAdapterCore",
);
const bundle = JSON.parse(fs.readFileSync(
  path.join(root, "runs", "mcp_hybrid_assist_v0.2_paired30", "evidence_bundle.json"),
  "utf8",
));
const priorDecision = JSON.parse(fs.readFileSync(
  path.join(root, "runs", "mcp_hybrid_assist_v0.2_paired30", "RELEASE_DECISION.json"),
  "utf8",
));

assert.equal(bundle.evidence.length, 30);
assert.equal(priorDecision.sampleSize, 30);
assert.equal(priorDecision.falsePositives, 0);
assert.equal(priorDecision.multisetUnchanged, true);
assert.equal(priorDecision.formalRunAuthorized, false);

const queue = [];
const evidenceByAsin = {};
for (const evidence of bundle.evidence) {
  const asin = assist.normalizeAsin(evidence.targetAsin);
  assert.ok(asin);
  assert.equal(evidence.targetAsin, evidence.actualAsin);
  assert.equal(evidence.finalAuthority, false);
  queue.push(asin);
  evidenceByAsin[asin] = assist.normalizeLookupRow({
    asin,
    finalAuthority: false,
    browserFallbackRequired: true,
    results: [{
      evidenceId: evidence.evidenceId,
      tool: "keepa_info",
      capturedAt: evidence.response?.capturedAt || "",
      expiresAt: evidence.response?.expiresAt || "",
      usableForRanking: true,
      browserFallbackRequired: true,
      usableForFinal: false,
      evidence: {
        ...evidence,
        browserFallbackRequired: true,
      },
    }],
  }, asin, Date.parse(evidence.response.capturedAt) + 1000);
  assert.equal(evidenceByAsin[asin].usableForRanking, true);
  assert.equal(evidenceByAsin[asin].source, "legacyResults");
  assert.equal(evidenceByAsin[asin].browserFallbackRequired, true);
}

assert.equal(new Set(queue).size, 30);
const ranked = assist.rankQueue(queue, evidenceByAsin, "auto", { balancedExplicit: false });
assert.equal(ranked.mode, "original");
assert.deepEqual(ranked.ranked, queue);
assert.equal(ranked.multisetUnchanged, true);
assert.equal(ranked.finalAuthority, false);
assert.equal(ranked.allowedAction, "reorder_only");

const requestId = "runner-adapter:paired30:20260729";
const auditId = "rank:paired30:20260729";
const detail = {
  ...ranked,
  requestId,
  eventProtocol: "runner-adapter/v2",
  assistVersion: "0.3.0",
  auditRequired: true,
  rankingAuditConfirmed: true,
  rankingAudit: {
    schemaVersion: "sellerSpriteMcpAuditReceipt/v1",
    requestId,
    auditId,
    persisted: true,
    idempotent: false,
    finalAuthority: false,
  },
};
const validated = Array.from(adapter.validateRankedResponse(detail, {
  requestId,
  text: queue.join("\n"),
  asins: queue,
  requestedMode: "auto",
  mode: "original",
  balancedExplicit: false,
}));
assert.deepEqual(validated, queue);
assert.equal(adapter.multisetSignature(validated), adapter.multisetSignature(queue));

assert.equal(
  sha256("sellersprite_mcp_hybrid_assist_v0.2.1.user.js"),
  "56E8A6FE711BF49A9E8B6F9C1A8B61A033CDE1C38867E29B50CC18D92C4388F1",
);
assert.equal(
  sha256("sellersprite_mcp_hybrid_runner_adapter_v0.1.0.user.js"),
  "CC0DB0EABFB520C2F306A545A23CCBBF464ED1794EEA2B82C4B542BA23321D43",
);

console.log("SellerSprite MCP Hybrid 0.3.0/0.2.0 paired-30 compatibility: PASS");
