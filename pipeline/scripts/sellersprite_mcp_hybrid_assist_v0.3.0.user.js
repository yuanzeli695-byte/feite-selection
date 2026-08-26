// ==UserScript==
// @name         SellerSprite MCP Hybrid Assist 0.3.0
// @namespace    amazon-products
// @version      0.3.0
// @description  Rank draft queues from audited loopback MCP evidence without changing A-F decisions.
// @match        https://www.amazon.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_setClipboard
// @connect      127.0.0.1
// @connect      localhost
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  var VERSION = '0.3.0';
  var MODE = 'shadow-assist';
  var FEATURE_FLAG = 'ENABLE_MCP_HYBRID_ASSIST_V0_3_0';
  var EVENT_PROTOCOL = 'runner-adapter/v2';
  var RESPONSE_SCHEMA = 'sellerSpriteMcpHybridResponse/v1';
  var BATCH_SCHEMA = 'sellerSpriteMcpBatchLookup/v1';
  var MERGED_RANKING_SCHEMA = 'sellerSpriteMcpMergedRanking/v1';
  var AUDIT_EVENT_SCHEMA = 'sellerSpriteMcpAuditEvent/v1';
  var AUDIT_RECEIPT_SCHEMA = 'sellerSpriteMcpAuditReceipt/v1';
  var MIN_BRIDGE_VERSION = '0.3.0';
  var TOOL_TTL_MS = Object.freeze({
    keepa_info: 6 * 60 * 60 * 1000,
    asin_detail: 6 * 60 * 60 * 1000,
    asin_sales_trend: 6 * 60 * 60 * 1000,
    traffic_listing_stat: 24 * 60 * 60 * 1000,
  });
  var SCORING_POLICY_ID = 'mcp-hybrid-ranking/v0.3.0:price4:rating2:reviews2:dimensions0.25:priceTrend0.25';
  var DEFAULT_BRIDGE_URL = 'http://127.0.0.1:8766';
  var ENABLE_KEY = 'ss-mcp-hybrid-assist-v030-enabled';
  var PANEL_ID = 'ss-mcp-hybrid-assist-panel';
  var REQUEST_EVENT = 'ss-mcp-hybrid:rank-request';
  var RANKED_EVENT = 'ss-mcp-hybrid:queue-ranked';
  var RANK_ERROR_EVENT = 'ss-mcp-hybrid:rank-error';
  var AUDIT_REQUEST_EVENT = 'ss-mcp-hybrid:audit-request';
  var AUDIT_CONFIRMED_EVENT = 'ss-mcp-hybrid:audit-confirmed';
  var AUDIT_ERROR_EVENT = 'ss-mcp-hybrid:audit-error';
  var ASIN_RE = /^B0[A-Z0-9]{8}$/;
  var ID_RE = /^[A-Za-z0-9._:-]{1,128}$/;
  var BUILD_FLAGS = Object.freeze({
    mergedRankingV1: true,
    requiredAuditRelayV1: true,
    largeTargetBaselineV1: true,
  });

  function normalizeAsin(value) {
    var text = String(value || '').trim().toUpperCase();
    return ASIN_RE.test(text) ? text : '';
  }

  function normalizeRequestId(value) {
    var text = String(value || '').trim();
    return ID_RE.test(text) ? text : '';
  }

  function normalizeAuditId(value) {
    return normalizeRequestId(value);
  }

  function createRequestId(prefix) {
    return String(prefix || 'assist') + ':' + Date.now() + ':' + Math.random().toString(16).slice(2);
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

  function createAuditId(kind, requestId, signature) {
    return String(kind || 'audit') + ':' + fnv1a(requestId) + ':' + fnv1a(signature);
  }

  function validateBridgeOrigin(value) {
    var url;
    try {
      url = new URL(String(value || '').trim());
    } catch (_) {
      throw new Error('Invalid Bridge URL');
    }
    if (url.protocol !== 'http:') throw new Error('Bridge must use HTTP');
    if (url.hostname !== '127.0.0.1' && url.hostname !== 'localhost') throw new Error('Bridge must be loopback');
    if (url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
      throw new Error('Bridge URL must contain only origin and port');
    }
    return url.origin;
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

  function validateBridgeHealth(payload) {
    if (!payload || payload.schemaVersion !== RESPONSE_SCHEMA || payload.ok !== true) {
      throw new Error('Bridge health response is invalid');
    }
    if (!versionAtLeast(payload.version, MIN_BRIDGE_VERSION)) {
      throw new Error('Bridge ' + MIN_BRIDGE_VERSION + ' or newer is required');
    }
    if (payload.mode !== 'shadow' || payload.outboundMcpEnabled !== false || payload.finalAuthority !== false) {
      throw new Error('Bridge authority boundary is invalid');
    }
    return {
      version: payload.version,
      runId: String(payload.runId || ''),
      policyVersion: String(payload.policyVersion || ''),
      policySha256: String(payload.policySha256 || ''),
      testMode: payload.testMode === true,
      finalAuthority: false,
    };
  }

  function finite(value) {
    var number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function objectOrEmpty(value) {
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  }

  function reasonList() {
    var reasons = [];
    Array.prototype.slice.call(arguments).forEach(function (value) {
      if (Array.isArray(value)) value.forEach(function (item) { reasons.push(String(item || '').toLowerCase()); });
      else if (value !== undefined && value !== null && value !== '') reasons.push(String(value).toLowerCase());
    });
    return reasons;
  }

  function hasUnsafeReason() {
    return reasonList.apply(null, arguments).some(function (reason) {
      return /stale|expired|mismatch|redirect|wrong[_ -]?asin|not[_ -]?exact/.test(reason);
    });
  }

  function timestampMs(value) {
    var parsed = Date.parse(String(value || ''));
    return Number.isFinite(parsed) ? parsed : null;
  }

  function isFreshWindow(capturedAt, expiresAt, tool, nowMs) {
    var captured = timestampMs(capturedAt);
    var expires = timestampMs(expiresAt);
    var current = Number.isFinite(nowMs) ? nowMs : Date.now();
    var ttl = tool ? TOOL_TTL_MS[String(tool || '')] : null;
    if (captured === null || expires === null || captured > current || current >= expires || expires <= captured) return false;
    return ttl == null || expires - captured <= ttl;
  }

  function normalizeFieldSource(value, nowMs) {
    var source = objectOrEmpty(value);
    var evidenceId = String(source.evidenceId || '');
    var tool = String(source.tool || '');
    var capturedAt = String(source.capturedAt || '');
    var expiresAt = String(source.expiresAt || '');
    var sourcePath = String(source.sourcePath || '');
    var semantics = String(source.semantics || '');
    if (!evidenceId || !tool || !sourcePath || !semantics
        || !isFreshWindow(capturedAt, expiresAt, tool, nowMs)
        || hasUnsafeReason(source.reason, source.reasonCodes, source.semantics)) return null;
    return {
      evidenceId: evidenceId,
      tool: tool,
      capturedAt: capturedAt,
      expiresAt: expiresAt,
      sourcePath: sourcePath,
      semantics: semantics,
    };
  }

  function unavailableLookup(asin, reason, browserFallbackRequired) {
    return {
      asin: asin,
      usable: false,
      usableForRanking: false,
      browserFallbackRequired: browserFallbackRequired !== false,
      fields: {},
      fieldSources: {},
      evidenceIds: [],
      source: 'none',
      finalAuthority: false,
      reason: reason,
    };
  }

  function normalizeMergedRanking(row, asin, nowMs) {
    var merged = row && row.mergedRanking;
    if (!merged) return null;
    if (merged.schemaVersion !== MERGED_RANKING_SCHEMA
        || merged.finalAuthority !== false
        || merged.usableForFinal !== false
        || merged.usableForRanking !== true
        || row.usableForRanking === false
        || hasUnsafeReason(merged.reasonCodes, row.reasonCodes)
        || !isFreshWindow(merged.capturedAt, merged.expiresAt, '', nowMs)) {
      return unavailableLookup(asin, 'invalid_merged_ranking', true);
    }
    var rawFields = objectOrEmpty(merged.fields);
    var rawSources = objectOrEmpty(merged.fieldSources);
    var fields = {};
    var fieldSources = {};
    var droppedField = false;
    Object.keys(rawFields).forEach(function (field) {
      var source = normalizeFieldSource(rawSources[field], nowMs);
      if (source && rawFields[field] !== undefined && rawFields[field] !== null && rawFields[field] !== '') {
        fields[field] = rawFields[field];
        fieldSources[field] = source;
      } else {
        droppedField = true;
      }
    });
    if (!Object.keys(fields).length) return unavailableLookup(asin, 'merged_ranking_fields_unproven', true);
    return {
      asin: asin,
      usable: true,
      usableForRanking: true,
      browserFallbackRequired: row.browserFallbackRequired === true || merged.browserFallbackRequired === true || droppedField,
      fields: fields,
      fieldSources: fieldSources,
      evidenceIds: Array.isArray(merged.evidenceIds) ? merged.evidenceIds.map(String) : [],
      capturedAt: String(merged.capturedAt || ''),
      expiresAt: String(merged.expiresAt || ''),
      source: 'mergedRanking',
      finalAuthority: false,
      reason: '',
    };
  }

  function exactFreshResult(item, asin, nowMs) {
    var evidence = item && item.evidence;
    var response = evidence ? objectOrEmpty(evidence.response) : {};
    if (!item || item.usableForRanking !== true || item.usableForFinal !== false || !evidence) return false;
    if (evidence.finalAuthority !== false
        || normalizeAsin(evidence.targetAsin) !== asin
        || normalizeAsin(evidence.actualAsin) !== asin) return false;
    if (item.stale === true || item.expired === true || item.asinMismatch === true
        || evidence.stale === true || evidence.expired === true || evidence.asinMismatch === true
        || evidence.fresh === false) return false;
    if (hasUnsafeReason(item.reason, item.reasonCodes, evidence.reason, evidence.reasonCodes, evidence.status)) return false;
    var toolName = String(item.tool || (evidence.tool && evidence.tool.name) || evidence.tool || '');
    if (!isFreshWindow(
      item.capturedAt || evidence.capturedAt || response.capturedAt,
      item.expiresAt || evidence.expiresAt || response.expiresAt,
      toolName,
      nowMs,
    )) return false;
    return Object.keys(objectOrEmpty(evidence.fields)).length > 0;
  }

  function sourceForResult(item, evidence, fieldProvenance) {
    var provenance = objectOrEmpty(fieldProvenance || evidence.provenance);
    var response = objectOrEmpty(evidence.response);
    var evidenceTool = evidence.tool && typeof evidence.tool === 'object' ? evidence.tool.name : evidence.tool;
    var actualAsin = normalizeAsin(evidence.actualAsin);
    if (!evidenceTool || (item.tool && item.tool !== evidenceTool) || provenance.sourceTool !== evidenceTool) return null;
    if (provenance.sourceAsin != null && normalizeAsin(provenance.sourceAsin) !== actualAsin) return null;
    return {
      evidenceId: String(item.evidenceId || evidence.evidenceId || evidence.id || ''),
      tool: String(item.tool || evidenceTool || ''),
      capturedAt: String(item.capturedAt || evidence.capturedAt || response.capturedAt || ''),
      expiresAt: String(item.expiresAt || evidence.expiresAt || response.expiresAt || ''),
      sourcePath: String(item.sourcePath || evidence.sourcePath || provenance.sourcePath || ''),
      semantics: String(provenance.semantics || 'legacy_results_exact_fresh_fallback'),
    };
  }

  function normalizeLegacyResults(row, asin, nowMs) {
    if (row.usableForRanking === false) return unavailableLookup(asin, 'row_not_usable_for_ranking', true);
    var results = Array.isArray(row.results) ? row.results : [];
    var usable = results.filter(function (item) { return exactFreshResult(item, asin, nowMs); });
    if (!usable.length) {
      return unavailableLookup(asin, results.length ? 'no_exact_fresh_ranking_evidence' : 'no_evidence', true);
    }
    var fields = {};
    var fieldSources = {};
    var evidenceIds = [];
    var browserFallbackRequired = row.browserFallbackRequired === true;
    usable.forEach(function (item) {
      var evidence = item.evidence;
      if (item.browserFallbackRequired === true || evidence.browserFallbackRequired === true) {
        browserFallbackRequired = true;
      }
      var provenanceByField = objectOrEmpty(evidence.fieldProvenance);
      Object.keys(objectOrEmpty(evidence.fields)).forEach(function (field) {
        var source = normalizeFieldSource(sourceForResult(item, evidence, provenanceByField[field]), nowMs);
        if (!Object.prototype.hasOwnProperty.call(fields, field)
            && source
            && evidence.fields[field] !== undefined
            && evidence.fields[field] !== null
            && evidence.fields[field] !== '') {
          fields[field] = evidence.fields[field];
          fieldSources[field] = source;
          if (source.evidenceId) evidenceIds.push(source.evidenceId);
        }
      });
    });
    if (!Object.keys(fields).length) return unavailableLookup(asin, 'ranking_fields_empty', true);
    return {
      asin: asin,
      usable: true,
      usableForRanking: true,
      browserFallbackRequired: browserFallbackRequired,
      fields: fields,
      fieldSources: fieldSources,
      evidenceIds: Array.from(new Set(evidenceIds)),
      source: 'legacyResults',
      finalAuthority: false,
      reason: '',
    };
  }

  function normalizeLookupRow(row, expectedAsin, nowMs) {
    var asin = normalizeAsin(expectedAsin);
    if (!row || normalizeAsin(row.asin) !== asin || row.finalAuthority !== false) {
      return unavailableLookup(asin, 'row_mismatch', true);
    }
    var merged = normalizeMergedRanking(row, asin, nowMs);
    if (merged) return merged;
    return normalizeLegacyResults(row, asin, nowMs);
  }

  function normalizeBatchResponse(payload, expectedAsins, nowMs) {
    var expected = (expectedAsins || []).map(normalizeAsin).filter(Boolean);
    if (!payload || payload.schemaVersion !== RESPONSE_SCHEMA || payload.ok !== true || payload.finalAuthority !== false) {
      return { ok: false, rows: [], finalAuthority: false, reason: 'invalid_bridge_response' };
    }
    var result = payload.result;
    if (!result || result.schemaVersion !== BATCH_SCHEMA || result.finalAuthority !== false) {
      return { ok: false, rows: [], finalAuthority: false, reason: 'invalid_batch_response' };
    }
    var rows = Array.isArray(result.rows) ? result.rows : [];
    if (rows.length !== expected.length) {
      return { ok: false, rows: [], finalAuthority: false, reason: 'batch_count_mismatch' };
    }
    var normalized = rows.map(function (row, index) { return normalizeLookupRow(row, expected[index], nowMs); });
    return { ok: true, rows: normalized, finalAuthority: false, reason: '' };
  }

  function scoreBreakdown(fields) {
    var source = objectOrEmpty(fields);
    var breakdown = { price: 0, rating: 0, reviews: 0, dimensions: 0, priceTrend: 0 };
    var price = finite(source.price);
    var rating = finite(source.rating);
    var reviews = finite(source.reviews);
    if (price !== null && price >= 9.9 && price <= 50) breakdown.price = 4;
    if (rating !== null && rating >= 4) breakdown.rating = 2;
    if (reviews !== null && reviews <= 115) breakdown.reviews = 2;
    if (source.dimensions || source.packageDimensions) breakdown.dimensions = 0.25;
    if (source.priceTrendClass === 'stable' || source.priceTrendClass === 'rising') breakdown.priceTrend = 0.25;
    return breakdown;
  }

  function scoreFields(fields) {
    var breakdown = scoreBreakdown(fields);
    return Object.keys(breakdown).reduce(function (sum, key) { return sum + breakdown[key]; }, 0);
  }

  function resolveMode(requestedMode, targetCount, balancedExplicit) {
    var requested = String(requestedMode || 'auto').toLowerCase();
    var count = Number(targetCount) || 0;
    if (requested === 'balanced') return balancedExplicit === true ? 'balanced' : 'original';
    if (requested === 'focus5') return count <= 5 ? 'focus5' : 'original';
    if (requested === 'original' || requested === 'baseline') return 'original';
    return count <= 5 ? 'focus5' : 'original';
  }

  function rankQueue(asins, evidenceByAsin, requestedMode, options) {
    var config = objectOrEmpty(options);
    var rows = (asins || []).map(function (value, index) {
      var asin = normalizeAsin(value);
      var evidence = evidenceByAsin && evidenceByAsin[asin] ? evidenceByAsin[asin] : unavailableLookup(asin, 'no_evidence', true);
      var score = evidence.usableForRanking === true ? scoreFields(evidence.fields) : 0;
      return {
        asin: asin,
        index: index,
        score: score,
        usableForRanking: evidence.usableForRanking === true,
        browserFallbackRequired: evidence.browserFallbackRequired !== false,
        source: evidence.source || 'none',
        finalAuthority: false,
      };
    });
    if (rows.some(function (row) { return !row.asin; })) throw new Error('Queue contains an invalid ASIN');
    var mode = resolveMode(requestedMode, rows.length, config.balancedExplicit === true);
    var rankedRows = mode === 'original' ? rows.slice() : rows.slice().sort(function (left, right) {
      return right.score - left.score || left.index - right.index;
    });
    var original = rows.map(function (row) { return row.asin; });
    var ranked = rankedRows.map(function (row) { return row.asin; });
    return {
      requestedMode: String(requestedMode || 'auto'),
      mode: mode,
      balancedExplicit: mode === 'balanced' && config.balancedExplicit === true,
      original: original,
      ranked: ranked,
      rows: rankedRows,
      multisetUnchanged: original.slice().sort().join('|') === ranked.slice().sort().join('|'),
      finalAuthority: false,
      allowedAction: 'reorder_only',
    };
  }

  function buildAdvisory(lookup) {
    var fields = lookup && lookup.fields ? lookup.fields : {};
    return {
      asin: lookup ? lookup.asin : '',
      usableForRanking: Boolean(lookup && lookup.usableForRanking),
      browserFallbackRequired: !lookup || lookup.browserFallbackRequired !== false,
      score: lookup && lookup.usableForRanking ? scoreFields(fields) : 0,
      scoreBreakdown: scoreBreakdown(fields),
      fields: fields,
      fieldSources: lookup && lookup.fieldSources ? lookup.fieldSources : {},
      finalAuthority: false,
      gateCProvided: false,
      allowedAction: 'reorder_only',
      forbiddenActions: ['pass_gate', 'write_runner_result', 'write_strict_history', 'create_batch', 'start_batch', 'skip_current_acceptance'],
    };
  }

  function validateAuditReceipt(payload, expected) {
    var result = payload && payload.result;
    if (!payload || payload.schemaVersion !== RESPONSE_SCHEMA || payload.ok !== true || payload.finalAuthority !== false
        || !result || result.schemaVersion !== AUDIT_RECEIPT_SCHEMA
        || result.requestId !== expected.requestId || result.auditId !== expected.auditId
        || result.persisted !== true || result.finalAuthority !== false) {
      throw new Error('Bridge audit receipt is invalid or stale');
    }
    return result;
  }

  function buildAuditRequest(eventType, payload, requestId, auditId) {
    var normalizedRequestId = normalizeRequestId(requestId);
    var normalizedAuditId = normalizeAuditId(auditId);
    var normalizedEventType = String(eventType || '').trim();
    if (!normalizedRequestId || !normalizedAuditId || !/^[a-z][a-z0-9_.:-]{0,63}$/.test(normalizedEventType)) {
      throw new Error('Audit request identifiers or event type are invalid');
    }
    return {
      schemaVersion: AUDIT_EVENT_SCHEMA,
      requestId: normalizedRequestId,
      auditId: normalizedAuditId,
      eventType: normalizedEventType,
      payload: Object.assign({}, objectOrEmpty(payload), { finalAuthority: false }),
    };
  }

  globalThis.SSMcpHybridAssistCore = Object.freeze({
    version: VERSION,
    mode: MODE,
    featureFlag: FEATURE_FLAG,
    buildFlags: BUILD_FLAGS,
    eventProtocol: EVENT_PROTOCOL,
    responseSchema: RESPONSE_SCHEMA,
    batchSchema: BATCH_SCHEMA,
    mergedRankingSchema: MERGED_RANKING_SCHEMA,
    auditEventSchema: AUDIT_EVENT_SCHEMA,
    auditReceiptSchema: AUDIT_RECEIPT_SCHEMA,
    minBridgeVersion: MIN_BRIDGE_VERSION,
    scoringPolicyId: SCORING_POLICY_ID,
    scoringPolicyHash: fnv1a(SCORING_POLICY_ID),
    normalizeAsin: normalizeAsin,
    normalizeRequestId: normalizeRequestId,
    normalizeAuditId: normalizeAuditId,
    createAuditId: createAuditId,
    validateBridgeOrigin: validateBridgeOrigin,
    versionAtLeast: versionAtLeast,
    validateBridgeHealth: validateBridgeHealth,
    isFreshWindow: isFreshWindow,
    normalizeLookupRow: normalizeLookupRow,
    normalizeBatchResponse: normalizeBatchResponse,
    scoreBreakdown: scoreBreakdown,
    scoreFields: scoreFields,
    resolveMode: resolveMode,
    rankQueue: rankQueue,
    buildAdvisory: buildAdvisory,
    buildAuditRequest: buildAuditRequest,
    validateAuditReceipt: validateAuditReceipt,
    fnv1a: fnv1a,
  });

  if (typeof document === 'undefined' || !document.documentElement) return;

  var bridgeOrigin = validateBridgeOrigin(DEFAULT_BRIDGE_URL);
  var sessionToken = '';
  var bridgeVersion = '';
  var bridgeRunId = '';
  var bridgePolicyVersion = '';
  var bridgePolicySha256 = '';
  var bridgeTestMode = false;
  var busy = false;

  function isEnabled() {
    return sessionStorage.getItem(ENABLE_KEY) === '1';
  }

  function setEnabled(value) {
    if (value) sessionStorage.setItem(ENABLE_KEY, '1');
    else sessionStorage.removeItem(ENABLE_KEY);
  }

  function requestJson(method, path, body) {
    return new Promise(function (resolve, reject) {
      var payload = body ? JSON.stringify(body) : '';
      GM_xmlhttpRequest({
        method: method,
        url: bridgeOrigin + path,
        headers: Object.assign(
          sessionToken ? { 'X-MCP-Hybrid-Token': sessionToken } : {},
          body ? { 'Content-Type': 'application/json' } : {},
        ),
        data: payload || undefined,
        timeout: 8000,
        onload: function (response) {
          var parsed;
          try { parsed = JSON.parse(response.responseText || '{}'); }
          catch (_) { reject(new Error('Bridge returned invalid JSON')); return; }
          if (response.status < 200 || response.status >= 300 || parsed.ok !== true) {
            reject(new Error(parsed.message || ('Bridge HTTP ' + response.status)));
            return;
          }
          resolve(parsed);
        },
        ontimeout: function () { reject(new Error('Bridge request timed out')); },
        onerror: function () { reject(new Error('Bridge unavailable')); },
      });
    });
  }

  async function forwardAuditEvent(eventType, payload, requestId, auditId) {
    if (!BUILD_FLAGS.requiredAuditRelayV1 || !isEnabled() || !sessionToken) throw new Error('Bridge not connected for required audit');
    var request = buildAuditRequest(eventType, payload, requestId, auditId);
    var response = await requestJson('POST', '/api/v1/audit/events', request);
    return validateAuditReceipt(response, { requestId: request.requestId, auditId: request.auditId });
  }

  function mountPanel() {
    var existing = document.getElementById(PANEL_ID);
    if (existing) {
      if (existing.getAttribute('data-ss-mcp-version') !== VERSION) {
        existing.setAttribute('data-ss-mcp-version-conflict', VERSION);
        var conflictStatus = existing.querySelector('#ss-mcp-assist-status');
        if (conflictStatus) {
          conflictStatus.textContent = 'Version conflict: disable the other Assist version and reload.';
          conflictStatus.style.color = '#b91c1c';
        }
      }
      return existing;
    }
    var panel = document.createElement('section');
    panel.id = PANEL_ID;
    panel.setAttribute('data-ss-mcp-version', VERSION);
    panel.setAttribute('data-ss-mcp-mode', MODE);
    panel.setAttribute('data-ss-mcp-feature-flag', FEATURE_FLAG);
    panel.setAttribute('data-ss-mcp-feature-enabled', 'false');
    panel.setAttribute('data-ss-mcp-final-authority', 'false');
    panel.setAttribute('data-ss-mcp-event-protocol', EVENT_PROTOCOL);
    panel.setAttribute('data-ss-mcp-audit-required', 'true');
    panel.setAttribute('data-ss-mcp-bridge-min-version', MIN_BRIDGE_VERSION);
    panel.style.cssText = 'position:fixed;right:12px;bottom:12px;z-index:2147483646;width:310px;padding:10px;border:1px solid #777;background:#fff;color:#111;font:13px/1.4 Arial,sans-serif;box-shadow:0 4px 16px rgba(0,0,0,.18)';
    panel.innerHTML = [
      '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px">',
      '<strong>MCP Hybrid Assist 0.3.0</strong>',
      '<label><input id="ss-mcp-assist-enabled" type="checkbox"> Enable</label>',
      '</div>',
      '<div id="ss-mcp-assist-status" style="margin-top:6px;color:#555">Disconnected</div>',
      '<textarea id="ss-mcp-assist-queue" rows="6" style="box-sizing:border-box;width:100%;margin-top:8px;font:12px/1.35 Consolas,monospace" placeholder="One ASIN per line"></textarea>',
      '<div style="display:flex;gap:6px;margin-top:6px">',
      '<button id="ss-mcp-assist-connect" type="button">Connect</button>',
      '<button id="ss-mcp-assist-rank" type="button">Rank</button>',
      '<button id="ss-mcp-assist-copy" type="button">Copy</button>',
      '</div>',
      '<label style="display:block;margin-top:6px">Mode <select id="ss-mcp-assist-mode"><option value="auto">Auto</option><option value="original">Baseline</option><option value="focus5">Focus 5</option><option value="balanced">Balanced (explicit)</option></select></label>',
      '<div style="margin-top:6px;color:#991b1b">Reorder only. A-F authority unchanged.</div>',
    ].join('');
    document.documentElement.appendChild(panel);
    var enabled = panel.querySelector('#ss-mcp-assist-enabled');
    enabled.checked = isEnabled();
    panel.setAttribute('data-ss-mcp-feature-enabled', enabled.checked ? 'true' : 'false');
    enabled.addEventListener('change', function () {
      setEnabled(enabled.checked);
      panel.setAttribute('data-ss-mcp-feature-enabled', enabled.checked ? 'true' : 'false');
      if (!enabled.checked) {
        sessionToken = '';
        bridgeVersion = '';
        bridgeRunId = '';
        bridgePolicyVersion = '';
        bridgePolicySha256 = '';
        bridgeTestMode = false;
        panel.removeAttribute('data-ss-mcp-bridge-version');
      }
    });
    panel.querySelector('#ss-mcp-assist-connect').addEventListener('click', connect);
    panel.querySelector('#ss-mcp-assist-rank').addEventListener('click', rankPanelQueue);
    panel.querySelector('#ss-mcp-assist-copy').addEventListener('click', function () {
      GM_setClipboard(panel.querySelector('#ss-mcp-assist-queue').value, 'text');
      renderStatus('Copied');
    });
    return panel;
  }

  function renderStatus(value) {
    mountPanel().querySelector('#ss-mcp-assist-status').textContent = value;
  }

  async function connect() {
    if (!isEnabled()) { renderStatus('Enable Assist 0.3.0 first'); return; }
    var token = window.prompt('Bridge session token', '');
    if (!token) return;
    sessionToken = token;
    try {
      var health = validateBridgeHealth(await requestJson('GET', '/api/v1/health'));
      var ledger = await requestJson('GET', '/api/v1/ledger');
      bridgeVersion = health.version;
      bridgeRunId = health.runId;
      bridgePolicyVersion = health.policyVersion;
      bridgePolicySha256 = health.policySha256;
      bridgeTestMode = health.testMode;
      var panel = mountPanel();
      panel.setAttribute('data-ss-mcp-bridge-version', bridgeVersion);
      panel.setAttribute('data-ss-mcp-bridge-run-id', bridgeRunId);
      renderStatus('Connected to Bridge ' + bridgeVersion + '; ledger ' + ledger.budget.monthlyUsed + '/' + ledger.budget.officialMonthlyLimit);
    } catch (error) {
      sessionToken = '';
      bridgeVersion = '';
      bridgeRunId = '';
      bridgePolicyVersion = '';
      bridgePolicySha256 = '';
      bridgeTestMode = false;
      renderStatus(error.message);
    }
  }

  async function lookupQueue(asins) {
    var unique = Array.from(new Set(asins));
    var evidenceByAsin = {};
    for (var offset = 0; offset < unique.length; offset += 40) {
      var chunk = unique.slice(offset, offset + 40);
      var payload = await requestJson('POST', '/api/v1/evidence/batch', { asins: chunk });
      var normalized = normalizeBatchResponse(payload, chunk, Date.now());
      if (!normalized.ok) throw new Error(normalized.reason);
      normalized.rows.forEach(function (row) { evidenceByAsin[row.asin] = row; });
    }
    return evidenceByAsin;
  }

  function rankingAuditPayload(result, evidenceByAsin) {
    var lookups = Object.keys(evidenceByAsin || {}).map(function (asin) { return evidenceByAsin[asin]; });
    var evidenceIds = Array.from(new Set([].concat.apply([], lookups.map(function (row) {
      return Array.isArray(row.evidenceIds) ? row.evidenceIds : [];
    })))).sort();
    var capturedAt = lookups.map(function (row) { return String(row.capturedAt || ''); }).filter(Boolean).sort();
    return {
      schemaVersion: 'sellerSpriteMcpRankingAudit/v1',
      assistVersion: VERSION,
      bridgeVersion: bridgeVersion,
      bridgeRunId: bridgeRunId,
      bridgePolicyVersion: bridgePolicyVersion,
      bridgePolicySha256: bridgePolicySha256,
      bridgeTestMode: bridgeTestMode,
      scoringPolicyId: SCORING_POLICY_ID,
      scoringPolicyHash: fnv1a(SCORING_POLICY_ID),
      eventProtocol: EVENT_PROTOCOL,
      requestedMode: result.requestedMode,
      mode: result.mode,
      balancedExplicit: result.balancedExplicit,
      count: result.original.length,
      originalOrderHash: fnv1a(result.original.join('\n')),
      rankedOrderHash: fnv1a(result.ranked.join('\n')),
      multisetHash: fnv1a(result.original.slice().sort().join('|')),
      usableForRankingCount: lookups.filter(function (row) { return row.usableForRanking === true; }).length,
      browserFallbackRequiredCount: lookups.filter(function (row) { return row.browserFallbackRequired !== false; }).length,
      mergedRankingCount: lookups.filter(function (row) { return row.source === 'mergedRanking'; }).length,
      legacyFallbackCount: lookups.filter(function (row) { return row.source === 'legacyResults'; }).length,
      evidenceIdCount: evidenceIds.length,
      evidenceSetHash: fnv1a(evidenceIds.join('|')),
      evidenceCapturedAtFirst: capturedAt.length ? capturedAt[0] : '',
      evidenceCapturedAtLast: capturedAt.length ? capturedAt[capturedAt.length - 1] : '',
      finalAuthority: false,
      allowedAction: 'reorder_only',
      batchCreated: false,
      batchStarted: false,
    };
  }

  async function rankAsins(asins, requestedMode, requestId, options) {
    if (!isEnabled() || !sessionToken || !versionAtLeast(bridgeVersion, MIN_BRIDGE_VERSION)) {
      throw new Error('Bridge 0.3.0+ is not connected');
    }
    var evidence = await lookupQueue(asins);
    var normalizedRequestId = normalizeRequestId(requestId) || createRequestId('assist');
    var result = Object.assign({}, rankQueue(asins, evidence, requestedMode, options), {
      requestId: normalizedRequestId,
      eventProtocol: EVENT_PROTOCOL,
      assistVersion: VERSION,
      auditRequired: true,
    });
    var auditId = createAuditId('rank', normalizedRequestId, result.original.join('|'));
    var receipt = await forwardAuditEvent('ranking_completed', rankingAuditPayload(result, evidence), normalizedRequestId, auditId);
    result.rankingAudit = receipt;
    result.rankingAuditConfirmed = true;
    window.dispatchEvent(new CustomEvent(RANKED_EVENT, { detail: result }));
    return result;
  }

  async function rankPanelQueue() {
    if (busy) return;
    var panel = mountPanel();
    var asins = panel.querySelector('#ss-mcp-assist-queue').value.split(/\s+/).map(normalizeAsin).filter(Boolean);
    if (!asins.length) { renderStatus('Queue is empty'); return; }
    busy = true;
    try {
      var requestedMode = panel.querySelector('#ss-mcp-assist-mode').value;
      var result = await rankAsins(asins, requestedMode, createRequestId('assist-manual'), {
        balancedExplicit: requestedMode === 'balanced',
      });
      panel.querySelector('#ss-mcp-assist-queue').value = result.ranked.join('\n');
      renderStatus('Audited ' + result.mode + ' order for ' + result.ranked.length + '; browser gates remain required');
    } catch (error) {
      renderStatus(error.message);
    } finally {
      busy = false;
    }
  }

  function emitError(name, detail) {
    window.dispatchEvent(new CustomEvent(name, { detail: Object.assign({
      eventProtocol: EVENT_PROTOCOL,
      finalAuthority: false,
    }, detail) }));
  }

  window.addEventListener(REQUEST_EVENT, function (event) {
    var detail = event && event.detail ? event.detail : {};
    var requestId = normalizeRequestId(detail.requestId) || createRequestId('assist-event');
    if (detail.eventProtocol !== EVENT_PROTOCOL || detail.finalAuthority !== false || detail.allowedAction !== 'reorder_only') {
      emitError(RANK_ERROR_EVENT, { requestId: requestId, message: 'Rank request protocol or authority mismatch' });
      return;
    }
    rankAsins(detail.asins || [], detail.mode || 'auto', requestId, {
      balancedExplicit: detail.balancedExplicit === true,
    }).catch(function (error) {
      emitError(RANK_ERROR_EVENT, { requestId: requestId, message: error.message });
    });
  });

  window.addEventListener(AUDIT_REQUEST_EVENT, function (event) {
    var detail = event && event.detail ? event.detail : {};
    var requestId = normalizeRequestId(detail.requestId);
    var auditId = normalizeAuditId(detail.auditId);
    if (detail.eventProtocol !== EVENT_PROTOCOL || detail.finalAuthority !== false || !requestId || !auditId) {
      emitError(AUDIT_ERROR_EVENT, { requestId: requestId, auditId: auditId, message: 'Audit request protocol or identifiers are invalid' });
      return;
    }
    forwardAuditEvent(detail.eventType, detail.payload, requestId, auditId).then(function (receipt) {
      window.dispatchEvent(new CustomEvent(AUDIT_CONFIRMED_EVENT, { detail: {
        eventProtocol: EVENT_PROTOCOL,
        requestId: requestId,
        auditId: auditId,
        receipt: receipt,
        persisted: true,
        finalAuthority: false,
      } }));
    }).catch(function (error) {
      emitError(AUDIT_ERROR_EVENT, { requestId: requestId, auditId: auditId, message: error.message });
    });
  });

  mountPanel();
})();
