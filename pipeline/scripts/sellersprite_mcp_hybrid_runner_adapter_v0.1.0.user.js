// ==UserScript==
// @name         SellerSprite MCP Hybrid Runner Adapter 0.1.0
// @namespace    amazon-products
// @version      0.1.0
// @description  Reorder a draft Runner queue through MCP Hybrid Assist without creating or starting a batch.
// @match        https://www.amazon.com/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  var VERSION = '0.1.0';
  var FEATURE_FLAG = 'ENABLE_MCP_HYBRID_RUNNER_ADAPTER_V0_1';
  var EVENT_PROTOCOL = 'runner-adapter/v1';
  var REQUIRED_ASSIST_VERSION = '0.2.1';
  var ENABLE_KEY = 'ss-mcp-hybrid-runner-adapter-enabled';
  var CONTROL_ID = 'ss-mcp-runner-adapter-controls';
  var REQUEST_EVENT = 'ss-mcp-hybrid:rank-request';
  var RANKED_EVENT = 'ss-mcp-hybrid:queue-ranked';
  var ERROR_EVENT = 'ss-mcp-hybrid:rank-error';
  var APPLIED_EVENT = 'ss-mcp-hybrid:runner-queue-applied';
  var ADAPTER_ERROR_EVENT = 'ss-mcp-hybrid:runner-queue-error';
  var RESPONSE_TIMEOUT_MS = 15000;
  var ASIN_RE = /^B0[A-Z0-9]{8}$/;
  var SUPPORTED_RUNNERS = Object.freeze({
    '0.3.7': /SellerSprite Integrated Runner\s+0\.3\.7\b/,
    '0.3.8.2': /卖家精灵一体化选品\s+0\.3\.8\.2\b/,
  });

  function adapterError(code, message) {
    var error = new Error(message);
    error.code = code;
    return error;
  }

  function normalizeAsin(value) {
    var text = String(value || '').trim().toUpperCase();
    return ASIN_RE.test(text) ? text : '';
  }

  function parseQueue(value) {
    var tokens = String(value || '').trim().split(/\s+/).filter(Boolean);
    if (!tokens.length) throw adapterError('queue_empty', 'Runner 队列为空。');
    var asins = tokens.map(normalizeAsin);
    if (asins.some(function (asin) { return !asin; })) {
      throw adapterError('queue_invalid', 'Runner 队列包含无效 ASIN，未发送重排请求。');
    }
    return asins;
  }

  function sameArray(left, right) {
    return Array.isArray(left) && Array.isArray(right)
      && left.length === right.length
      && left.every(function (value, index) { return value === right[index]; });
  }

  function multisetSignature(asins) {
    return (asins || []).slice().sort().join('|');
  }

  function fnv1a(value) {
    var hash = 0x811c9dc5;
    var text = String(value || '');
    for (var index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 0x01000193);
    }
    return ('00000000' + (hash >>> 0).toString(16)).slice(-8);
  }

  function detectRunnerVersion(title) {
    var text = String(title || '').replace(/\s+/g, ' ').trim();
    var versions = Object.keys(SUPPORTED_RUNNERS);
    for (var index = 0; index < versions.length; index += 1) {
      if (SUPPORTED_RUNNERS[versions[index]].test(text)) return versions[index];
    }
    return '';
  }

  function validateRankedResponse(detail, expected) {
    if (!detail || detail.eventProtocol !== EVENT_PROTOCOL) {
      throw adapterError('response_protocol', 'Assist 响应协议不匹配。');
    }
    if (detail.requestId !== expected.requestId) {
      throw adapterError('response_stale', '收到不属于本次请求的 Assist 响应。');
    }
    if (detail.finalAuthority !== false || detail.allowedAction !== 'reorder_only') {
      throw adapterError('response_authority', 'Assist 响应越过了仅重排边界。');
    }
    if (detail.mode !== expected.mode || detail.multisetUnchanged !== true) {
      throw adapterError('response_contract', 'Assist 响应未声明相同模式和相同候选集合。');
    }
    if (!sameArray(detail.original, expected.asins)) {
      throw adapterError('response_original', 'Assist 响应的原始队列与当前请求不一致。');
    }
    if (!Array.isArray(detail.ranked) || detail.ranked.length !== expected.asins.length) {
      throw adapterError('response_count', 'Assist 响应的 ASIN 数量发生变化。');
    }
    var ranked = detail.ranked.map(normalizeAsin);
    if (ranked.some(function (asin) { return !asin; })) {
      throw adapterError('response_invalid_asin', 'Assist 响应包含无效 ASIN。');
    }
    if (multisetSignature(ranked) !== multisetSignature(expected.asins)) {
      throw adapterError('response_multiset', 'Assist 响应增删了 ASIN 或改变了重复次数。');
    }
    return ranked;
  }

  function applyRankedQueue(queue, picker, snapshot, detail) {
    if (!queue || !picker || String(picker.value || '') !== '') {
      throw adapterError('runner_not_draft', 'Runner 已选择或生成批次，拒绝覆盖队列。');
    }
    if (String(queue.value || '') !== snapshot.text) {
      throw adapterError('queue_changed', '等待期间 Runner 队列已变化，未覆盖新内容。');
    }
    var ranked = validateRankedResponse(detail, snapshot);
    var rankedText = ranked.join('\n');
    try {
      queue.value = rankedText;
      queue.dispatchEvent(new Event('input', { bubbles: true }));
      queue.dispatchEvent(new Event('change', { bubbles: true }));
      if (queue.value !== rankedText) throw adapterError('queue_event_changed', 'Runner 事件处理改变了重排结果。');
    } catch (error) {
      queue.value = snapshot.text;
      throw error;
    }
    return ranked;
  }

  globalThis.SSMcpHybridRunnerAdapterCore = Object.freeze({
    version: VERSION,
    featureFlag: FEATURE_FLAG,
    eventProtocol: EVENT_PROTOCOL,
    requiredAssistVersion: REQUIRED_ASSIST_VERSION,
    normalizeAsin: normalizeAsin,
    parseQueue: parseQueue,
    sameArray: sameArray,
    multisetSignature: multisetSignature,
    detectRunnerVersion: detectRunnerVersion,
    validateRankedResponse: validateRankedResponse,
    applyRankedQueue: applyRankedQueue,
    discoverRunner: discoverRunner,
    discoverAssist: discoverAssist,
    waitForRanking: waitForRanking,
    fnv1a: fnv1a,
  });

  if (typeof document === 'undefined' || !document.documentElement) return;

  var pending = false;

  function isEnabled() {
    return sessionStorage.getItem(ENABLE_KEY) === '1';
  }

  function setEnabled(value) {
    if (value) sessionStorage.setItem(ENABLE_KEY, '1');
    else sessionStorage.removeItem(ENABLE_KEY);
  }

  function discoverRunner(requireDraft) {
    var panels = Array.from(document.querySelectorAll('#ss-v3-panel'));
    if (panels.length !== 1) {
      throw adapterError('runner_panel_count', '需要且只能存在一个 Runner 面板，当前为 ' + panels.length + ' 个。');
    }
    var panel = panels[0];
    var version = detectRunnerVersion(panel.querySelector('h3') ? panel.querySelector('h3').textContent : '');
    if (!version) throw adapterError('runner_version', 'Runner 版本不在适配白名单中。');
    var queues = panel.querySelectorAll('#ss-v3-queue');
    var pickers = panel.querySelectorAll('#ss-v3-picker');
    var generateButtons = panel.querySelectorAll('#ss-v3-generate');
    if (queues.length !== 1 || pickers.length !== 1 || generateButtons.length !== 1) {
      throw adapterError('runner_contract', 'Runner 队列、批次选择器或生成按钮不唯一。');
    }
    var queue = queues[0];
    var picker = pickers[0];
    if (queue.disabled || queue.readOnly) throw adapterError('runner_queue_locked', 'Runner 队列当前不可编辑。');
    if (requireDraft && String(picker.value || '') !== '') {
      throw adapterError('runner_not_draft', '请在尚未生成批次的空白选择项中重排队列。');
    }
    return { panel: panel, queue: queue, picker: picker, generateButton: generateButtons[0], version: version };
  }

  function discoverAssist() {
    var panels = Array.from(document.querySelectorAll('#ss-mcp-hybrid-assist-panel'));
    if (panels.length !== 1) throw adapterError('assist_panel_count', '需要且只能存在一个 MCP Hybrid Assist 面板。');
    var panel = panels[0];
    if (panel.getAttribute('data-ss-mcp-version') !== REQUIRED_ASSIST_VERSION
        || panel.getAttribute('data-ss-mcp-event-protocol') !== EVENT_PROTOCOL
        || panel.getAttribute('data-ss-mcp-final-authority') !== 'false') {
      throw adapterError('assist_version', '请启用配套的 MCP Hybrid Assist ' + REQUIRED_ASSIST_VERSION + '。');
    }
    var enabled = panel.querySelector('#ss-mcp-assist-enabled');
    if (!enabled || !enabled.checked) throw adapterError('assist_disabled', 'MCP Hybrid Assist 尚未启用。');
    return panel;
  }

  function createRequestId() {
    return 'runner-adapter:' + Date.now() + ':' + Math.random().toString(16).slice(2);
  }

  function waitForRanking(snapshot) {
    return new Promise(function (resolve, reject) {
      var timer;
      function cleanup() {
        window.removeEventListener(RANKED_EVENT, onRanked);
        window.removeEventListener(ERROR_EVENT, onError);
        clearTimeout(timer);
      }
      function onRanked(event) {
        var detail = event && event.detail ? event.detail : {};
        if (detail.requestId !== snapshot.requestId) return;
        cleanup();
        try { resolve({ detail: detail, ranked: validateRankedResponse(detail, snapshot) }); }
        catch (error) { reject(error); }
      }
      function onError(event) {
        var detail = event && event.detail ? event.detail : {};
        if (detail.requestId !== snapshot.requestId) return;
        cleanup();
        reject(adapterError('assist_error', String(detail.message || 'Assist 排序失败。')));
      }
      window.addEventListener(RANKED_EVENT, onRanked);
      window.addEventListener(ERROR_EVENT, onError);
      timer = setTimeout(function () {
        cleanup();
        reject(adapterError('assist_timeout', '等待 Assist 响应超时，Runner 队列未改变。'));
      }, RESPONSE_TIMEOUT_MS);
      window.dispatchEvent(new CustomEvent(REQUEST_EVENT, { detail: {
        requestId: snapshot.requestId,
        eventProtocol: EVENT_PROTOCOL,
        asins: snapshot.asins.slice(),
        mode: snapshot.mode,
        finalAuthority: false,
        allowedAction: 'reorder_only',
      } }));
    });
  }

  function setStatus(control, message, isError) {
    var status = control && control.querySelector('#ss-mcp-runner-adapter-status');
    if (!status) return;
    status.textContent = message;
    status.style.color = isError ? '#b91c1c' : '#166534';
  }

  function emitAudit(name, detail) {
    window.dispatchEvent(new CustomEvent(name, { detail: detail }));
  }

  async function rankCurrentQueue(control) {
    if (pending) return;
    if (!isEnabled()) { setStatus(control, '请先启用 Adapter。', true); return; }
    var requestId = '';
    var startedAtMs = Date.now();
    pending = true;
    control.querySelector('#ss-mcp-runner-adapter-rank').disabled = true;
    try {
      var runner = discoverRunner(true);
      discoverAssist();
      var text = String(runner.queue.value || '');
      var asins = parseQueue(text);
      var mode = control.querySelector('#ss-mcp-runner-adapter-mode').value === 'focus5' ? 'focus5' : 'balanced';
      requestId = createRequestId();
      var snapshot = { requestId: requestId, text: text, asins: asins, mode: mode };
      setStatus(control, '正在请求 Assist 重排 ' + asins.length + ' 个 ASIN...', false);
      var response = await waitForRanking(snapshot);
      var currentRunner = discoverRunner(true);
      if (currentRunner.panel !== runner.panel || currentRunner.queue !== runner.queue) {
        throw adapterError('runner_replaced', '等待期间 Runner 面板已替换。');
      }
      var ranked = applyRankedQueue(currentRunner.queue, currentRunner.picker, snapshot, response.detail);
      var durationMs = Date.now() - startedAtMs;
      var audit = {
        schemaVersion: 'sellerSpriteMcpRunnerAdapterAudit/v1',
        adapterVersion: VERSION,
        assistVersion: REQUIRED_ASSIST_VERSION,
        runnerVersion: runner.version,
        requestId: requestId,
        mode: mode,
        count: ranked.length,
        durationMs: durationMs,
        originalOrderHash: fnv1a(asins.join('\n')),
        rankedOrderHash: fnv1a(ranked.join('\n')),
        multisetHash: fnv1a(multisetSignature(asins)),
        finalAuthority: false,
        allowedAction: 'reorder_only',
        batchCreated: false,
        batchStarted: false,
      };
      control.setAttribute('data-last-request-id', requestId);
      control.setAttribute('data-last-result', 'applied');
      emitAudit(APPLIED_EVENT, audit);
      setStatus(control, '已重排 ' + ranked.length + ' 个 ASIN；尚未生成批次，A-F 不变。', false);
    } catch (error) {
      control.setAttribute('data-last-request-id', requestId);
      control.setAttribute('data-last-result', 'error');
      emitAudit(ADAPTER_ERROR_EVENT, {
        schemaVersion: 'sellerSpriteMcpRunnerAdapterAudit/v1',
        adapterVersion: VERSION,
        requestId: requestId,
        code: error && error.code ? error.code : 'unexpected',
        message: error && error.message ? error.message : String(error),
        durationMs: Date.now() - startedAtMs,
        adapterMutation: false,
        finalAuthority: false,
      });
      setStatus(control, error && error.message ? error.message : String(error), true);
    } finally {
      pending = false;
      control.querySelector('#ss-mcp-runner-adapter-rank').disabled = false;
    }
  }

  function mountControls() {
    var runner;
    try { runner = discoverRunner(false); }
    catch (_) { return null; }
    var existing = runner.panel.querySelector('#' + CONTROL_ID);
    if (existing) return existing;
    var control = document.createElement('div');
    control.id = CONTROL_ID;
    control.setAttribute('data-ss-mcp-runner-adapter-version', VERSION);
    control.setAttribute('data-ss-mcp-feature-flag', FEATURE_FLAG);
    control.setAttribute('data-ss-mcp-event-protocol', EVENT_PROTOCOL);
    control.setAttribute('data-ss-mcp-final-authority', 'false');
    control.style.cssText = 'margin:8px 0;padding:7px;border:1px solid #0f766e;background:#f0fdfa;color:#111';
    control.innerHTML = [
      '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">',
      '<label style="margin:0;font-weight:700"><input id="ss-mcp-runner-adapter-enabled" type="checkbox" style="width:auto"> MCP 队列加速</label>',
      '<select id="ss-mcp-runner-adapter-mode" style="width:auto"><option value="balanced">Balanced</option><option value="focus5">Focus 5</option></select>',
      '<button id="ss-mcp-runner-adapter-rank" type="button">重排当前队列</button>',
      '</div>',
      '<div id="ss-mcp-runner-adapter-status" style="margin-top:5px;color:#6b7280">默认关闭；仅在生成批次前可用。</div>',
    ].join('');
    runner.generateButton.parentNode.insertBefore(control, runner.generateButton);
    var enabled = control.querySelector('#ss-mcp-runner-adapter-enabled');
    enabled.checked = isEnabled();
    enabled.addEventListener('change', function () {
      setEnabled(enabled.checked);
      setStatus(control, enabled.checked ? '已启用；请确认 Assist 0.2.1 已连接。' : '已关闭；Runner 队列不会被 Adapter 改动。', false);
    });
    control.querySelector('#ss-mcp-runner-adapter-rank').addEventListener('click', function () {
      rankCurrentQueue(control);
    });
    return control;
  }

  mountControls();
  new MutationObserver(function () { mountControls(); }).observe(document.documentElement, { childList: true, subtree: true });
})();
