// ==UserScript==
// @name         SellerSprite MCP Hybrid Assist 0.2.0
// @namespace    amazon-products
// @version      0.2.0
// @description  Rank queues from loopback MCP shadow evidence without changing A-F decisions.
// @match        https://www.amazon.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_setClipboard
// @connect      127.0.0.1
// @connect      localhost
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  var VERSION = '0.2.0';
  var MODE = 'shadow-assist';
  var FEATURE_FLAG = 'ENABLE_MCP_HYBRID_ASSIST_V0_2';
  var RESPONSE_SCHEMA = 'sellerSpriteMcpHybridResponse/v1';
  var BATCH_SCHEMA = 'sellerSpriteMcpBatchLookup/v1';
  var DEFAULT_BRIDGE_URL = 'http://127.0.0.1:8766';
  var ENABLE_KEY = 'ss-mcp-hybrid-assist-enabled';
  var PANEL_ID = 'ss-mcp-hybrid-assist-panel';
  var ASIN_RE = /^B0[A-Z0-9]{8}$/;

  function normalizeAsin(value) {
    var text = String(value || '').trim().toUpperCase();
    return ASIN_RE.test(text) ? text : '';
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

  function finite(value) {
    var number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function normalizeLookupRow(row, expectedAsin) {
    var asin = normalizeAsin(expectedAsin);
    if (!row || normalizeAsin(row.asin) !== asin || row.finalAuthority !== false) {
      return { asin: asin, usable: false, fields: {}, finalAuthority: false, reason: 'row_mismatch' };
    }
    var results = Array.isArray(row.results) ? row.results : [];
    var usable = results.find(function (item) {
      var evidence = item && item.evidence;
      return item && item.usableForShadow === true && item.usableForFinal === false
        && evidence && normalizeAsin(evidence.targetAsin) === asin
        && normalizeAsin(evidence.actualAsin) === asin
        && evidence.finalAuthority === false;
    });
    return {
      asin: asin,
      usable: Boolean(usable),
      fields: usable && usable.evidence && usable.evidence.fields ? usable.evidence.fields : {},
      finalAuthority: false,
      reason: usable ? '' : (results.length ? 'no_usable_exact_evidence' : 'no_evidence'),
    };
  }

  function normalizeBatchResponse(payload, expectedAsins) {
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
    var normalized = rows.map(function (row, index) { return normalizeLookupRow(row, expected[index]); });
    return { ok: true, rows: normalized, finalAuthority: false, reason: '' };
  }

  function scoreFields(fields) {
    var source = fields && typeof fields === 'object' ? fields : {};
    var score = 0;
    var price = finite(source.price);
    var rating = finite(source.rating);
    var reviews = finite(source.reviews);
    if (price !== null && price >= 9.9 && price <= 50) score += 2;
    if (rating !== null && rating >= 4) score += 1;
    if (reviews !== null && reviews <= 115) score += 1;
    if (source.dimensions || source.packageDimensions) score += 2;
    if (source.priceTrendClass === 'stable' || source.priceTrendClass === 'rising') score += 3;
    return score;
  }

  function rankQueue(asins, evidenceByAsin, mode) {
    var rows = (asins || []).map(function (value, index) {
      var asin = normalizeAsin(value);
      var evidence = evidenceByAsin && evidenceByAsin[asin] ? evidenceByAsin[asin] : { usable: false, fields: {} };
      var score = evidence.usable ? scoreFields(evidence.fields) : 0;
      var weight = mode === 'focus5' ? 1000 : 7;
      return {
        asin: asin,
        index: index,
        score: score,
        usable: evidence.usable === true,
        priority: score * weight - index,
        finalAuthority: false,
      };
    });
    if (rows.some(function (row) { return !row.asin; })) throw new Error('Queue contains an invalid ASIN');
    var ranked = rows.slice().sort(function (left, right) {
      return right.priority - left.priority || left.index - right.index;
    });
    return {
      mode: mode === 'focus5' ? 'focus5' : 'balanced',
      original: rows.map(function (row) { return row.asin; }),
      ranked: ranked.map(function (row) { return row.asin; }),
      rows: ranked,
      multisetUnchanged: rows.map(function (row) { return row.asin; }).sort().join('|') === ranked.map(function (row) { return row.asin; }).sort().join('|'),
      finalAuthority: false,
      allowedAction: 'reorder_only',
    };
  }

  function buildAdvisory(lookup) {
    var fields = lookup && lookup.fields ? lookup.fields : {};
    return {
      asin: lookup ? lookup.asin : '',
      usable: Boolean(lookup && lookup.usable),
      score: lookup && lookup.usable ? scoreFields(fields) : 0,
      fields: fields,
      finalAuthority: false,
      gateCProvided: false,
      allowedAction: 'reorder_only',
      forbiddenActions: ['pass_gate', 'write_runner_result', 'write_strict_history', 'skip_current_acceptance'],
    };
  }

  globalThis.SSMcpHybridAssistCore = Object.freeze({
    version: VERSION,
    mode: MODE,
    featureFlag: FEATURE_FLAG,
    responseSchema: RESPONSE_SCHEMA,
    batchSchema: BATCH_SCHEMA,
    normalizeAsin: normalizeAsin,
    validateBridgeOrigin: validateBridgeOrigin,
    normalizeLookupRow: normalizeLookupRow,
    normalizeBatchResponse: normalizeBatchResponse,
    scoreFields: scoreFields,
    rankQueue: rankQueue,
    buildAdvisory: buildAdvisory,
  });

  if (typeof document === 'undefined' || !document.documentElement) return;

  var bridgeOrigin = DEFAULT_BRIDGE_URL;
  var sessionToken = '';
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
          { 'X-MCP-Hybrid-Token': sessionToken },
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

  function mountPanel() {
    var existing = document.getElementById(PANEL_ID);
    if (existing) return existing;
    var panel = document.createElement('section');
    panel.id = PANEL_ID;
    panel.setAttribute('data-ss-mcp-version', VERSION);
    panel.setAttribute('data-ss-mcp-mode', MODE);
    panel.setAttribute('data-ss-mcp-feature-flag', FEATURE_FLAG);
    panel.setAttribute('data-ss-mcp-final-authority', 'false');
    panel.style.cssText = 'position:fixed;right:12px;bottom:12px;z-index:2147483646;width:300px;padding:10px;border:1px solid #777;background:#fff;color:#111;font:13px/1.4 Arial,sans-serif;box-shadow:0 4px 16px rgba(0,0,0,.18)';
    panel.innerHTML = [
      '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px">',
      '<strong>MCP Hybrid Assist 0.2.0</strong>',
      '<label><input id="ss-mcp-assist-enabled" type="checkbox"> Enable</label>',
      '</div>',
      '<div id="ss-mcp-assist-status" style="margin-top:6px;color:#555">Disconnected</div>',
      '<textarea id="ss-mcp-assist-queue" rows="6" style="box-sizing:border-box;width:100%;margin-top:8px;font:12px/1.35 Consolas,monospace" placeholder="One ASIN per line"></textarea>',
      '<div style="display:flex;gap:6px;margin-top:6px">',
      '<button id="ss-mcp-assist-connect" type="button">Connect</button>',
      '<button id="ss-mcp-assist-rank" type="button">Rank</button>',
      '<button id="ss-mcp-assist-copy" type="button">Copy</button>',
      '</div>',
      '<label style="display:block;margin-top:6px">Mode <select id="ss-mcp-assist-mode"><option value="balanced">Balanced</option><option value="focus5">Focus 5</option></select></label>',
      '<div style="margin-top:6px;color:#991b1b">Reorder only. A-F authority unchanged.</div>',
    ].join('');
    document.documentElement.appendChild(panel);
    var enabled = panel.querySelector('#ss-mcp-assist-enabled');
    enabled.checked = isEnabled();
    enabled.addEventListener('change', function () {
      setEnabled(enabled.checked);
      if (!enabled.checked) sessionToken = '';
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
    if (!isEnabled()) { renderStatus('Enable first'); return; }
    var token = window.prompt('Bridge session token', '');
    if (!token) return;
    sessionToken = token;
    try {
      var ledger = await requestJson('GET', '/api/v1/ledger');
      renderStatus('Connected; local ledger ' + ledger.budget.monthlyUsed + '/' + ledger.budget.officialMonthlyLimit);
    } catch (error) {
      sessionToken = '';
      renderStatus(error.message);
    }
  }

  async function lookupQueue(asins) {
    var unique = Array.from(new Set(asins));
    var evidenceByAsin = {};
    for (var offset = 0; offset < unique.length; offset += 40) {
      var chunk = unique.slice(offset, offset + 40);
      var payload = await requestJson('POST', '/api/v1/evidence/batch', { asins: chunk });
      var normalized = normalizeBatchResponse(payload, chunk);
      if (!normalized.ok) throw new Error(normalized.reason);
      normalized.rows.forEach(function (row) { evidenceByAsin[row.asin] = row; });
    }
    return evidenceByAsin;
  }

  async function rankAsins(asins, mode) {
    if (!isEnabled() || !sessionToken) throw new Error('Bridge not connected');
    var evidence = await lookupQueue(asins);
    var result = rankQueue(asins, evidence, mode);
    window.dispatchEvent(new CustomEvent('ss-mcp-hybrid:queue-ranked', { detail: result }));
    return result;
  }

  async function rankPanelQueue() {
    if (busy) return;
    var panel = mountPanel();
    var asins = panel.querySelector('#ss-mcp-assist-queue').value.split(/\s+/).map(normalizeAsin).filter(Boolean);
    if (!asins.length) { renderStatus('Queue is empty'); return; }
    busy = true;
    try {
      var result = await rankAsins(asins, panel.querySelector('#ss-mcp-assist-mode').value);
      panel.querySelector('#ss-mcp-assist-queue').value = result.ranked.join('\n');
      renderStatus('Ranked ' + result.ranked.length + '; evidence does not pass gates');
    } catch (error) {
      renderStatus(error.message);
    } finally {
      busy = false;
    }
  }

  window.addEventListener('ss-mcp-hybrid:rank-request', function (event) {
    var detail = event && event.detail ? event.detail : {};
    rankAsins(detail.asins || [], detail.mode || 'balanced').catch(function (error) {
      window.dispatchEvent(new CustomEvent('ss-mcp-hybrid:rank-error', { detail: { message: error.message, finalAuthority: false } }));
    });
  });

  mountPanel();
})();
