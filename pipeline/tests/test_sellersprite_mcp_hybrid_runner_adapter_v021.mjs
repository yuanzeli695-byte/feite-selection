import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const fileName = "sellersprite_mcp_hybrid_runner_adapter_v0.2.1.user.js";
const source = fs.readFileSync(path.join(root, "scripts", fileName), "utf8");
const sandbox = { console, globalThis: {} };
vm.runInNewContext(source, sandbox, { filename: fileName });
const core = sandbox.globalThis.SSMcpHybridRunnerAdapterCore;

assert.ok(core);
assert.equal(core.detectRunnerVersion("SellerSprite Integrated Runner 0.3.7"), "0.3.7");
assert.equal(core.detectRunnerVersion("卖家精灵一体化选品 0.3.8.2 中文 Excel 版"), "0.3.8.2");
assert.equal(core.detectRunnerVersion("卖家精灵一体化选品 0.3.10 快速闭环候选版"), "0.3.10");
assert.equal(core.detectRunnerVersion("卖家精灵一体化选品 0.3.9"), "");
assert.match(source, /@version\s+0\.2\.1/);
assert.match(source, /ENABLE_MCP_HYBRID_RUNNER_ADAPTER_V0_2_1/);
assert.match(source, /allowedAction:\s*'reorder_only'/);
assert.equal(source.includes("strict-qualified-history"), false);

console.log("SellerSprite MCP Hybrid Runner Adapter 0.2.1 compatibility: PASS");
