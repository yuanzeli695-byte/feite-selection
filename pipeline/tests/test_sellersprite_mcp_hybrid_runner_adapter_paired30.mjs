import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function loadCore(fileName, globalName, extra = {}) {
  const source = fs.readFileSync(path.join(root, "scripts", fileName), "utf8");
  const sandbox = { console, globalThis: {}, URL, Event: class {}, ...extra };
  vm.runInNewContext(source, sandbox, { filename: fileName });
  return sandbox.globalThis[globalName];
}

const assist = loadCore(
  "sellersprite_mcp_hybrid_assist_v0.2.1.user.js",
  "SSMcpHybridAssistCore",
);
const adapter = loadCore(
  "sellersprite_mcp_hybrid_runner_adapter_v0.1.0.user.js",
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
for (const row of bundle.evidence) {
  assert.equal(row.finalAuthority, false);
  assert.equal(row.targetAsin, row.actualAsin);
  const asin = assist.normalizeAsin(row.targetAsin);
  assert.ok(asin);
  queue.push(asin);
  evidenceByAsin[asin] = {
    asin,
    usable: true,
    fields: row.fields || {},
    finalAuthority: false,
  };
}

assert.equal(new Set(queue).size, 30);
const ranked = assist.rankQueue(queue, evidenceByAsin, "balanced");
const requestId = "runner-adapter:paired30:20260729";
const detail = {
  ...ranked,
  requestId,
  eventProtocol: "runner-adapter/v1",
};
const validated = Array.from(adapter.validateRankedResponse(detail, {
  requestId,
  text: queue.join("\n"),
  asins: queue,
  mode: "balanced",
}));

assert.equal(validated.length, 30);
assert.equal(adapter.multisetSignature(validated), adapter.multisetSignature(queue));
assert.equal(detail.finalAuthority, false);
assert.equal(detail.allowedAction, "reorder_only");
assert.equal(detail.multisetUnchanged, true);

console.log("SellerSprite MCP Hybrid Runner Adapter paired-30 handshake: PASS");
