import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const fileName = "sellersprite_mcp_hybrid_shadow_v0.1.0.user.js";
const source = fs.readFileSync(path.join(root, "scripts", fileName), "utf8");
const sandbox = { console, globalThis: {}, location: { href: "https://www.amazon.com/dp/B0AAAA0001" }, URL };
vm.runInNewContext(source, sandbox, { filename: fileName });
const core = sandbox.globalThis.SSMcpHybridShadowCore;

assert.ok(core, "shadow core must be exposed for offline tests");
assert.equal(core.version, "0.1.0");
assert.equal(core.mode, "shadow");
assert.equal(core.featureFlag, "MCP_SHADOW_V0_1");
assert.equal(core.protocolVersion, "sellerSpriteMcpHybridProtocol/v1");
assert.equal(core.normalizeAsin(" b0aaaa0001 "), "B0AAAA0001");
assert.equal(core.normalizeAsin("B0BAD"), "");
assert.equal(core.asinFromUrl("https://www.amazon.com/dp/B0AAAA0001?th=1"), "B0AAAA0001");
assert.equal(core.asinFromUrl("https://www.amazon.com/gp/product/B0AAAA0001"), "B0AAAA0001");
assert.equal(core.validateBridgeOrigin("http://127.0.0.1:8766"), "http://127.0.0.1:8766");
assert.throws(() => core.validateBridgeOrigin("https://127.0.0.1:8766"));
assert.throws(() => core.validateBridgeOrigin("http://192.168.1.5:8766"));

const good = core.normalizeLookupResponse(
  {
    schemaVersion: "sellerSpriteMcpHybridResponse/v1",
    ok: true,
    asin: "B0AAAA0001",
    finalAuthority: false,
    results: [
      { usableForShadow: true, usableForFinal: false, fallbackRequired: false },
      { usableForShadow: false, usableForFinal: false, fallbackRequired: true },
    ],
  },
  "B0AAAA0001",
);
assert.deepEqual(
  { ok: good.ok, evidenceCount: good.evidenceCount, usableCount: good.usableCount, fallbackCount: good.fallbackCount },
  { ok: true, evidenceCount: 2, usableCount: 1, fallbackCount: 1 },
);
const denied = core.normalizeLookupResponse(
  { schemaVersion: "sellerSpriteMcpHybridResponse/v1", ok: true, asin: "B0AAAA0002", finalAuthority: false, results: [] },
  "B0AAAA0001",
);
assert.equal(denied.reason, "asin_or_authority_mismatch");
assert.equal(core.budgetState({ monthlyUsed: 100, state: "normal" }), "normal");
assert.equal(core.budgetState({ monthlyUsed: 100, state: "warning" }), "warning");
assert.equal(core.budgetState({ monthlyUsed: 12000, state: "operational_cap" }), "blocked");

const comparison = core.fieldComparison({ price: 19.99, rating: 4.8 }, { price: 19.99, rating: 4.7 });
assert.equal(comparison.length, 2);
assert.equal(comparison.find((row) => row.field === "price").equal, true);
assert.equal(comparison.find((row) => row.field === "rating").equal, false);

assert.equal(source.includes("localStorage"), false, "shadow companion must not use persistent browser storage");
assert.equal(source.includes("finalAuthority = true"), false, "shadow companion must never become final authority");
assert.match(source, /@connect\s+127\.0\.0\.1/);
assert.match(source, /data-ss-mcp-final-authority/);

console.log("SellerSprite MCP Hybrid Shadow core tests: PASS");
