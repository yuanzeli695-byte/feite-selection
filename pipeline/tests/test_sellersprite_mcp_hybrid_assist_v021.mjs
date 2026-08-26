import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const fileName = "sellersprite_mcp_hybrid_assist_v0.2.1.user.js";
const source = fs.readFileSync(path.join(root, "scripts", fileName), "utf8");
const sandbox = { console, globalThis: {}, URL };
vm.runInNewContext(source, sandbox, { filename: fileName });
const core = sandbox.globalThis.SSMcpHybridAssistCore;

assert.ok(core);
assert.equal(core.version, "0.2.1");
assert.equal(core.mode, "shadow-assist");
assert.equal(core.featureFlag, "ENABLE_MCP_HYBRID_ASSIST_V0_2_1");
assert.equal(core.eventProtocol, "runner-adapter/v1");
assert.equal(core.normalizeRequestId(" runner-adapter:123:abc "), "runner-adapter:123:abc");
assert.equal(core.normalizeRequestId("bad request id"), "");

const evidence = {
  schemaVersion: "sellerSpriteMcpHybridResponse/v1",
  ok: true,
  finalAuthority: false,
  result: {
    schemaVersion: "sellerSpriteMcpBatchLookup/v1",
    finalAuthority: false,
    rows: [
      {
        asin: "B0AAAA0001",
        finalAuthority: false,
        results: [{
          usableForShadow: true,
          usableForFinal: false,
          evidence: {
            targetAsin: "B0AAAA0001",
            actualAsin: "B0AAAA0001",
            finalAuthority: false,
            fields: { price: 19.99, rating: 4.8, reviews: 10, dimensions: "10 x 8 inches", priceTrendClass: "stable" },
          },
        }],
      },
      { asin: "B0AAAA0002", finalAuthority: false, results: [] },
    ],
  },
};
const normalized = core.normalizeBatchResponse(evidence, ["B0AAAA0001", "B0AAAA0002"]);
const ranked = core.rankQueue(
  ["B0AAAA0002", "B0AAAA0001", "B0AAAA0002"],
  { B0AAAA0001: normalized.rows[0], B0AAAA0002: normalized.rows[1] },
  "balanced",
);

assert.deepEqual(ranked.ranked, ["B0AAAA0001", "B0AAAA0002", "B0AAAA0002"]);
assert.equal(ranked.multisetUnchanged, true);
assert.equal(ranked.finalAuthority, false);
assert.equal(ranked.allowedAction, "reorder_only");
assert.equal(source.includes("localStorage"), false);
assert.match(source, /data-ss-mcp-event-protocol/);
assert.match(source, /requestId:\s*requestId/);
assert.match(source, /eventProtocol:\s*EVENT_PROTOCOL/);

console.log("SellerSprite MCP Hybrid Assist 0.2.1 tests: PASS");
