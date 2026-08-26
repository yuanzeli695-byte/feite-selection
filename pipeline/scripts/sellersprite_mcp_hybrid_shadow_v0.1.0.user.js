// ==UserScript==
// @name         SellerSprite MCP Hybrid Shadow 0.1.0
// @namespace    amazon-products
// @version      0.1.0
// @description  Observe loopback MCP evidence without changing SellerSprite Runner decisions.
// @match        https://www.amazon.com/*
// @grant        GM_xmlhttpRequest
// @connect      127.0.0.1
// @connect      localhost
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  var VERSION = '0.1.0';
  var MODE = 'shadow';
  var FEATURE_FLAG = 'MCP_SHADOW_V0_1';
  var PROTOCOL_VERSION = 'sellerSpriteMcpHybridProtocol/v1';
  var RESPONSE_SCHEMA = 'sellerSpriteMcpHybridResponse/v1';
  var DEFAULT_BRIDGE_URL = 'http://127.0.0.1:8766';
  var SESSION_ENABLE_KEY = 'ss-mcp-hybrid-shadow-enabled';
  var PANEL_ID = 'ss-mcp-hybrid-shadow-panel';
  var ASIN_RE = /^B0[A-Z0-9]{8}$/;

  function normalizeAsin(value) {
    var text = String(value || '').trim().toUpperCase();
    return ASIN_RE.test(text) ? text : '';
  }

  function asinFromUrl(urlValue) {
    try {
      var url = new URL(String(urlValue || ''));
      var match = url.pathname.match(/\/(?:dp|gp\/product)\/([A-Z0-9]{10})(?:[/?]|$)/i);
      return normalizeAsin(match && match[1]);
    } catch (_) {
      return '';
    }
  }

  function validateBridgeOrigin(value) {
    var url;
    try {
      url = new URL(String(value || '').trim());
    } catch (_) {
      throw new Error('Bridge URL is invalid');
    }
    if (url.protocol !== 'http:') throw new Error('Bridge must use loopback HTTP');
    if (url.hostname !== '127.0.0.1' && url.hostname !== 'localhost') {
      throw new Error('Bridge host must be 127.0.0.1 or localhost');
    }
    if (url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
      throw new Error('Bridge URL must contain only scheme, host, and port');
    }
    return url.origin;
  }

  function normalizeLookupResponse(payload, expectedAsin) {
    var asin = normalizeAsin(expectedAsin);
    if (!payload || payload.schemaVersion !== RESPONSE_SCHEMA || payload.ok !== true) {
      return {
        ok: false,
        asin: asin,
        evidenceCount: 0,
        usableCount: 0,
        fallbackCount: 0,
        finalAuthority: false,
        reason: 'invalid_bridge_response',
      };
    }
    if (normalizeAsin(payload.asin) !== asin || payload.finalAuthority !== false) {
      return {
        ok: false,
        asin: asin,
        evidenceCount: 0,
        usableCount: 0,
        fallbackCount: 0,
        finalAuthority: false,
        reason: 'asin_or_authority_mismatch',
      };
    }
    var rows = Array.isArray(payload.results) ? payload.results : [];
    var usable = rows.filter(function (row) {
      return row && row.usableForShadow === true && row.usableForFinal === false;
    });
    var fallback = rows.filter(function (row) {
      return row && row.fallbackRequired === true;
    });
    return {
      ok: true,
      asin: asin,
      evidenceCount: rows.length,
      usableCount: usable.length,
      fallbackCount: fallback.length,
      finalAuthority: false,
      reason: rows.length ? '' : 'no_evidence',
      results: rows,
    };
  }

  function budgetState(summary) {
    if (!summary || !Number.isFinite(Number(summary.monthlyUsed))) return 'unknown';
    if (summary.state === 'operational_cap') return 'blocked';
    if (summary.state === 'warning') return 'warning';
    return 'normal';
  }

  function fieldComparison(evidenceFields, browserFields) {
    var source = evidenceFields && typeof evidenceFields === 'object' ? evidenceFields : {};
    var browser = browserFields && typeof browserFields === 'object' ? browserFields : {};
    var keys = Array.from(new Set(Object.keys(source).concat(Object.keys(browser)))).sort();
    return keys.map(function (key) {
      var mcpValue = Object.prototype.hasOwnProperty.call(source, key) ? source[key] : null;
      var browserValue = Object.prototype.hasOwnProperty.call(browser, key) ? browser[key] : null;
      return {
        field: key,
        mcpValue: mcpValue,
        browserValue: browserValue,
        equal: JSON.stringify(mcpValue) === JSON.stringify(browserValue),
      };
    });
  }

  globalThis.SSMcpHybridShadowCore = Object.freeze({
    version: VERSION,
    mode: MODE,
    featureFlag: FEATURE_FLAG,
    protocolVersion: PROTOCOL_VERSION,
    responseSchema: RESPONSE_SCHEMA,
    normalizeAsin: normalizeAsin,
    asinFromUrl: asinFromUrl,
    validateBridgeOrigin: validateBridgeOrigin,
    normalizeLookupResponse: normalizeLookupResponse,
    budgetState: budgetState,
    fieldComparison: fieldComparison,
  });

  if (typeof document === 'undefined' || !document.documentElement) return;

  var bridgeOrigin = DEFAULT_BRIDGE_URL;
  var sessionToken = '';
  var lastUrl = location.href;
  var requestInFlight = false;

  function requestJson(path, token) {
    return new Promise(function (resolve, reject) {
      GM_xmlhttpRequest({
        method: 'GET',
        url: bridgeOrigin + path,
        headers: token ? { 'X-MCP-Hybrid-Token': token } : {},
        timeout: 8000,
        onload: function (response) {
          var payload;
          try {
            payload = JSON.parse(response.responseText || '{}');
          } catch (_) {
            reject(new Error('Bridge returned invalid JSON'));
            return;
          }
          if (response.status < 200 || response.status >= 300 || payload.ok !== true) {
            reject(new Error(payload.message || ('Bridge HTTP ' + response.status)));
            return;
          }
          resolve(payload);
        },
        ontimeout: function () { reject(new Error('Bridge request timed out')); },
        onerror: function () { reject(new Error('Bridge is unavailable')); },
      });
    });
  }

  function isEnabled() {
    return sessionStorage.getItem(SESSION_ENABLE_KEY) === '1';
  }

  function setEnabled(enabled) {
    if (enabled) sessionStorage.setItem(SESSION_ENABLE_KEY, '1');
    else sessionStorage.removeItem(SESSION_ENABLE_KEY);
  }

  function mountPanel() {
    if (document.getElementById(PANEL_ID)) return document.getElementById(PANEL_ID);
    var panel = document.createElement('section');
    panel.id = PANEL_ID;
    panel.setAttribute('data-ss-mcp-protocol-version', PROTOCOL_VERSION);
    panel.setAttribute('data-ss-mcp-mode', MODE);
    panel.setAttribute('data-ss-mcp-feature-flag', FEATURE_FLAG);
    panel.setAttribute('data-ss-mcp-final-authority', 'false');
    panel.style.cssText = [
      'position:fixed',
      'right:12px',
      'bottom:12px',
      'z-index:2147483646',
      'width:280px',
      'font:13px/1.45 Arial,sans-serif',
      'color:#1f2937',
      'background:#fff',
      'border:1px solid #9ca3af',
      'box-shadow:0 4px 16px rgba(0,0,0,.18)',
      'padding:10px',
    ].join(';');
    panel.innerHTML = [
      '<div style="display:flex;align-items:center;justify-content:space-between;gap:8px">',
      '<strong>MCP 影子观察 0.1.0</strong>',
      '<label style="white-space:nowrap"><input id="ss-mcp-enabled" type="checkbox"> 启用</label>',
      '</div>',
      '<div id="ss-mcp-status" style="margin-top:8px;color:#4b5563">未连接</div>',
      '<div id="ss-mcp-asin" style="margin-top:4px">ASIN: -</div>',
      '<div id="ss-mcp-evidence" style="margin-top:4px">证据: -</div>',
      '<div style="display:flex;gap:6px;margin-top:8px">',
      '<button id="ss-mcp-connect" type="button">连接</button>',
      '<button id="ss-mcp-refresh" type="button">刷新</button>',
      '<button id="ss-mcp-origin" type="button" title="更改本机 Bridge 地址">地址</button>',
      '</div>',
      '<div style="margin-top:6px;color:#991b1b">仅对比，不参与 A-F 放行</div>',
    ].join('');
    document.documentElement.appendChild(panel);
    var enabledInput = panel.querySelector('#ss-mcp-enabled');
    enabledInput.checked = isEnabled();
    enabledInput.addEventListener('change', function () {
      setEnabled(enabledInput.checked);
      if (!enabledInput.checked) {
        sessionToken = '';
        renderStatus('已停用', '-');
      }
    });
    panel.querySelector('#ss-mcp-connect').addEventListener('click', connect);
    panel.querySelector('#ss-mcp-refresh').addEventListener('click', refreshEvidence);
    panel.querySelector('#ss-mcp-origin').addEventListener('click', changeOrigin);
    return panel;
  }

  function renderStatus(status, evidenceText) {
    var panel = mountPanel();
    var asin = asinFromUrl(location.href);
    panel.querySelector('#ss-mcp-status').textContent = status;
    panel.querySelector('#ss-mcp-asin').textContent = 'ASIN: ' + (asin || '-');
    panel.querySelector('#ss-mcp-evidence').textContent = '证据: ' + evidenceText;
  }

  async function connect() {
    if (!isEnabled()) {
      renderStatus('请先启用影子观察', '-');
      return;
    }
    var entered = window.prompt('输入本次 Bridge 会话令牌。令牌只保存在当前页面内存中。', '');
    if (!entered) return;
    try {
      await requestJson('/api/v1/ledger', entered);
      sessionToken = entered;
      renderStatus('Bridge 已连接', '-');
      await refreshEvidence();
    } catch (error) {
      sessionToken = '';
      renderStatus('连接失败: ' + error.message, '-');
    }
  }

  function changeOrigin() {
    var entered = window.prompt('本机 Bridge 地址', bridgeOrigin);
    if (!entered) return;
    try {
      bridgeOrigin = validateBridgeOrigin(entered);
      sessionToken = '';
      renderStatus('地址已更新，请重新连接', '-');
    } catch (error) {
      renderStatus('地址无效: ' + error.message, '-');
    }
  }

  async function refreshEvidence() {
    var asin = asinFromUrl(location.href);
    if (!isEnabled()) {
      renderStatus('影子观察未启用', '-');
      return;
    }
    if (!sessionToken) {
      renderStatus('尚未连接 Bridge', '-');
      return;
    }
    if (!asin) {
      renderStatus('当前页面没有有效 ASIN', '-');
      return;
    }
    if (requestInFlight) return;
    requestInFlight = true;
    try {
      var payload = await requestJson('/api/v1/evidence?asin=' + encodeURIComponent(asin), sessionToken);
      var normalized = normalizeLookupResponse(payload, asin);
      if (!normalized.ok) {
        renderStatus('证据响应被拒绝: ' + normalized.reason, '-');
        return;
      }
      renderStatus(
        normalized.fallbackCount ? '存在回退项' : '影子证据已读取',
        normalized.evidenceCount + ' 条，可比较 ' + normalized.usableCount + ' 条',
      );
    } catch (error) {
      renderStatus('读取失败: ' + error.message, '-');
    } finally {
      requestInFlight = false;
    }
  }

  mountPanel();
  renderStatus(isEnabled() ? '尚未连接 Bridge' : '影子观察未启用', '-');
  window.setInterval(function () {
    if (location.href === lastUrl) return;
    lastUrl = location.href;
    renderStatus(sessionToken ? '页面已变化，正在刷新' : '页面已变化', '-');
    if (sessionToken && isEnabled()) refreshEvidence();
  }, 2000);
})();
