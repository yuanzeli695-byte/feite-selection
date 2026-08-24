// ==UserScript==
// @name         Amazon Selection Console Browser Bridge v2
// @namespace    amazon-selection-console
// @version      2.1.6
// @description  Loopback control for Runner 0.3.8.13 deferred JSON and Collector 0.4.6.4.
// @match        https://www.amazon.com/*
// @updateURL    http://127.0.0.1:8788/browser-bridge.user.js
// @downloadURL  http://127.0.0.1:8788/browser-bridge.user.js
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @connect      localhost
// ==/UserScript==

(function () {
  "use strict";

  const API = "http://127.0.0.1:8788";
  const PROTOCOL = "browser-bridge-v2";
  const BRIDGE_VERSION = "2.1.3";
  const SCRIPT_VERSION = "2.1.6";
  const COLLECTOR_VERSION = "0.4.6.4";
  const RUNNER_VERSION = "0.3.8.13";
  const RUNNER_STORAGE_PREFIX = "ssIntegratedRunner:v0.3:";
  const ENABLE_RUNNER_DOM_AUTOMATION = true;
  const ENABLE_LOCALIZED_PANEL_AND_DELIVERY_FIX = true;
  const ENABLE_RUNNER_HISTORY_SKIP_RECONCILIATION = true;
  const ENABLE_RUNNING_BATCH_RECOVERY = true;
  const STORAGE_KEY = "amazon-selection-console-bridge-v2";
  const QUEUE_CONTRACT_SCHEMA = "bridgeQueueContract/v1";
  const STRICT_HISTORY_KEY = `${RUNNER_STORAGE_PREFIX}strict-qualified-history`;
  const state = Object.assign({
    pairingToken: "",
    batchId: "",
    batchToken: "",
    deliveryZip: "10010",
    expectedBatchName: "",
    expectedQueueHash: "",
    queueContract: null,
    auditConfirmed: false,
    startPending: null,
    startVerifiedAt: "",
    connected: false,
    preparing: false,
    lastCommand: "",
    lastSignature: "",
    uploadedHash: "",
  }, loadState());

  function loadState() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}"); } catch (_) { return {}; }
  }

  function saveState() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }

  function request(path, method, body) {
    return new Promise((resolve, reject) => {
      GM_xmlhttpRequest({
        method,
        url: API + path,
        headers: { "Content-Type": "application/json" },
        data: body ? JSON.stringify(body) : undefined,
        timeout: 30000,
        onload: (response) => {
          let payload = {};
          try { payload = JSON.parse(response.responseText || "{}"); } catch (_) { reject(new Error("控制台响应不是 JSON")); return; }
          if (response.status < 200 || response.status >= 300) { reject(new Error(payload.error || `HTTP ${response.status}`)); return; }
          resolve(payload);
        },
        onerror: () => reject(new Error("无法连接 127.0.0.1:8788")),
        ontimeout: () => reject(new Error("控制台连接超时")),
      });
    });
  }

  function setStatus(message, tone) {
    const node = document.querySelector("#asc-v2-status");
    if (!node) return;
    node.textContent = message;
    node.dataset.tone = tone || "neutral";
  }

  function runnerElements() {
    const runnerPanels = document.querySelectorAll("#ss-v3-panel");
    const collectorPanels = document.querySelectorAll("#ss-collector-panel");
    if (runnerPanels.length !== 1) throw new Error(`Runner 面板数量必须为 1，当前 ${runnerPanels.length}`);
    if (collectorPanels.length !== 1) throw new Error(`Collector 面板数量必须为 1，当前 ${collectorPanels.length}`);
    const runner = runnerPanels[0];
    const collector = collectorPanels[0];
    if (!runner.textContent.includes(`卖家精灵一体化选品 ${RUNNER_VERSION}`)) throw new Error(`Runner 版本必须为 ${RUNNER_VERSION}`);
    const collectorText = collector.textContent || "";
    const collectorVersionMatches = ENABLE_LOCALIZED_PANEL_AND_DELIVERY_FIX
      ? collectorText.includes(COLLECTOR_VERSION)
      : collectorText.includes(`SellerSprite Traffic Collector ${COLLECTOR_VERSION}`);
    if (!collectorVersionMatches) throw new Error(`Collector 版本必须为 ${COLLECTOR_VERSION}`);
    return { runner, collector };
  }

  function checkAmazonState(expectedZip) {
    if (document.querySelector("#captchacharacters, form[action*='validateCaptcha']")) throw new Error("Amazon 出现 CAPTCHA，需要人工处理");
    if (document.querySelector("form[name='signIn'], #ap_email")) throw new Error("Amazon 登录已失效，需要人工处理");
    const deliveryNodes = ENABLE_LOCALIZED_PANEL_AND_DELIVERY_FIX
      ? document.querySelectorAll("#glow-ingress-block, #glow-ingress-line1, #glow-ingress-line2")
      : [document.querySelector("#glow-ingress-line2")].filter(Boolean);
    const delivery = Array.from(deliveryNodes).map((node) => (node.textContent || "").trim()).filter(Boolean).join(" ");
    if (!expectedZip || !delivery.includes(expectedZip)) throw new Error(`Amazon 配送地址必须显示美国邮编 ${expectedZip}；当前: ${delivery || "未识别"}`);
    return delivery;
  }

  function fillInput(root, selector, value) {
    const input = root.querySelector(selector);
    if (!input) throw new Error(`Runner 缺少字段 ${selector}`);
    input.value = String(value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function clickButton(root, selector) {
    const button = root.querySelector(selector);
    if (!button) throw new Error(`Runner 缺少按钮 ${selector}`);
    if (button.disabled) throw new Error(`Runner 按钮当前不可用 ${selector}`);
    button.click();
  }

  function wait(milliseconds) {
    return new Promise((resolve) => setTimeout(resolve, milliseconds));
  }

  function runnerBatchStorageKey(queueHash) {
    return `${RUNNER_STORAGE_PREFIX}batch:${queueHash}`;
  }

  function loadRunnerStorageBatch(queueHash) {
    if (!/^[0-9a-f]{8}$/.test(String(queueHash || ""))) return null;
    try {
      const parsed = JSON.parse(localStorage.getItem(runnerBatchStorageKey(queueHash)) || "null");
      return parsed && parsed.queueHash === queueHash && Array.isArray(parsed.results) ? parsed : null;
    } catch (_) {
      return null;
    }
  }

  function selectedRunnerHash() {
    return localStorage.getItem(`${RUNNER_STORAGE_PREFIX}selected`) || "";
  }

  function parseRunnerOutput() {
    const output = document.querySelector("#ss-v3-output");
    if (output?.value.trim()) {
      try {
        const parsed = JSON.parse(output.value);
        if (parsed && Array.isArray(parsed.results)) return parsed;
      } catch (_) {}
    }
    return loadRunnerStorageBatch(selectedRunnerHash());
  }

  function runnerStats(batch) {
    const results = Array.isArray(batch?.results) ? batch.results : [];
    const completed = results.filter(Boolean).length;
    const qualified = results.filter((row) => row && row.qualified === true).length;
    const rejected = results.filter((row) => row && row.qualified === false).length;
    const execution = state.queueContract?.execution || {};
    return {
      status: batch?.status || "waiting",
      batchName: batch?.batchName || "",
      queueHash: batch?.queueHash || "",
      total: Array.isArray(batch?.queue) ? batch.queue.length : 0,
      completed,
      qualifiedCount: qualified,
      rejectedCount: rejected,
      errorCount: Math.max(completed - qualified - rejected, 0),
      rowIndex: Number(batch?.currentIndex || 0),
      asin: batch?.queue?.[Number(batch?.currentIndex || 0)] || "",
      gate: batch?.currentStep || "",
      message: batch?.message || "",
      bridgeVersion: BRIDGE_VERSION,
      commandId: execution.commandId || "",
      executionMode: execution.mode || "",
      runnerVersion: RUNNER_VERSION,
      collectorVersion: COLLECTOR_VERSION,
    };
  }

  function queueMismatch(reason) {
    return new Error(`Runner Generate 后 ASIN 队列与控制台不一致：${reason}`);
  }

  function normalizeQueueForReconciliation(values, label) {
    if (!Array.isArray(values)) throw queueMismatch(`${label}不是数组`);
    const normalized = values.map((asin) => String(asin).trim().toUpperCase());
    if (normalized.some((asin) => !/^B0[A-Z0-9]{8}$/.test(asin))) throw queueMismatch(`${label}包含无效 ASIN`);
    if (new Set(normalized).size !== normalized.length) throw queueMismatch(`${label}包含重复 ASIN`);
    return normalized;
  }

  function sameQueue(left, right) {
    return left.length === right.length && left.every((asin, index) => asin === right[index]);
  }

  async function queueSha256(values) {
    if (!globalThis.crypto?.subtle || typeof TextEncoder !== "function") throw new Error("浏览器不支持队列 SHA-256 校验");
    const queue = normalizeQueueForReconciliation(values, "控制台队列");
    const bytes = new TextEncoder().encode(`${queue.join("\n")}\n`);
    const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  }

  async function assertConsoleQueueDigest(payload) {
    const expectedDigest = String(payload?.queueSha256 || "");
    if (!/^[0-9a-f]{64}$/.test(expectedDigest)) throw queueMismatch("控制台队列 SHA-256 缺失或格式错误");
    const expected = normalizeQueueForReconciliation(payload?.queueAsins, "控制台队列");
    if (!expected.length) throw queueMismatch("控制台队列为空");
    const actualDigest = await queueSha256(expected);
    if (actualDigest !== expectedDigest) throw queueMismatch("控制台队列 SHA-256 与批准队列内容不一致");
    return expected;
  }

  function readStrictHistoryEvidence() {
    let history;
    try {
      history = JSON.parse(localStorage.getItem(STRICT_HISTORY_KEY) || "null");
    } catch (_) {
      throw queueMismatch("Runner 严格历史台账无法解析");
    }
    if (!history || typeof history !== "object" || Array.isArray(history) || history.schemaVersion !== "strictQualifiedHistory/v1") {
      throw queueMismatch("Runner 严格历史台账 schema 无效");
    }
    if (!history.asins || typeof history.asins !== "object" || Array.isArray(history.asins)) {
      throw queueMismatch("Runner 严格历史台账 ASIN 索引无效");
    }
    for (const [asin, record] of Object.entries(history.asins)) {
      if (!/^B0[A-Z0-9]{8}$/.test(asin)) throw queueMismatch("Runner 严格历史台账包含无效 ASIN 键");
      if (!record || typeof record !== "object" || Array.isArray(record) || !Object.keys(record).length) {
        throw queueMismatch(`Runner 严格历史台账 ${asin} 记录无效`);
      }
    }
    return { asins: history.asins, count: Object.keys(history.asins).length };
  }

  function validateHistoryEvidence(batch, skipped, baselineRegistryCount = null) {
    if (!Number.isInteger(batch?.historySkippedCount) || batch.historySkippedCount !== skipped.length) {
      throw queueMismatch("Runner 历史跳过计数与清单不一致");
    }
    const batchRegistryCount = batch?.historyRegistryCount;
    if (!Number.isInteger(batchRegistryCount) || batchRegistryCount < 0 || batchRegistryCount < skipped.length) {
      throw queueMismatch("Runner 历史台账计数无效");
    }
    const registry = readStrictHistoryEvidence();
    if (baselineRegistryCount == null) {
      if (registry.count < batchRegistryCount) throw queueMismatch("Runner 生成批次的历史台账相对当前台账发生回退");
    } else {
      if (!Number.isInteger(baselineRegistryCount) || baselineRegistryCount < 0) throw queueMismatch("Bridge 历史台账基线无效");
      if (batchRegistryCount < baselineRegistryCount || registry.count < batchRegistryCount) {
        throw queueMismatch("Runner 严格历史台账相对生成时发生回退");
      }
    }
    for (const asin of skipped) {
      const record = registry.asins[asin];
      if (!record || typeof record !== "object" || Array.isArray(record) || !Object.keys(record).length) {
        throw queueMismatch(`历史跳过 ASIN ${asin} 缺少严格合格记录`);
      }
    }
    return { batchRegistryCount, currentRegistryCount: registry.count };
  }

  function reconcileGeneratedQueue(batch, payload, baselineRegistryCount = null) {
    const expected = normalizeQueueForReconciliation(payload?.queueAsins, "控制台队列");
    const actual = normalizeQueueForReconciliation(batch?.queue, "Runner 队列");
    if (!expected.length) throw queueMismatch("控制台队列为空");
    if (!actual.length) throw queueMismatch("Runner 实际待采集队列为空");
    const consoleQueueSha256 = String(payload?.queueSha256 || "");
    if (!/^[0-9a-f]{64}$/.test(consoleQueueSha256)) throw queueMismatch("控制台队列 SHA-256 缺失或格式错误");
    const rawSkipped = batch?.historySkippedAsins;
    if (rawSkipped != null && !Array.isArray(rawSkipped)) throw queueMismatch("Runner 历史跳过清单不是数组");
    const skipped = normalizeQueueForReconciliation(rawSkipped || [], "Runner 历史跳过清单");
    const historyEvidence = validateHistoryEvidence(batch, skipped, baselineRegistryCount);

    if (!ENABLE_RUNNER_HISTORY_SKIP_RECONCILIATION || !skipped.length) {
      if (!sameQueue(actual, expected)) throw queueMismatch("实际队列不是控制台原队列");
      return {
        mode: "exact",
        approvedQueueCount: expected.length,
        runnerQueueCount: actual.length,
        runnerQueueAsins: actual,
        historySkippedCount: 0,
        historySkippedAsins: [],
        historyRegistryCount: historyEvidence.batchRegistryCount,
        currentHistoryRegistryCount: historyEvidence.currentRegistryCount,
        consoleQueueSha256,
      };
    }

    const expectedSet = new Set(expected);
    if (skipped.some((asin) => !expectedSet.has(asin))) throw queueMismatch("历史跳过清单包含控制台未批准 ASIN");
    const skippedSet = new Set(skipped);
    const expectedSkipped = expected.filter((asin) => skippedSet.has(asin));
    if (!sameQueue(skipped, expectedSkipped)) throw queueMismatch("历史跳过清单顺序与控制台队列不一致");
    const expectedActual = expected.filter((asin) => !skippedSet.has(asin));
    if (!sameQueue(actual, expectedActual)) throw queueMismatch("移除明确历史命中后仍无法重构控制台队列");

    return {
      mode: "runner_history_skip",
      approvedQueueCount: expected.length,
      runnerQueueCount: actual.length,
      runnerQueueAsins: actual,
      historySkippedCount: skipped.length,
      historySkippedAsins: skipped,
      historyRegistryCount: historyEvidence.batchRegistryCount,
      currentHistoryRegistryCount: historyEvidence.currentRegistryCount,
      consoleQueueSha256,
    };
  }

  function assertGeneratedBatch(batch, payload, baselineRegistryCount = null) {
    if (!batch || batch.batchName !== payload.batchName || !/^[0-9a-f]{8}$/.test(String(batch.queueHash || ""))) {
      throw new Error("Runner Generate 后批次校验失败");
    }
    return { ...batch, bridgeQueueReconciliation: reconcileGeneratedQueue(batch, payload, baselineRegistryCount) };
  }

  function batchFingerprint(batch) {
    if (!batch) return "";
    return JSON.stringify([
      batch.queueHash || "", batch.batchName || "", batch.generatedAt || "", batch.createdAt || "", batch.updatedAt || "",
      batch.status || "", batch.currentIndex, batch.queue || [], batch.historySkippedAsins || [], batch.results || [],
    ]);
  }

  function matchingRunnerOptions(runner, batchName) {
    const picker = runner.querySelector("#ss-v3-picker");
    if (!picker) throw new Error("Runner 缺少批次选择器 #ss-v3-picker");
    const prefix = `${batchName} (`;
    return { picker, options: Array.from(picker.options || []).filter((item) => /^[0-9a-f]{8}$/.test(String(item.value || "")) && String(item.textContent || "").trim().startsWith(prefix)) };
  }

  function snapshotRunnerBatchFingerprints(runner, payload) {
    const { options } = matchingRunnerOptions(runner, payload.batchName);
    return options.map((option) => batchFingerprint(loadRunnerStorageBatch(String(option.value)))).filter(Boolean);
  }

  function assertFreshGeneratedBatch(batch, payload, generationContext) {
    const verified = assertGeneratedBatch(batch, payload);
    if (verified.status !== "idle" || verified.currentIndex !== 0) throw new Error("Runner 新批次必须处于待开始状态");
    if (!Array.isArray(verified.results) || verified.results.length !== verified.queue.length || verified.results.some((row) => row !== null)) {
      throw new Error("Runner 新批次包含旧结果或结果槽位异常");
    }
    if (Number(verified.qualifiedCount || 0) !== 0 || Number(verified.rejectedCount || 0) !== 0) {
      throw new Error("Runner 新批次统计不是空状态");
    }
    const generatedAtMs = Date.parse(String(verified.generatedAt || ""));
    const createdAtMs = Date.parse(String(verified.createdAt || ""));
    const updatedAtMs = Date.parse(String(verified.updatedAt || ""));
    if (![generatedAtMs, createdAtMs, updatedAtMs].every(Number.isFinite)) throw new Error("Runner 新批次时间戳无效");
    if (generatedAtMs < generationContext.startedAtMs || createdAtMs < generationContext.startedAtMs || updatedAtMs < generationContext.startedAtMs) {
      throw new Error("Runner Generate 未产生本次请求的新批次");
    }
    if ((generationContext.beforeFingerprints || []).includes(batchFingerprint(verified))) {
      throw new Error("Runner Generate 仍是点击前的旧批次");
    }
    return verified;
  }

  function selectRunnerBatchByHash(runner, payload, queueHash) {
    const { picker, options } = matchingRunnerOptions(runner, payload.batchName);
    const matches = options.filter((option) => option.value === queueHash);
    if (matches.length !== 1) throw new Error("Runner 新批次选择项不唯一");
    picker.value = queueHash;
    picker.dispatchEvent(new Event("change", { bubbles: true }));
    if (picker.value !== queueHash || selectedRunnerHash() !== queueHash) throw new Error("Runner 未选中本次新生成批次");
    return queueHash;
  }

  async function waitForFreshGeneratedBatch(runner, payload, generationContext, timeout = 10000) {
    const deadline = Date.now() + timeout;
    let lastError = null;
    while (Date.now() < deadline) {
      const candidates = [];
      const seen = new Set();
      for (const option of matchingRunnerOptions(runner, payload.batchName).options) {
        if (seen.has(option.value)) continue;
        seen.add(option.value);
        try {
          candidates.push(assertFreshGeneratedBatch(loadRunnerStorageBatch(option.value), payload, generationContext));
        } catch (error) {
          lastError = error;
        }
      }
      if (candidates.length > 1) throw new Error("Runner Generate 后出现多个可接受的新批次");
      if (candidates.length === 1) {
        selectRunnerBatchByHash(runner, payload, candidates[0].queueHash);
        return assertFreshGeneratedBatch(loadRunnerStorageBatch(candidates[0].queueHash), payload, generationContext);
      }
      await wait(100);
    }
    throw lastError || new Error("Runner Generate 后批次校验失败");
  }

  function buildQueueContract(command, payload, generated) {
    const reconciliation = generated.bridgeQueueReconciliation;
    return {
      schemaVersion: QUEUE_CONTRACT_SCHEMA,
      batchId: command.batchId,
      batchName: generated.batchName,
      runnerQueueHash: generated.queueHash,
      approvedQueueAsins: normalizeQueueForReconciliation(payload.queueAsins, "控制台队列"),
      approvedQueueSha256: reconciliation.consoleQueueSha256,
      runnerQueueAsins: reconciliation.runnerQueueAsins.slice(),
      historySkippedAsins: reconciliation.historySkippedAsins.slice(),
      historyRegistryCountAtGenerate: reconciliation.historyRegistryCount,
      generatedAt: generated.generatedAt,
      createdAt: generated.createdAt,
      auditEventId: `${command.batchId}:${generated.queueHash}:${reconciliation.consoleQueueSha256}`,
      execution: {
        mode: "generated_for_command",
        commandId: command.id,
        recordedAt: new Date().toISOString(),
      },
    };
  }

  async function validateQueueContract(raw = state.queueContract) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw) || raw.schemaVersion !== QUEUE_CONTRACT_SCHEMA) {
      throw new Error("旧 Bridge 连接缺少批准队列契约；请从控制台重新开始 Runner");
    }
    if (!state.batchId || raw.batchId !== state.batchId || !raw.batchName || !/^[0-9a-f]{8}$/.test(String(raw.runnerQueueHash || ""))) {
      throw new Error("Bridge 批次契约身份无效");
    }
    const approved = await assertConsoleQueueDigest({ queueAsins: raw.approvedQueueAsins, queueSha256: raw.approvedQueueSha256 });
    const runnerQueue = normalizeQueueForReconciliation(raw.runnerQueueAsins, "Bridge Runner 队列契约");
    const skipped = normalizeQueueForReconciliation(raw.historySkippedAsins, "Bridge 历史跳过契约");
    if (!runnerQueue.length) throw queueMismatch("Bridge Runner 队列契约为空");
    const skippedSet = new Set(skipped);
    if (!sameQueue(skipped, approved.filter((asin) => skippedSet.has(asin)))) throw queueMismatch("Bridge 历史跳过契约顺序无效");
    if (!sameQueue(runnerQueue, approved.filter((asin) => !skippedSet.has(asin)))) throw queueMismatch("Bridge 持久化队列契约无法重构批准队列");
    if (!Number.isInteger(raw.historyRegistryCountAtGenerate) || raw.historyRegistryCountAtGenerate < skipped.length) {
      throw queueMismatch("Bridge 历史台账生成基线无效");
    }
    if (![raw.generatedAt, raw.createdAt].every((value) => Number.isFinite(Date.parse(String(value || ""))))) {
      throw new Error("Bridge 批次契约时间戳无效");
    }
    const execution = raw.execution;
    if (!execution || !["generated_for_command", "adopted_existing"].includes(execution.mode)
      || !String(execution.commandId || "").trim()
      || !Number.isFinite(Date.parse(String(execution.recordedAt || "")))) {
      throw new Error("Bridge 批次契约缺少可审计执行来源");
    }
    return { ...raw, approvedQueueAsins: approved, runnerQueueAsins: runnerQueue, historySkippedAsins: skipped };
  }

  function activeRunnerBatch(batch) {
    const contract = state.queueContract;
    return Boolean(batch && contract && batch.batchName === contract.batchName && batch.queueHash === contract.runnerQueueHash);
  }

  function assertBatchMatchesContract(batch, contract, allowedStatuses = null) {
    if (!batch || batch.batchName !== contract.batchName || batch.queueHash !== contract.runnerQueueHash) {
      throw new Error(`Runner 当前不是控制台批次 ${contract.batchName}`);
    }
    const verified = assertGeneratedBatch(batch, {
      batchName: contract.batchName,
      queueAsins: contract.approvedQueueAsins,
      queueSha256: contract.approvedQueueSha256,
    }, contract.historyRegistryCountAtGenerate);
    const reconciliation = verified.bridgeQueueReconciliation;
    if (!sameQueue(reconciliation.runnerQueueAsins, contract.runnerQueueAsins)
      || !sameQueue(reconciliation.historySkippedAsins, contract.historySkippedAsins)
      || verified.generatedAt !== contract.generatedAt
      || verified.createdAt !== contract.createdAt) {
      throw queueMismatch("Runner 当前批次已偏离持久化批准队列契约");
    }
    if (allowedStatuses && !allowedStatuses.includes(verified.status)) {
      throw new Error(`Runner 当前状态 ${verified.status || "未知"} 不允许此操作`);
    }
    return verified;
  }

  async function requireActiveRunnerBatch(allowedStatuses = null) {
    const contract = await validateQueueContract();
    const batch = loadRunnerStorageBatch(contract.runnerQueueHash);
    return assertBatchMatchesContract(batch, contract, allowedStatuses);
  }

  function assertStartedBatchWithContract(contract) {
    const batch = assertBatchMatchesContract(loadRunnerStorageBatch(contract.runnerQueueHash), contract, ["running"]);
    if (batch.currentIndex !== 0 || batch.queue?.[0] !== contract.runnerQueueAsins[0]) {
      throw new Error("Runner Start 后没有停留在本批第一个 ASIN");
    }
    return batch;
  }

  async function assertStartedBatch() {
    return assertStartedBatchWithContract(await validateQueueContract());
  }

  function assertRecoverableStartedBatch(contract) {
    const batch = assertBatchMatchesContract(
      loadRunnerStorageBatch(contract.runnerQueueHash),
      contract,
      ["running", "paused", "done"],
    );
    validateCompletedResults(batch, contract);
    const completed = batch.results.filter(Boolean).length;
    if (!Number.isInteger(batch.currentIndex) || batch.currentIndex !== completed) {
      throw new Error("Runner 恢复时当前行与已保存结果前缀不一致");
    }
    return batch;
  }

  async function registerBatch(current) {
    const contract = await validateQueueContract();
    const verified = assertBatchMatchesContract(current, contract);
    await request("/bridge/register", "POST", {
      batchId: state.batchId,
      token: state.batchToken,
      protocol: PROTOCOL,
      bridgeVersion: BRIDGE_VERSION,
      scriptVersion: SCRIPT_VERSION,
      collectorVersion: COLLECTOR_VERSION,
      runnerVersion: RUNNER_VERSION,
      batchName: verified.batchName,
      queueHash: verified.queueHash,
      commandId: contract.execution.commandId,
      executionMode: contract.execution.mode,
    });
    if (!state.auditConfirmed) {
      const reconciliation = verified.bridgeQueueReconciliation;
      await request("/bridge/event", "POST", {
        batchId: state.batchId,
        token: state.batchToken,
        protocol: PROTOCOL,
        bridgeVersion: BRIDGE_VERSION,
        batchName: verified.batchName,
        queueHash: verified.queueHash,
        eventType: "runner_queue_reconciled",
        auditEventId: contract.auditEventId,
        commandId: contract.execution.commandId,
        message: reconciliation.historySkippedCount
          ? `Runner 历史去重已核验：${reconciliation.runnerQueueCount} 个待采集，${reconciliation.historySkippedCount} 个严格历史命中`
          : `Runner 队列已逐项核验：${reconciliation.runnerQueueCount} 个待采集`,
        scriptVersion: SCRIPT_VERSION,
        executionMode: contract.execution.mode,
        ...reconciliation,
      });
      state.auditConfirmed = true;
      saveState();
    }
    return verified;
  }

  async function adoptExistingRunnerBatch(command, payload) {
    if (!ENABLE_RUNNING_BATCH_RECOVERY) return null;
    const selectedHash = selectedRunnerHash();
    const existing = loadRunnerStorageBatch(selectedHash);
    if (existing?.batchName === payload.batchName && existing.status === "paused") {
      throw new Error("Runner 当前批次已暂停；请使用“继续”，不能把暂停状态当作新的启动成功");
    }
    if (!existing || existing.batchName !== payload.batchName || !["running", "done"].includes(existing.status)) return null;
    const verified = assertGeneratedBatch(existing, payload);
    state.queueContract = buildQueueContract(command, payload, verified);
    state.queueContract.execution = {
      mode: "adopted_existing",
      commandId: command.id,
      recordedAt: new Date().toISOString(),
    };
    state.expectedQueueHash = verified.queueHash;
    state.auditConfirmed = false;
    saveState();
    await registerBatch(verified);
    const contract = await validateQueueContract();
    const recovered = assertRecoverableStartedBatch(contract);
    state.startPending = {
      ...(state.startPending || {}),
      commandId: command.id,
      batchId: command.batchId,
      phase: "running_verified",
      adoptedAt: new Date().toISOString(),
    };
    state.connected = true;
    state.preparing = false;
    state.startVerifiedAt = new Date().toISOString();
    saveState();
    if (recovered.status === "done") await uploadMergedJson();
    setStatus(`已安全接管 ${payload.batchName} · ${recovered.results.filter(Boolean).length}/${recovered.queue.length}`, "good");
    return recovered;
  }

  async function prepareAndStart(command) {
    if (!ENABLE_RUNNER_DOM_AUTOMATION) throw new Error("Runner DOM 自动化功能未启用");
    const rawPayload = command.payload || {};
    const approvedQueue = await assertConsoleQueueDigest(rawPayload);
    const payload = { ...rawPayload, queueAsins: approvedQueue };
    checkAmazonState(payload.deliveryZip || "10010");
    const { runner } = runnerElements();
    state.batchId = command.batchId;
    state.batchToken = command.batchToken;
    state.deliveryZip = payload.deliveryZip || state.deliveryZip || "10010";
    state.expectedBatchName = payload.batchName || "";
    state.expectedQueueHash = "";
    state.queueContract = null;
    state.auditConfirmed = false;
    state.startPending = {
      ...(state.startPending || {}),
      commandId: command.id,
      batchId: command.batchId,
      phase: "preparing",
      requestedAt: state.startPending?.requestedAt || new Date().toISOString(),
    };
    state.startVerifiedAt = "";
    state.connected = false;
    state.preparing = true;
    state.uploadedHash = "";
    state.lastSignature = "";
    saveState();
    if (await adoptExistingRunnerBatch(command, payload)) return;
    fillInput(runner, "#ss-v3-name", payload.batchName);
    fillInput(runner, "#ss-v3-operator", payload.operator);
    fillInput(runner, "#ss-v3-target", payload.targetQualified);
    fillInput(runner, "#ss-v3-remaining", payload.targetQualified);
    fillInput(runner, "#ss-v3-queue", payload.queueAsins.join("\n"));
    const beforeFingerprints = snapshotRunnerBatchFingerprints(runner, payload);
    const generationContext = { startedAtMs: Date.now(), beforeFingerprints };
    clickButton(runner, "#ss-v3-generate");
    const generated = await waitForFreshGeneratedBatch(runner, payload, generationContext);
    state.queueContract = buildQueueContract(command, payload, generated);
    state.expectedQueueHash = generated.queueHash;
    saveState();
    await registerBatch(generated);
    const contract = await validateQueueContract();
    state.startPending = { ...state.startPending, phase: "start_requested" };
    saveState();
    clickButton(runner, "#ss-v3-start");
    assertStartedBatchWithContract(contract);
    state.connected = true;
    state.preparing = false;
    state.startPending = { ...state.startPending, phase: "running_verified" };
    state.startVerifiedAt = new Date().toISOString();
    saveState();
    setStatus(`已启动 ${payload.batchName}`, "good");
  }

  async function executeCommand(command) {
    if (!command) return;
    if (command.id === state.lastCommand) {
      const replayPreparingStart = command.action === "start"
        && state.startPending?.commandId === command.id
        && state.startPending?.phase !== "running_verified";
      if (command.action === "start" && state.startPending?.commandId === command.id && !replayPreparingStart) {
        try {
          const contract = await validateQueueContract();
          const recovered = assertRecoverableStartedBatch(contract);
          await registerBatch(recovered);
          state.connected = true;
          state.preparing = false;
          state.startVerifiedAt = state.startVerifiedAt || new Date().toISOString();
          saveState();
          if (recovered.status === "done") await uploadMergedJson();
          await request("/bridge/control/ack", "POST", { pairingToken: state.pairingToken, batchId: command.batchId, commandId: command.id, status: "accepted", message: "Runner 启动状态已验证" });
          state.startPending = null;
          saveState();
        } catch (error) {
          setStatus(`Runner 已启动，控制台回执待恢复：${error.message}`, "bad");
        }
        return;
      }
      if (!replayPreparingStart) return;
    }
    if (command.id !== state.lastCommand) state.lastCommand = command.id;
    if (command.action === "start") {
      state.startPending = {
        commandId: command.id,
        batchId: command.batchId,
        phase: "preparing",
        requestedAt: new Date().toISOString(),
      };
    }
    saveState();
    try {
      if (command.action === "start") {
        await prepareAndStart(command);
      } else {
        if (!state.connected || command.batchId !== state.batchId) throw new Error("控制命令与当前 Bridge 批次不一致");
        await requireActiveRunnerBatch();
        const { runner } = runnerElements();
        const selector = {
          pause: "#ss-v3-pause",
          resume: "#ss-v3-resume",
          stop_after_current: "#ss-v3-stop-row",
          export: "#ss-v3-copy",
        }[command.action];
        if (!selector) throw new Error(`不支持命令 ${command.action}`);
        clickButton(runner, selector);
        if (command.action === "export") await uploadMergedJson();
      }
    } catch (error) {
      if (command.action === "start") {
        state.connected = false;
        state.startPending = null;
      }
      state.preparing = false;
      saveState();
      setStatus(error.message, "bad");
      await request("/bridge/control/ack", "POST", { pairingToken: state.pairingToken, batchId: command.batchId, commandId: command.id, status: "failed", message: error.message }).catch(() => {});
      return;
    }
    try {
      await request("/bridge/control/ack", "POST", { pairingToken: state.pairingToken, batchId: command.batchId, commandId: command.id, status: "accepted", message: "Runner 已执行命令" });
      if (command.action === "start" && state.startPending?.commandId === command.id) {
        state.startPending = null;
        saveState();
      }
    } catch (error) {
      setStatus(`Runner 已执行；控制台回执待自动恢复：${error.message}`, "bad");
    }
  }

  function validateCompletedResults(batch, contract) {
    if (!Array.isArray(batch.results) || batch.results.length !== contract.runnerQueueAsins.length) {
      throw new Error("Runner 完整批次结果槽位与队列长度不一致");
    }
    let reachedEmpty = false;
    batch.results.forEach((row, index) => {
      if (row == null) {
        reachedEmpty = true;
        return;
      }
      if (reachedEmpty || !row || typeof row !== "object") throw new Error("Runner 结果不是按队列前缀连续写入");
      const asin = String(row.targetAsin || row.asin || "").trim().toUpperCase();
      if (asin !== contract.runnerQueueAsins[index]) throw new Error("Runner 结果 ASIN 顺序与批准队列契约不一致");
    });
  }

  async function uploadMergedJson() {
    if (!state.connected) return;
    const batch = await requireActiveRunnerBatch(["done"]);
    const contract = await validateQueueContract();
    validateCompletedResults(batch, contract);
    const signature = `${batch.queueHash || ""}:${(batch.results || []).filter(Boolean).length}:${batch.updatedAt || ""}`;
    if (state.uploadedHash === signature) return;
    const mergedJson = {
      ...batch,
      results: batch.results.filter(Boolean),
      bridgeExecution: contract.execution,
      runnerVersion: RUNNER_VERSION,
      collectorVersion: COLLECTOR_VERSION,
    };
    await request("/bridge/merged-json", "POST", {
      batchId: state.batchId,
      token: state.batchToken,
      protocol: PROTOCOL,
      bridgeVersion: BRIDGE_VERSION,
      scriptVersion: SCRIPT_VERSION,
      batchName: batch.batchName,
      queueHash: batch.queueHash,
      commandId: contract.execution.commandId,
      executionMode: contract.execution.mode,
      mergedJson,
    });
    state.uploadedHash = signature;
    saveState();
    setStatus("Runner 已完成，合并 JSON 已回传", "good");
  }

  let heartbeatBusy = false;

  async function heartbeat() {
    if (heartbeatBusy || !state.connected || !state.batchId || !state.batchToken) return;
    heartbeatBusy = true;
    let batch;
    try {
      batch = await requireActiveRunnerBatch();
    } catch (error) {
      state.connected = false;
      saveState();
      const contract = state.queueContract || {};
      const execution = contract.execution || {};
      await request("/bridge/event", "POST", {
        batchId: state.batchId,
        token: state.batchToken,
        protocol: PROTOCOL,
        bridgeVersion: BRIDGE_VERSION,
        scriptVersion: SCRIPT_VERSION,
        batchName: contract.batchName || state.expectedBatchName,
        queueHash: contract.runnerQueueHash || state.expectedQueueHash,
        commandId: execution.commandId || "",
        executionMode: execution.mode || "",
        eventType: "needs_attention",
        message: `Bridge 队列契约复核失败：${error.message}`,
      }).catch(() => {});
      setStatus(error.message, "bad");
      heartbeatBusy = false;
      return;
    }
    const stats = runnerStats(batch);
    try {
      checkAmazonState(state.deliveryZip || "10010");
      await request("/bridge/heartbeat", "POST", { batchId: state.batchId, token: state.batchToken, protocol: PROTOCOL, scriptVersion: SCRIPT_VERSION, ...stats, stats });
      const signature = JSON.stringify([stats.status, stats.completed, stats.qualifiedCount, stats.rejectedCount, stats.asin, stats.gate, stats.message]);
      if (signature !== state.lastSignature) {
        const eventType = stats.status === "done" ? "done" : (stats.completed ? "row_committed" : "runner_state");
        await request("/bridge/event", "POST", { batchId: state.batchId, token: state.batchToken, protocol: PROTOCOL, scriptVersion: SCRIPT_VERSION, eventType, ...stats });
        state.lastSignature = signature;
        saveState();
      }
      if (stats.status === "done") await uploadMergedJson();
      if (stats.status !== "done") setStatus(`已连接 · ${stats.completed}/${stats.total} · ${stats.asin || "等待"}`, "good");
    } catch (error) {
      const attention = /CAPTCHA|登录|配送地址/.test(error.message);
      if (attention) {
        await request("/bridge/event", "POST", { batchId: state.batchId, token: state.batchToken, protocol: PROTOCOL, scriptVersion: SCRIPT_VERSION, eventType: "needs_attention", ...stats, message: error.message }).catch(() => {});
      }
      setStatus(error.message, "bad");
    } finally {
      heartbeatBusy = false;
    }
  }

  async function pollControl() {
    if (!state.pairingToken) return;
    try {
      const payload = await request("/bridge/control/poll", "POST", { pairingToken: state.pairingToken, protocol: PROTOCOL, bridgeVersion: BRIDGE_VERSION, scriptVersion: SCRIPT_VERSION });
      for (const command of payload.commands || []) await executeCommand(command);
      if (!state.connected) setStatus("已配对，等待控制台命令", "good");
    } catch (error) {
      setStatus(error.message, "bad");
    }
  }

  function pair() {
    const value = document.querySelector("#asc-v2-pairing").value.trim();
    if (!value) return setStatus("请输入控制台配对码", "bad");
    state.pairingToken = value;
    state.connected = false;
    state.preparing = false;
    state.batchId = "";
    state.batchToken = "";
    state.expectedBatchName = "";
    state.expectedQueueHash = "";
    state.queueContract = null;
    state.auditConfirmed = false;
    state.startPending = null;
    state.startVerifiedAt = "";
    state.lastCommand = "";
    saveState();
    setStatus("正在配对", "neutral");
    pollControl();
  }

  function mount() {
    if (document.querySelector("#asc-v2-panel")) return;
    const panel = document.createElement("aside");
    panel.id = "asc-v2-panel";
    panel.className = "notranslate";
    panel.innerHTML = `<strong>Selection Console Bridge ${BRIDGE_VERSION} / script ${SCRIPT_VERSION}</strong><span id="asc-v2-status" data-tone="neutral">未配对</span><input id="asc-v2-pairing" type="password" placeholder="控制台配对码"><button id="asc-v2-pair">配对</button><small>Collector ${COLLECTOR_VERSION} · Runner ${RUNNER_VERSION}</small>`;
    Object.assign(panel.style, { position: "fixed", right: "12px", bottom: "12px", zIndex: 2147483647, width: "268px", padding: "12px", background: "#fff", color: "#161b1a", border: "1px solid #9ca3af", borderRadius: "6px", boxShadow: "0 8px 24px #0003", font: "12px Arial", display: "grid", gap: "7px" });
    document.body.appendChild(panel);
    const input = panel.querySelector("#asc-v2-pairing");
    input.value = state.pairingToken || "";
    input.style.cssText = "width:100%;padding:6px;border:1px solid #aaa;border-radius:3px";
    const button = panel.querySelector("#asc-v2-pair");
    button.style.cssText = "padding:6px;border:1px solid #0b6b63;border-radius:3px;background:#0b6b63;color:#fff;cursor:pointer";
    button.addEventListener("click", pair);
    if (state.pairingToken) setStatus("已配对，等待控制台命令", "good");
  }

  async function restoreConnection() {
    if (!state.pairingToken || !state.batchId || !state.batchToken) return;
    if (!state.connected && !state.startPending) return;
    try {
      runnerElements();
      checkAmazonState(state.deliveryZip || "10010");
      const contract = await validateQueueContract();
      if (!state.auditConfirmed) throw new Error("Bridge 队列对账审计未确认，拒绝恢复连接");
      const allowedStatuses = ["running", "paused", "done"];
      const current = assertBatchMatchesContract(loadRunnerStorageBatch(contract.runnerQueueHash), contract, allowedStatuses);
      const recovered = state.startPending ? assertRecoverableStartedBatch(contract) : current;
      await registerBatch(current);
      state.connected = true;
      state.preparing = false;
      state.startVerifiedAt = state.startVerifiedAt || new Date().toISOString();
      saveState();
      if (recovered.status === "done") await uploadMergedJson();
      if (state.startPending) {
        const pending = state.startPending;
        await request("/bridge/control/ack", "POST", {
          pairingToken: state.pairingToken,
          batchId: pending.batchId,
          commandId: pending.commandId,
          status: "accepted",
          message: "Runner 启动状态已在页面恢复后验证",
        });
        state.startPending = null;
        saveState();
      }
      setStatus("已恢复控制台连接", "good");
    } catch (error) {
      state.connected = false;
      saveState();
      setStatus(error.message, "bad");
    }
  }

  mount();
  restoreConnection();
  setInterval(pollControl, 2500);
  setInterval(heartbeat, 3000);
})();
