// ==UserScript==
// @name         SellerSprite Traffic Collector MVP
// @namespace    codex.amazon.product-selection
// @version      0.4.4
// @description  Collect recent SellerSprite traffic data and stop as soon as the strict 70% gate fails.
// @match        https://www.amazon.com/*
// @match        https://amazon.com/*
// @homepageURL  https://github.com/yuanzeli695-byte/sellersprite-userscripts
// @supportURL   https://github.com/yuanzeli695-byte/sellersprite-userscripts/issues
// @updateURL    https://raw.githubusercontent.com/yuanzeli695-byte/sellersprite-userscripts/main/scripts/sellersprite-traffic-collector.user.js
// @downloadURL  https://raw.githubusercontent.com/yuanzeli695-byte/sellersprite-userscripts/main/scripts/sellersprite-traffic-collector.user.js
// @grant        GM_setClipboard
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";

  var VERSION = "0.4.4";
  var PROTOCOL_VERSION = "1";
  var SCHEMA_VERSION = "sellerSpriteTraffic/v1";

  var labels = {
    total: "\u603b\u6d41\u91cf",
    natural: "\u81ea\u7136\u6d41\u91cf",
    sp: "SP\u5e7f\u544a\u6d41\u91cf",
    sb: "SB\u5e7f\u544a\u6d41\u91cf",
    sbv: "SBV\u5e7f\u544a\u6d41\u91cf"
  };

  var MAX_RECENT_WEEKS = 4;
  var MIN_REQUIRED_WEEKS = 3;
  var TRAFFIC_WINDOW_LABEL = "recent 4 weeks / min 3 weeks";

  var state = {
    running: false,
    lastResult: null,
    autoStarted: false,
    runSequence: 0
  };

  function delay(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms);
    });
  }

  function getAsin() {
    var match = location.href.match(/\/(?:dp|gp\/product)\/([A-Z0-9]{10})/i);
    return match ? match[1].toUpperCase() : "";
  }

  function sanitizedPageUrl() {
    var url = new URL(location.href);
    url.hash = "";
    url.searchParams.delete("ss-v3");
    url.searchParams.delete("ss-v3-hash");
    url.searchParams.delete("ss-v3-index");
    url.searchParams.delete("ss-auto");
    return url.toString();
  }

  function nextRunId() {
    state.runSequence += 1;
    return Date.now().toString(36) + "-" + state.runSequence.toString(36);
  }

  function safeText(value) {
    return value == null ? "" : String(value);
  }

  function parseNumber(text) {
    var match = safeText(text).match(/-?\d[\d,]*(?:\.\d+)?/);
    return match ? Number(match[0].replace(/,/g, "")) : null;
  }

  function pct(value) {
    return typeof value === "number" && Number.isFinite(value) ? value.toFixed(2) + "%" : "";
  }

  function weekSortKey(text) {
    var source = safeText(text);
    var match = source.match(/(20\d{2}).*?(\d{1,2}).*?(?:\u5468|\/)/);
    if (match) return Number(match[1]) * 100 + Number(match[2]);
    var dateMatch = source.match(/(20\d{2})-(\d{2})-(\d{2})/);
    if (!dateMatch) return null;
    var d = new Date(dateMatch[1] + "-" + dateMatch[2] + "-" + dateMatch[3] + "T00:00:00Z");
    if (Number.isNaN(d.getTime())) return null;
    var start = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    var day = Math.floor((d - start) / 86400000) + 1;
    return d.getUTCFullYear() * 100 + Math.ceil(day / 7);
  }

  function getChartElement() {
    var nodes = document.querySelectorAll(".echarts-trends-box");
    var best = null;
    var bestArea = 0;
    for (var i = 0; i < nodes.length; i += 1) {
      var target = nodes[i];
      var rect = target.getBoundingClientRect();
      var style = getComputedStyle(target);
      if (rect.width <= 0 || rect.height <= 0 || style.display === "none" || style.visibility === "hidden") continue;
      var area = rect.width * rect.height;
      if (area > bestArea) {
        best = target;
        bestArea = area;
      }
    }
    return best;
  }

  function hasSellerSpriteText() {
    var bodyText = document.body ? document.body.innerText || "" : "";
    return (
      bodyText.indexOf("SellerSprite") >= 0 ||
      bodyText.indexOf("v5.0.4") >= 0 ||
      bodyText.indexOf(labels.natural) >= 0 ||
      bodyText.indexOf(labels.sp) >= 0 ||
      !!document.querySelector(".echarts-trends-box")
    );
  }

  function pageStatusText() {
    return [
      "ASIN: " + getAsin(),
      "SellerSprite visible: " + (hasSellerSpriteText() ? "YES" : "NO"),
      "Traffic chart visible: " + (getChartElement() ? "YES" : "NO"),
      "URL: " + sanitizedPageUrl()
    ].join("\n");
  }

  function waitForChart(maxMs) {
    var started = Date.now();
    return new Promise(function (resolve) {
      function tick() {
        var chart = getChartElement();
        if (chart) {
          resolve(chart);
          return;
        }
        if (Date.now() - started >= maxMs) {
          resolve(null);
          return;
        }
        setStatus("Waiting for SellerSprite chart: " + Math.ceil((Date.now() - started) / 1000) + "s", "#344054");
        setTimeout(tick, 1000);
      }
      tick();
    });
  }

  function visibleTooltipTexts() {
    var chart = getChartElement();
    if (!chart) return [];
    var candidates = [chart].concat(Array.from(chart.querySelectorAll("div,span,p")));
    var overlays = document.querySelectorAll(".echarts-tooltip,[class*='echarts-tooltip'],[class*='chart-tooltip']");
    candidates = candidates.concat(Array.from(overlays));
    var all = Array.from(new Set(candidates));
    var hits = [];
    for (var i = 0; i < all.length; i += 1) {
      var el = all[i];
      var text = (el.innerText || el.textContent || "").trim();
      if (!text) continue;
      if (text.indexOf(labels.total) < 0 || text.indexOf(labels.natural) < 0) continue;
      var rect = el.getBoundingClientRect();
      var style = getComputedStyle(el);
      if (rect.width < 120 || rect.height < 50) continue;
      if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) continue;
      hits.push({
        text: text,
        rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height }
      });
    }
    hits.sort(function (a, b) {
      return a.rect.w * a.rect.h - b.rect.w * b.rect.h;
    });
    return hits.slice(0, 8);
  }

  function parseTip(text) {
    var lines = safeText(text)
      .split(/\n+/)
      .map(function (line) {
        return line.trim();
      })
      .filter(Boolean);
    var week = "";
    for (var i = 0; i < lines.length; i += 1) {
      if (/20\d{2}.*(?:\u5468|\d{2}\/\d{2})/.test(lines[i])) {
        week = lines[i];
        break;
      }
    }

    function findAfter(label) {
      var idx = -1;
      for (var i = 0; i < lines.length; i += 1) {
        if (lines[i].indexOf(label) >= 0) {
          idx = i;
          break;
        }
      }
      if (idx < 0) return null;
      for (var j = idx + 1; j < Math.min(lines.length, idx + 8); j += 1) {
        var value = parseNumber(lines[j]);
        if (value !== null) return value;
      }
      return null;
    }

    function shareAfter(label, nextLabel) {
      var idx = -1;
      for (var i = 0; i < lines.length; i += 1) {
        if (lines[i].indexOf(label) >= 0) {
          idx = i;
          break;
        }
      }
      if (idx < 0) return null;
      var end = -1;
      for (var j = idx + 1; j < lines.length; j += 1) {
        if (nextLabel && lines[j].indexOf(nextLabel) >= 0) {
          end = j;
          break;
        }
      }
      var segment = lines.slice(idx, end > idx ? end : Math.min(lines.length, idx + 12));
      for (var k = 0; k < segment.length; k += 1) {
        var match = segment[k].match(/(?:\u5360|\u5360\u6bd4|\u53c2\u4e0e)\s*(\d+(?:\.\d+)?)%/);
        if (match) return Number(match[1]);
      }
      return null;
    }

    return {
      week: week,
      weekSort: weekSortKey(week),
      totalTraffic: findAfter(labels.total),
      naturalTraffic: findAfter(labels.natural),
      naturalSharePct: shareAfter(labels.natural, labels.sp),
      spTraffic: findAfter(labels.sp),
      spSharePct: shareAfter(labels.sp, labels.sb),
      rawText: text
    };
  }

  function fireMouseAt(x, y, fallback) {
    var target = document.elementFromPoint(x, y) || fallback || document.body;
    var eventView = target.ownerDocument && target.ownerDocument.defaultView ? target.ownerDocument.defaultView : window;
    var PointerEventCtor = eventView.PointerEvent;
    var MouseEventCtor = eventView.MouseEvent;
    var common = {
      bubbles: true,
      cancelable: true,
      composed: true,
      clientX: x,
      clientY: y,
      screenX: window.screenX + x,
      screenY: window.screenY + y
    };
    if (PointerEventCtor) {
      try {
        target.dispatchEvent(new PointerEventCtor("pointerover", common));
        target.dispatchEvent(new PointerEventCtor("pointermove", common));
      } catch (error) {}
    }
    target.dispatchEvent(new MouseEventCtor("mouseover", common));
    target.dispatchEvent(new MouseEventCtor("mousemove", common));
  }

  function summarize(details, method) {
    details.sort(function (a, b) {
      return (b.weekSort || 0) - (a.weekSort || 0);
    });
    var shares = [];
    for (var i = 0; i < Math.min(4, details.length); i += 1) {
      var value = details[i].naturalSharePct;
      if (typeof value === "number" && Number.isFinite(value)) shares.push(value);
    }
    var avg = null;
    var min = null;
    if (shares.length) {
      var sum = 0;
      min = shares[0];
      for (var j = 0; j < shares.length; j += 1) {
        sum += shares[j];
        if (shares[j] < min) min = shares[j];
      }
      avg = sum / shares.length;
    }
    var pass70 = shares.length >= MIN_REQUIRED_WEEKS && min >= 70;
    var status = details.length ? "ok" : "no_data";
    var decision = "review";
    if (status === "ok" && shares.length >= 3) decision = pass70 ? "pass" : "fail";
    if (status === "ok" && shares.length < 3) decision = "sample_low_review";
    return {
      asin: getAsin(),
      status: status,
      decision: decision,
      latest: details[0] || null,
      recent4AvgNaturalSharePct: avg,
      recent4MinNaturalSharePct: min,
      pass70: pass70,
      weeksRead: shares.length,
      trafficWindow: TRAFFIC_WINDOW_LABEL,
      maxRecentWeeks: MAX_RECENT_WEEKS,
      details: details,
      method: method,
      url: sanitizedPageUrl(),
      collectedAt: new Date().toISOString()
    };
  }

  function finalizeResult(result, runId) {
    result = result || {};
    result.schemaVersion = SCHEMA_VERSION;
    result.collectorVersion = VERSION;
    result.runId = runId;
    result.url = sanitizedPageUrl();
    result.collectedAt = new Date().toISOString();
    return result;
  }

  function collectorErrorResult(error, runId) {
    return finalizeResult({
      asin: getAsin(),
      status: "error",
      decision: "review",
      latest: null,
      recent4AvgNaturalSharePct: null,
      recent4MinNaturalSharePct: null,
      pass70: false,
      weeksRead: 0,
      trafficWindow: TRAFFIC_WINDOW_LABEL,
      maxRecentWeeks: MAX_RECENT_WEEKS,
      details: [],
      method: "collector_exception",
      error: safeText(error && error.message ? error.message : error)
    }, runId);
  }

  function earlyTrafficFailureReason(details) {
    var ordered = (details || []).slice().sort(function (a, b) {
      return (b.weekSort || 0) - (a.weekSort || 0);
    });
    if (!ordered.length) return "";
    var latest = ordered[0].naturalSharePct;
    if (typeof latest === "number" && Number.isFinite(latest) && latest < 70) return "traffic_latest_below_70";
    for (var i = 0; i < ordered.length; i += 1) {
      var share = ordered[i].naturalSharePct;
      if (typeof share === "number" && Number.isFinite(share) && share < 70) return "traffic_recent4_min_below_70";
    }
    return "";
  }

  async function scanTooltip() {
    var chart = getChartElement();
    if (!chart) return summarize([], "no_chart");
    var rect = chart.getBoundingClientRect();
    var xs = [];
    for (var i = 0; i <= 18; i += 1) {
      xs.push(rect.x + 70 + (rect.width - 140) * i / 18);
    }
    xs.reverse();
    var ys = [
      rect.y + rect.height * 0.34,
      rect.y + rect.height * 0.52,
      rect.y + rect.height * 0.7,
      rect.y + rect.height * 0.88
    ];
    var details = [];
    var seen = {};
    var missesAfterEnough = 0;

    for (var xi = 0; xi < xs.length; xi += 1) {
      for (var yi = 0; yi < ys.length; yi += 1) {
        fireMouseAt(Math.round(xs[xi]), Math.round(ys[yi]), chart);
        await delay(180);
        var tips = visibleTooltipTexts();
        var chosen = null;
        for (var ti = 0; ti < tips.length; ti += 1) {
          if (tips[ti].rect.w < 700) {
            chosen = tips[ti];
            break;
          }
        }
        if (!chosen && tips.length) chosen = tips[0];
        if (!chosen) {
          if (details.length >= MIN_REQUIRED_WEEKS) missesAfterEnough += 1;
          if (missesAfterEnough >= 16) break;
          continue;
        }
        var parsed = parseTip(chosen.text);
        var key = parsed.weekSort || parsed.week;
        if (parsed.week && !seen[key]) {
          seen[key] = true;
          details.push(parsed);
          missesAfterEnough = 0;
          var earlyReason = earlyTrafficFailureReason(details);
          if (earlyReason) {
            var failed = summarize(details, "tooltip_scan_short_circuit");
            failed.decision = "fail";
            failed.shortCircuited = true;
            failed.shortCircuitReason = earlyReason;
            return failed;
          }
          if (details.length >= MAX_RECENT_WEEKS) break;
        } else if (details.length >= MIN_REQUIRED_WEEKS) {
          missesAfterEnough += 1;
        }
      }
      if (details.length >= MAX_RECENT_WEEKS) break;
      if (missesAfterEnough >= 16) break;
    }

    return summarize(details, "tooltip_scan_recent_4_weeks");
  }

  globalThis.SSTrafficCollectorCore = Object.freeze({
    earlyTrafficFailureReason: earlyTrafficFailureReason,
    maxRecentWeeks: MAX_RECENT_WEEKS,
    minRequiredWeeks: MIN_REQUIRED_WEEKS
  });

  if (typeof window === "undefined" || typeof document === "undefined") return;

  function resultText(result) {
    var latestShare = result.latest ? pct(result.latest.naturalSharePct) : "";
    var tCell =
      result.status === "ok"
        ? "latest " + latestShare + "; recent4 avg " + pct(result.recent4AvgNaturalSharePct) + "; min " + pct(result.recent4MinNaturalSharePct) + "; decision " + result.decision
        : "retake/review: reliable natural traffic share not collected";
    if (result.status === "no_chart_loaded") {
      tCell = "retake/review: SellerSprite traffic chart did not load within timeout";
    }
    return [
      "ASIN: " + (result.asin || ""),
      "Status: " + result.status,
      "Decision: " + result.decision,
      "Latest week: " + (result.latest ? result.latest.week : ""),
      "Latest natural share: " + latestShare,
      "Recent4 avg: " + pct(result.recent4AvgNaturalSharePct),
      "Recent4 min: " + pct(result.recent4MinNaturalSharePct),
      "Weeks read: " + result.weeksRead,
      "Window: " + (result.trafficWindow || TRAFFIC_WINDOW_LABEL),
      "Short circuit: " + (result.shortCircuitReason || ""),
      "Method: " + result.method,
      "",
      "T cell:",
      tCell
    ].join("\n");
  }

  function setStatus(text, color) {
    var node = document.getElementById("ss-collector-status");
    if (!node) return;
    node.textContent = text;
    node.style.color = color || "#344054";
    var panel = document.getElementById("ss-collector-panel");
    if (panel) panel.setAttribute("data-ss-status-text", text);
  }

  function setOutput(text) {
    var node = document.getElementById("ss-collector-output");
    if (node) node.textContent = text;
  }

  function setJsonNodeText(node, json) {
    if (!node) return;
    if ("value" in node) node.value = json;
    node.textContent = json;
  }

  function publishResult(result) {
    state.lastResult = result;
    window.__SellerSpriteTrafficCollectorLast = result;
    var json = JSON.stringify(result, null, 2);
    var jsonNode = document.getElementById("ss-collector-json");
    setJsonNodeText(jsonNode, json);
    var panel = document.getElementById("ss-collector-panel");
    if (panel) {
      panel.setAttribute("data-ss-result-ready", "1");
      panel.setAttribute("data-ss-result-status", result.status || "");
      panel.setAttribute("data-ss-result-decision", result.decision || "");
      panel.setAttribute("data-ss-result-asin", result.asin || "");
      panel.setAttribute("data-ss-result-weeks", String(result.weeksRead || 0));
      panel.setAttribute("data-ss-result-run-id", result.runId || "");
    }
  }

  function clearPublishedResult(runId) {
    state.lastResult = null;
    var jsonNode = document.getElementById("ss-collector-json");
    setJsonNodeText(jsonNode, "");
    var panel = document.getElementById("ss-collector-panel");
    if (panel) {
      panel.setAttribute("data-ss-result-ready", "0");
      panel.setAttribute("data-ss-result-status", "");
      panel.setAttribute("data-ss-result-decision", "");
      panel.setAttribute("data-ss-result-asin", getAsin());
      panel.setAttribute("data-ss-result-weeks", "0");
      panel.setAttribute("data-ss-result-run-id", "");
      panel.setAttribute("data-ss-run-id", runId);
      panel.setAttribute("data-ss-running", "1");
    }
  }

  function copyText(text) {
    try {
      GM_setClipboard(text, "text");
      return true;
    } catch (error) {
      try {
        navigator.clipboard.writeText(text);
      } catch (ignore) {}
      return false;
    }
  }

  async function collect(options) {
    if (state.running) return;
    options = options || {};
    var runId = nextRunId();
    state.running = true;
    clearPublishedResult(runId);
    setStatus("Collecting. Do not move mouse or switch tabs.", "#344054");
    try {
      var chart = getChartElement() || (await waitForChart(options.chartTimeoutMs || 60000));
      var result;
      if (!chart) {
        result = summarize([], "no_chart_timeout");
        result.status = "no_chart_loaded";
        result.decision = "review";
      } else {
        result = await scanTooltip();
      }
      result = finalizeResult(result, runId);
      publishResult(result);
      setOutput(resultText(result));
      setStatus(result.status === "ok" ? "Done: " + result.decision : "Need review: " + result.status, result.status === "ok" ? "#067647" : "#b42318");
    } catch (error) {
      var failed = collectorErrorResult(error, runId);
      publishResult(failed);
      setOutput(resultText(failed));
      setStatus("Error: " + (error && error.message ? error.message : error), "#b42318");
    } finally {
      state.running = false;
      var panel = document.getElementById("ss-collector-panel");
      if (panel) panel.setAttribute("data-ss-running", "0");
    }
  }

  function copyJson() {
    if (!state.lastResult) {
      setStatus("No result yet.", "#b42318");
      return;
    }
    copyText(JSON.stringify(state.lastResult, null, 2));
    setStatus("JSON copied.", "#067647");
  }

  function copyPanelText() {
    var text = document.getElementById("ss-collector-output").textContent || "";
    copyText(text);
    setStatus("Text copied.", "#067647");
  }

  function addPanel() {
    if (document.getElementById("ss-collector-panel")) return;
    var style = document.createElement("style");
    style.textContent =
      "#ss-collector-panel{position:fixed;left:16px;bottom:90px;z-index:2147483647;width:380px;max-height:480px;overflow:auto;padding:12px;border:2px solid #f97316;border-radius:8px;background:#fff;box-shadow:0 8px 28px rgba(16,24,40,.22);color:#101828;font:13px Arial,sans-serif;}" +
      "#ss-collector-panel button{border:1px solid #d0d5dd;background:#f9fafb;border-radius:6px;padding:6px 8px;cursor:pointer;font-size:12px;margin-right:6px;margin-bottom:8px;}" +
      "#ss-collector-panel button:hover{background:#eef4ff;}" +
      "#ss-collector-output{white-space:pre-wrap;word-break:break-word;max-height:280px;overflow:auto;margin:0;padding:8px;background:#f9fafb;border:1px solid #eaecf0;border-radius:6px;font-size:12px;}" +
      "#ss-collector-json{display:none;}";
    document.documentElement.appendChild(style);

    var panel = document.createElement("div");
    panel.id = "ss-collector-panel";
    panel.className = "notranslate";
    panel.setAttribute("translate", "no");
    panel.setAttribute("data-ss-result-ready", "0");
    panel.setAttribute("data-ss-result-asin", getAsin());
    panel.setAttribute("data-ss-protocol-version", PROTOCOL_VERSION);
    panel.setAttribute("data-ss-schema-version", SCHEMA_VERSION);
    panel.setAttribute("data-ss-running", "0");
    panel.setAttribute("data-ss-run-id", "");
    panel.setAttribute("data-ss-result-run-id", "");
    panel.innerHTML =
      '<div style="font-weight:700;margin-bottom:6px;">SellerSprite Traffic Collector ' + VERSION + '</div>' +
      '<div id="ss-collector-status" style="font-size:12px;color:#344054;margin-bottom:8px;">Ready.</div>' +
      '<button id="ss-collector-check" type="button">Check Page</button>' +
      '<button id="ss-collector-run" type="button">Collect Traffic</button>' +
      '<button id="ss-collector-copy-text" type="button">Copy Text</button>' +
      '<button id="ss-collector-copy-json" type="button">Copy JSON</button>' +
      '<pre id="ss-collector-output" translate="no" class="notranslate"></pre>' +
      '<textarea id="ss-collector-json" translate="no" class="notranslate"></textarea>';
    document.documentElement.appendChild(panel);

    document.getElementById("ss-collector-check").addEventListener("click", function () {
      setOutput(pageStatusText());
      setStatus("Page checked.", "#067647");
    });
    document.getElementById("ss-collector-run").addEventListener("click", collect);
    document.getElementById("ss-collector-copy-text").addEventListener("click", copyPanelText);
    document.getElementById("ss-collector-copy-json").addEventListener("click", copyJson);
    setOutput(pageStatusText());
  }

  function boot() {
    if (!/(^|\.)amazon\.com$/i.test(location.hostname)) return;
    addPanel();
    if (!state.autoStarted && /(?:^|[#&?])ss-auto=1(?:$|[&=])/.test(location.hash + "&" + location.search)) {
      state.autoStarted = true;
      setTimeout(function () {
        collect({ chartTimeoutMs: 90000 });
      }, 1500);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, false);
  } else {
    boot();
  }
})();
