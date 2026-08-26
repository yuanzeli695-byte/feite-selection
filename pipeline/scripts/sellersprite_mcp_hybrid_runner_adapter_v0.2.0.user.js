// ==UserScript==
// @name         SellerSprite MCP Hybrid Runner Adapter 0.2.0
// @namespace    amazon-products
// @version      0.2.0
// @description  Apply only audited reorder-only results to a draft Runner queue.
// @match        https://www.amazon.com/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  var VERSION = '0.2.0';
  var FEATURE_FLAG = 'ENABLE_MCP_HYBRID_RUNNER_ADAPTER_V0_2_0';
  var EVENT_PROTOCOL = 'runner-adapter/v2';
  var REQUIRED_ASSIST_VERSION = '0.3.0';
  var MIN_BRIDGE_VERSION = '0.3.0';
  var AUDIT_RECEIPT_SCHEMA = 'sellerSpriteMcpAuditReceipt/v1';
  var ENABLE_KEY = 'ss-mcp-hybrid-runner-adapter-v020-enabled';
  var CONTROL_ID = 'ss-mcp-runner-adapter-controls';
  var REQUEST_EVENT = 'ss-mcp-hybrid:rank-request';
  var RANKED_EVENT = 'ss-mcp-hybrid:queue-ranked';
  var ERROR_EVENT = 'ss-mcp-hybrid:rank-error';
  var AUDIT_REQUEST_EVENT = 'ss-mcp-hybrid:audit-request';
  var AUDIT_CONFIRMED_EVENT = 'ss-mcp-hybrid:audit-confirmed';
  var AUDIT_ERROR_EVENT = 'ss-mcp-hybrid:audit-error';
  var APPLIED_EVENT = 'ss-mcp-hybrid:runner-queue-applied';
  var ADAPTER_ERROR_EVENT = 'ss-mcp-hybrid:runner-queue-error';
  var RESPONSE_TIMEOUT_MS = 15000;
  var ASIN_RE = /^B0[A-Z0-9]{8}$/;
  var ID_RE = /^[A-Za-z0-9._:-]{1,128}$/;
  var BUILD_FLAGS = Object.freeze({
    stableDomContractV1: true,
    requiredRankingAuditV1: true,
    requiredApplicationAuditV1: true,
    rollbackOnAuditFailureV1: true,
    largeTargetBaselineV1: true,
  });
  var SUPPORTED_RUNNERS = Object.freeze({
    '0.3.7': /^SellerSprite Integrated Runner\s+0\.3\.7\b/,
    '0.3.8.2': /^\u5356\u5bb6\u7cbe\u7075\u4e00\u4f53\u5316\u9009\u54c1\s+0\.3\.8\.2\b/,
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

  function normalizeId(value) {
    var text = String(value || '').trim();
    return ID_RE.test(text) ? text : '';
  }

  function parseQueue(value) {
    var tokens = String(value || '').trim().split(/\s+/).filter(Boolean);
    if (!tokens.length) throw adapterError('queue_empty', 'Runner queue is empty.');
    var asins = tokens.map(normalizeAsin);
    if (asins.some(function (asin) { return !asin; })) {
      throw adapterError('queue_invalid', 'Runner queue contains an invalid ASIN; no rank request was sent.');
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

  function semverParts(value) {
    var match = String(value || '').trim().match(/^(\d+)\.(\d+)\.(\d+)$/);
    return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : null;
  }

  function versionAtLeast(value, minimum) {
    var left = semverParts(value);
    var right = semverParts(minimum);
    if (!left || !right) return false;
    for (var index = 0; index < 3; index += 1) {
      if (left[index] !== right[index]) return left[index] > right[index];
    }
    return true;
  }

  function detectRunnerVersion(title) {
    var text = String(title || '').replace(/\s+/g, ' ').trim();
    var versions = Object.keys(SUPPORTED_RUNNERS);
    for (var index = 0; index < versions.length; index += 1) {
      if (SUPPORTED_RUNNERS[versions[index]].test(text)) return versions[index];
    }
    return '';
  }

  function assertNodeTag(node, expected, code, label) {
    if (!node) throw adapterError(code, label + ' is missing.');
    if (node.tagName && String(node.tagName).toUpperCase() !== expected) {
      throw adapterError(code, label + ' DOM type changed; expected ' + expected + '.');
    }
  }

  function resolveMode(requestedMode, count) {
    var requested = String(requestedMode || 'auto').toLowerCase();
    if (requested === 'balanced') return { requestedMode: requested, mode: 'balanced', balancedExplicit: true };
    if (requested === 'focus5') {
      return { requestedMode: requested, mode: count <= 5 ? 'focus5' : 'original', balancedExplicit: false };
    }
    if (requested === 'original' || requested === 'baseline') {
      return { requestedMode: requested, mode: 'original', balancedExplicit: false };
    }
    return { requestedMode: 'auto', mode: count <= 5 ? 'focus5' : 'original', balancedExplicit: false };
  }

  function validateAuditReceipt(receipt, expected) {
    if (!receipt || receipt.schemaVersion !== AUDIT_RECEIPT_SCHEMA
        || receipt.requestId !== expected.requestId
        || receipt.auditId !== expected.auditId
        || receipt.persisted !== true
        || receipt.finalAuthority !== false) {
      throw adapterError('audit_receipt', 'Audit receipt is invalid, stale, or not persisted.');
    }
    return receipt;
  }

  function validateRankedResponse(detail, expected) {
    if (!detail || detail.eventProtocol !== EVENT_PROTOCOL) {
      throw adapterError('response_protocol', 'Assist response protocol mismatch; Assist 0.3.0 is required.');
    }
    if (detail.assistVersion !== REQUIRED_ASSIST_VERSION) {
      throw adapterError('response_assist_version', 'Assist response version mismatch; enable Assist 0.3.0 only.');
    }
    if (detail.requestId !== expected.requestId) {
      throw adapterError('response_stale', 'Received a response for a different rank request.');
    }
    if (detail.finalAuthority !== false || detail.allowedAction !== 'reorder_only') {
      throw adapterError('response_authority', 'Assist response exceeded the reorder-only boundary.');
    }
    if (detail.mode !== expected.mode || detail.multisetUnchanged !== true) {
      throw adapterError('response_contract', 'Assist mode or candidate multiset contract failed.');
    }
    if (expected.mode === 'balanced' && (expected.balancedExplicit !== true || detail.balancedExplicit !== true)) {
      throw adapterError('response_balanced_opt_in', 'Balanced mode requires explicit selection.');
    }
    if (!sameArray(detail.original, expected.asins)) {
      throw adapterError('response_original', 'Assist original queue differs from the current request.');
    }
    if (!Array.isArray(detail.ranked) || detail.ranked.length !== expected.asins.length) {
      throw adapterError('response_count', 'Assist changed the ASIN count.');
    }
    var ranked = detail.ranked.map(normalizeAsin);
    if (ranked.some(function (asin) { return !asin; })) {
      throw adapterError('response_invalid_asin', 'Assist response contains an invalid ASIN.');
    }
    if (multisetSignature(ranked) !== multisetSignature(expected.asins)) {
      throw adapterError('response_multiset', 'Assist added, removed, or changed duplicate ASINs.');
    }
    if (detail.auditRequired !== true || detail.rankingAuditConfirmed !== true || !detail.rankingAudit) {
      throw adapterError('ranking_audit_missing', 'Ranking audit was not confirmed by Bridge.');
    }
    validateAuditReceipt(detail.rankingAudit, {
      requestId: expected.requestId,
      auditId: normalizeId(detail.rankingAudit.auditId),
    });
    return ranked;
  }

  function applyRankedQueue(queue, picker, snapshot, detail) {
    if (!queue || !picker || String(picker.value || '') !== '') {
      throw adapterError('runner_not_draft', 'Runner is no longer an ungenerated draft; queue was not overwritten.');
    }
    if (String(queue.value || '') !== snapshot.text) {
      throw adapterError('queue_changed', 'Runner queue changed while waiting; newer content was preserved.');
    }
    var ranked = validateRankedResponse(detail, snapshot);
    var rankedText = ranked.join('\n');
    try {
      queue.value = rankedText;
      queue.dispatchEvent(new Event('input', { bubbles: true }));
      queue.dispatchEvent(new Event('change', { bubbles: true }));
      if (queue.value !== rankedText) throw adapterError('queue_event_changed', 'Runner event handlers changed the ranked queue.');
    } catch (error) {
      queue.value = snapshot.text;
      throw error;
    }
    return ranked;
  }

  function restoreQueue(queue, picker, snapshot, expectedCurrentText) {
    if (!queue || !picker || String(picker.value || '') !== '') {
      throw adapterError('rollback_not_draft', 'Cannot rollback because Runner is no longer a draft.');
    }
    if (String(queue.value || '') !== String(expectedCurrentText || '')) {
      throw adapterError('rollback_queue_changed', 'Cannot rollback because the ranked queue changed after application.');
    }
    queue.value = snapshot.text;
    queue.dispatchEvent(new Event('input', { bubbles: true }));
    queue.dispatchEvent(new Event('change', { bubbles: true }));
    if (String(queue.value || '') !== snapshot.text) {
      throw adapterError('rollback_event_changed', 'Runner event handlers prevented queue rollback.');
    }
    return true;
  }

  function lockGenerateButton(button, requestId) {
    if (!button) throw adapterError('runner_generate_missing', 'Runner Generate button is missing.');
    var lock = { button: button, requestId: requestId, previouslyDisabled: button.disabled === true, active: true };
    button.disabled = true;
    if (button.setAttribute) button.setAttribute('data-ss-mcp-audit-lock', requestId);
    return lock;
  }

  function releaseGenerateButton(lock) {
    if (!lock || !lock.active || !lock.button) return;
    if (lock.button.getAttribute) {
      var owner = lock.button.getAttribute('data-ss-mcp-audit-lock');
      if (owner && owner !== lock.requestId) throw adapterError('generate_lock_owner', 'Generate lock owner changed.');
      lock.button.removeAttribute('data-ss-mcp-audit-lock');
    }
    lock.button.disabled = lock.previouslyDisabled;
    lock.active = false;
  }

  function rollbackAfterAuditFailure(queue, picker, snapshot, rankedText, generationLock) {
    var rollbackSucceeded = false;
    var releaseSucceeded = false;
    var error = null;
    try {
      restoreQueue(queue, picker, snapshot, rankedText);
      rollbackSucceeded = true;
    } catch (rollbackError) {
      error = rollbackError;
    }
    if (rollbackSucceeded) {
      try {
        releaseGenerateButton(generationLock);
        releaseSucceeded = true;
      } catch (releaseError) {
        error = releaseError;
      }
    }
    if ((!rollbackSucceeded || !releaseSucceeded) && generationLock && generationLock.button) {
      generationLock.button.disabled = true;
    }
    return {
      rollbackSucceeded: rollbackSucceeded,
      releaseSucceeded: releaseSucceeded,
      mutationApplied: !rollbackSucceeded,
      generateLocked: Boolean(generationLock && generationLock.active),
      error: error,
    };
  }

  function applicationAuditPayload(snapshot, ranked, runnerVersion, durationMs) {
    return {
      schemaVersion: 'sellerSpriteMcpRunnerApplyAudit/v1',
      adapterVersion: VERSION,
      assistVersion: REQUIRED_ASSIST_VERSION,
      runnerVersion: runnerVersion,
      eventProtocol: EVENT_PROTOCOL,
      requestedMode: snapshot.requestedMode,
      mode: snapshot.mode,
      balancedExplicit: snapshot.balancedExplicit,
      count: ranked.length,
      durationMs: durationMs,
      originalOrderHash: fnv1a(snapshot.asins.join('\n')),
      rankedOrderHash: fnv1a(ranked.join('\n')),
      multisetHash: fnv1a(multisetSignature(snapshot.asins)),
      rankingAuditId: snapshot.rankingAuditId,
      finalAuthority: false,
      allowedAction: 'reorder_only',
      batchCreated: false,
      batchStarted: false,
      strictHistoryWritten: false,
    };
  }

  globalThis.SSMcpHybridRunnerAdapterCore = Object.freeze({
    version: VERSION,
    featureFlag: FEATURE_FLAG,
    buildFlags: BUILD_FLAGS,
    eventProtocol: EVENT_PROTOCOL,
    requiredAssistVersion: REQUIRED_ASSIST_VERSION,
    minBridgeVersion: MIN_BRIDGE_VERSION,
    auditReceiptSchema: AUDIT_RECEIPT_SCHEMA,
    normalizeAsin: normalizeAsin,
    normalizeId: normalizeId,
    parseQueue: parseQueue,
    sameArray: sameArray,
    multisetSignature: multisetSignature,
    versionAtLeast: versionAtLeast,
    detectRunnerVersion: detectRunnerVersion,
    resolveMode: resolveMode,
    validateAuditReceipt: validateAuditReceipt,
    validateRankedResponse: validateRankedResponse,
    applyRankedQueue: applyRankedQueue,
    restoreQueue: restoreQueue,
    lockGenerateButton: lockGenerateButton,
    releaseGenerateButton: releaseGenerateButton,
    rollbackAfterAuditFailure: rollbackAfterAuditFailure,
    applicationAuditPayload: applicationAuditPayload,
    discoverRunner: discoverRunner,
    discoverAssist: discoverAssist,
    waitForRanking: waitForRanking,
    waitForAuditConfirmation: waitForAuditConfirmation,
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
      throw adapterError('runner_panel_count', 'Exactly one Runner panel is required; found ' + panels.length + '.');
    }
    var panel = panels[0];
    assertNodeTag(panel, 'DIV', 'runner_panel_contract', 'Runner panel');
    if (panel.id && panel.id !== 'ss-v3-panel') throw adapterError('runner_panel_contract', 'Runner panel ID changed.');
    var heading = panel.querySelector('h3');
    assertNodeTag(heading, 'H3', 'runner_heading_contract', 'Runner heading');
    var version = detectRunnerVersion(heading.textContent);
    if (!version) {
      throw adapterError('runner_version', 'Unsupported Runner version. Use 0.3.7 or 0.3.8.2.');
    }
    var queues = panel.querySelectorAll('#ss-v3-queue');
    var pickers = panel.querySelectorAll('#ss-v3-picker');
    var generateButtons = panel.querySelectorAll('#ss-v3-generate');
    if (queues.length !== 1 || pickers.length !== 1 || generateButtons.length !== 1) {
      throw adapterError('runner_contract', 'Runner queue, batch picker, and Generate button must each be unique.');
    }
    var queue = queues[0];
    var picker = pickers[0];
    var generateButton = generateButtons[0];
    assertNodeTag(queue, 'TEXTAREA', 'runner_queue_contract', 'Runner queue');
    assertNodeTag(picker, 'SELECT', 'runner_picker_contract', 'Runner batch picker');
    assertNodeTag(generateButton, 'BUTTON', 'runner_generate_contract', 'Runner Generate button');
    if (queue.disabled || queue.readOnly) throw adapterError('runner_queue_locked', 'Runner queue is not editable.');
    if (requireDraft && String(picker.value || '') !== '') {
      throw adapterError('runner_not_draft', 'Select the empty ungenerated Runner draft before ranking.');
    }
    return { panel: panel, queue: queue, picker: picker, generateButton: generateButton, version: version };
  }

  function discoverAssist() {
    var panels = Array.from(document.querySelectorAll('#ss-mcp-hybrid-assist-panel'));
    if (panels.length !== 1) throw adapterError('assist_panel_count', 'Exactly one MCP Hybrid Assist panel is required.');
    var panel = panels[0];
    var version = panel.getAttribute('data-ss-mcp-version');
    var protocol = panel.getAttribute('data-ss-mcp-event-protocol');
    var finalAuthority = panel.getAttribute('data-ss-mcp-final-authority');
    var featureFlag = panel.getAttribute('data-ss-mcp-feature-flag');
    var featureEnabled = panel.getAttribute('data-ss-mcp-feature-enabled');
    var auditRequired = panel.getAttribute('data-ss-mcp-audit-required');
    var bridgeVersion = panel.getAttribute('data-ss-mcp-bridge-version');
    if (version !== REQUIRED_ASSIST_VERSION || protocol !== EVENT_PROTOCOL || finalAuthority !== 'false'
        || featureFlag !== 'ENABLE_MCP_HYBRID_ASSIST_V0_3_0' || featureEnabled !== 'true' || auditRequired !== 'true') {
      throw adapterError('assist_version', 'Assist DOM contract mismatch. Enable only MCP Hybrid Assist 0.3.0.');
    }
    if (!versionAtLeast(bridgeVersion, MIN_BRIDGE_VERSION)) {
      throw adapterError('bridge_version', 'Assist must be connected to Bridge 0.3.0 or newer.');
    }
    var enabled = panel.querySelector('#ss-mcp-assist-enabled');
    if (!enabled || !enabled.checked) throw adapterError('assist_disabled', 'MCP Hybrid Assist 0.3.0 is disabled.');
    return panel;
  }

  function createRequestId() {
    return 'runner-adapter:' + Date.now() + ':' + Math.random().toString(16).slice(2);
  }

  function createApplicationAuditId(requestId, ranked) {
    return 'apply:' + fnv1a(requestId) + ':' + fnv1a(ranked.join('|'));
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
        reject(adapterError('assist_error', String(detail.message || 'Assist ranking failed.')));
      }
      window.addEventListener(RANKED_EVENT, onRanked);
      window.addEventListener(ERROR_EVENT, onError);
      timer = setTimeout(function () {
        cleanup();
        reject(adapterError('assist_timeout', 'Assist ranking timed out; Runner queue was not changed.'));
      }, RESPONSE_TIMEOUT_MS);
      window.dispatchEvent(new CustomEvent(REQUEST_EVENT, { detail: {
        requestId: snapshot.requestId,
        eventProtocol: EVENT_PROTOCOL,
        asins: snapshot.asins.slice(),
        requestedMode: snapshot.requestedMode,
        mode: snapshot.mode,
        balancedExplicit: snapshot.balancedExplicit,
        finalAuthority: false,
        allowedAction: 'reorder_only',
      } }));
    });
  }

  function waitForAuditConfirmation(expected, payload) {
    return new Promise(function (resolve, reject) {
      var timer;
      function cleanup() {
        window.removeEventListener(AUDIT_CONFIRMED_EVENT, onConfirmed);
        window.removeEventListener(AUDIT_ERROR_EVENT, onError);
        clearTimeout(timer);
      }
      function onConfirmed(event) {
        var detail = event && event.detail ? event.detail : {};
        if (detail.requestId !== expected.requestId || detail.auditId !== expected.auditId) return;
        cleanup();
        try {
          if (detail.eventProtocol !== EVENT_PROTOCOL || detail.persisted !== true || detail.finalAuthority !== false) {
            throw adapterError('audit_confirmation', 'Assist audit confirmation contract failed.');
          }
          resolve(validateAuditReceipt(detail.receipt, expected));
        } catch (error) { reject(error); }
      }
      function onError(event) {
        var detail = event && event.detail ? event.detail : {};
        if (detail.requestId !== expected.requestId || detail.auditId !== expected.auditId) return;
        cleanup();
        reject(adapterError('audit_failed', String(detail.message || 'Bridge audit persistence failed.')));
      }
      window.addEventListener(AUDIT_CONFIRMED_EVENT, onConfirmed);
      window.addEventListener(AUDIT_ERROR_EVENT, onError);
      timer = setTimeout(function () {
        cleanup();
        reject(adapterError('audit_timeout', 'Bridge application audit timed out.'));
      }, RESPONSE_TIMEOUT_MS);
      window.dispatchEvent(new CustomEvent(AUDIT_REQUEST_EVENT, { detail: {
        requestId: expected.requestId,
        auditId: expected.auditId,
        eventType: 'queue_applied',
        eventProtocol: EVENT_PROTOCOL,
        payload: payload,
        finalAuthority: false,
      } }));
    });
  }

  function setStatus(control, message, isError) {
    var status = control && control.querySelector('#ss-mcp-runner-adapter-status');
    if (!status) return;
    status.textContent = message;
    status.style.color = isError ? '#b91c1c' : '#166534';
  }

  function emitLocal(name, detail) {
    window.dispatchEvent(new CustomEvent(name, { detail: detail }));
  }

  async function rankCurrentQueue(control) {
    if (pending) return;
    if (!isEnabled()) { setStatus(control, 'Enable Adapter 0.2.0 first.', true); return; }
    var requestId = '';
    var startedAtMs = Date.now();
    var runner = null;
    var snapshot = null;
    var ranked = null;
    var rankedText = '';
    var generationLock = null;
    var mutationApplied = false;
    var rollbackSucceeded = false;
    pending = true;
    control.querySelector('#ss-mcp-runner-adapter-rank').disabled = true;
    try {
      runner = discoverRunner(true);
      discoverAssist();
      var text = String(runner.queue.value || '');
      var asins = parseQueue(text);
      var requestedMode = control.querySelector('#ss-mcp-runner-adapter-mode').value;
      var mode = resolveMode(requestedMode, asins.length);
      requestId = createRequestId();
      snapshot = {
        requestId: requestId,
        text: text,
        asins: asins,
        requestedMode: mode.requestedMode,
        mode: mode.mode,
        balancedExplicit: mode.balancedExplicit,
      };
      generationLock = lockGenerateButton(runner.generateButton, requestId);
      setStatus(control, 'Requesting audited ' + mode.mode + ' order for ' + asins.length + ' ASINs...', false);
      var response = await waitForRanking(snapshot);
      if (!isEnabled()) throw adapterError('adapter_disabled_midflight', 'Adapter was disabled before queue application.');
      var currentRunner = discoverRunner(true);
      discoverAssist();
      if (currentRunner.panel !== runner.panel || currentRunner.queue !== runner.queue || currentRunner.generateButton !== runner.generateButton) {
        throw adapterError('runner_replaced', 'Runner panel changed while waiting; queue was not applied.');
      }
      snapshot.rankingAuditId = response.detail.rankingAudit.auditId;
      ranked = applyRankedQueue(currentRunner.queue, currentRunner.picker, snapshot, response.detail);
      rankedText = ranked.join('\n');
      mutationApplied = true;
      var auditId = createApplicationAuditId(requestId, ranked);
      var auditPayload = applicationAuditPayload(snapshot, ranked, runner.version, Date.now() - startedAtMs);
      var receipt = await waitForAuditConfirmation({ requestId: requestId, auditId: auditId }, auditPayload);
      var verifiedRunner = discoverRunner(true);
      if (verifiedRunner.queue !== runner.queue || String(verifiedRunner.queue.value || '') !== rankedText) {
        throw adapterError('queue_changed_after_audit', 'Runner queue changed before audit completion.');
      }
      releaseGenerateButton(generationLock);
      control.setAttribute('data-last-request-id', requestId);
      control.setAttribute('data-last-audit-id', receipt.auditId);
      control.setAttribute('data-last-result', 'applied-audited');
      emitLocal(APPLIED_EVENT, Object.assign({}, auditPayload, {
        requestId: requestId,
        auditId: receipt.auditId,
        auditPersisted: true,
        finalAuthority: false,
      }));
      setStatus(control, 'Applied and audited ' + ranked.length + ' ASINs; no batch was generated.', false);
    } catch (error) {
      if (mutationApplied && runner && snapshot) {
        var rollback = rollbackAfterAuditFailure(runner.queue, runner.picker, snapshot, rankedText, generationLock);
        rollbackSucceeded = rollback.rollbackSucceeded;
        mutationApplied = rollback.mutationApplied;
      } else {
        try { releaseGenerateButton(generationLock); } catch (_) { /* preserve lock on ownership mismatch */ }
      }
      control.setAttribute('data-last-request-id', requestId);
      control.setAttribute('data-last-result', mutationApplied ? 'error-generate-locked' : 'error-no-mutation');
      emitLocal(ADAPTER_ERROR_EVENT, {
        schemaVersion: 'sellerSpriteMcpRunnerAdapterAudit/v2',
        adapterVersion: VERSION,
        requestId: requestId,
        code: error && error.code ? error.code : 'unexpected',
        message: error && error.message ? error.message : String(error),
        durationMs: Date.now() - startedAtMs,
        adapterMutation: mutationApplied,
        rollbackSucceeded: rollbackSucceeded,
        generateLocked: Boolean(generationLock && generationLock.active),
        finalAuthority: false,
      });
      setStatus(control, (error && error.message ? error.message : String(error))
        + (mutationApplied ? ' Generate remains disabled.' : (rollbackSucceeded ? ' Original queue restored.' : '')), true);
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
    if (existing) {
      if (existing.getAttribute('data-ss-mcp-runner-adapter-version') !== VERSION) {
        existing.setAttribute('data-ss-mcp-version-conflict', VERSION);
        setStatus(existing, 'Version conflict: disable the other Adapter version and reload.', true);
      }
      return existing;
    }
    var control = document.createElement('div');
    control.id = CONTROL_ID;
    control.setAttribute('data-ss-mcp-runner-adapter-version', VERSION);
    control.setAttribute('data-ss-mcp-feature-flag', FEATURE_FLAG);
    control.setAttribute('data-ss-mcp-feature-enabled', 'false');
    control.setAttribute('data-ss-mcp-event-protocol', EVENT_PROTOCOL);
    control.setAttribute('data-ss-mcp-final-authority', 'false');
    control.setAttribute('data-ss-mcp-audit-required', 'true');
    control.style.cssText = 'margin:8px 0;padding:7px;border:1px solid #0f766e;background:#f0fdfa;color:#111';
    control.innerHTML = [
      '<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">',
      '<label style="margin:0;font-weight:700"><input id="ss-mcp-runner-adapter-enabled" type="checkbox" style="width:auto"> MCP queue assist</label>',
      '<select id="ss-mcp-runner-adapter-mode" style="width:auto"><option value="auto">Auto</option><option value="original">Baseline</option><option value="focus5">Focus 5</option><option value="balanced">Balanced (explicit)</option></select>',
      '<button id="ss-mcp-runner-adapter-rank" type="button">Rank draft queue</button>',
      '</div>',
      '<div id="ss-mcp-runner-adapter-status" style="margin-top:5px;color:#6b7280">Disabled by default; draft queue only.</div>',
    ].join('');
    runner.generateButton.parentNode.insertBefore(control, runner.generateButton);
    var enabled = control.querySelector('#ss-mcp-runner-adapter-enabled');
    enabled.checked = isEnabled();
    control.setAttribute('data-ss-mcp-feature-enabled', enabled.checked ? 'true' : 'false');
    enabled.addEventListener('change', function () {
      setEnabled(enabled.checked);
      control.setAttribute('data-ss-mcp-feature-enabled', enabled.checked ? 'true' : 'false');
      setStatus(control, enabled.checked
        ? 'Enabled; Assist 0.3.0 and Bridge 0.3.0+ audit confirmation are required.'
        : 'Disabled; Adapter will not change the Runner queue.', false);
    });
    control.querySelector('#ss-mcp-runner-adapter-rank').addEventListener('click', function () {
      rankCurrentQueue(control);
    });
    return control;
  }

  mountControls();
  new MutationObserver(function () { mountControls(); }).observe(document.documentElement, { childList: true, subtree: true });
})();
