// ==UserScript==
// @name         SellerSprite Traffic Collector 0.4.7 [P2 baseline OFF]
// @namespace    codex.amazon.product-selection
// @version      0.4.7-p2off
// @description  Paired-validation baseline with the P2 deadline protocol disabled.
// @match        https://www.amazon.com/*
// @match        https://amazon.com/*
// @homepageURL  https://github.com/yuanzeli695-byte/sellersprite-userscripts
// @supportURL   https://github.com/yuanzeli695-byte/sellersprite-userscripts/issues
// @grant        GM_setClipboard
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";

  var VERSION = "0.4.7";
  var ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL = false;
  var P2_DEADLINE_PROTOCOL_VERSION = "p2-collector-owned-deadline-v1";
  var P2_DEADLINE_OWNER = "collector";
  var LEGACY_PROTOCOL_NAME = "legacy_status_text_v1";
  var LEGACY_DEADLINE_OWNER = "runner";
  var P2_CHART_READY_BUDGET_MS = 60000;
  var P2_TOOLTIP_SCAN_WATCHDOG_MS = 45000;
  var P2_HEARTBEAT_INTERVAL_MS = 1000;
  var PROTOCOL_VERSION = ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL ? "2" : "1";
  var PROTOCOL_NAME = ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL ? P2_DEADLINE_PROTOCOL_VERSION : LEGACY_PROTOCOL_NAME;
  var DEADLINE_OWNER = ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL ? P2_DEADLINE_OWNER : LEGACY_DEADLINE_OWNER;
  var SCHEMA_VERSION = "sellerSpriteTraffic/v1";
  var ENABLE_TIER0_TELEMETRY = true;
  var ENABLE_TIER2_1_ZERO_SHARE_DERIVATION = true;
  var TIER2_READER_VERSION = "tier2.1-zero-share-v1";
  var TELEMETRY_SCHEMA_VERSION = "sellerSpriteTelemetry/v1";

  var GATE_LOG_COLUMNS = [
    "collectedAt",
    "asin",
    "collectorVersion",
    "outcome",
    "shortCircuitGate",
    "gateA",
    "gateB",
    "gateC",
    "gateD",
    "gateE",
    "gateF",
    "trafficStatus",
    "trafficDecision",
    "weeksRead",
    "latestNaturalSharePct",
    "recent4AvgNaturalSharePct",
    "recent4MinNaturalSharePct",
    "shortCircuitReason",
    "method",
    "runId"
  ];

  var TIMING_LOG_COLUMNS = [
    "startedAt",
    "completedAt",
    "asin",
    "collectorVersion",
    "detailPageMs",
    "detailPageMsReason",
    "trafficChartMs",
    "priceChartMs",
    "priceChartMsReason",
    "chartWaitMs",
    "tooltipScanMs",
    "retryCount",
    "totalMs",
    "runId"
  ];

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
    runSequence: 0,
    deadlineProtocol: null
  };

  function finiteEpochMs(value) {
    if (value === null || value === undefined || value === "") return null;
    var parsed = Number(value);
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
  }

  function positiveBudgetMs(value, fallback) {
    var parsed = Number(value);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
  }

  function collectorDeadlineReached(deadlineAtMs, startedAtMs, maxMs, nowMs) {
    var now = finiteEpochMs(nowMs);
    if (now === null) return false;
    var started = finiteEpochMs(startedAtMs);
    if (ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL && started !== null && now < started) return true;
    var absoluteDeadline = finiteEpochMs(deadlineAtMs);
    if (absoluteDeadline !== null) return now >= absoluteDeadline;
    return started !== null && now - started >= Number(maxMs);
  }

  function observeCollectorWallClock(protocol, atMs) {
    if (!protocol) return false;
    var at = finiteEpochMs(atMs);
    if (at === null) return false;
    var last = finiteEpochMs(protocol.lastObservedAtMs);
    if (last !== null && at < last) {
      if (!protocol.clockAnomalyKind) {
        protocol.clockAnomalyKind = "wall_clock_backward";
        protocol.clockAnomalyObservedAtMs = at;
      }
      return true;
    }
    protocol.lastObservedAtMs = at;
    return false;
  }

  function createCollectorDeadlineState(runId, acceptedAtMs, chartReadyBudgetMs) {
    if (!ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL) return null;
    var accepted = finiteEpochMs(acceptedAtMs);
    if (accepted === null) throw new Error("collector deadline acceptedAtMs is invalid");
    var chartBudget = positiveBudgetMs(chartReadyBudgetMs, P2_CHART_READY_BUDGET_MS);
    return {
      protocolVersion: P2_DEADLINE_PROTOCOL_VERSION,
      protocolName: P2_DEADLINE_PROTOCOL_VERSION,
      domProtocolVersion: PROTOCOL_VERSION,
      owner: P2_DEADLINE_OWNER,
      runId: safeText(runId),
      phase: "chart_wait",
      phaseDeadlineKind: "hard_readiness",
      acceptedAtMs: accepted,
      phaseStartedAtMs: accepted,
      phaseDeadlineAtMs: accepted + chartBudget,
      chartReadyDeadlineAtMs: accepted + chartBudget,
      chartReadyBudgetMs: chartBudget,
      tooltipScanWatchdogMs: P2_TOOLTIP_SCAN_WATCHDOG_MS,
      heartbeatAtMs: accepted,
      lastObservedAtMs: accepted,
      clockAnomalyKind: "",
      clockAnomalyObservedAtMs: null,
      chartReadyAtMs: null,
      chartReadyDeadlineExceededByMs: null,
      resultReadyAtMs: null,
      terminalFromPhase: "",
      deadlineExceededByMs: null,
      terminalReason: "",
      visibilityState: "",
      hiddenObservedAtMs: null
    };
  }

  function advanceCollectorDeadlineState(protocol, phase, atMs, terminalReason) {
    if (!protocol) return null;
    var at = finiteEpochMs(atMs);
    if (at === null) throw new Error("collector deadline transition timestamp is invalid");
    observeCollectorWallClock(protocol, at);
    var priorPhase = protocol.phase;
    var priorDeadlineAtMs = finiteEpochMs(protocol.phaseDeadlineAtMs);
    protocol.phase = safeText(phase);
    protocol.phaseStartedAtMs = at;
    protocol.heartbeatAtMs = at;
    if (phase === "tooltip_scan") {
      protocol.phaseDeadlineKind = "observer_watchdog";
      protocol.phaseDeadlineAtMs = at + P2_TOOLTIP_SCAN_WATCHDOG_MS;
      protocol.chartReadyAtMs = at;
      protocol.chartReadyDeadlineExceededByMs = priorDeadlineAtMs === null ? null : Math.max(0, at - priorDeadlineAtMs);
    } else if (phase === "result_ready") {
      protocol.terminalFromPhase = safeText(priorPhase || "");
      protocol.deadlineExceededByMs = priorDeadlineAtMs === null ? null : Math.max(0, at - priorDeadlineAtMs);
      protocol.phaseDeadlineKind = "terminal";
      protocol.phaseDeadlineAtMs = null;
      protocol.resultReadyAtMs = at;
      protocol.terminalReason = safeText(terminalReason);
    }
    return protocol;
  }

  function heartbeatCollectorDeadlineState(protocol, atMs) {
    if (!protocol) return null;
    var at = finiteEpochMs(atMs);
    if (at !== null) {
      observeCollectorWallClock(protocol, at);
      protocol.heartbeatAtMs = at;
    }
    return protocol;
  }

  function collectorDeadlineAttributes(protocol) {
    if (!protocol) return {};
    function attr(value) {
      return value === null || value === undefined ? "" : String(value);
    }
    return {
      "data-ss-collector-version": VERSION,
      "data-ss-protocol-name": attr(protocol.protocolName),
      "data-ss-deadline-protocol-version": attr(protocol.protocolVersion),
      "data-ss-deadline-owner": attr(protocol.owner),
      "data-ss-deadline-run-id": attr(protocol.runId),
      "data-ss-deadline-phase": attr(protocol.phase),
      "data-ss-deadline-kind": attr(protocol.phaseDeadlineKind),
      "data-ss-deadline-accepted-at-ms": attr(protocol.acceptedAtMs),
      "data-ss-deadline-phase-started-at-ms": attr(protocol.phaseStartedAtMs),
      "data-ss-deadline-at-ms": attr(protocol.phaseDeadlineAtMs),
      "data-ss-deadline-chart-ready-deadline-at-ms": attr(protocol.chartReadyDeadlineAtMs),
      "data-ss-deadline-heartbeat-at-ms": attr(protocol.heartbeatAtMs),
      "data-ss-deadline-last-observed-at-ms": attr(protocol.lastObservedAtMs),
      "data-ss-clock-anomaly-kind": attr(protocol.clockAnomalyKind),
      "data-ss-clock-anomaly-observed-at-ms": attr(protocol.clockAnomalyObservedAtMs),
      "data-ss-deadline-chart-ready-at-ms": attr(protocol.chartReadyAtMs),
      "data-ss-deadline-chart-ready-exceeded-by-ms": attr(protocol.chartReadyDeadlineExceededByMs),
      "data-ss-deadline-result-ready-at-ms": attr(protocol.resultReadyAtMs),
      "data-ss-deadline-terminal-from-phase": attr(protocol.terminalFromPhase),
      "data-ss-deadline-exceeded-by-ms": attr(protocol.deadlineExceededByMs),
      "data-ss-deadline-terminal-reason": attr(protocol.terminalReason),
      "data-ss-visibility-state": attr(protocol.visibilityState),
      "data-ss-hidden-observed-at-ms": attr(protocol.hiddenObservedAtMs)
    };
  }

  function collectorDeadlineSnapshot(protocol) {
    if (!protocol) return null;
    return JSON.parse(JSON.stringify(protocol));
  }

  function collectorDeadlinePayload(protocol) {
    var snapshot = collectorDeadlineSnapshot(protocol);
    if (!snapshot) return null;
    return {
      protocolName: snapshot.protocolName,
      protocolVersion: snapshot.domProtocolVersion,
      deadlineOwner: snapshot.owner,
      runId: snapshot.runId,
      acceptedAtMs: snapshot.acceptedAtMs,
      chartReadyDeadlineAtMs: snapshot.chartReadyDeadlineAtMs,
      chartReadyAtMs: snapshot.chartReadyAtMs,
      phase: snapshot.phase,
      phaseStartedAtMs: snapshot.phaseStartedAtMs,
      phaseDeadlineAtMs: snapshot.phaseDeadlineAtMs,
      heartbeatAtMs: snapshot.heartbeatAtMs,
      lastObservedAtMs: snapshot.lastObservedAtMs,
      clockAnomalyKind: snapshot.clockAnomalyKind,
      clockAnomalyObservedAtMs: snapshot.clockAnomalyObservedAtMs,
      resultReadyAtMs: snapshot.resultReadyAtMs,
      terminalReason: snapshot.terminalReason,
      deadlineExceededByMs: snapshot.deadlineExceededByMs,
      visibilityState: snapshot.visibilityState,
      hiddenObservedAtMs: snapshot.hiddenObservedAtMs
    };
  }

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

  function explicitMetricValue(lines, label) {
    var labelIndex = -1;
    for (var i = 0; i < lines.length; i += 1) {
      if (lines[i].indexOf(label) >= 0) {
        labelIndex = i;
        break;
      }
    }
    if (labelIndex < 0) return { state: "missing", value: null, raw: "" };

    var labelLine = lines[labelIndex];
    var labelOffset = labelLine.indexOf(label) + label.length;
    var candidate = labelLine.slice(labelOffset).trim();
    if (!candidate && labelIndex + 1 < lines.length) candidate = lines[labelIndex + 1].trim();
    if (!candidate) return { state: "missing", value: null, raw: "" };
    if (/^(?:--|N\/?A|NA|null)(?:\b|\s|\(|$)/i.test(candidate)) {
      return { state: "missing", value: null, raw: candidate };
    }
    var match = candidate.match(/^(-?\d[\d,]*(?:\.\d+)?)(?=\s|\(|$)/);
    if (!match) return { state: "ambiguous", value: null, raw: candidate };
    var value = Number(match[1].replace(/,/g, ""));
    return Number.isFinite(value)
      ? { state: "number", value: value, raw: candidate }
      : { state: "ambiguous", value: null, raw: candidate };
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

  function publishCollectorDeadlineProtocol() {
    if (!ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL || !state.deadlineProtocol) return;
    var panel = document.getElementById("ss-collector-panel");
    if (!panel) return;
    state.deadlineProtocol.visibilityState = document.visibilityState || "unknown";
    if (state.deadlineProtocol.visibilityState !== "visible" && state.deadlineProtocol.hiddenObservedAtMs === null) {
      state.deadlineProtocol.hiddenObservedAtMs = Date.now();
    }
    var attributes = collectorDeadlineAttributes(state.deadlineProtocol);
    Object.keys(attributes).forEach(function (name) {
      panel.setAttribute(name, attributes[name]);
    });
  }

  function setCollectorDeadlinePhase(phase, atMs, terminalReason) {
    advanceCollectorDeadlineState(state.deadlineProtocol, phase, atMs, terminalReason);
    publishCollectorDeadlineProtocol();
  }

  function heartbeatCollectorDeadline(atMs) {
    heartbeatCollectorDeadlineState(state.deadlineProtocol, atMs);
    publishCollectorDeadlineProtocol();
  }

  function attachCollectorDeadlineTelemetry(result) {
    if (!ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL || !state.deadlineProtocol) return result;
    var snapshot = collectorDeadlineSnapshot(state.deadlineProtocol);
    result.telemetry = result.telemetry || {};
    result.telemetry.deadline = snapshot;
    result.deadlineProtocol = collectorDeadlinePayload(state.deadlineProtocol);
    return result;
  }

  function waitForChart(maxMs, deadlineAtMs) {
    var started = Date.now();
    return new Promise(function (resolve) {
      function tick() {
        var nowMs = Date.now();
        heartbeatCollectorDeadline(nowMs);
        if (ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL && state.deadlineProtocol && state.deadlineProtocol.clockAnomalyKind) {
          resolve(null);
          return;
        }
        if (ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL && collectorDeadlineReached(deadlineAtMs, started, maxMs, nowMs)) {
          resolve(null);
          return;
        }
        var chart = getChartElement();
        if (chart) {
          resolve(chart);
          return;
        }
        if (!ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL && collectorDeadlineReached(deadlineAtMs, started, maxMs, nowMs)) {
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

    var totalEvidence = explicitMetricValue(lines, labels.total);
    var naturalEvidence = explicitMetricValue(lines, labels.natural);
    var totalTraffic = ENABLE_TIER2_1_ZERO_SHARE_DERIVATION
      ? (totalEvidence.state === "number" ? totalEvidence.value : null)
      : findAfter(labels.total);
    var naturalTraffic = ENABLE_TIER2_1_ZERO_SHARE_DERIVATION
      ? (naturalEvidence.state === "number" ? naturalEvidence.value : null)
      : findAfter(labels.natural);
    var naturalSharePct = shareAfter(labels.natural, labels.sp);
    var naturalShareDerived = false;
    if (
      ENABLE_TIER2_1_ZERO_SHARE_DERIVATION &&
      naturalSharePct === null &&
      totalEvidence.state === "number" &&
      totalEvidence.value > 0 &&
      naturalEvidence.state === "number" &&
      naturalEvidence.value === 0
    ) {
      naturalSharePct = 0;
      naturalShareDerived = true;
    }

    var parsed = {
      week: week,
      weekSort: weekSortKey(week),
      totalTraffic: totalTraffic,
      naturalTraffic: naturalTraffic,
      naturalSharePct: naturalSharePct,
      spTraffic: findAfter(labels.sp),
      spSharePct: shareAfter(labels.sp, labels.sb),
      rawText: text
    };
    if (ENABLE_TIER2_1_ZERO_SHARE_DERIVATION) {
      parsed.naturalShareDerived = naturalShareDerived;
      parsed.naturalShareSource = naturalShareDerived
        ? "derived_explicit_zero_over_positive_total"
        : (typeof naturalSharePct === "number" ? "sellersprite_explicit" : "missing");
      parsed.tier2ReaderVersion = TIER2_READER_VERSION;
    }
    return parsed;
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

  function latestNaturalShare(result) {
    return result && result.latest && typeof result.latest.naturalSharePct === "number"
      ? result.latest.naturalSharePct
      : null;
  }

  function buildGateLogRow(result) {
    result = result || {};
    var passed = result.status === "ok" && result.decision === "pass" && result.pass70 === true;
    return {
      collectedAt: result.collectedAt || "",
      asin: result.asin || "",
      collectorVersion: result.collectorVersion || VERSION,
      outcome: passed ? "pass" : "reject",
      shortCircuitGate: passed ? "" : "C",
      gateA: "not_evaluated_in_collector",
      gateB: "not_evaluated_in_collector",
      gateC: passed ? "pass" : "reject",
      gateD: "not_evaluated_in_collector",
      gateE: "not_evaluated_in_collector",
      gateF: "not_evaluated_in_collector",
      trafficStatus: result.status || "",
      trafficDecision: result.decision || "",
      weeksRead: typeof result.weeksRead === "number" ? result.weeksRead : null,
      latestNaturalSharePct: latestNaturalShare(result),
      recent4AvgNaturalSharePct:
        typeof result.recent4AvgNaturalSharePct === "number" ? result.recent4AvgNaturalSharePct : null,
      recent4MinNaturalSharePct:
        typeof result.recent4MinNaturalSharePct === "number" ? result.recent4MinNaturalSharePct : null,
      shortCircuitReason: passed
        ? ""
        : (result.shortCircuitReason || result.error || result.decision || result.status || ""),
      method: result.method || "",
      runId: result.runId || ""
    };
  }

  function buildTimingLogRow(result, measurements) {
    result = result || {};
    measurements = measurements || {};
    return {
      startedAt: measurements.startedAt || "",
      completedAt: measurements.completedAt || "",
      asin: result.asin || "",
      collectorVersion: result.collectorVersion || VERSION,
      detailPageMs: null,
      detailPageMsReason: "measured_by_runner",
      trafficChartMs:
        typeof measurements.trafficChartMs === "number" ? measurements.trafficChartMs : null,
      priceChartMs: null,
      priceChartMsReason: "measured_by_runner",
      chartWaitMs: typeof measurements.chartWaitMs === "number" ? measurements.chartWaitMs : null,
      tooltipScanMs:
        typeof measurements.tooltipScanMs === "number" ? measurements.tooltipScanMs : null,
      retryCount: 0,
      totalMs: typeof measurements.totalMs === "number" ? measurements.totalMs : null,
      runId: result.runId || ""
    };
  }

  function tsvCell(value) {
    if (value == null) return "";
    var text = typeof value === "object" ? JSON.stringify(value) : String(value);
    return text.replace(/[\t\r\n]+/g, " ");
  }

  function rowsToTsv(rows, columns) {
    rows = Array.isArray(rows) ? rows : [];
    columns = Array.isArray(columns) ? columns : [];
    var lines = [columns.join("\t")];
    for (var i = 0; i < rows.length; i += 1) {
      lines.push(
        columns.map(function (column) {
          return tsvCell(rows[i] ? rows[i][column] : "");
        }).join("\t")
      );
    }
    return lines.join("\n");
  }

  function attachTelemetry(result, measurements) {
    if (!ENABLE_TIER0_TELEMETRY) return result;
    result.telemetry = {
      schemaVersion: TELEMETRY_SCHEMA_VERSION,
      gate: buildGateLogRow(result),
      timing: buildTimingLogRow(result, measurements)
    };
    return result;
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
    parseTip: parseTip,
    summarize: summarize,
    explicitMetricValue: explicitMetricValue,
    earlyTrafficFailureReason: earlyTrafficFailureReason,
    buildGateLogRow: buildGateLogRow,
    buildTimingLogRow: buildTimingLogRow,
    attachTelemetry: attachTelemetry,
    rowsToTsv: rowsToTsv,
    createCollectorDeadlineState: createCollectorDeadlineState,
    observeCollectorWallClock: observeCollectorWallClock,
    advanceCollectorDeadlineState: advanceCollectorDeadlineState,
    heartbeatCollectorDeadlineState: heartbeatCollectorDeadlineState,
    collectorDeadlineAttributes: collectorDeadlineAttributes,
    collectorDeadlineSnapshot: collectorDeadlineSnapshot,
    collectorDeadlinePayload: collectorDeadlinePayload,
    collectorDeadlineReached: collectorDeadlineReached,
    waitForChart: waitForChart,
    gateLogColumns: GATE_LOG_COLUMNS.slice(),
    timingLogColumns: TIMING_LOG_COLUMNS.slice(),
    telemetryEnabled: ENABLE_TIER0_TELEMETRY,
    tier21ZeroShareEnabled: ENABLE_TIER2_1_ZERO_SHARE_DERIVATION,
    tier2ReaderVersion: TIER2_READER_VERSION,
    p2CollectorDeadlineEnabled: ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL,
    p2DeadlineProtocolVersion: P2_DEADLINE_PROTOCOL_VERSION,
    p2DeadlineOwner: P2_DEADLINE_OWNER,
    p2ChartReadyBudgetMs: P2_CHART_READY_BUDGET_MS,
    p2TooltipScanWatchdogMs: P2_TOOLTIP_SCAN_WATCHDOG_MS,
    protocolVersion: PROTOCOL_VERSION,
    protocolName: PROTOCOL_NAME,
    deadlineOwner: DEADLINE_OWNER,
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
    publishCollectorDeadlineProtocol();
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
    var runStartedMs = Date.now();
    var startedAt = new Date(runStartedMs).toISOString();
    var chartWaitMs = 0;
    var tooltipScanMs = 0;
    var heartbeatTimer = null;
    var chartReadyBudgetMs = options.chartTimeoutMs || P2_CHART_READY_BUDGET_MS;
    state.running = true;
    state.deadlineProtocol = createCollectorDeadlineState(runId, runStartedMs, chartReadyBudgetMs);
    clearPublishedResult(runId);
    if (ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL) {
      heartbeatTimer = setInterval(function () {
        heartbeatCollectorDeadline(Date.now());
      }, P2_HEARTBEAT_INTERVAL_MS);
    }
    setStatus("Collecting. Do not move mouse or switch tabs.", "#344054");
    try {
      var chartWaitStartedMs = Date.now();
      var chartDeadlineAtMs = state.deadlineProtocol ? state.deadlineProtocol.phaseDeadlineAtMs : null;
      var chart = await waitForChart(chartReadyBudgetMs, chartDeadlineAtMs);
      chartWaitMs = Date.now() - chartWaitStartedMs;
      var result;
      if (!chart) {
        result = summarize([], "no_chart_timeout");
        result.status = "no_chart_loaded";
        result.decision = "review";
      } else {
        setCollectorDeadlinePhase("tooltip_scan", Date.now(), "");
        var tooltipScanStartedMs = Date.now();
        try {
          result = await scanTooltip();
        } finally {
          tooltipScanMs = Date.now() - tooltipScanStartedMs;
        }
      }
      result = finalizeResult(result, runId);
      attachTelemetry(result, {
        startedAt: startedAt,
        completedAt: new Date().toISOString(),
        chartWaitMs: chartWaitMs,
        tooltipScanMs: tooltipScanMs,
        trafficChartMs: chartWaitMs + tooltipScanMs,
        totalMs: Date.now() - runStartedMs
      });
      setCollectorDeadlinePhase("result_ready", Date.now(), result.status || "unknown");
      attachCollectorDeadlineTelemetry(result);
      publishResult(result);
      setOutput(resultText(result));
      setStatus(result.status === "ok" ? "Done: " + result.decision : "Need review: " + result.status, result.status === "ok" ? "#067647" : "#b42318");
    } catch (error) {
      var failed = collectorErrorResult(error, runId);
      attachTelemetry(failed, {
        startedAt: startedAt,
        completedAt: new Date().toISOString(),
        chartWaitMs: chartWaitMs,
        tooltipScanMs: tooltipScanMs,
        trafficChartMs: chartWaitMs + tooltipScanMs,
        totalMs: Date.now() - runStartedMs
      });
      setCollectorDeadlinePhase("result_ready", Date.now(), failed.status || "error");
      attachCollectorDeadlineTelemetry(failed);
      publishResult(failed);
      setOutput(resultText(failed));
      setStatus("Error: " + (error && error.message ? error.message : error), "#b42318");
    } finally {
      if (heartbeatTimer !== null) clearInterval(heartbeatTimer);
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

  function copyTelemetryTable(kind) {
    if (!state.lastResult || !state.lastResult.telemetry) {
      setStatus("No telemetry result yet.", "#b42318");
      return;
    }
    var isGate = kind === "gate";
    var row = state.lastResult.telemetry[kind];
    var columns = isGate ? GATE_LOG_COLUMNS : TIMING_LOG_COLUMNS;
    copyText(rowsToTsv([row], columns));
    setStatus((isGate ? "Gate" : "Timing") + " TSV copied.", "#067647");
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
    panel.setAttribute("data-ss-collector-version", VERSION);
    panel.setAttribute("data-ss-p2-deadline-enabled", ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL ? "1" : "0");
    panel.setAttribute("data-ss-protocol-version", PROTOCOL_VERSION);
    panel.setAttribute("data-ss-protocol-name", PROTOCOL_NAME);
    panel.setAttribute("data-ss-deadline-owner", DEADLINE_OWNER);
    panel.setAttribute("data-ss-schema-version", SCHEMA_VERSION);
    panel.setAttribute("data-ss-running", "0");
    panel.setAttribute("data-ss-run-id", "");
    panel.setAttribute("data-ss-result-run-id", "");
    if (ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL) {
      panel.setAttribute("data-ss-deadline-protocol-version", P2_DEADLINE_PROTOCOL_VERSION);
      panel.setAttribute("data-ss-protocol-name", P2_DEADLINE_PROTOCOL_VERSION);
      panel.setAttribute("data-ss-deadline-owner", P2_DEADLINE_OWNER);
      panel.setAttribute("data-ss-deadline-run-id", "");
      panel.setAttribute("data-ss-deadline-phase", "idle");
      panel.setAttribute("data-ss-deadline-kind", "");
      panel.setAttribute("data-ss-deadline-accepted-at-ms", "");
      panel.setAttribute("data-ss-deadline-phase-started-at-ms", "");
      panel.setAttribute("data-ss-deadline-at-ms", "");
      panel.setAttribute("data-ss-deadline-chart-ready-deadline-at-ms", "");
      panel.setAttribute("data-ss-deadline-heartbeat-at-ms", "");
      panel.setAttribute("data-ss-deadline-last-observed-at-ms", "");
      panel.setAttribute("data-ss-clock-anomaly-kind", "");
      panel.setAttribute("data-ss-clock-anomaly-observed-at-ms", "");
      panel.setAttribute("data-ss-deadline-chart-ready-at-ms", "");
      panel.setAttribute("data-ss-deadline-chart-ready-exceeded-by-ms", "");
      panel.setAttribute("data-ss-deadline-result-ready-at-ms", "");
      panel.setAttribute("data-ss-deadline-terminal-from-phase", "");
      panel.setAttribute("data-ss-deadline-exceeded-by-ms", "");
      panel.setAttribute("data-ss-deadline-terminal-reason", "");
      panel.setAttribute("data-ss-visibility-state", document.visibilityState || "unknown");
      panel.setAttribute("data-ss-hidden-observed-at-ms", "");
    }
    var telemetryButtons = ENABLE_TIER0_TELEMETRY
      ? '<button id="ss-collector-copy-gate-tsv" type="button">Copy Gate TSV</button>' +
        '<button id="ss-collector-copy-timing-tsv" type="button">Copy Timing TSV</button>'
      : "";
    panel.innerHTML =
      '<div style="font-weight:700;margin-bottom:6px;">SellerSprite Traffic Collector ' + VERSION + ' P2 OFF</div>' +
      '<div id="ss-collector-status" style="font-size:12px;color:#344054;margin-bottom:8px;">Ready.</div>' +
      '<button id="ss-collector-check" type="button">Check Page</button>' +
      '<button id="ss-collector-run" type="button">Collect Traffic</button>' +
      '<button id="ss-collector-copy-text" type="button">Copy Text</button>' +
      '<button id="ss-collector-copy-json" type="button">Copy JSON</button>' +
      telemetryButtons +
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
    if (ENABLE_TIER0_TELEMETRY) {
      document.getElementById("ss-collector-copy-gate-tsv").addEventListener("click", function () {
        copyTelemetryTable("gate");
      });
      document.getElementById("ss-collector-copy-timing-tsv").addEventListener("click", function () {
        copyTelemetryTable("timing");
      });
    }
    setOutput(pageStatusText());
  }

  function boot() {
    if (!/(^|\.)amazon\.com$/i.test(location.hostname)) return;
    addPanel();
    if (ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL) {
      document.addEventListener("visibilitychange", function () {
        if (state.running && state.deadlineProtocol) heartbeatCollectorDeadline(Date.now());
      });
    }
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
