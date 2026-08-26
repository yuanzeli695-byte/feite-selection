// ==UserScript==
// @name         卖家精灵一体化选品 0.3.8.12
// @namespace    amazon-products
// @version      0.3.8.12
// @description  基于 0.3.8.11；Keepa 图表最长等待 30 秒，流量洞察 5 秒快速淘汰与所有硬门槛不变。
// @match        https://www.amazon.com/*
// @grant        GM_setClipboard
// @grant        GM_xmlhttpRequest
// @grant        GM_download
// @connect      127.0.0.1
// @connect      localhost
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  var VERSION = '0.3.8.12';
  var SCHEMA_VERSION = 'sellerSpriteIntegratedBatch/v0.3.0';
  var ENABLE_ZH_UI = true;
  var ENABLE_ACCEPTED_EXCEL_BRIDGE = true;
  var ENABLE_TIER0_TELEMETRY = true;
  var ENABLE_TIER0_GRANULAR_TELEMETRY = true;
  var ENABLE_P1_CUMULATIVE_TARGET_CONTROL = true;
  var ENABLE_STORAGE_HARDENING = true;
  var ENABLE_DEFERRED_FULL_JSON = true;
  var ENABLE_TIER2_2_CONDITIONAL_RETRY = true;
  var ENABLE_TRAFFIC_TAB_READY_GRACE = true;
  var ENABLE_TRAFFIC_BLOCK_FAST_SKIP = true;
  var TRAFFIC_TAB_READY_GRACE_VERSION = 'traffic-tab-ready-grace-8s-v1';
  var TRAFFIC_TAB_READY_GRACE_MS = 8000;
  var TRAFFIC_TAB_READY_POLL_MS = 100;
  var TRAFFIC_BLOCK_FAST_SKIP_VERSION = 'traffic-block-fast-skip-5s-v1';
  var TRAFFIC_BLOCK_READY_TIMEOUT_MS = 5000;
  var ENABLE_AGGREGATE_NATURAL_TRAFFIC_GATE = true;
  var ENABLE_CONFIRMED_NO_DATA_FAST_FAIL = true;
  var ENABLE_KEEPA_CHART_READY_PROTOCOL = true;
  var ENABLE_KEEPA_PARENT_CLICK_PROTOCOL = true;
  var CONFIRMED_NO_DATA_FAST_FAIL_VERSION = 'confirmed-no-data-fast-fail-v1';
  var KEEPA_CHART_READY_VERSION = 'keepa-chart-ready-30s-v3';
  var KEEPA_PARENT_CLICK_VERSION = 'keepa-parent-click-v1';
  var KEEPA_TAB_READY_TIMEOUT_MS = 8000;
  var KEEPA_CHART_READY_TIMEOUT_MS = 30000;
  var KEEPA_CHART_READY_RETRY_AT_MS = 5000;
  var KEEPA_CHART_READY_POLL_MS = 200;
  var AGGREGATE_NATURAL_TRAFFIC_GATE_VERSION = 'aggregate-weighted-share-v1';
  var TIER2_RETRY_VERSION = 'tier2.2-conditional-retry-v1';
  var TELEMETRY_SCHEMA_VERSION = 'sellerSpriteTelemetry/v1';
  var GRANULAR_TELEMETRY_SCHEMA_VERSION = 'sellerSpriteGranularTelemetry/v1';
  var GRANULAR_TELEMETRY_VERSION = 'tier0.2-granular-v1';
  var TARGET_CONTROL_VERSION = 'p1-cumulative-remaining-v1';
  var STORAGE_HARDENING_VERSION = 'storage-hardening-v1';
  var DEFERRED_FULL_JSON_VERSION = 'deferred-full-json-v1';
  var STORAGE_PREFIX = 'ssIntegratedRunner:v0.3:';
  var PRICE_MIN_USD = 9.9;
  var PRICE_MAX_USD = 50;
  var INDEX_KEY = STORAGE_PREFIX + 'index';
  var SELECTED_KEY = STORAGE_PREFIX + 'selected';
  var STRICT_HISTORY_KEY = STORAGE_PREFIX + 'strict-qualified-history';
  var GRANULAR_STORAGE_PREFIX = STORAGE_PREFIX + 'granular:v1:';
  var EXCEL_BRIDGE_URL_KEY = STORAGE_PREFIX + 'excel-bridge-url';
  var EXCEL_BRIDGE_TOKEN_KEY = STORAGE_PREFIX + 'excel-bridge-token';
  var EXCEL_BRIDGE_REQUEST_SCHEMA = 'sellerSpriteExcelBridgeRequest/v1';
  var EXCEL_BRIDGE_RESPONSE_SCHEMA = 'sellerSpriteExcelBridgeResponse/v1';
  var DEFAULT_EXCEL_BRIDGE_URL = 'http://127.0.0.1:8765';
  var RUNNER_INJECTED_AT_MS = Date.now();
  var RUNNER_DOCUMENT_READY_STATE = typeof document === 'undefined' ? '' : document.readyState;
  var ACTIVE_ROW_TIMING = null;
  var ACTIVE_GRANULAR_CONTEXT = null;
  var LAST_GRANULAR_TELEMETRY_ERROR = '';
  var LAST_STORAGE_ERROR = '';
  var BOOTSTRAP_STRICT_QUALIFIED_ASINS = [
    'B0G13L54YJ', 'B0G6B1QMZ9', 'B0GCHYHJ1K', 'B0GD1JJPGP', 'B0GDZJKDDP',
    'B0GKPLMCBW', 'B0GPSDTCRK', 'B0GQF915RX', 'B0GQXD4RTK', 'B0GR8R37RG',
    'B0GRGP6XCZ', 'B0GSD21KK3', 'B0GSFKBJG1', 'B0GSFSJKRF', 'B0GSQYZYNG',
    'B0GSTM7S86', 'B0GSZG9SL4', 'B0GT1YJLF3', 'B0GT9LVYK6', 'B0GTHRBXVV',
    'B0GTLKVTPV', 'B0GTYFBN9F', 'B0GV45ZG2F', 'B0GV7W7KDY', 'B0GVB3SPJX',
    'B0GVB9P9BK', 'B0GVDDW8LC', 'B0GWCPW954', 'B0GWKS2RZD', 'B0GWMP6B9V',
    'B0GWPTQ165', 'B0GX12QFSV', 'B0GX1GQZDB', 'B0GX56PWJH', 'B0GX5M4D9S',
    'B0GX7MVHV1', 'B0GXDJ74HR', 'B0GXR4ZYJN', 'B0GY3N2S23', 'B0GY45RKR1',
    'B0GY6ZST9G', 'B0GYN3WLDG', 'B0GYYT43HQ', 'B0H2YQW5LG', 'B0H3P3KG2V'
  ];
  var AUTO_PARAM = 'ss-v3';
  var HASH_PARAM = 'ss-v3-hash';
  var INDEX_PARAM = 'ss-v3-index';
  var GATE_LOG_COLUMNS = [
    'finishedAt', 'batchName', 'queueHash', 'asin', 'runnerVersion', 'collectorVersion', 'outcome',
    'shortCircuitGate', 'shortCircuitStage', 'gateA', 'gateB', 'gateC', 'gateD',
    'gateE', 'gateF', 'trafficStatus', 'weeksRead', 'latestNaturalSharePct',
    'recent4AvgNaturalSharePct', 'recent4MinNaturalSharePct', 'aggregateNaturalTraffic',
    'aggregateTotalTraffic', 'aggregateNaturalSharePct', 'aggregateWeeksRead', 'dimensions',
    'dimensionsSource', 'currentPrice', 'priceTrendClass', 'priceCollectionStatus',
    'priceReadyWaitMs', 'priceRetryCount', 'rejectionRule',
    'rejectionReason', 'skippedSteps', 'url'
  ];
  var TIMING_LOG_COLUMNS = [
    'startedAt', 'finishedAt', 'batchName', 'queueHash', 'asin', 'runnerVersion', 'collectorVersion',
    'detailPageMs', 'detailPageMsReason', 'trafficChartMs', 'trafficChartMsReason',
    'dimensionsMs', 'dimensionsMsReason', 'priceChartMs', 'priceChartMsReason',
    'retryCount', 'retryDecision', 'retryReason', 'totalMs'
  ];
  var GRANULAR_TIMING_COLUMNS = [
    'row', 'asin', 'batchName', 'queueHash', 'runnerVersion', 'collectorVersion',
    'navigationIntentAtMs', 'navigationStartAtMs', 'amazonDomReadyAtMs', 'runnerInjectedAtMs',
    'autoProcessStartedAtMs', 'navigationType', 'preNavigationMs', 'navigationDomMs',
    'domToRunnerInjectionMs', 'runnerBootDelayMs', 'documentReadyState',
    'trafficTabWaitStartedAtMs', 'trafficTabClickAtMs', 'trafficTabClickFound',
    'trafficTabGraceWaitMs', 'trafficTabPollCount', 'trafficTabGraceRecovered', 'trafficChartReadyAtMs',
    'trafficTabToChartReadyMs', 'collectorAttempts', 'persistenceCallCount',
    'serializeTotalMs', 'storageWriteTotalMs', 'persistenceTotalMs', 'persistenceMaxMs',
    'panelRenderCallCount', 'panelRenderTotalMs', 'panelRenderMaxMs', 'panelJsonSerializeMs',
    'autoStartRequestedMs', 'autoStartActualMs', 'interRowRequestedMs', 'interRowActualMs',
    'postResultToNextNavigationMs', 'pauseRecoveryMs', 'resultFinishedAtMs', 'flushAtMs',
    'missingReason'
  ];
  var CONTROL_EVENT_COLUMNS = [
    'atMs', 'event', 'row', 'asin', 'stepBefore', 'statusBefore', 'pauseId',
    'pauseDurationMs', 'recoveryKind', 'recoveryEvidence', 'reason'
  ];

  function oneLine(value) {
    return String(value == null ? '' : value).replace(/\s+/g, ' ').trim();
  }

  function numberOrNull(value) {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    var match = String(value == null ? '' : value).replace(/,/g, '').match(/-?\d+(?:\.\d+)?/);
    return match ? Number(match[0]) : null;
  }

  function normalizeAsin(value) {
    var match = String(value || '').toUpperCase().match(/\b(B0[A-Z0-9]{8})\b/);
    return match ? match[1] : '';
  }

  function uniqueAsins(value) {
    var matches = String(value || '').toUpperCase().match(/\bB0[A-Z0-9]{8}\b/g) || [];
    return Array.from(new Set(matches));
  }

  function filterHistoricalQueue(queue, knownAsins) {
    var history = knownAsins || {};
    var accepted = [];
    var skipped = [];
    (queue || []).forEach(function (value) {
      var asin = normalizeAsin(value);
      if (!asin) return;
      if (history[asin]) skipped.push(asin);
      else accepted.push(asin);
    });
    return { queue: accepted, skipped: skipped };
  }

  function parseTrafficCollector(payload, targetAsin, actualAsin) {
    payload = payload || {};
    var latest = payload.latest || {};
    var latestShare = numberOrNull(latest.naturalSharePct);
    var avg = numberOrNull(payload.recent4AvgNaturalSharePct);
    var min = numberOrNull(payload.recent4MinNaturalSharePct);
    var aggregateNaturalTraffic = numberOrNull(payload.aggregateNaturalTraffic);
    var aggregateTotalTraffic = numberOrNull(payload.aggregateTotalTraffic);
    var aggregateNaturalSharePct = numberOrNull(payload.aggregateNaturalSharePct);
    var aggregateWeeksRead = Number(payload.aggregateWeeksRead || 0);
    var weeks = Number(payload.weeksRead || 0);
    return {
      targetAsin: normalizeAsin(targetAsin),
      actualAsin: normalizeAsin(actualAsin),
      status: payload.status || 'error',
      decision: payload.decision || 'review',
      latestWeek: oneLine(latest.week),
      latestNaturalSharePct: latestShare,
      latestNaturalShareDerived: latest.naturalShareDerived === true,
      latestNaturalShareSource: oneLine(latest.naturalShareSource || ''),
      recent4AvgNaturalSharePct: avg,
      recent4MinNaturalSharePct: min,
      aggregateNaturalTraffic: aggregateNaturalTraffic,
      aggregateTotalTraffic: aggregateTotalTraffic,
      aggregateNaturalSharePct: aggregateNaturalSharePct,
      aggregateWeeksRead: aggregateWeeksRead,
      trafficDetails: Array.isArray(payload.details) ? payload.details : [],
      noDataEvidence: payload.noDataEvidence || null,
      weeksRead: weeks,
      trafficWindow: payload.trafficWindow || 'recent 2 months / max 9 weeks',
      pass70: payload.pass70 === true,
      collectorVersion: payload.collectorVersion || '',
      method: payload.method || 'collector_0.4.6',
      collectedAt: payload.collectedAt || new Date().toISOString(),
      note: payload.status === 'ok' ? oneLine(payload.decision || 'ok') : oneLine(payload.status || 'error')
    };
  }

  function evaluateTrafficGate(traffic, asinMismatch) {
    if (asinMismatch) return { pass: false, stage: 'asin', rule: 'asin_mismatch', reason: 'amazon_variant_redirect' };
    if (ENABLE_CONFIRMED_NO_DATA_FAST_FAIL && traffic && traffic.status === 'no_data_confirmed') {
      return { pass: false, stage: 'traffic', rule: 'traffic_no_data_confirmed', reason: 'seller_sprite_explicit_no_data' };
    }
    if (!traffic || traffic.status !== 'ok') return { pass: false, stage: 'traffic', rule: 'traffic_error', reason: oneLine((traffic || {}).note || (traffic || {}).status || 'missing_traffic') };
    if (!ENABLE_AGGREGATE_NATURAL_TRAFFIC_GATE && Number(traffic.weeksRead || 0) < 3) return { pass: false, stage: 'traffic', rule: 'traffic_weeks_insufficient', reason: 'weeksRead < 3' };
    if (ENABLE_AGGREGATE_NATURAL_TRAFFIC_GATE) {
      var aggregateWeeks = Number(traffic.aggregateWeeksRead || 0);
      var aggregateShare = traffic.aggregateNaturalSharePct;
      if (aggregateWeeks < 3) return { pass: false, stage: 'traffic', rule: 'traffic_weeks_insufficient', reason: 'aggregateWeeksRead < 3' };
      if (!Number.isFinite(aggregateShare)) return { pass: false, stage: 'traffic', rule: 'traffic_metric_missing', reason: 'aggregateNaturalSharePct missing' };
      if (aggregateShare < 70) return { pass: false, stage: 'traffic', rule: 'traffic_aggregate_below_70', reason: aggregateShare.toFixed(2) + '% < 70%' };
      return { pass: true, stage: 'traffic', rule: 'traffic_aggregate_pass', reason: 'aggregate natural traffic share >= 70%' };
    }
    var checks = [
      ['traffic_latest_below_70', traffic.latestNaturalSharePct],
      ['traffic_recent4_avg_below_70', traffic.recent4AvgNaturalSharePct],
      ['traffic_recent4_min_below_70', traffic.recent4MinNaturalSharePct]
    ];
    for (var i = 0; i < checks.length; i += 1) {
      var value = checks[i][1];
      if (!Number.isFinite(value)) return { pass: false, stage: 'traffic', rule: 'traffic_metric_missing', reason: checks[i][0] + ' missing' };
      if (value < 70) return { pass: false, stage: 'traffic', rule: checks[i][0], reason: value.toFixed(2) + '% < 70%' };
    }
    return { pass: true, stage: 'traffic', rule: 'traffic_pass', reason: 'traffic thresholds pass' };
  }

  function collectorHasKnownTrafficFailure(payload) {
    payload = payload || {};
    var latest = numberOrNull((payload.latest || {}).naturalSharePct);
    var avg = numberOrNull(payload.recent4AvgNaturalSharePct);
    var min = numberOrNull(payload.recent4MinNaturalSharePct);
    var aggregate = numberOrNull(payload.aggregateNaturalSharePct);
    return (ENABLE_CONFIRMED_NO_DATA_FAST_FAIL && payload.status === 'no_data_confirmed')
      || payload.shortCircuited === true
      || (ENABLE_AGGREGATE_NATURAL_TRAFFIC_GATE && Number(payload.aggregateWeeksRead || 0) >= 3 && Number.isFinite(aggregate) && aggregate < 70)
      || (!ENABLE_AGGREGATE_NATURAL_TRAFFIC_GATE && Number.isFinite(latest) && latest < 70)
      || (!ENABLE_AGGREGATE_NATURAL_TRAFFIC_GATE && Number.isFinite(avg) && avg < 70)
      || (!ENABLE_AGGREGATE_NATURAL_TRAFFIC_GATE && Number.isFinite(min) && min < 70);
  }

  function legacyCollectorRetryReason(payload) {
    payload = payload || {};
    if (collectorHasKnownTrafficFailure(payload)) return '';
    return payload.status !== 'ok' || Number(payload.weeksRead || 0) < 3
      ? 'legacy_incomplete_traffic'
      : '';
  }

  function collectorRetryReason(payload) {
    payload = payload || {};
    if (ENABLE_CONFIRMED_NO_DATA_FAST_FAIL && payload.status === 'no_data_confirmed') return '';
    if (collectorHasKnownTrafficFailure(payload)) return '';
    if (payload.retryable === true) return oneLine(payload.retryReason || 'collector_not_ready');
    if (payload.status === 'no_chart_loaded') return 'chart_not_ready';
    if (payload.status === 'no_data' && (!Array.isArray(payload.details) || payload.details.length === 0)) {
      return 'tooltip_not_ready';
    }
    return '';
  }

  function shouldRetryCollector(payload) {
    return Boolean(ENABLE_TIER2_2_CONDITIONAL_RETRY
      ? collectorRetryReason(payload)
      : legacyCollectorRetryReason(payload));
  }

  function evaluateDimensionsGate(dimensions) {
    return oneLine(dimensions)
      ? { pass: true, stage: 'dimensions', rule: 'dimensions_pass', reason: 'dimensions present' }
      : { pass: false, stage: 'dimensions', rule: 'dimensions_missing', reason: 'dimensions missing' };
  }

  function currentPriceFromSamples(samples) {
    var clean = normalizePriceSamples(samples);
    return clean.length ? clean[clean.length - 1].price : null;
  }

  function evaluatePriceGate(priceTrendClass, currentPrice) {
    var value = oneLine(priceTrendClass).toLowerCase();
    var price = Number(currentPrice);
    if (!Number.isFinite(price) || price <= 0) {
      return { pass: false, stage: 'price', rule: 'price_current_missing', reason: 'current price missing' };
    }
    if (price < PRICE_MIN_USD || price > PRICE_MAX_USD) {
      return {
        pass: false,
        stage: 'price',
        rule: 'price_current_out_of_range',
        reason: usd(price) + ' outside $' + PRICE_MIN_USD.toFixed(2) + '-$' + PRICE_MAX_USD.toFixed(2)
      };
    }
    return ['stable', 'rising'].indexOf(value) >= 0
      ? { pass: true, stage: 'price', rule: 'price_trend_pass', reason: value }
      : { pass: false, stage: 'price', rule: 'price_trend_not_allowed', reason: value || 'no_data' };
  }

  function isQualifiedResult(result) {
    if (!result) return false;
    if (result.strictDecision) return result.strictDecision === 'pass';
    var currentPrice = Number.isFinite(Number(result.currentPrice))
      ? Number(result.currentPrice)
      : currentPriceFromSamples(result.priceSamples);
    return evaluateTrafficGate(result, Boolean(result.asinMismatch)).pass
      && evaluateDimensionsGate(result.dimensions).pass
      && evaluatePriceGate(result.priceTrendClass, currentPrice).pass;
  }

  function summarizeResults(results) {
    var completed = (results || []).filter(Boolean).length;
    var qualified = (results || []).filter(isQualifiedResult).length;
    return { completed: completed, qualified: qualified, rejected: completed - qualified };
  }

  function nonNegativeIntegerOrNull(value) {
    if (value === null || value === undefined || value === '') return null;
    var number = Number(value);
    return Number.isInteger(number) && number >= 0 ? number : null;
  }

  function positiveIntegerOrNull(value) {
    var number = nonNegativeIntegerOrNull(value);
    return number !== null && number > 0 ? number : null;
  }

  function normalizeTargetControl(state) {
    state = state || {};
    var requested = positiveIntegerOrNull(state.requestedFinalTargetAtStart);
    var legacyTarget = positiveIntegerOrNull(state.targetQualified);
    var hasRemaining = ENABLE_P1_CUMULATIVE_TARGET_CONTROL
      && state.targetControlVersion === TARGET_CONTROL_VERSION;
    var remaining = hasRemaining ? nonNegativeIntegerOrNull(state.remainingTargetAtStart) : null;
    if (hasRemaining && remaining === null) {
      return { valid: false, mode: 'cumulative_remaining', reason: 'remaining_target_missing_or_invalid' };
    }
    requested = requested || legacyTarget || 20;
    var effective = remaining === null ? (legacyTarget || requested) : remaining;
    if (effective > requested) {
      return { valid: false, mode: 'cumulative_remaining', reason: 'remaining_target_exceeds_requested_target' };
    }
    return {
      valid: true,
      mode: remaining === null ? 'legacy_batch' : 'cumulative_remaining',
      requestedFinalTargetAtStart: requested,
      remainingTargetAtStart: remaining,
      effectiveStopBudget: effective,
      version: remaining === null ? '' : TARGET_CONTROL_VERSION
    };
  }

  function effectiveStopBudget(state) {
    var control = normalizeTargetControl(state);
    return control.valid ? control.effectiveStopBudget : null;
  }

  function browserPassesThisBatch(state) {
    return summarizeResults((state || {}).results).qualified;
  }

  function stopDecision(state) {
    var control = normalizeTargetControl(state);
    var passes = browserPassesThisBatch(state);
    if (!control.valid) {
      return { stop: true, reason: 'invalid_target_control', action: 'fail_closed', passes: passes, control: control };
    }
    if (state && state.stopAfterCurrentRowRequested) {
      return { stop: true, reason: 'operator_stop_after_current_row', action: 'stop_after_current_row', passes: passes, control: control };
    }
    if (control.effectiveStopBudget === 0) {
      return { stop: true, reason: 'target_already_reached', action: 'none', passes: passes, control: control };
    }
    if (passes >= control.effectiveStopBudget) {
      return { stop: true, reason: 'target_reached', action: 'stop_after_current_row', passes: passes, control: control };
    }
    return { stop: false, reason: '', action: '', passes: passes, control: control };
  }

  function requestStopAfterCurrentRow(state, source) {
    state = state || {};
    state.stopAfterCurrentRowRequested = true;
    state.stopAction = source || 'operator_stop_after_current_row';
    state.message = 'Stop requested; the current row will finish and be saved.';
    return state;
  }

  function mergeLatestControlState(state, latestState) {
    if (!state || !latestState || state.queueHash !== latestState.queueHash) return state;
    [
      'status',
      'stopAfterCurrentRowRequested',
      'stopAction',
      'stoppedReason',
      'stopReason',
      'pauseId',
      'pausedAtMs',
      'pendingPauseRecoveryMs'
    ].forEach(function (field) {
      if (Object.prototype.hasOwnProperty.call(latestState, field)) state[field] = latestState[field];
    });
    return state;
  }

  function mergeGranularRowSidecar(latestSidecar, fallbackSidecar, index, row) {
    var fallback = fallbackSidecar || {};
    var latestIsCompatible = latestSidecar
      && latestSidecar.schemaVersion === GRANULAR_TELEMETRY_SCHEMA_VERSION
      && latestSidecar.queueHash
      && latestSidecar.queueHash === fallback.queueHash
      && (latestSidecar.batchCreatedAt || '') === (fallback.batchCreatedAt || '');
    var sidecar = latestIsCompatible ? latestSidecar : fallback;
    if (!sidecar.rowsByIndex || typeof sidecar.rowsByIndex !== 'object') sidecar.rowsByIndex = {};
    sidecar.rowsByIndex[String(index)] = row;
    return sidecar;
  }

  function gateCodeForStage(stage) {
    return { traffic: 'C', dimensions: 'D', price: 'E' }[oneLine(stage)] || '';
  }

  function buildRunnerGateLogRow(result, context) {
    result = result || {};
    context = context || {};
    var passed = result.strictDecision === 'pass';
    var stage = passed ? '' : oneLine(result.rejectionStage);
    var gateC = 'not_run';
    var gateD = 'not_run';
    var gateE = 'not_run';
    if (passed) {
      gateC = 'pass';
      gateD = 'pass';
      gateE = 'pass';
    } else if (stage === 'traffic') {
      gateC = 'reject';
    } else if (stage === 'dimensions') {
      gateC = 'pass';
      gateD = 'reject';
    } else if (stage === 'price') {
      gateC = 'pass';
      gateD = 'pass';
      gateE = 'reject';
    }
    return {
      finishedAt: result.finishedAt || '',
      batchName: context.batchName || '',
      queueHash: context.queueHash || '',
      asin: result.targetAsin || result.asin || '',
      runnerVersion: VERSION,
      collectorVersion: result.collectorVersion || '',
      outcome: passed ? 'pass' : 'reject',
      shortCircuitGate: gateCodeForStage(stage),
      shortCircuitStage: stage,
      gateA: 'not_evaluated_in_runner',
      gateB: 'not_evaluated_in_runner',
      gateC: gateC,
      gateD: gateD,
      gateE: gateE,
      gateF: 'not_evaluated_in_runner',
      trafficStatus: result.status || '',
      weeksRead: typeof result.weeksRead === 'number' ? result.weeksRead : null,
      latestNaturalSharePct:
        typeof result.latestNaturalSharePct === 'number' ? result.latestNaturalSharePct : null,
      recent4AvgNaturalSharePct:
        typeof result.recent4AvgNaturalSharePct === 'number' ? result.recent4AvgNaturalSharePct : null,
      recent4MinNaturalSharePct:
        typeof result.recent4MinNaturalSharePct === 'number' ? result.recent4MinNaturalSharePct : null,
      aggregateNaturalTraffic:
        typeof result.aggregateNaturalTraffic === 'number' ? result.aggregateNaturalTraffic : null,
      aggregateTotalTraffic:
        typeof result.aggregateTotalTraffic === 'number' ? result.aggregateTotalTraffic : null,
      aggregateNaturalSharePct:
        typeof result.aggregateNaturalSharePct === 'number' ? result.aggregateNaturalSharePct : null,
      aggregateWeeksRead: typeof result.aggregateWeeksRead === 'number' ? result.aggregateWeeksRead : null,
      dimensions: result.dimensions || '',
      dimensionsSource: result.dimensionsSource || '',
      currentPrice: typeof result.currentPrice === 'number' ? result.currentPrice : null,
      priceTrendClass: result.priceTrendClass || '',
      priceCollectionStatus: result.priceCollectionStatus || '',
      priceReadyWaitMs: typeof result.priceReadyWaitMs === 'number' ? result.priceReadyWaitMs : null,
      priceRetryCount: typeof result.priceRetryCount === 'number' ? result.priceRetryCount : 0,
      rejectionRule: result.rejectionRule || '',
      rejectionReason: result.rejectionReason || '',
      skippedSteps: Array.isArray(result.skippedSteps) ? result.skippedSteps.join(',') : '',
      url: result.url || ''
    };
  }

  function buildHistorySkipGateLogRow(asin, context) {
    context = context || {};
    return {
      finishedAt: context.generatedAt || '',
      batchName: context.batchName || '',
      queueHash: context.queueHash || '',
      asin: normalizeAsin(asin),
      runnerVersion: VERSION,
      collectorVersion: '',
      outcome: 'skip',
      shortCircuitGate: '',
      shortCircuitStage: 'history',
      gateA: 'not_run_history_skip',
      gateB: 'not_run_history_skip',
      gateC: 'not_run_history_skip',
      gateD: 'not_run_history_skip',
      gateE: 'not_run_history_skip',
      gateF: 'not_run_history_skip',
      trafficStatus: '',
      weeksRead: null,
      latestNaturalSharePct: null,
      recent4AvgNaturalSharePct: null,
      recent4MinNaturalSharePct: null,
      aggregateNaturalTraffic: null,
      aggregateTotalTraffic: null,
      aggregateNaturalSharePct: null,
      aggregateWeeksRead: null,
      dimensions: '',
      dimensionsSource: '',
      currentPrice: null,
      priceTrendClass: '',
      rejectionRule: 'strict_qualified_history_hit',
      rejectionReason: 'historical strict-qualified ASIN skipped; cache did not pass it',
      skippedSteps: 'traffic,dimensions,price',
      url: ''
    };
  }

  function measurementReason(value, configuredReason) {
    return typeof value === 'number' && Number.isFinite(value) ? '' : (configuredReason || 'not_measured');
  }

  function buildRunnerTimingLogRow(result, measurements, context) {
    result = result || {};
    measurements = measurements || {};
    context = context || {};
    return {
      startedAt: result.startedAt || measurements.startedAt || '',
      finishedAt: result.finishedAt || measurements.finishedAt || '',
      batchName: context.batchName || '',
      queueHash: context.queueHash || '',
      asin: result.targetAsin || result.asin || '',
      runnerVersion: VERSION,
      collectorVersion: result.collectorVersion || '',
      detailPageMs: typeof measurements.detailPageMs === 'number' ? measurements.detailPageMs : null,
      detailPageMsReason: measurementReason(measurements.detailPageMs, measurements.detailPageMsReason),
      trafficChartMs: typeof measurements.trafficChartMs === 'number' ? measurements.trafficChartMs : null,
      trafficChartMsReason: measurementReason(measurements.trafficChartMs, measurements.trafficChartMsReason),
      dimensionsMs: typeof measurements.dimensionsMs === 'number' ? measurements.dimensionsMs : null,
      dimensionsMsReason: measurementReason(measurements.dimensionsMs, measurements.dimensionsMsReason),
      priceChartMs: typeof measurements.priceChartMs === 'number' ? measurements.priceChartMs : null,
      priceChartMsReason: measurementReason(measurements.priceChartMs, measurements.priceChartMsReason),
      retryCount: Number.isInteger(measurements.retryCount) ? measurements.retryCount : 0,
      retryDecision: measurements.retryDecision || '',
      retryReason: measurements.retryReason || '',
      totalMs: typeof measurements.totalMs === 'number' ? measurements.totalMs : null
    };
  }

  function buildHistorySkipTimingLogRow(asin, context) {
    return buildRunnerTimingLogRow(
      { asin: normalizeAsin(asin), startedAt: '', finishedAt: (context || {}).generatedAt || '' },
      {
        detailPageMsReason: 'history_skip_no_browser_visit',
        trafficChartMsReason: 'history_skip_no_browser_visit',
        dimensionsMsReason: 'history_skip_no_browser_visit',
        priceChartMsReason: 'history_skip_no_browser_visit',
        retryCount: 0,
        retryDecision: 'not_run_history_skip',
        retryReason: 'history_skip_no_browser_visit',
        totalMs: 0
      },
      context
    );
  }

  function tsvCell(value) {
    if (value == null) return '';
    var text = typeof value === 'object' ? JSON.stringify(value) : String(value);
    return text.replace(/[\t\r\n]+/g, ' ');
  }

  function rowsToTsv(rows, columns) {
    rows = Array.isArray(rows) ? rows : [];
    columns = Array.isArray(columns) ? columns : [];
    var lines = [columns.join('\t')];
    rows.forEach(function (row) {
      lines.push(columns.map(function (column) { return tsvCell(row ? row[column] : ''); }).join('\t'));
    });
    return lines.join('\n');
  }

  function attachRunnerTelemetry(result, measurements, context) {
    if (!ENABLE_TIER0_TELEMETRY) return result;
    result.telemetry = {
      schemaVersion: TELEMETRY_SCHEMA_VERSION,
      gate: buildRunnerGateLogRow(result, context),
      timing: buildRunnerTimingLogRow(result, measurements, context)
    };
    return result;
  }

  function parsePriceTooltip(text) {
    var clean = oneLine(text);
    var dateMatch = clean.match(/\b(20\d{2}-\d{2}-\d{2})\b/);
    if (!dateMatch) return null;
    var patterns = [
      /Buybox价格\s*\$\s*([\d,.]+)/i,
      /Buy Box(?: price)?\s*\$\s*([\d,.]+)/i,
      /新品价格\s*\$\s*([\d,.]+)/i,
      /价格\s*\$\s*([\d,.]+)/i,
      /\$\s*([\d,.]+)/
    ];
    var price = null;
    for (var i = 0; i < patterns.length; i += 1) {
      var match = clean.match(patterns[i]);
      if (match) {
        price = numberOrNull(match[1]);
        break;
      }
    }
    if (!Number.isFinite(price) || price <= 0) return null;
    return { date: dateMatch[1], price: price, rawText: clean };
  }

  function normalizePriceSamples(samples) {
    var byDate = {};
    (samples || []).forEach(function (sample) {
      if (!sample || !sample.date || !Number.isFinite(Number(sample.price)) || Number(sample.price) <= 0) return;
      byDate[sample.date] = { date: sample.date, price: Number(sample.price) };
    });
    return Object.keys(byDate).sort().map(function (date) { return byDate[date]; });
  }

  function average(values) {
    if (!values.length) return null;
    return values.reduce(function (sum, value) { return sum + value; }, 0) / values.length;
  }

  function classifyPriceSamples(samples) {
    var clean = normalizePriceSamples(samples);
    if (clean.length < 3) return 'no_data';
    var prices = clean.map(function (sample) { return sample.price; });
    var groupSize = Math.max(1, Math.ceil(prices.length / 3));
    var firstAverage = average(prices.slice(0, groupSize));
    var lastAverage = average(prices.slice(-groupSize));
    var current = prices[prices.length - 1];
    var minimum = Math.min.apply(null, prices);
    var maximum = Math.max.apply(null, prices);
    var changePct = firstAverage ? (lastAverage - firstAverage) / firstAverage : 0;
    var rangePct = minimum ? (maximum - minimum) / minimum : 0;
    var peakToCurrent = maximum ? (maximum - current) / maximum : 0;
    var reversals = 0;
    var previousDirection = 0;
    for (var i = 1; i < prices.length; i += 1) {
      var base = prices[i - 1] || 1;
      var deltaPct = (prices[i] - prices[i - 1]) / base;
      var direction = Math.abs(deltaPct) < 0.01 ? 0 : (deltaPct > 0 ? 1 : -1);
      if (direction && previousDirection && direction !== previousDirection) reversals += 1;
      if (direction) previousDirection = direction;
    }
    if (changePct <= -0.08 || (peakToCurrent >= 0.12 && current <= minimum * 1.03)) return 'declining';
    if (rangePct >= 0.35 && reversals >= 2) return 'volatile';
    if (changePct >= 0.05 || (current >= maximum * 0.97 && current > firstAverage * 1.03)) return 'rising';
    if (rangePct <= 0.20 || Math.abs(changePct) < 0.05) return 'stable';
    return 'volatile';
  }

  function usd(value) {
    return '$' + Number(value).toFixed(2);
  }

  function buildPriceTrend(samples) {
    var clean = normalizePriceSamples(samples);
    var priceTrendClass = classifyPriceSamples(clean);
    if (!clean.length) {
      return {
        priceTrend: '近1个月价格趋势数据不足。',
        priceTrendClass: 'no_data',
        priceTrendWindow: '近1个月',
        priceTrendSource: 'SellerSprite Keepa插件替代图',
        currentPrice: null,
        priceMin: null,
        priceMax: null,
        priceSamples: []
      };
    }
    var prices = clean.map(function (sample) { return sample.price; });
    var minimum = Math.min.apply(null, prices);
    var maximum = Math.max.apply(null, prices);
    var current = prices[prices.length - 1];
    var suffix = {
      stable: '整体波动有限，判定稳定。',
      rising: '当前处于区间高位或上涨趋势。',
      declining: '当前处于区间低位，呈下降趋势。',
      volatile: '价格往返波动较大，判定高波动。',
      no_data: '有效价格样本不足。'
    }[priceTrendClass];
    return {
      priceTrend: '近1个月价格区间 ' + usd(minimum) + '-' + usd(maximum) + '，当前 ' + usd(current) + '，' + suffix,
      priceTrendClass: priceTrendClass,
      priceTrendWindow: '近1个月',
      priceTrendSource: 'SellerSprite Keepa插件替代图',
      currentPrice: current,
      priceMin: minimum,
      priceMax: maximum,
      priceSamples: clean
    };
  }

  function buildDimensions(fields) {
    fields = fields || {};
    var parts = [];
    [
      ['\u5546\u54c1\u5c3a\u5bf8', fields.itemDimensions],
      ['\u5546\u54c1\u91cd\u91cf', fields.itemWeight],
      ['\u5305\u88c5\u5c3a\u5bf8', fields.packageDimensions],
      ['\u5305\u88c5\u91cd\u91cf', fields.packageWeight]
    ].forEach(function (entry) {
      var value = oneLine(entry[1]);
      if (value) parts.push(entry[0] + ' ' + value);
    });
    return parts.join('\uFF1B');
  }

  function valueAfterLabel(text, label) {
    var clean = oneLine(text);
    if (clean.toLowerCase().indexOf(String(label).toLowerCase()) !== 0) return '';
    var remainder = oneLine(clean.slice(String(label).length).replace(/^\s*[:\uFF1A]\s*/, ''));
    return remainder && !/^[:\uFF1A]+$/.test(remainder) ? remainder : '';
  }

  function panelOutputValue(state) {
    if (ENABLE_DEFERRED_FULL_JSON) {
      return '完整 JSON 已延迟生成。需要时请点击“复制合并 JSON”或其他导出按钮。';
    }
    return JSON.stringify(exportBatch(state), null, 2);
  }

  function commitCompletedRow(state, index, result, persistState, recordHistory, readHistory) {
    persistState = persistState || saveBatch;
    recordHistory = recordHistory || recordStrictQualified;
    readHistory = readHistory || getStrictHistory;
    state.results[index] = result;
    state.currentIndex = index + 1;
    state.currentStep = 'saved';
    persistState(state);
    var history;
    if (result.strictDecision === 'pass') {
      history = recordHistory(normalizeAsin(result.targetAsin || result.asin || state.queue[index]), {
        qualifiedAt: result.finishedAt,
        batchName: state.batchName,
        queueHash: state.queueHash
      });
    } else {
      history = readHistory();
    }
    state.historyRegistryCount = Object.keys((history || {}).asins || {}).length;
    return { state: state, history: history };
  }

  function classifySellerSpriteAccessState(snapshot) {
    snapshot = snapshot || {};
    if (snapshot.loginVisible === true) {
      return {
        code: 'seller_sprite_login_required',
        message: '卖家精灵插件未登录；请同步网页端账号后继续。'
      };
    }
    var contentText = oneLine(snapshot.contentText || '');
    if (/仅限付费用户|升级套餐后即可查看/.test(contentText)) {
      return {
        code: 'seller_sprite_paid_plan_required',
        message: '卖家精灵流量洞察需要有效付费套餐；续费或切换有权限账号后继续。'
      };
    }
    return null;
  }

  function applySellerSpriteAccessPause(state, index, asin, blocker, nowMs) {
    state.status = 'paused';
    state.currentIndex = index;
    state.currentStep = 'external_blocked';
    state.message = blocker.message;
    state.pauseId = 'seller-sprite-access-' + nowMs;
    state.pausedAtMs = nowMs;
    state.externalBlockerCode = blocker.code;
    state.externalBlockerAsin = asin;
    return state;
  }

  globalThis.SSIntegratedRunnerCore = Object.freeze({
    buildDimensions: buildDimensions,
    buildPriceTrend: buildPriceTrend,
    classifyPriceSamples: classifyPriceSamples,
    normalizeAsin: normalizeAsin,
    parsePriceTooltip: parsePriceTooltip,
    parseTrafficCollector: parseTrafficCollector,
    evaluateTrafficGate: evaluateTrafficGate,
    collectorHasKnownTrafficFailure: collectorHasKnownTrafficFailure,
    legacyCollectorRetryReason: legacyCollectorRetryReason,
    collectorRetryReason: collectorRetryReason,
    shouldRetryCollector: shouldRetryCollector,
    evaluateDimensionsGate: evaluateDimensionsGate,
    evaluatePriceGate: evaluatePriceGate,
    currentPriceFromSamples: currentPriceFromSamples,
    isQualifiedResult: isQualifiedResult,
    summarizeResults: summarizeResults,
    buildRunnerGateLogRow: buildRunnerGateLogRow,
    buildHistorySkipGateLogRow: buildHistorySkipGateLogRow,
    buildRunnerTimingLogRow: buildRunnerTimingLogRow,
    buildHistorySkipTimingLogRow: buildHistorySkipTimingLogRow,
    attachRunnerTelemetry: attachRunnerTelemetry,
    rowsToTsv: rowsToTsv,
    normalizeTargetControl: normalizeTargetControl,
    effectiveStopBudget: effectiveStopBudget,
    browserPassesThisBatch: browserPassesThisBatch,
    stopDecision: stopDecision,
    requestStopAfterCurrentRow: requestStopAfterCurrentRow,
    mergeLatestControlState: mergeLatestControlState,
    mergeGranularRowSidecar: mergeGranularRowSidecar,
    storageInventory: storageInventory,
    reconcileStorageRecords: reconcileStorageRecords,
    removeCompletedBatchStorage: removeCompletedBatchStorage,
    persistBatchStorageWithRecovery: persistBatchStorageWithRecovery,
    panelOutputValue: panelOutputValue,
    commitCompletedRow: commitCompletedRow,
    classifySellerSpriteAccessState: classifySellerSpriteAccessState,
    applySellerSpriteAccessPause: applySellerSpriteAccessPause,
    isStorageQuotaError: isStorageQuotaError,
    gateLogColumns: GATE_LOG_COLUMNS.slice(),
    timingLogColumns: TIMING_LOG_COLUMNS.slice(),
    granularTimingColumns: GRANULAR_TIMING_COLUMNS.slice(),
    controlEventColumns: CONTROL_EVENT_COLUMNS.slice(),
    telemetryEnabled: ENABLE_TIER0_TELEMETRY,
    granularTelemetryEnabled: ENABLE_TIER0_GRANULAR_TELEMETRY,
    cumulativeTargetControlEnabled: ENABLE_P1_CUMULATIVE_TARGET_CONTROL,
    storageHardeningEnabled: ENABLE_STORAGE_HARDENING,
    deferredFullJsonEnabled: ENABLE_DEFERRED_FULL_JSON,
    tier22ConditionalRetryEnabled: ENABLE_TIER2_2_CONDITIONAL_RETRY,
    trafficTabReadyGraceEnabled: ENABLE_TRAFFIC_TAB_READY_GRACE,
    trafficTabReadyGraceVersion: TRAFFIC_TAB_READY_GRACE_VERSION,
    trafficTabReadyGraceMs: TRAFFIC_TAB_READY_GRACE_MS,
    trafficBlockFastSkipEnabled: ENABLE_TRAFFIC_BLOCK_FAST_SKIP,
    trafficBlockFastSkipVersion: TRAFFIC_BLOCK_FAST_SKIP_VERSION,
    trafficBlockReadyTimeoutMs: TRAFFIC_BLOCK_READY_TIMEOUT_MS,
    trafficBlockRemainingMs: trafficBlockRemainingMs,
    aggregateNaturalTrafficGateEnabled: ENABLE_AGGREGATE_NATURAL_TRAFFIC_GATE,
    aggregateNaturalTrafficGateVersion: AGGREGATE_NATURAL_TRAFFIC_GATE_VERSION,
    confirmedNoDataFastFailEnabled: ENABLE_CONFIRMED_NO_DATA_FAST_FAIL,
    confirmedNoDataFastFailVersion: CONFIRMED_NO_DATA_FAST_FAIL_VERSION,
    keepaChartReadyEnabled: ENABLE_KEEPA_CHART_READY_PROTOCOL,
    keepaChartReadyVersion: KEEPA_CHART_READY_VERSION,
    keepaChartReadyTimeoutMs: KEEPA_CHART_READY_TIMEOUT_MS,
    keepaChartReadyRetryAtMs: KEEPA_CHART_READY_RETRY_AT_MS,
    keepaParentClickEnabled: ENABLE_KEEPA_PARENT_CLICK_PROTOCOL,
    keepaParentClickVersion: KEEPA_PARENT_CLICK_VERSION,
    keepaTabReadyTimeoutMs: KEEPA_TAB_READY_TIMEOUT_MS,
    keepaTabTarget: keepaTabTarget,
    clickKeepaTab: clickKeepaTab,
    keepaModuleIsLoading: keepaModuleIsLoading,
    largestReadyKeepaCanvas: largestReadyKeepaCanvas,
    waitForKeepaChartReady: waitForKeepaChartReady,
    clickTrafficTabWithGrace: clickTrafficTabWithGrace,
    tier2RetryVersion: TIER2_RETRY_VERSION,
    granularTelemetryVersion: GRANULAR_TELEMETRY_VERSION,
    targetControlVersion: TARGET_CONTROL_VERSION,
    storageHardeningVersion: STORAGE_HARDENING_VERSION,
    deferredFullJsonVersion: DEFERRED_FULL_JSON_VERSION,
    maxCollectorRetries: 1,
    uniqueAsins: uniqueAsins,
    filterHistoricalQueue: filterHistoricalQueue,
    valueAfterLabel: valueAfterLabel
  });

  if (typeof window === 'undefined' || typeof document === 'undefined') return;

  function sleep(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  async function waitFor(getter, timeoutMs, intervalMs) {
    var started = Date.now();
    var lastError = null;
    while (Date.now() - started < timeoutMs) {
      try {
        var value = getter();
        if (value) return value;
      } catch (error) {
        lastError = error;
      }
      await sleep(intervalMs || 250);
    }
    if (lastError) throw lastError;
    throw new Error('Timed out after ' + timeoutMs + 'ms');
  }

  function visible(element) {
    if (!element) return false;
    var style = getComputedStyle(element);
    var rect = element.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  }

  function clickExactText(text, root) {
    root = root || document;
    var candidates = Array.from(root.querySelectorAll('span,div,p,a,button')).filter(function (element) {
      return oneLine(element.textContent) === text && visible(element);
    });
    candidates.sort(function (a, b) {
      return a.children.length - b.children.length || oneLine(a.textContent).length - oneLine(b.textContent).length;
    });
    if (!candidates.length) return false;
    candidates[0].click();
    return true;
  }

  function keepaTabTarget(root) {
    root = root || document;
    var candidates = Array.from(root.querySelectorAll('span,div,p,a,button')).filter(function (element) {
      return oneLine(element.textContent) === 'Keepa插件替代' && visible(element);
    });
    candidates.sort(function (a, b) {
      return a.children.length - b.children.length || oneLine(a.textContent).length - oneLine(b.textContent).length;
    });
    if (!candidates.length) return null;
    var label = candidates[0];
    var parentTab = label.closest ? label.closest('.list') : label.parentElement;
    return parentTab && visible(parentTab) ? parentTab : label;
  }

  function clickKeepaTab(root) {
    var target = keepaTabTarget(root);
    if (!target) return false;
    target.click();
    return true;
  }

  function keepaModuleIsLoading(module) {
    if (!module) return false;
    if (/加载中|loading|please wait/i.test(oneLine(module.textContent || module.innerText || ''))) return true;
    return Array.from(module.querySelectorAll('[class*="loading"],[class*="spinner"],[class*="progress"]')).some(visible);
  }

  async function waitForKeepaTabReady() {
    return waitFor(function () {
      return keepaTabTarget(document);
    }, KEEPA_TAB_READY_TIMEOUT_MS, 100);
  }

  function detectSellerSpriteAccessBlocker() {
    var loginOverlay = document.querySelector('.ext-sign-in-container');
    var loginMessage = document.querySelector('#quick-view-page .product-info .no-login');
    var infoContainer = document.querySelector('#quick-view-page .product-info .info-container');
    return classifySellerSpriteAccessState({
      loginVisible: visible(loginOverlay) || visible(loginMessage),
      contentText: visible(infoContainer) ? infoContainer.textContent || '' : ''
    });
  }

  function sellerSpriteAccessError(blocker) {
    var error = new Error(blocker.message);
    error.code = 'SS_SELLERSPRITE_ACCESS_BLOCKED';
    error.accessBlocker = blocker;
    return error;
  }

  function trafficBlockTimeoutError(stage) {
    var error = new Error('traffic_block_timeout_5s:' + stage);
    error.code = 'SS_TRAFFIC_BLOCK_TIMEOUT';
    error.trafficBlockStage = stage;
    return error;
  }

  function trafficBlockRemainingMs(waitStartedAtMs, nowMs) {
    if (!ENABLE_TRAFFIC_BLOCK_FAST_SKIP) return 15000;
    var elapsedMs = Math.max(0, Number(nowMs) - Number(waitStartedAtMs));
    return Math.max(1, TRAFFIC_BLOCK_READY_TIMEOUT_MS - elapsedMs);
  }

  async function clickTrafficTabWithGrace() {
    var waitStartedAtMs = Date.now();
    var pollCount = 0;
    do {
      pollCount += 1;
      var blocker = detectSellerSpriteAccessBlocker();
      if (blocker) throw sellerSpriteAccessError(blocker);
      if (clickExactText('流量洞察')) {
        var clickedAtMs = Date.now();
        return {
          found: true,
          waitStartedAtMs: waitStartedAtMs,
          clickedAtMs: clickedAtMs,
          pollCount: pollCount,
          waitMs: Math.max(0, clickedAtMs - waitStartedAtMs)
        };
      }
      if (!ENABLE_TRAFFIC_TAB_READY_GRACE) break;
      await sleep(TRAFFIC_TAB_READY_POLL_MS);
    } while (Date.now() - waitStartedAtMs < (ENABLE_TRAFFIC_BLOCK_FAST_SKIP
      ? TRAFFIC_BLOCK_READY_TIMEOUT_MS
      : TRAFFIC_TAB_READY_GRACE_MS));
    return {
      found: false,
      waitStartedAtMs: waitStartedAtMs,
      clickedAtMs: null,
      pollCount: pollCount,
      waitMs: Math.max(0, Date.now() - waitStartedAtMs)
    };
  }

  function currentAsin() {
    return normalizeAsin(location.pathname) || normalizeAsin(location.href);
  }

  function stateKey(hash) {
    return STORAGE_PREFIX + 'batch:' + hash;
  }

  function readJson(key, fallback) {
    try {
      var raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (error) {
      return fallback;
    }
  }

  function writeJson(key, value) {
    return writeJsonMeasured(key, value);
  }

  function writeJsonMeasured(key, value) {
    var serializeStartedAtMs = Date.now();
    var serialized = JSON.stringify(value);
    var serializeMs = Date.now() - serializeStartedAtMs;
    var storageStartedAtMs = Date.now();
    localStorage.setItem(key, serialized);
    var storageWriteMs = Date.now() - storageStartedAtMs;
    return {
      serializeMs: serializeMs,
      storageWriteMs: storageWriteMs,
      totalMs: serializeMs + storageWriteMs
    };
  }

  function writeJsonMeasuredToStorage(storage, key, value) {
    var serializeStartedAtMs = Date.now();
    var serialized = JSON.stringify(value);
    var serializeMs = Date.now() - serializeStartedAtMs;
    var storageStartedAtMs = Date.now();
    storage.setItem(key, serialized);
    var storageWriteMs = Date.now() - storageStartedAtMs;
    return {
      serializeMs: serializeMs,
      storageWriteMs: storageWriteMs,
      totalMs: serializeMs + storageWriteMs
    };
  }

  function storageKeys(storage) {
    var keys = [];
    for (var i = 0; i < storage.length; i += 1) {
      var key = storage.key(i);
      if (key) keys.push(key);
    }
    return keys;
  }

  function readStorageJson(storage, key, fallback) {
    try {
      var raw = storage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (error) {
      return fallback;
    }
  }

  function isStorageQuotaError(error) {
    if (!error) return false;
    var name = oneLine(error.name || '');
    var message = oneLine(error.message || error);
    return name === 'QuotaExceededError'
      || name === 'NS_ERROR_DOM_QUOTA_REACHED'
      || Number(error.code) === 22
      || Number(error.code) === 1014
      || /quota|storage.*full|exceeded.*storage/i.test(message);
  }

  function batchIndexItem(state) {
    return {
      queueHash: oneLine((state || {}).queueHash),
      batchName: oneLine((state || {}).batchName),
      createdAt: oneLine((state || {}).createdAt)
    };
  }

  function storageInventory(storage) {
    var batchPrefix = STORAGE_PREFIX + 'batch:';
    var validBatches = {};
    var invalidBatchKeys = [];
    var sidecarKeys = [];
    storageKeys(storage).forEach(function (key) {
      if (key.indexOf(batchPrefix) === 0) {
        var hash = key.slice(batchPrefix.length);
        var state = readStorageJson(storage, key, null);
        if (state
            && typeof state === 'object'
            && !Array.isArray(state)
            && state.queueHash === hash
            && Array.isArray(state.queue)
            && Array.isArray(state.results)) {
          validBatches[hash] = state;
        } else {
          invalidBatchKeys.push(key);
        }
      } else if (key.indexOf(GRANULAR_STORAGE_PREFIX) === 0) {
        sidecarKeys.push(key);
      }
    });
    var orphanSidecarKeys = sidecarKeys.filter(function (key) {
      var hash = key.slice(GRANULAR_STORAGE_PREFIX.length);
      var batch = validBatches[hash];
      var sidecar = readStorageJson(storage, key, null);
      return !batch
        || !sidecar
        || sidecar.queueHash !== hash
        || (sidecar.batchCreatedAt || '') !== (batch.createdAt || '');
    });
    var rawIndex = readStorageJson(storage, INDEX_KEY, []);
    if (!Array.isArray(rawIndex)) rawIndex = [];
    return {
      validBatches: validBatches,
      invalidBatchKeys: invalidBatchKeys,
      orphanSidecarKeys: orphanSidecarKeys,
      rawIndex: rawIndex,
      selectedHash: oneLine(storage.getItem(SELECTED_KEY) || '')
    };
  }

  function reconciledBatchIndex(inventory, preferredState) {
    var validBatches = inventory.validBatches || {};
    var preferredHash = oneLine((preferredState || {}).queueHash);
    var allowed = Object.assign({}, validBatches);
    if (preferredHash) allowed[preferredHash] = preferredState;
    var seen = {};
    var index = [];
    function add(state) {
      var item = batchIndexItem(state);
      if (!item.queueHash || seen[item.queueHash] || !allowed[item.queueHash]) return;
      seen[item.queueHash] = true;
      index.push(item);
    }
    if (preferredHash) add(preferredState);
    (inventory.rawIndex || []).forEach(function (item) {
      var hash = oneLine((item || {}).queueHash);
      if (hash && allowed[hash]) add(allowed[hash]);
    });
    Object.keys(validBatches).sort(function (left, right) {
      var leftState = validBatches[left] || {};
      var rightState = validBatches[right] || {};
      return oneLine(rightState.updatedAt || rightState.createdAt).localeCompare(oneLine(leftState.updatedAt || leftState.createdAt));
    }).forEach(function (hash) { add(validBatches[hash]); });
    return index;
  }

  function combinePersistenceMeasurements(measurements) {
    return (measurements || []).reduce(function (total, measurement) {
      measurement = measurement || {};
      total.serializeMs += Number(measurement.serializeMs || 0);
      total.storageWriteMs += Number(measurement.storageWriteMs || 0);
      total.totalMs += Number(measurement.totalMs || 0);
      return total;
    }, { serializeMs: 0, storageWriteMs: 0, totalMs: 0 });
  }

  function reconcileStorageRecords(storage, preferredState) {
    var inventory = storageInventory(storage);
    var index = reconciledBatchIndex(inventory, preferredState || null);
    inventory.orphanSidecarKeys.forEach(function (key) { storage.removeItem(key); });
    var indexWrite = { serializeMs: 0, storageWriteMs: 0, totalMs: 0 };
    if (JSON.stringify(inventory.rawIndex) !== JSON.stringify(index)) {
      indexWrite = writeJsonMeasuredToStorage(storage, INDEX_KEY, index);
    }
    var preferredHash = oneLine((preferredState || {}).queueHash);
    var selected = inventory.selectedHash;
    var validSelected = selected && (inventory.validBatches[selected] || selected === preferredHash);
    if (!validSelected) selected = preferredHash || ((index[0] || {}).queueHash || '');
    var selectedStartedAtMs = Date.now();
    if (selected !== inventory.selectedHash) {
      if (selected) storage.setItem(SELECTED_KEY, selected);
      else storage.removeItem(SELECTED_KEY);
    }
    var selectedWriteMs = Date.now() - selectedStartedAtMs;
    return {
      index: index,
      selectedHash: selected,
      removedOrphanSidecarKeys: inventory.orphanSidecarKeys.slice(),
      invalidBatchKeys: inventory.invalidBatchKeys.slice(),
      measurement: combinePersistenceMeasurements([
        indexWrite,
        { serializeMs: 0, storageWriteMs: selectedWriteMs, totalMs: selectedWriteMs }
      ])
    };
  }

  function removeCompletedBatchStorage(storage, hash) {
    var normalizedHash = oneLine(hash);
    var state = normalizedHash ? readStorageJson(storage, stateKey(normalizedHash), null) : null;
    if (!state || state.queueHash !== normalizedHash || !Array.isArray(state.queue) || !Array.isArray(state.results)) {
      throw new Error('找不到可删除的有效批次。');
    }
    if (state.status !== 'done') {
      throw new Error('只有状态为 done 的已完成批次才能删除。');
    }
    storage.removeItem(stateKey(normalizedHash));
    storage.removeItem(granularKey(normalizedHash));
    var reconciliation = reconcileStorageRecords(storage, null);
    return {
      removedQueueHash: normalizedHash,
      removedBatchName: oneLine(state.batchName),
      selectedHash: reconciliation.selectedHash,
      remainingBatchCount: reconciliation.index.length
    };
  }

  function legacyPersistBatchStorage(storage, state) {
    var stateWrite = writeJsonMeasuredToStorage(storage, stateKey(state.queueHash), state);
    var index = readStorageJson(storage, INDEX_KEY, []).filter(function (item) { return item.queueHash !== state.queueHash; });
    index.unshift(batchIndexItem(state));
    var indexWrite = writeJsonMeasuredToStorage(storage, INDEX_KEY, index);
    var selectedStartedAtMs = Date.now();
    storage.setItem(SELECTED_KEY, state.queueHash);
    var selectedWriteMs = Date.now() - selectedStartedAtMs;
    return combinePersistenceMeasurements([
      stateWrite,
      indexWrite,
      { serializeMs: 0, storageWriteMs: selectedWriteMs, totalMs: selectedWriteMs }
    ]);
  }

  function persistBatchStorageOnce(storage, state) {
    if (!ENABLE_STORAGE_HARDENING) return legacyPersistBatchStorage(storage, state);
    var reconciliation = reconcileStorageRecords(storage, state);
    var stateWrite = writeJsonMeasuredToStorage(storage, stateKey(state.queueHash), state);
    return combinePersistenceMeasurements([reconciliation.measurement, stateWrite]);
  }

  function storagePersistenceError(error, retried) {
    var wrapped = new Error('Storage persistence failed after ' + (retried ? 'quota recovery retry' : 'write') + ': ' + oneLine(error && error.message ? error.message : error));
    wrapped.name = 'StoragePersistenceError';
    wrapped.code = 'SS_STORAGE_PERSISTENCE_FAILED';
    wrapped.cause = error;
    return wrapped;
  }

  function persistBatchStorageWithRecovery(storage, state) {
    try {
      var measurement = persistBatchStorageOnce(storage, state);
      LAST_STORAGE_ERROR = '';
      return measurement;
    } catch (error) {
      if (!ENABLE_STORAGE_HARDENING || !isStorageQuotaError(error)) {
        LAST_STORAGE_ERROR = oneLine(error && error.message ? error.message : error);
        throw storagePersistenceError(error, false);
      }
      try {
        storage.removeItem(granularKey(state.queueHash));
      } catch (clearError) {
        LAST_GRANULAR_TELEMETRY_ERROR = oneLine(clearError && clearError.message ? clearError.message : clearError);
      }
      try {
        var retryMeasurement = persistBatchStorageOnce(storage, state);
        LAST_STORAGE_ERROR = '';
        LAST_GRANULAR_TELEMETRY_ERROR = '';
        return retryMeasurement;
      } catch (retryError) {
        LAST_STORAGE_ERROR = oneLine(retryError && retryError.message ? retryError.message : retryError);
        throw storagePersistenceError(retryError, true);
      }
    }
  }

  function granularKey(hash) {
    return GRANULAR_STORAGE_PREFIX + hash;
  }

  function emptyGranularSidecar(state) {
    return {
      schemaVersion: GRANULAR_TELEMETRY_SCHEMA_VERSION,
      instrumentationVersion: GRANULAR_TELEMETRY_VERSION,
      queueHash: (state || {}).queueHash || '',
      batchName: (state || {}).batchName || '',
      batchCreatedAt: (state || {}).createdAt || '',
      rowsByIndex: {},
      controlEvents: [],
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString()
    };
  }

  function loadGranularSidecar(state) {
    if (!ENABLE_TIER0_GRANULAR_TELEMETRY || !state || !state.queueHash) return null;
    var sidecar = readJson(granularKey(state.queueHash), null);
    if (!sidecar
        || sidecar.schemaVersion !== GRANULAR_TELEMETRY_SCHEMA_VERSION
        || sidecar.queueHash !== state.queueHash
        || (sidecar.batchCreatedAt || '') !== (state.createdAt || '')) {
      return emptyGranularSidecar(state);
    }
    if (!sidecar.rowsByIndex || typeof sidecar.rowsByIndex !== 'object') sidecar.rowsByIndex = {};
    if (!Array.isArray(sidecar.controlEvents)) sidecar.controlEvents = [];
    return sidecar;
  }

  function saveGranularSidecar(sidecar) {
    if (!ENABLE_TIER0_GRANULAR_TELEMETRY || !sidecar || !sidecar.queueHash) return null;
    try {
      sidecar.updatedAt = new Date().toISOString();
      var measurement = writeJsonMeasured(granularKey(sidecar.queueHash), sidecar);
      LAST_GRANULAR_TELEMETRY_ERROR = '';
      return measurement;
    } catch (error) {
      LAST_GRANULAR_TELEMETRY_ERROR = oneLine(error && error.message ? error.message : error);
      if (ENABLE_STORAGE_HARDENING && isStorageQuotaError(error)) {
        try {
          localStorage.removeItem(granularKey(sidecar.queueHash));
        } catch (clearError) {
          LAST_GRANULAR_TELEMETRY_ERROR = oneLine(clearError && clearError.message ? clearError.message : clearError);
        }
      }
      return null;
    }
  }

  function clearGranularSidecar(hash) {
    if (!ENABLE_TIER0_GRANULAR_TELEMETRY || !hash) return;
    try {
      localStorage.removeItem(granularKey(hash));
      LAST_GRANULAR_TELEMETRY_ERROR = '';
    } catch (error) {
      LAST_GRANULAR_TELEMETRY_ERROR = oneLine(error && error.message ? error.message : error);
    }
  }

  function navigationTimingSnapshot() {
    if (typeof performance === 'undefined' || typeof performance.getEntriesByType !== 'function') {
      return { navigationStartAtMs: null, amazonDomReadyAtMs: null, navigationType: '', reason: 'performance_navigation_unavailable' };
    }
    var entry = performance.getEntriesByType('navigation')[0];
    if (!entry || !Number.isFinite(Number(performance.timeOrigin))) {
      return { navigationStartAtMs: null, amazonDomReadyAtMs: null, navigationType: '', reason: 'navigation_entry_unavailable' };
    }
    var origin = Number(performance.timeOrigin);
    var domReady = Number(entry.domContentLoadedEventEnd);
    return {
      navigationStartAtMs: origin + Number(entry.startTime || 0),
      amazonDomReadyAtMs: Number.isFinite(domReady) && domReady > 0 ? origin + domReady : null,
      navigationType: entry.type || '',
      reason: Number.isFinite(domReady) && domReady > 0 ? '' : 'dom_ready_timing_unavailable'
    };
  }

  function createGranularRow(state, index) {
    var navigation = navigationTimingSnapshot();
    return {
      row: index + 1,
      asin: state.queue[index] || '',
      runnerVersion: VERSION,
      collectorVersion: '',
      navigation: {
        navigationIntentAtMs: null,
        navigationStartAtMs: navigation.navigationStartAtMs,
        amazonDomReadyAtMs: navigation.amazonDomReadyAtMs,
        runnerInjectedAtMs: RUNNER_INJECTED_AT_MS,
        autoProcessStartedAtMs: null,
        navigationType: navigation.navigationType,
        preNavigationMs: null,
        navigationDomMs: navigation.navigationStartAtMs !== null && navigation.amazonDomReadyAtMs !== null
          ? Math.max(0, navigation.amazonDomReadyAtMs - navigation.navigationStartAtMs)
          : null,
        domToRunnerInjectionMs: navigation.amazonDomReadyAtMs !== null
          ? Math.max(0, RUNNER_INJECTED_AT_MS - navigation.amazonDomReadyAtMs)
          : null,
        runnerBootDelayMs: null,
        documentReadyState: RUNNER_DOCUMENT_READY_STATE,
        reason: navigation.reason
      },
      sellerSprite: {
        collectorButtonObservedAtMs: null,
        sellerSpriteUiFirstObservedAtMs: null,
        trafficTabWaitStartedAtMs: null,
        trafficTabClickAtMs: null,
        trafficTabClickFound: null,
        trafficTabGraceWaitMs: null,
        trafficTabPollCount: 0,
        trafficTabGraceRecovered: false,
        trafficChartReadyAtMs: null,
        trafficTabToChartReadyMs: null,
        reason: ''
      },
      collectorAttempts: [],
      persistence: {
        callCount: 0,
        serializeTotalMs: 0,
        storageWriteTotalMs: 0,
        persistenceTotalMs: 0,
        persistenceMaxMs: 0,
        panelRenderCallCount: 0,
        panelRenderTotalMs: 0,
        panelRenderMaxMs: 0,
        panelJsonSerializeMs: 0
      },
      delays: {
        autoStartRequestedMs: 400,
        autoStartActualMs: null,
        interRowRequestedMs: 500,
        interRowActualMs: null,
        postResultToNextNavigationMs: null,
        pauseRecoveryMs: Number.isFinite(Number(state.pendingPauseRecoveryMs)) ? Number(state.pendingPauseRecoveryMs) : null
      },
      completion: {
        resultFinishedAtMs: null,
        flushAtMs: null,
        missingReason: ''
      }
    };
  }

  function recordGranularNavigationIntent(state, index, atMs) {
    if (!ENABLE_TIER0_GRANULAR_TELEMETRY) return;
    var sidecar = loadGranularSidecar(state);
    if (!sidecar) return;
    var key = String(index);
    var row = sidecar.rowsByIndex[key] || createGranularRow(state, index);
    row.navigation.navigationIntentAtMs = atMs;
    sidecar.rowsByIndex[key] = row;
    saveGranularSidecar(sidecar);
  }

  function beginGranularRow(state, index, processStartedAtMs) {
    if (!ENABLE_TIER0_GRANULAR_TELEMETRY) return null;
    var sidecar = loadGranularSidecar(state);
    if (!sidecar) return null;
    var key = String(index);
    var row = sidecar.rowsByIndex[key] || createGranularRow(state, index);
    var navigation = navigationTimingSnapshot();
    row.navigation.navigationStartAtMs = navigation.navigationStartAtMs;
    row.navigation.amazonDomReadyAtMs = navigation.amazonDomReadyAtMs;
    row.navigation.navigationType = navigation.navigationType;
    row.navigation.reason = navigation.reason;
    row.navigation.runnerInjectedAtMs = RUNNER_INJECTED_AT_MS;
    row.navigation.autoProcessStartedAtMs = processStartedAtMs;
    row.navigation.preNavigationMs = Number.isFinite(Number(row.navigation.navigationIntentAtMs))
      ? Math.max(0, RUNNER_INJECTED_AT_MS - Number(row.navigation.navigationIntentAtMs))
      : null;
    row.navigation.navigationDomMs = navigation.navigationStartAtMs !== null && navigation.amazonDomReadyAtMs !== null
      ? Math.max(0, navigation.amazonDomReadyAtMs - navigation.navigationStartAtMs)
      : null;
    row.navigation.domToRunnerInjectionMs = navigation.amazonDomReadyAtMs !== null
      ? Math.max(0, RUNNER_INJECTED_AT_MS - navigation.amazonDomReadyAtMs)
      : null;
    row.navigation.runnerBootDelayMs = Math.max(0, processStartedAtMs - RUNNER_INJECTED_AT_MS);
    row.delays.autoStartActualMs = row.navigation.runnerBootDelayMs;
    sidecar.rowsByIndex[key] = row;
    ACTIVE_ROW_TIMING = {
      callCount: 0,
      serializeTotalMs: 0,
      storageWriteTotalMs: 0,
      persistenceTotalMs: 0,
      persistenceMaxMs: 0,
      panelRenderCallCount: 0,
      panelRenderTotalMs: 0,
      panelRenderMaxMs: 0,
      panelJsonSerializeMs: 0
    };
    ACTIVE_GRANULAR_CONTEXT = { sidecar: sidecar, row: row, index: index };
    saveGranularSidecar(sidecar);
    return row;
  }

  function recordActivePersistence(measurement, panelRenderMs) {
    if (!ACTIVE_ROW_TIMING) return;
    ACTIVE_ROW_TIMING.callCount += 1;
    ACTIVE_ROW_TIMING.serializeTotalMs += measurement.serializeMs;
    ACTIVE_ROW_TIMING.storageWriteTotalMs += measurement.storageWriteMs;
    ACTIVE_ROW_TIMING.persistenceTotalMs += measurement.totalMs;
    ACTIVE_ROW_TIMING.persistenceMaxMs = Math.max(ACTIVE_ROW_TIMING.persistenceMaxMs, measurement.totalMs);
    ACTIVE_ROW_TIMING.panelRenderCallCount += 1;
    ACTIVE_ROW_TIMING.panelRenderTotalMs += panelRenderMs;
    ACTIVE_ROW_TIMING.panelRenderMaxMs = Math.max(ACTIVE_ROW_TIMING.panelRenderMaxMs, panelRenderMs);
  }

  function recordPanelJsonSerialize(ms) {
    if (ACTIVE_ROW_TIMING) ACTIVE_ROW_TIMING.panelJsonSerializeMs += ms;
  }

  function finalizeActiveGranular(reason, nextNavigationAtMs) {
    if (!ACTIVE_GRANULAR_CONTEXT) return;
    var context = ACTIVE_GRANULAR_CONTEXT;
    if (ACTIVE_ROW_TIMING) context.row.persistence = Object.assign({}, context.row.persistence, ACTIVE_ROW_TIMING);
    if (Number.isFinite(Number(nextNavigationAtMs)) && Number.isFinite(Number(context.row.completion.resultFinishedAtMs))) {
      var interval = Math.max(0, Number(nextNavigationAtMs) - Number(context.row.completion.resultFinishedAtMs));
      context.row.delays.interRowActualMs = interval;
      context.row.delays.postResultToNextNavigationMs = interval;
    }
    context.row.completion.flushAtMs = Date.now();
    context.row.completion.missingReason = reason || '';
    var latestSidecar = loadGranularSidecar({
      queueHash: context.sidecar.queueHash,
      batchName: context.sidecar.batchName,
      createdAt: context.sidecar.batchCreatedAt
    });
    saveGranularSidecar(mergeGranularRowSidecar(latestSidecar, context.sidecar, context.index, context.row));
    ACTIVE_ROW_TIMING = null;
    ACTIVE_GRANULAR_CONTEXT = null;
  }

  function recordControlEvent(state, event, details) {
    if (!ENABLE_TIER0_GRANULAR_TELEMETRY || !state) return;
    var sidecar = loadGranularSidecar(state);
    if (!sidecar) return;
    details = details || {};
    sidecar.controlEvents.push({
      atMs: Date.now(),
      event: event,
      row: Number.isInteger(Number(details.row)) ? Number(details.row) : Number(state.currentIndex || 0) + 1,
      asin: details.asin || state.queue[state.currentIndex] || '',
      stepBefore: details.stepBefore || state.currentStep || '',
      statusBefore: details.statusBefore || state.status || '',
      pauseId: details.pauseId || '',
      pauseDurationMs: Number.isFinite(Number(details.pauseDurationMs)) ? Number(details.pauseDurationMs) : null,
      recoveryKind: details.recoveryKind || '',
      recoveryEvidence: details.recoveryEvidence || '',
      reason: details.reason || ''
    });
    saveGranularSidecar(sidecar);
  }

  function granularTimingRows(sidecar) {
    if (!sidecar || !sidecar.rowsByIndex) return [];
    return Object.keys(sidecar.rowsByIndex).sort(function (a, b) { return Number(a) - Number(b); }).map(function (key) {
      var row = sidecar.rowsByIndex[key];
      var navigation = row.navigation || {};
      var sellerSprite = row.sellerSprite || {};
      var persistence = row.persistence || {};
      var delays = row.delays || {};
      var completion = row.completion || {};
      return {
        row: row.row,
        asin: row.asin,
        batchName: sidecar.batchName,
        queueHash: sidecar.queueHash,
        runnerVersion: row.runnerVersion || VERSION,
        collectorVersion: row.collectorVersion || '',
        navigationIntentAtMs: navigation.navigationIntentAtMs,
        navigationStartAtMs: navigation.navigationStartAtMs,
        amazonDomReadyAtMs: navigation.amazonDomReadyAtMs,
        runnerInjectedAtMs: navigation.runnerInjectedAtMs,
        autoProcessStartedAtMs: navigation.autoProcessStartedAtMs,
        navigationType: navigation.navigationType || '',
        preNavigationMs: navigation.preNavigationMs,
        navigationDomMs: navigation.navigationDomMs,
        domToRunnerInjectionMs: navigation.domToRunnerInjectionMs,
        runnerBootDelayMs: navigation.runnerBootDelayMs,
        documentReadyState: navigation.documentReadyState || '',
        trafficTabWaitStartedAtMs: sellerSprite.trafficTabWaitStartedAtMs,
        trafficTabClickAtMs: sellerSprite.trafficTabClickAtMs,
        trafficTabClickFound: sellerSprite.trafficTabClickFound,
        trafficTabGraceWaitMs: sellerSprite.trafficTabGraceWaitMs,
        trafficTabPollCount: sellerSprite.trafficTabPollCount,
        trafficTabGraceRecovered: sellerSprite.trafficTabGraceRecovered,
        trafficChartReadyAtMs: sellerSprite.trafficChartReadyAtMs,
        trafficTabToChartReadyMs: sellerSprite.trafficTabToChartReadyMs,
        collectorAttempts: row.collectorAttempts || [],
        persistenceCallCount: persistence.callCount,
        serializeTotalMs: persistence.serializeTotalMs,
        storageWriteTotalMs: persistence.storageWriteTotalMs,
        persistenceTotalMs: persistence.persistenceTotalMs,
        persistenceMaxMs: persistence.persistenceMaxMs,
        panelRenderCallCount: persistence.panelRenderCallCount,
        panelRenderTotalMs: persistence.panelRenderTotalMs,
        panelRenderMaxMs: persistence.panelRenderMaxMs,
        panelJsonSerializeMs: persistence.panelJsonSerializeMs,
        autoStartRequestedMs: delays.autoStartRequestedMs,
        autoStartActualMs: delays.autoStartActualMs,
        interRowRequestedMs: delays.interRowRequestedMs,
        interRowActualMs: delays.interRowActualMs,
        postResultToNextNavigationMs: delays.postResultToNextNavigationMs,
        pauseRecoveryMs: delays.pauseRecoveryMs,
        resultFinishedAtMs: completion.resultFinishedAtMs,
        flushAtMs: completion.flushAtMs,
        missingReason: completion.missingReason || navigation.reason || sellerSprite.reason || ''
      };
    });
  }

  function controlEventRows(sidecar) {
    return sidecar && Array.isArray(sidecar.controlEvents) ? sidecar.controlEvents.slice() : [];
  }

  function getStrictHistory() {
    var history = readJson(STRICT_HISTORY_KEY, null);
    var changed = false;
    if (!history || typeof history !== 'object' || Array.isArray(history)) {
      history = { schemaVersion: 'strictQualifiedHistory/v1', asins: {} };
      changed = true;
    }
    if (!history.asins || typeof history.asins !== 'object' || Array.isArray(history.asins)) {
      history.asins = {};
      changed = true;
    }
    BOOTSTRAP_STRICT_QUALIFIED_ASINS.forEach(function (asin) {
      if (history.asins[asin]) return;
      history.asins[asin] = {
        qualifiedAt: 'preloaded',
        source: 'preloaded_deliveries'
      };
      changed = true;
    });
    if (history.schemaVersion !== 'strictQualifiedHistory/v1') {
      history.schemaVersion = 'strictQualifiedHistory/v1';
      changed = true;
    }
    if (changed) {
      history.updatedAt = new Date().toISOString();
      writeJson(STRICT_HISTORY_KEY, history);
    }
    return history;
  }

  function strictHistoryCount(history) {
    return Object.keys((history || {}).asins || {}).length;
  }

  function recordStrictQualified(asin, metadata) {
    metadata = metadata || {};
    var normalized = normalizeAsin(asin);
    var history = getStrictHistory();
    if (!normalized) return history;
    var previous = history.asins[normalized] || {};
    history.asins[normalized] = {
      qualifiedAt: previous.qualifiedAt || metadata.qualifiedAt || new Date().toISOString(),
      lastQualifiedAt: metadata.qualifiedAt || new Date().toISOString(),
      source: previous.source || 'integrated_runner',
      batchName: metadata.batchName || previous.batchName || '',
      queueHash: metadata.queueHash || previous.queueHash || ''
    };
    history.updatedAt = new Date().toISOString();
    writeJson(STRICT_HISTORY_KEY, history);
    return history;
  }

  function getBatchIndex() {
    return readJson(INDEX_KEY, []);
  }

  function saveBatch(state) {
    var summary = summarizeResults(state.results);
    var targetControl = normalizeTargetControl(state);
    if (targetControl.valid) {
      state.targetQualified = targetControl.requestedFinalTargetAtStart;
      state.requestedFinalTargetAtStart = targetControl.requestedFinalTargetAtStart;
      state.remainingTargetAtStart = targetControl.remainingTargetAtStart;
      state.targetControlVersion = targetControl.version;
    }
    state.qualifiedCount = summary.qualified;
    state.browserPassesThisBatch = summary.qualified;
    state.remainingTargetAfterBrowser = targetControl.valid && targetControl.remainingTargetAtStart !== null
      ? Math.max(0, targetControl.remainingTargetAtStart - summary.qualified)
      : null;
    state.rejectedCount = summary.rejected;
    state.historySkippedCount = (state.historySkippedAsins || []).length;
    state.updatedAt = new Date().toISOString();
    var persistenceMeasurement;
    try {
      persistenceMeasurement = persistBatchStorageWithRecovery(localStorage, state);
    } catch (error) {
      state.status = 'paused';
      state.currentStep = 'storage_blocked';
      state.message = '本地存储写入失败；已停止自动跳转。请释放站点存储后刷新，当前行会按最后成功状态重新采集。';
      setPanelMessage(state.message + ' ' + oneLine(error && error.message ? error.message : error));
      throw error;
    }
    var renderStartedAtMs = Date.now();
    renderPanel();
    recordActivePersistence(persistenceMeasurement, Date.now() - renderStartedAtMs);
  }

  function loadBatch(hash) {
    return hash ? readJson(stateKey(hash), null) : null;
  }

  function fnv1a(value) {
    var hash = 0x811c9dc5;
    for (var i = 0; i < value.length; i += 1) {
      hash ^= value.charCodeAt(i);
      hash = Math.imul(hash, 0x01000193);
    }
    return ('00000000' + (hash >>> 0).toString(16)).slice(-8);
  }

  function selectedHash() {
    return localStorage.getItem(SELECTED_KEY) || '';
  }

  function gateLogRows(state) {
    var rows = (state.results || []).filter(Boolean).map(function (result) {
      return buildRunnerGateLogRow(result, state);
    });
    (state.historySkippedAsins || []).forEach(function (asin) {
      rows.push(buildHistorySkipGateLogRow(asin, state));
    });
    return rows;
  }

  function timingLogRows(state) {
    var rows = (state.results || []).filter(Boolean).map(function (result) {
      var measurements = result.telemetry && result.telemetry.timing ? result.telemetry.timing : {};
      return buildRunnerTimingLogRow(result, measurements, state);
    });
    (state.historySkippedAsins || []).forEach(function (asin) {
      rows.push(buildHistorySkipTimingLogRow(asin, state));
    });
    return rows;
  }

  function exportBatch(state) {
    var exported = {
      schemaVersion: SCHEMA_VERSION,
      batchName: state.batchName,
      operator: state.operator,
      generatedAt: state.generatedAt,
      queueHash: state.queueHash,
      queue: state.queue,
      status: state.status,
      currentIndex: state.currentIndex,
      targetQualified: state.targetQualified,
      requestedFinalTargetAtStart: state.requestedFinalTargetAtStart || state.targetQualified,
      remainingTargetAtStart: state.remainingTargetAtStart == null ? null : state.remainingTargetAtStart,
      remainingTargetAfterBrowser: state.remainingTargetAfterBrowser == null ? null : state.remainingTargetAfterBrowser,
      browserPassesThisBatch: state.browserPassesThisBatch || 0,
      targetControlVersion: state.targetControlVersion || '',
      stopAfterCurrentRowRequested: Boolean(state.stopAfterCurrentRowRequested),
      stopAction: state.stopAction || '',
      qualifiedCount: state.qualifiedCount,
      rejectedCount: state.rejectedCount,
      historySkippedAsins: state.historySkippedAsins || [],
      historySkippedCount: (state.historySkippedAsins || []).length,
      historyRegistryCount: state.historyRegistryCount || 0,
      stoppedReason: state.stoppedReason || '',
      results: state.results.filter(Boolean),
      createdAt: state.createdAt,
      updatedAt: state.updatedAt
    };
    if (ENABLE_TIER0_TELEMETRY) {
      exported.telemetry = {
        schemaVersion: TELEMETRY_SCHEMA_VERSION,
        gateRows: gateLogRows(state),
        timingRows: timingLogRows(state)
      };
    }
    return exported;
  }

  function enrichmentOnly(state) {
    return state.results.filter(Boolean).map(function (result) {
      return {
        asin: result.targetAsin,
        status: result.enrichmentStatus,
        dimensions: result.dimensions || '',
        itemDimensions: result.itemDimensions || '',
        itemWeight: result.itemWeight || '',
        packageDimensions: result.packageDimensions || '',
        packageWeight: result.packageWeight || '',
        dimensionsSource: result.dimensionsSource || '',
        priceTrend: result.priceTrend || '',
        priceTrendClass: result.priceTrendClass || '',
        priceTrendWindow: result.priceTrendWindow || '',
        priceTrendSource: result.priceTrendSource || '',
        priceSamples: result.priceSamples || [],
        collectedAt: result.enrichmentCollectedAt || result.collectedAt
      };
    });
  }

  async function copyText(text) {
    if (typeof GM_setClipboard === 'function') {
      GM_setClipboard(text, 'text');
      return;
    }
    await navigator.clipboard.writeText(text);
  }

  function setPanelMessage(message) {
    var element = document.querySelector('#ss-v3-message');
    if (element) element.textContent = message;
  }

  function uiStatus(value) {
    if (!ENABLE_ZH_UI) return value || '';
    return ({ idle: '待开始', running: '运行中', paused: '已暂停', done: '已完成' })[value] || value || '';
  }

  function uiStep(value) {
    if (!ENABLE_ZH_UI) return value || '';
    return ({
      idle: '待开始', navigate: '打开商品页', traffic: '采集流量', dimensions: '读取尺寸',
      price: '读取价格趋势', saved: '已保存当前行', paused: '已暂停', external_blocked: '卖家精灵访问受阻', done: '已完成'
    })[value] || value || '';
  }

  function normalizeBridgeOrigin(value) {
    var url;
    try {
      url = new URL(oneLine(value));
    } catch (error) {
      throw new Error('Excel 服务地址格式不正确。');
    }
    if (url.protocol !== 'http:' || (url.hostname !== '127.0.0.1' && url.hostname !== 'localhost')) {
      throw new Error('Excel 服务只允许连接本机 127.0.0.1 或 localhost。');
    }
    if (url.username || url.password) throw new Error('Excel 服务地址不能包含用户名或密码。');
    return 'http://127.0.0.1' + (url.port ? ':' + url.port : '');
  }

  function validatedDownloadUrl(value, bridgeOrigin) {
    var url;
    try {
      url = new URL(oneLine(value));
    } catch (error) {
      throw new Error('Excel 下载地址无效。');
    }
    if (url.origin !== bridgeOrigin || url.pathname !== '/api/v1/download') {
      throw new Error('Excel 下载地址不是当前本机服务提供的受验收文件。');
    }
    if (url.searchParams.get('kind') !== 'final' || !url.searchParams.get('attempt') || !url.searchParams.get('token')) {
      throw new Error('Excel 下载地址缺少验收标识。');
    }
    return url.href;
  }

  function postExcelBridge(origin, token, batch) {
    if (typeof GM_xmlhttpRequest !== 'function') {
      return Promise.reject(new Error('脚本管理器未授予 GM_xmlhttpRequest 权限。'));
    }
    return new Promise(function (resolve, reject) {
      GM_xmlhttpRequest({
        method: 'POST',
        url: origin + '/api/v1/export',
        headers: {
          'Content-Type': 'application/json',
          'X-Selection-Bridge-Token': token
        },
        data: JSON.stringify({ schemaVersion: EXCEL_BRIDGE_REQUEST_SCHEMA, batch: batch }),
        timeout: 900000,
        onload: function (response) {
          var payload;
          try {
            payload = JSON.parse(response.responseText || '{}');
          } catch (error) {
            reject(new Error('Excel 服务返回了无法解析的响应。'));
            return;
          }
          if (response.status < 200 || response.status >= 300) {
            var stage = oneLine(payload.stage || 'unknown');
            reject(new Error(oneLine(payload.message || ('Excel 服务请求失败，HTTP ' + response.status)) + ' [' + stage + ']'));
            return;
          }
          if (payload.schemaVersion !== EXCEL_BRIDGE_RESPONSE_SCHEMA || payload.accepted !== true || payload.machineAcceptancePassed !== true) {
            reject(new Error('Excel 服务未返回有效的机器验收通过结果。'));
            return;
          }
          if (payload.visualAcceptanceRequired !== true || payload.productionHistoryUpdated !== false) {
            reject(new Error('Excel 服务没有保留人工预览或正式历史保护约束。'));
            return;
          }
          resolve(payload);
        },
        ontimeout: function () { reject(new Error('Excel 服务执行超时。')); },
        onerror: function () { reject(new Error('无法连接本机 Excel 服务，请先启动桥接程序。')); }
      });
    });
  }

  function downloadAcceptedWorkbook(url, name) {
    if (typeof GM_download !== 'function') return Promise.reject(new Error('脚本管理器未授予 GM_download 权限。'));
    return new Promise(function (resolve, reject) {
      GM_download({
        url: url,
        name: oneLine(name) || '亚马逊严格选品_待人工预览.xlsx',
        saveAs: true,
        onload: resolve,
        onerror: function () { reject(new Error('Excel 下载失败。')); },
        ontimeout: function () { reject(new Error('Excel 下载超时。')); }
      });
    });
  }

  async function exportAcceptedExcel() {
    var button = document.querySelector('#ss-v3-excel');
    var state = loadBatch(selectedHash());
    if (!state || state.status !== 'done') {
      setPanelMessage('批次完成后才能生成 Excel。');
      return;
    }
    var urlInput = document.querySelector('#ss-v3-excel-url');
    var tokenInput = document.querySelector('#ss-v3-excel-token');
    var token = oneLine(tokenInput && tokenInput.value);
    if (!token) {
      setPanelMessage('请填写本机 Excel 服务令牌。');
      return;
    }
    try {
      if (button) button.disabled = true;
      var origin = normalizeBridgeOrigin(urlInput && urlInput.value);
      localStorage.setItem(EXCEL_BRIDGE_URL_KEY, origin);
      localStorage.setItem(EXCEL_BRIDGE_TOKEN_KEY, token);
      setPanelMessage('正在离线回放、生成工作簿并执行机器验收，请稍候...');
      var response = await postExcelBridge(origin, token, exportBatch(state));
      var downloadUrl = validatedDownloadUrl(response.finalWorkbookUrl, origin);
      await downloadAcceptedWorkbook(downloadUrl, response.finalWorkbookName);
      setPanelMessage('机器验收已通过并下载 Excel；仍须人工预览，正式合格历史尚未更新。');
    } catch (error) {
      setPanelMessage('Excel 未生成：' + oneLine(error && error.message ? error.message : error));
    } finally {
      if (button) button.disabled = false;
      renderPanel();
    }
  }

  function createPanel() {
    if (document.querySelector('#ss-v3-panel')) return;
    var style = document.createElement('style');
    style.textContent = [
      '#ss-v3-panel{position:fixed;right:12px;top:12px;width:430px;max-height:94vh;overflow:auto;z-index:2147483647;background:#fff;border:2px solid #0f766e;border-radius:6px;box-shadow:0 8px 24px rgba(0,0,0,.3);padding:10px;font:12px/1.4 Arial,sans-serif;color:#111}',
      '#ss-v3-panel *{box-sizing:border-box}',
      '#ss-v3-panel h3{margin:0 0 8px;color:#0f766e;font-size:15px}',
      '#ss-v3-panel label{display:block;font-weight:700;margin-top:6px}',
      '#ss-v3-panel input,#ss-v3-panel textarea,#ss-v3-panel select{width:100%;border:1px solid #aaa;border-radius:3px;padding:5px;font:12px Consolas,monospace}',
      '#ss-v3-panel textarea{height:92px;resize:vertical}',
      '#ss-v3-panel button{margin:6px 5px 0 0;padding:5px 8px;border:1px solid #0f766e;border-radius:3px;background:#ecfdf5;cursor:pointer}',
      '#ss-v3-panel button.ss-v3-primary{background:#0f766e;color:#fff}',
      '#ss-v3-panel button:disabled{cursor:not-allowed;opacity:.5}',
      '#ss-v3-panel pre{white-space:pre-wrap;background:#f3f4f6;border:1px solid #ddd;padding:6px;max-height:190px;overflow:auto}',
      '#ss-v3-panel .ss-v3-divider{border:0;border-top:1px solid #d1d5db;margin:10px 0 4px}',
      '#ss-v3-message{color:#b45309;font-weight:700;margin-left:4px}',
      '#ss-v3-panel.ss-v3-collapsed .ss-v3-body{display:none}'
    ].join('\n');
    document.head.appendChild(style);

    var panel = document.createElement('div');
    panel.id = 'ss-v3-panel';
    panel.className = 'notranslate';
    var telemetryButtons = ENABLE_TIER0_TELEMETRY
      ? '<button id="ss-v3-copy-gate-tsv">复制门槛日志 TSV</button>' +
        '<button id="ss-v3-copy-timing-tsv">复制耗时日志 TSV</button>'
      : '';
    var granularButtons = ENABLE_TIER0_GRANULAR_TELEMETRY
      ? '<button id="ss-v3-copy-granular-json">复制细粒度 JSON</button>' +
        '<button id="ss-v3-copy-granular-tsv">复制细粒度 TSV</button>' +
        '<button id="ss-v3-copy-control-tsv">复制控制日志 TSV</button>'
      : '';
    var targetControlFields = ENABLE_P1_CUMULATIVE_TARGET_CONTROL
      ? '<label>本批浏览器剩余目标数（离线回放快照，可选）</label><input id="ss-v3-remaining" type="number" min="0" placeholder="留空则使用完整批次目标">'
      : '';
    var stopRowButton = ENABLE_P1_CUMULATIVE_TARGET_CONTROL
      ? '<button id="ss-v3-stop-row">当前行完成后停止</button>'
      : '';
    var excelControls = ENABLE_ACCEPTED_EXCEL_BRIDGE
      ? '<hr class="ss-v3-divider">' +
        '<label>本机 Excel 服务地址</label><input id="ss-v3-excel-url" value="' + DEFAULT_EXCEL_BRIDGE_URL + '">' +
        '<label>Excel 服务令牌</label><input id="ss-v3-excel-token" type="password" autocomplete="off" placeholder="启动桥接程序后粘贴令牌">' +
        '<button class="ss-v3-primary" id="ss-v3-excel" disabled>一键生成待验收 Excel</button>'
      : '';
    panel.innerHTML = [
      '<h3>卖家精灵一体化选品 ' + VERSION + ' <button id="ss-v3-toggle">收起</button></h3>',
      '<div class="ss-v3-body">',
      '<label>本地批次</label><select id="ss-v3-picker"></select>',
       '<label>批次名称</label><input id="ss-v3-name" value="strict20-integrated-' + new Date().toISOString().slice(0, 10) + '">',
       '<label>操作人</label><input id="ss-v3-operator" value="liyuanze">',
       '<label>最终合格目标数</label><input id="ss-v3-target" type="number" min="1" value="20">',
       targetControlFields,
       '<label>候选 ASIN 队列</label><textarea id="ss-v3-queue" placeholder="每行一个 ASIN"></textarea>',
      '<button id="ss-v3-generate">生成批次</button><span id="ss-v3-message"></span><br>',
      '<button class="ss-v3-primary" id="ss-v3-start">开始</button>',
       '<button id="ss-v3-pause">暂停</button>',
       '<button id="ss-v3-resume">继续</button>',
       stopRowButton,
      '<button id="ss-v3-copy">复制合并 JSON</button>',
      '<button id="ss-v3-copy-enrichment">复制补充数据 JSON</button>',
       telemetryButtons,
       granularButtons,
       excelControls,
      '<button id="ss-v3-clear" title="不清除有效批次，只删除确认的孤立存储">清理孤立存储</button>',
      '<button id="ss-v3-delete-done" title="仅在导出证据后删除当前已完成批次">删除已完成批次</button>',
      '<pre id="ss-v3-status">尚未选择批次。</pre>',
      '<textarea id="ss-v3-output" readonly></textarea>',
      '</div>'
    ].join('');
    document.body.appendChild(panel);

    panel.querySelector('#ss-v3-toggle').addEventListener('click', function () {
      panel.classList.toggle('ss-v3-collapsed');
      this.textContent = panel.classList.contains('ss-v3-collapsed') ? '展开' : '收起';
    });
    panel.querySelector('#ss-v3-picker').addEventListener('change', function () {
      localStorage.setItem(SELECTED_KEY, this.value);
      renderPanel();
    });
    panel.querySelector('#ss-v3-generate').addEventListener('click', generateBatchFromPanel);
    panel.querySelector('#ss-v3-start').addEventListener('click', startSelectedBatch);
    panel.querySelector('#ss-v3-pause').addEventListener('click', pauseSelectedBatch);
    panel.querySelector('#ss-v3-resume').addEventListener('click', resumeSelectedBatch);
    if (ENABLE_P1_CUMULATIVE_TARGET_CONTROL) {
      panel.querySelector('#ss-v3-stop-row').addEventListener('click', stopAfterCurrentRowSelectedBatch);
    }
    panel.querySelector('#ss-v3-copy').addEventListener('click', function () { copySelected(false); });
    panel.querySelector('#ss-v3-copy-enrichment').addEventListener('click', function () { copySelected(true); });
    if (ENABLE_TIER0_TELEMETRY) {
      panel.querySelector('#ss-v3-copy-gate-tsv').addEventListener('click', function () { copyTelemetry('gate'); });
      panel.querySelector('#ss-v3-copy-timing-tsv').addEventListener('click', function () { copyTelemetry('timing'); });
    }
    if (ENABLE_TIER0_GRANULAR_TELEMETRY) {
      panel.querySelector('#ss-v3-copy-granular-json').addEventListener('click', function () { copyGranularTelemetry('json'); });
      panel.querySelector('#ss-v3-copy-granular-tsv').addEventListener('click', function () { copyGranularTelemetry('timing'); });
      panel.querySelector('#ss-v3-copy-control-tsv').addEventListener('click', function () { copyGranularTelemetry('control'); });
    }
    if (ENABLE_ACCEPTED_EXCEL_BRIDGE) {
      panel.querySelector('#ss-v3-excel-url').value = localStorage.getItem(EXCEL_BRIDGE_URL_KEY) || DEFAULT_EXCEL_BRIDGE_URL;
      panel.querySelector('#ss-v3-excel-token').value = localStorage.getItem(EXCEL_BRIDGE_TOKEN_KEY) || '';
      panel.querySelector('#ss-v3-excel').addEventListener('click', exportAcceptedExcel);
    }
    panel.querySelector('#ss-v3-clear').addEventListener('click', clearSelectedBatch);
    panel.querySelector('#ss-v3-delete-done').addEventListener('click', deleteSelectedCompletedBatch);
    renderPanel();
  }

  function renderPanel() {
    var panel = document.querySelector('#ss-v3-panel');
    if (!panel) return;
    var history = getStrictHistory();
    var historyCount = strictHistoryCount(history);
    var picker = panel.querySelector('#ss-v3-picker');
    var selected = selectedHash();
    var index = getBatchIndex();
    picker.innerHTML = '<option value="">尚未生成批次</option>' + index.map(function (item) {
      return '<option value="' + item.queueHash + '">' + item.batchName + ' (' + item.queueHash + ')</option>';
    }).join('');
    picker.value = selected;
    var state = loadBatch(selected);
    if (!state) {
      panel.querySelector('#ss-v3-status').textContent = '尚未选择批次。\n本地严格合格历史：' + historyCount + '（自动跳过）。';
      panel.querySelector('#ss-v3-output').value = '';
      if (ENABLE_ACCEPTED_EXCEL_BRIDGE) panel.querySelector('#ss-v3-excel').disabled = true;
      panel.querySelector('#ss-v3-delete-done').disabled = true;
      return;
    }
    panel.querySelector('#ss-v3-name').value = state.batchName;
    panel.querySelector('#ss-v3-operator').value = state.operator;
    panel.querySelector('#ss-v3-target').value = state.requestedFinalTargetAtStart || state.targetQualified || 20;
    var remainingInput = panel.querySelector('#ss-v3-remaining');
    if (remainingInput) remainingInput.value = state.remainingTargetAtStart == null ? '' : state.remainingTargetAtStart;
    panel.querySelector('#ss-v3-queue').value = state.queue.join('\n');
    var summary = summarizeResults(state.results);
    var targetControl = normalizeTargetControl(state);
    panel.querySelector('#ss-v3-status').textContent = [
      '批次：' + state.batchName,
      '队列哈希：' + state.queueHash,
      '状态：' + uiStatus(state.status),
      '进度：' + summary.completed + '/' + state.queue.length,
      '最终目标：' + (state.targetQualified || 20),
      '目标控制：' + targetControl.mode + ' / 本批停止数 ' + (targetControl.valid ? targetControl.effectiveStopBudget : 'INVALID'),
      '本批开始时剩余目标：' + (state.remainingTargetAtStart == null ? '未设置' : state.remainingTargetAtStart),
      '本批浏览器通过：' + summary.qualified + '/' + (targetControl.valid ? targetControl.effectiveStopBudget : 'INVALID') + '（最终以离线回放为准）',
      '已拒绝：' + summary.rejected,
      '历史自动跳过：' + (state.historySkippedAsins || []).length,
      '本地严格合格历史：' + historyCount,
      '当前行：' + (state.currentIndex + 1),
      '当前 ASIN：' + (state.queue[state.currentIndex] || ''),
      '步骤：' + uiStep(state.currentStep || 'idle'),
      '当前行后停止：' + (state.stopAfterCurrentRowRequested ? '已请求' : '未请求'),
      '消息：' + (state.message || '')
    ].join('\n');
    var panelJsonStartedAtMs = Date.now();
    panel.querySelector('#ss-v3-output').value = panelOutputValue(state);
    recordPanelJsonSerialize(ENABLE_DEFERRED_FULL_JSON ? 0 : Date.now() - panelJsonStartedAtMs);
    if (ENABLE_ACCEPTED_EXCEL_BRIDGE) panel.querySelector('#ss-v3-excel').disabled = state.status !== 'done';
    panel.querySelector('#ss-v3-delete-done').disabled = state.status !== 'done';
  }

  function generateBatchFromPanel() {
    var inputQueue = uniqueAsins(document.querySelector('#ss-v3-queue').value);
    if (!inputQueue.length) {
      setPanelMessage('QUEUE 中没有有效 ASIN。');
      return;
    }
    var history = getStrictHistory();
    var filtered = filterHistoricalQueue(inputQueue, history.asins);
    var queue = filtered.queue;
    if (!queue.length) {
      setPanelMessage('QUEUE 中 ' + inputQueue.length + ' 个 ASIN 均已严格合格，已全部直接跳过。');
      return;
    }
    var batchName = oneLine(document.querySelector('#ss-v3-name').value) || ('integrated-' + Date.now());
    var operator = oneLine(document.querySelector('#ss-v3-operator').value) || 'operator';
    var requestedFinalTargetAtStart = Number(document.querySelector('#ss-v3-target').value);
    if (!Number.isInteger(requestedFinalTargetAtStart) || requestedFinalTargetAtStart < 1) requestedFinalTargetAtStart = 20;
    var remainingInput = document.querySelector('#ss-v3-remaining');
    var remainingText = remainingInput ? String(remainingInput.value || '').trim() : '';
    var remainingTargetAtStart = remainingText === '' ? null : nonNegativeIntegerOrNull(remainingText);
    if (ENABLE_P1_CUMULATIVE_TARGET_CONTROL && remainingText !== '' && remainingTargetAtStart === null) {
      setPanelMessage('本批浏览器剩余目标数必须是非负整数。');
      return;
    }
    if (ENABLE_P1_CUMULATIVE_TARGET_CONTROL && remainingTargetAtStart !== null && remainingTargetAtStart > requestedFinalTargetAtStart) {
      setPanelMessage('本批浏览器剩余目标数不能大于最终合格目标数。');
      return;
    }
    if (ENABLE_P1_CUMULATIVE_TARGET_CONTROL && remainingTargetAtStart === 0) {
      setPanelMessage('离线回放已达到最终目标，无需生成新的浏览器批次。');
      return;
    }
    var targetQualified = requestedFinalTargetAtStart;
    var hash = fnv1a(batchName + '\n' + operator + '\n' + requestedFinalTargetAtStart + '\n' + (remainingTargetAtStart == null ? '' : remainingTargetAtStart) + '\n' + queue.join('\n'));
    var now = new Date().toISOString();
    var state = {
      schemaVersion: SCHEMA_VERSION,
      batchName: batchName,
      operator: operator,
      generatedAt: now,
      queueHash: hash,
      queue: queue,
      status: 'idle',
      currentIndex: 0,
      targetQualified: targetQualified,
      requestedFinalTargetAtStart: requestedFinalTargetAtStart,
      remainingTargetAtStart: remainingTargetAtStart,
      remainingTargetAfterBrowser: remainingTargetAtStart,
      browserPassesThisBatch: 0,
      targetControlVersion: remainingTargetAtStart === null ? '' : TARGET_CONTROL_VERSION,
      stopAfterCurrentRowRequested: false,
      stopAction: '',
      qualifiedCount: 0,
      rejectedCount: 0,
      historySkippedAsins: filtered.skipped,
      historyRegistryCount: strictHistoryCount(history),
      stoppedReason: '',
      currentStep: 'idle',
      message: '',
      results: new Array(queue.length).fill(null),
      createdAt: now,
      updatedAt: now
    };
    clearGranularSidecar(hash);
    saveBatch(state);
    setPanelMessage('已生成 ' + queue.length + ' 个 ASIN；历史严格合格直接跳过 ' + filtered.skipped.length + ' 个。');
  }

  function firstMissingIndex(state) {
    for (var i = 0; i < state.queue.length; i += 1) if (!state.results[i]) return i;
    return state.queue.length;
  }

  function finishBatch(state, reason, message) {
    state.status = 'done';
    state.currentStep = 'done';
    state.stoppedReason = reason;
    state.stopReason = reason;
    state.stopAction = state.stopAction || reason;
    state.message = message;
    saveBatch(state);
  }

  function navigateToRow(state, index) {
    var latestState = loadBatch(state.queueHash);
    if (latestState) state = latestState;
    var decision = stopDecision(state);
    if (decision.stop) {
      var targetLabel = decision.control && decision.control.effectiveStopBudget != null
        ? decision.control.effectiveStopBudget
        : state.targetQualified || 20;
      finishBatch(
        state,
        decision.reason,
        decision.reason === 'operator_stop_after_current_row'
          ? '当前行已保存，已按操作人请求停止。'
          : '目标控制已停止批次：本批浏览器通过 ' + decision.passes + '/' + targetLabel + '。'
      );
      finalizeActiveGranular(decision.reason, null);
      return;
    }
    if (index >= state.queue.length) {
      finishBatch(state, 'queue_exhausted', '队列已处理完：本批浏览器通过 ' + decision.passes + '/' + (decision.control.effectiveStopBudget || state.targetQualified || 20) + '。');
      finalizeActiveGranular('queue_exhausted', null);
      return;
    }
    state.currentIndex = index;
    state.currentStep = 'navigate';
    state.message = '正在打开 ' + state.queue[index];
    var navigationIntentAtMs = Date.now();
    if (ENABLE_TIER0_TELEMETRY) state.currentNavigationStartedAtMs = navigationIntentAtMs;
    saveBatch(state);
    finalizeActiveGranular('', navigationIntentAtMs);
    recordGranularNavigationIntent(state, index, navigationIntentAtMs);
    var url = new URL('https://www.amazon.com/dp/' + state.queue[index]);
    url.searchParams.set('th', '1');
    url.searchParams.set(AUTO_PARAM, '1');
    url.searchParams.set(HASH_PARAM, state.queueHash);
    url.searchParams.set(INDEX_PARAM, String(index));
    location.assign(url.href);
  }

  function startSelectedBatch() {
    var state = loadBatch(selectedHash());
    if (!state) return setPanelMessage('请先生成批次。');
    var index = firstMissingIndex(state);
    state.status = 'running';
    state.currentIndex = index;
    state.stopAfterCurrentRowRequested = false;
    state.stopAction = '';
    state.stoppedReason = '';
    saveBatch(state);
    navigateToRow(state, index);
  }

  function pauseSelectedBatch() {
    var state = loadBatch(selectedHash());
    if (!state) return;
    var statusBefore = state.status;
    var stepBefore = state.currentStep;
    state.status = 'paused';
    state.currentStep = 'paused';
    state.message = '已请求暂停；当前行会完整保存后再停止。';
    state.pauseId = 'pause-' + Date.now();
    state.pausedAtMs = Date.now();
    recordControlEvent(state, 'pause_requested', {
      statusBefore: statusBefore,
      stepBefore: stepBefore,
      pauseId: state.pauseId
    });
    saveBatch(state);
  }

  function resumeSelectedBatch() {
    var state = loadBatch(selectedHash());
    if (!state) return;
    var statusBefore = state.status;
    var pauseDurationMs = Number.isFinite(Number(state.pausedAtMs))
      ? Math.max(0, Date.now() - Number(state.pausedAtMs))
      : null;
    var index = firstMissingIndex(state);
    state.status = 'running';
    state.currentIndex = index;
    state.stopAfterCurrentRowRequested = false;
    state.stopAction = '';
    state.stoppedReason = '';
    state.externalBlockerCode = '';
    state.externalBlockerAsin = '';
    state.pendingPauseRecoveryMs = pauseDurationMs;
    recordControlEvent(state, 'resume_requested', {
      statusBefore: statusBefore,
      pauseId: state.pauseId || '',
      pauseDurationMs: pauseDurationMs
    });
    saveBatch(state);
    navigateToRow(state, index);
  }

  function stopAfterCurrentRowSelectedBatch() {
    var state = loadBatch(selectedHash());
    if (!state) return;
    requestStopAfterCurrentRow(state, 'operator_stop_after_current_row');
    recordControlEvent(state, 'stop_after_current_row_requested', {
      reason: 'operator_stop_after_current_row'
    });
    saveBatch(state);
    if (state.status !== 'running') {
      finishBatch(state, 'operator_stop_after_current_row', '已请求停止；当前没有正在处理的行。');
    }
  }

  async function copySelected(enrichment) {
    var state = loadBatch(selectedHash());
    if (!state) return setPanelMessage('没有可复制的批次。');
    var value = enrichment ? enrichmentOnly(state) : exportBatch(state);
    var text = JSON.stringify(value, null, 2);
    await copyText(text);
    document.querySelector('#ss-v3-output').value = text;
    setPanelMessage(enrichment ? '已复制 enrichment JSON。' : '已复制合并 JSON。');
  }

  async function copyTelemetry(kind) {
    var state = loadBatch(selectedHash());
    if (!state) return setPanelMessage('没有可导出遥测日志的批次。');
    var isGate = kind === 'gate';
    var rows = isGate ? gateLogRows(state) : timingLogRows(state);
    var columns = isGate ? GATE_LOG_COLUMNS : TIMING_LOG_COLUMNS;
    var text = rowsToTsv(rows, columns);
    await copyText(text);
    document.querySelector('#ss-v3-output').value = text;
    setPanelMessage((isGate ? '门槛' : '耗时') + '遥测 TSV 已复制。');
  }

  async function copyGranularTelemetry(kind) {
    var state = loadBatch(selectedHash());
    if (!state) return setPanelMessage('没有可导出细粒度遥测的批次。');
    var sidecar = readJson(granularKey(state.queueHash), null);
    if (!sidecar
        || sidecar.schemaVersion !== GRANULAR_TELEMETRY_SCHEMA_VERSION
        || sidecar.queueHash !== state.queueHash
        || (sidecar.batchCreatedAt || '') !== (state.createdAt || '')) {
      return setPanelMessage('未找到对应的细粒度遥测 sidecar；没有推断或补写任何数值。');
    }
    var value;
    var text;
    if (kind === 'json') {
      text = JSON.stringify(sidecar, null, 2);
    } else if (kind === 'control') {
      text = rowsToTsv(controlEventRows(sidecar), CONTROL_EVENT_COLUMNS);
    } else {
      text = rowsToTsv(granularTimingRows(sidecar), GRANULAR_TIMING_COLUMNS);
    }
    value = text;
    await copyText(value);
    document.querySelector('#ss-v3-output').value = value;
    setPanelMessage('细粒度 ' + kind + ' 遥测已复制。');
  }

  function clearSelectedBatch() {
    var inventory = storageInventory(localStorage);
    var orphanKeys = inventory.orphanSidecarKeys.concat(inventory.invalidBatchKeys);
    if (!orphanKeys.length) return setPanelMessage('未发现可确认清理的孤立存储；所有有效批次均已保留。');
    if (!window.confirm('仅清理 ' + orphanKeys.length + ' 个无法关联到有效批次的孤立存储项。有效批次不会删除，是否继续？')) return;
    orphanKeys.forEach(function (key) { localStorage.removeItem(key); });
    reconcileStorageRecords(localStorage, null);
    setPanelMessage('已清理 ' + orphanKeys.length + ' 个孤立存储项；有效批次未删除。');
    renderPanel();
  }

  function deleteSelectedCompletedBatch() {
    var hash = selectedHash();
    var state = loadBatch(hash);
    if (!state) return setPanelMessage('没有可删除的已完成批次。');
    if (state.status !== 'done') return setPanelMessage('当前批次尚未完成，不能删除。请先暂停并保留证据。');
    var label = oneLine(state.batchName) + ' (' + state.queueHash + ')';
    if (!window.confirm('仅在合并 JSON/TSV 和 Excel 证据已保存后删除已完成批次：' + label + '。此操作不可撤销，是否继续？')) return;
    try {
      var result = removeCompletedBatchStorage(localStorage, hash);
      setPanelMessage('已删除已完成批次 ' + result.removedBatchName + '；剩余本地批次 ' + result.remainingBatchCount + ' 个。');
      renderPanel();
    } catch (error) {
      setPanelMessage('删除失败：' + oneLine(error && error.message ? error.message : error));
    }
  }

  function parseDirectLabel(root, labels) {
    if (!root) return '';
    var nodes = root.querySelectorAll('div,span,tr,li');
    var candidates = [];
    for (var i = 0; i < nodes.length; i += 1) {
      var text = oneLine(nodes[i].textContent);
      for (var j = 0; j < labels.length; j += 1) {
        var value = valueAfterLabel(text, labels[j]);
        if (value && text.length < 220) candidates.push(value);
      }
    }
    candidates.sort(function (a, b) { return a.length - b.length; });
    return candidates[0] || '';
  }

  function parseAmazonTable(labels) {
    var rows = document.querySelectorAll('#productOverview_feature_div tr,#productDetails_techSpec_section_1 tr,#productDetails_detailBullets_sections1 tr');
    for (var i = 0; i < rows.length; i += 1) {
      var cells = rows[i].querySelectorAll('th,td');
      if (cells.length < 2) continue;
      var label = oneLine(cells[0].textContent);
      if (labels.some(function (candidate) { return label.toLowerCase().indexOf(candidate.toLowerCase()) >= 0; })) {
        return oneLine(cells[cells.length - 1].textContent);
      }
    }
    return '';
  }

  function extractDimensions() {
    var root = document.querySelector('#seller-sprite-extension-quick-view-listing');
    var fields = {
      itemDimensions: parseDirectLabel(root, ['商品尺寸', 'Product Dimensions']) || parseAmazonTable(['Product Dimensions', 'Item Dimensions']),
      itemWeight: parseDirectLabel(root, ['商品重量', 'Item Weight']) || parseAmazonTable(['Item Weight']),
      packageDimensions: parseDirectLabel(root, ['包装尺寸', 'Package Dimensions']) || parseAmazonTable(['Package Dimensions']),
      packageWeight: parseDirectLabel(root, ['包装重量', 'Package Weight']) || parseAmazonTable(['Package Weight'])
    };
    fields.dimensions = buildDimensions(fields);
    fields.dimensionsSource = root ? 'SellerSprite商品详情/Amazon详情' : 'Amazon详情';
    return fields;
  }

  function visibleTooltip(container, pattern) {
    if (!container) return '';
    var nodes = container.querySelectorAll('div');
    var matches = [];
    for (var i = 0; i < nodes.length; i += 1) {
      var element = nodes[i];
      var text = oneLine(element.textContent);
      if (!text || !pattern.test(text) || !visible(element)) continue;
      var style = getComputedStyle(element);
      if (style.position !== 'absolute' && style.position !== 'fixed') continue;
      var rect = element.getBoundingClientRect();
      matches.push({ text: text, area: rect.width * rect.height, z: Number(style.zIndex) || 0 });
    }
    matches.sort(function (a, b) { return b.z - a.z || a.area - b.area; });
    return matches.length ? matches[0].text : '';
  }

  function dispatchChartMove(canvas, xRatio, yRatio) {
    var rect = canvas.getBoundingClientRect();
    var clientX = rect.left + rect.width * xRatio;
    var clientY = rect.top + rect.height * yRatio;
    var init = { bubbles: true, cancelable: true, clientX: clientX, clientY: clientY };
    // ECharts listens in the page realm. Events created by the userscript realm
    // can be ignored even when dispatchEvent succeeds, so use the canvas window.
    var eventView = canvas.ownerDocument && canvas.ownerDocument.defaultView;
    var MouseEventCtor = eventView && eventView.MouseEvent ? eventView.MouseEvent : MouseEvent;
    var PointerEventCtor = eventView && eventView.PointerEvent ? eventView.PointerEvent : (typeof PointerEvent === 'function' ? PointerEvent : null);
    canvas.dispatchEvent(new MouseEventCtor('mouseover', init));
    canvas.dispatchEvent(new MouseEventCtor('mousemove', init));
    if (PointerEventCtor) canvas.dispatchEvent(new PointerEventCtor('pointermove', init));
  }

  function dispatchChartLeave(canvas) {
    var eventView = canvas.ownerDocument && canvas.ownerDocument.defaultView;
    var MouseEventCtor = eventView && eventView.MouseEvent ? eventView.MouseEvent : MouseEvent;
    canvas.dispatchEvent(new MouseEventCtor('mouseout', { bubbles: true }));
  }

  function largestReadyKeepaCanvas(module) {
    if (!module) return null;
    var canvases = Array.from(module.querySelectorAll('canvas')).filter(function (canvas) {
      if (!visible(canvas)) return false;
      var rect = canvas.getBoundingClientRect();
      return Number(canvas.width || 0) > 0
        && Number(canvas.height || 0) > 0
        && rect.width >= 100
        && rect.height >= 80;
    });
    canvases.sort(function (a, b) { return b.width * b.height - a.width * a.height; });
    return canvases[0] || null;
  }

  async function waitForKeepaChartReady(initialModule, onRetry) {
    var startedAtMs = Date.now();
    var retryCount = 0;
    var sawCanvas = false;
    var lastCanvas = null;
    var probeRatios = [0.12, 0.34, 0.58, 0.82];
    var probeIndex = 0;
    while (Date.now() - startedAtMs < KEEPA_CHART_READY_TIMEOUT_MS) {
      var module = document.querySelector('.keepa-module') || initialModule;
      var canvas = largestReadyKeepaCanvas(module);
      if (canvas) {
        sawCanvas = true;
        lastCanvas = canvas;
        dispatchChartMove(canvas, probeRatios[probeIndex % probeRatios.length], 0.28);
        probeIndex += 1;
        await sleep(90);
        var text = visibleTooltip(module, /20\d{2}-\d{2}-\d{2}.*\$\s*\d/i);
        var seedSample = parsePriceTooltip(text);
        if (seedSample) {
          dispatchChartLeave(canvas);
          return {
            module: module,
            canvas: canvas,
            seedSample: seedSample,
            sawCanvas: true,
            waitMs: Math.max(0, Date.now() - startedAtMs),
            retryCount: retryCount
          };
        }
      }
      if (!retryCount && Date.now() - startedAtMs >= KEEPA_CHART_READY_RETRY_AT_MS) {
        retryCount = 1;
        if (typeof onRetry === 'function') await onRetry(module);
      }
      await sleep(KEEPA_CHART_READY_POLL_MS);
    }
    if (lastCanvas) dispatchChartLeave(lastCanvas);
    return {
      module: document.querySelector('.keepa-module') || initialModule,
      canvas: lastCanvas,
      seedSample: null,
      sawCanvas: sawCanvas,
      waitMs: Math.max(0, Date.now() - startedAtMs),
      retryCount: retryCount
    };
  }

  async function collectPriceTrend(priceTiming) {
    priceTiming = priceTiming || {};
    if (ENABLE_KEEPA_PARENT_CLICK_PROTOCOL) {
      await waitForKeepaTabReady();
      clickKeepaTab(document);
    } else {
      clickExactText('Keepa插件替代');
    }
    var module = await waitFor(function () {
      var element = document.querySelector('.keepa-module');
      return element && visible(element) ? element : null;
    }, 12000, 250);
    clickExactText('近1个月', module);
    var ready;
    if (ENABLE_KEEPA_CHART_READY_PROTOCOL) {
      ready = await waitForKeepaChartReady(module, async function (currentModule) {
        if (keepaModuleIsLoading(currentModule)) return;
        if (ENABLE_KEEPA_PARENT_CLICK_PROTOCOL) clickKeepaTab(document);
        else clickExactText('Keepa插件替代');
        await sleep(250);
        var refreshedModule = document.querySelector('.keepa-module') || currentModule || module;
        clickExactText('近1个月', refreshedModule);
      });
    } else {
      await sleep(700);
      var legacyCanvas = largestReadyKeepaCanvas(module);
      ready = {
        module: module,
        canvas: legacyCanvas,
        seedSample: null,
        sawCanvas: Boolean(legacyCanvas),
        waitMs: 700,
        retryCount: 0
      };
    }
    priceTiming.priceReadyWaitMs = ready.waitMs;
    priceTiming.priceRetryCount = ready.retryCount;
    module = ready.module || module;
    var canvas = ready.canvas;
    if (!canvas || (ENABLE_KEEPA_CHART_READY_PROTOCOL && !ready.seedSample)) {
      priceTiming.priceCollectionStatus = ready.sawCanvas ? 'keepa_tooltip_not_ready' : 'keepa_chart_not_ready';
      var readinessError = new Error(priceTiming.priceCollectionStatus + ' after ' + ready.waitMs + 'ms and ' + ready.retryCount + ' retry');
      readinessError.code = ready.sawCanvas ? 'SS_KEEPA_TOOLTIP_NOT_READY' : 'SS_KEEPA_CHART_NOT_READY';
      throw readinessError;
    }
    var samples = ready.seedSample ? [ready.seedSample] : [];
    for (var i = 0; i < 28; i += 1) {
      dispatchChartMove(canvas, 0.04 + (0.92 * i / 27), 0.28);
      await sleep(75);
      var text = visibleTooltip(module, /20\d{2}-\d{2}-\d{2}.*\$\s*\d/i);
      var parsed = parsePriceTooltip(text);
      if (parsed) samples.push(parsed);
    }
    dispatchChartLeave(canvas);
    if (!samples.length) {
      priceTiming.priceCollectionStatus = 'keepa_tooltip_not_ready';
      var tooltipError = new Error('keepa_tooltip_not_ready after chart became visible');
      tooltipError.code = 'SS_KEEPA_TOOLTIP_NOT_READY';
      throw tooltipError;
    }
    priceTiming.priceCollectionStatus = 'ok';
    return buildPriceTrend(samples);
  }

  async function runCollectorOnce(granularRow, attemptNumber) {
    var attempt = {
      attempt: attemptNumber,
      handshakeMode: 'status_text_v1_observed',
      buttonWaitStartedAtMs: Date.now(),
      buttonObservedAtMs: null,
      trafficTabWaitStartedAtMs: null,
      trafficTabClickAtMs: null,
      trafficTabClickFound: null,
      trafficTabGraceWaitMs: null,
      trafficTabPollCount: 0,
      trafficTabGraceRecovered: false,
      chartWaitStartedAtMs: null,
      chartReadyAtMs: null,
      collectorClickAtMs: null,
      collectingObservedAtMs: null,
      completedObservedAtMs: null,
      jsonParsedAtMs: null,
      collectorRunId: '',
      resultRunId: '',
      resultReadyAttr: '',
      runningAttr: '',
      startAckMs: null,
      resultWaitMs: null,
      totalObservedMs: null,
      collectorInternalChartWaitMs: null,
      collectorTooltipScanMs: null,
      collectorInternalTotalMs: null,
      accessBlockerCode: '',
      failureCode: '',
      payloadStatus: '',
      outcome: '',
      reason: ''
    };
    try {
      try {
        await waitFor(function () { return document.querySelector('#ss-collector-run'); }, 18000, 250);
      } catch (error) {
        throw sellerSpriteAccessError({
          code: 'seller_sprite_collector_unavailable',
          message: '流量采集器面板未就绪；请确认 Collector 已启用并刷新后继续。'
        });
      }
      attempt.buttonObservedAtMs = Date.now();
      var accessBlockerBeforeTab = detectSellerSpriteAccessBlocker();
      if (accessBlockerBeforeTab) throw sellerSpriteAccessError(accessBlockerBeforeTab);
      var trafficTabReady = await clickTrafficTabWithGrace();
      attempt.trafficTabWaitStartedAtMs = trafficTabReady.waitStartedAtMs;
      attempt.trafficTabClickAtMs = trafficTabReady.clickedAtMs;
      attempt.trafficTabClickFound = trafficTabReady.found;
      attempt.trafficTabGraceWaitMs = trafficTabReady.waitMs;
      attempt.trafficTabPollCount = trafficTabReady.pollCount;
      attempt.trafficTabGraceRecovered = trafficTabReady.found && trafficTabReady.pollCount > 1;
      if (!attempt.trafficTabClickFound) {
        if (ENABLE_TRAFFIC_BLOCK_FAST_SKIP) throw trafficBlockTimeoutError('traffic_tab_not_ready');
        throw sellerSpriteAccessError({
          code: 'seller_sprite_traffic_tab_unavailable',
          message: '卖家精灵流量洞察标签在 8 秒内未就绪；请刷新页面后从当前 ASIN 继续。'
        });
      }
      attempt.chartWaitStartedAtMs = Date.now();
      var trafficChartWaitMs = trafficBlockRemainingMs(attempt.trafficTabWaitStartedAtMs, attempt.chartWaitStartedAtMs);
      var chartReady;
      try {
        chartReady = await waitFor(function () {
          var accessBlocker = detectSellerSpriteAccessBlocker();
          if (accessBlocker) return { accessBlocker: accessBlocker };
          var box = document.querySelector('.echarts-trends-box');
          return box && visible(box) ? { box: box } : null;
        }, trafficChartWaitMs, 250);
      } catch (error) {
        if (ENABLE_TRAFFIC_BLOCK_FAST_SKIP) throw trafficBlockTimeoutError('traffic_chart_not_ready');
        throw sellerSpriteAccessError({
          code: 'seller_sprite_traffic_chart_unavailable',
          message: '卖家精灵流量图在 15 秒内未加载；请确认登录和套餐权限，刷新后继续。'
        });
      }
      if (chartReady.accessBlocker) throw sellerSpriteAccessError(chartReady.accessBlocker);
      attempt.chartReadyAtMs = Date.now();
      var button = document.querySelector('#ss-collector-run');
      var status = document.querySelector('#ss-collector-status');
      var output = document.querySelector('#ss-collector-json');
      var collectorPanel = document.querySelector('#ss-collector-panel');
      attempt.collectorClickAtMs = Date.now();
      button.click();
      await waitFor(function () { return status && /Collecting/i.test(status.textContent || ''); }, 5000, 100);
      attempt.collectingObservedAtMs = Date.now();
      await waitFor(function () { return status && !/Collecting/i.test(status.textContent || ''); }, 45000, 250);
      attempt.completedObservedAtMs = Date.now();
      var payload = JSON.parse(output.value || '{}');
      attempt.jsonParsedAtMs = Date.now();
      attempt.collectorRunId = collectorPanel ? collectorPanel.getAttribute('data-ss-run-id') || '' : '';
      attempt.resultRunId = collectorPanel ? collectorPanel.getAttribute('data-ss-result-run-id') || '' : '';
      attempt.resultReadyAttr = collectorPanel ? collectorPanel.getAttribute('data-ss-result-ready') || '' : '';
      attempt.runningAttr = collectorPanel ? collectorPanel.getAttribute('data-ss-running') || '' : '';
      attempt.startAckMs = attempt.collectingObservedAtMs - attempt.collectorClickAtMs;
      attempt.resultWaitMs = attempt.completedObservedAtMs - attempt.collectingObservedAtMs;
      attempt.totalObservedMs = attempt.jsonParsedAtMs - attempt.collectorClickAtMs;
      var internal = payload && payload.telemetry && payload.telemetry.timing ? payload.telemetry.timing : {};
      attempt.collectorInternalChartWaitMs = Number.isFinite(Number(internal.chartWaitMs)) ? Number(internal.chartWaitMs) : null;
      attempt.collectorTooltipScanMs = Number.isFinite(Number(internal.tooltipScanMs)) ? Number(internal.tooltipScanMs) : null;
      attempt.collectorInternalTotalMs = Number.isFinite(Number(internal.totalMs)) ? Number(internal.totalMs) : null;
      attempt.payloadStatus = payload.status || '';
      attempt.outcome = 'payload';
      return payload;
    } catch (error) {
      attempt.outcome = 'error';
      attempt.reason = oneLine(error && error.message ? error.message : error);
      attempt.accessBlockerCode = error && error.accessBlocker ? error.accessBlocker.code : '';
      attempt.failureCode = oneLine(error && error.code ? error.code : '');
      throw error;
    } finally {
      if (granularRow) {
        granularRow.collectorAttempts.push(attempt);
        granularRow.sellerSprite.collectorButtonObservedAtMs = granularRow.sellerSprite.collectorButtonObservedAtMs || attempt.buttonObservedAtMs;
        granularRow.sellerSprite.sellerSpriteUiFirstObservedAtMs = granularRow.sellerSprite.sellerSpriteUiFirstObservedAtMs || attempt.buttonObservedAtMs;
        granularRow.sellerSprite.trafficTabWaitStartedAtMs = granularRow.sellerSprite.trafficTabWaitStartedAtMs || attempt.trafficTabWaitStartedAtMs;
        granularRow.sellerSprite.trafficTabClickAtMs = granularRow.sellerSprite.trafficTabClickAtMs || attempt.trafficTabClickAtMs;
        granularRow.sellerSprite.trafficTabClickFound = attempt.trafficTabClickFound;
        granularRow.sellerSprite.trafficTabGraceWaitMs = Math.max(
          Number(granularRow.sellerSprite.trafficTabGraceWaitMs || 0),
          Number(attempt.trafficTabGraceWaitMs || 0)
        );
        granularRow.sellerSprite.trafficTabPollCount = Math.max(
          Number(granularRow.sellerSprite.trafficTabPollCount || 0),
          Number(attempt.trafficTabPollCount || 0)
        );
        granularRow.sellerSprite.trafficTabGraceRecovered = granularRow.sellerSprite.trafficTabGraceRecovered || attempt.trafficTabGraceRecovered;
        granularRow.sellerSprite.trafficChartReadyAtMs = granularRow.sellerSprite.trafficChartReadyAtMs || attempt.chartReadyAtMs;
        granularRow.sellerSprite.trafficTabToChartReadyMs = attempt.chartReadyAtMs !== null && attempt.trafficTabClickAtMs !== null
          ? Math.max(0, attempt.chartReadyAtMs - attempt.trafficTabClickAtMs)
          : null;
        if (attempt.reason) granularRow.sellerSprite.reason = attempt.reason;
      }
    }
  }

  async function collectTraffic(telemetry, granularRow) {
    if (telemetry) {
      telemetry.retryCount = 0;
      telemetry.retryDecision = 'no_retry';
      telemetry.retryReason = '';
    }
    var payload = await runCollectorOnce(granularRow, 1);
    var retryReason = ENABLE_TIER2_2_CONDITIONAL_RETRY
      ? collectorRetryReason(payload)
      : legacyCollectorRetryReason(payload);
    var shouldRetry = shouldRetryCollector(payload);
    if (telemetry) {
      telemetry.retryReason = retryReason || (collectorHasKnownTrafficFailure(payload) ? 'known_traffic_failure' : 'not_ready_not_confirmed');
      telemetry.retryDecision = shouldRetry ? 'retry' : 'no_retry';
    }
    if (shouldRetry) {
      if (telemetry) telemetry.retryCount += 1;
      await sleep(600);
      var retry = await runCollectorOnce(granularRow, 2);
      if (retry.status === 'ok' && Number(retry.weeksRead || 0) >= Number(payload.weeksRead || 0)) payload = retry;
    }
    return payload;
  }

  function updateCurrentStep(state, step, message) {
    mergeLatestControlState(state, loadBatch(state.queueHash));
    state.currentStep = step;
    state.message = message || '';
    saveBatch(state);
  }

  async function processAutoRow() {
    var params = new URLSearchParams(location.search);
    if (params.get(AUTO_PARAM) !== '1') return;
    var hash = params.get(HASH_PARAM) || '';
    var index = Number(params.get(INDEX_PARAM) || 0);
    var state = loadBatch(hash);
    if (!state || state.status !== 'running') return;
    if (!Number.isInteger(index) || index < 0 || index >= state.queue.length) return;
    var targetAsin = state.queue[index];
    var actualAsin = currentAsin();
    var mismatch = Boolean(actualAsin && targetAsin !== actualAsin);
    var processStartedMs = Date.now();
    var previousStep = state.currentStep || '';
    var granularRow = beginGranularRow(state, index, processStartedMs);
    if (!state.results[index] && ['traffic', 'dimensions', 'price'].indexOf(previousStep) >= 0) {
      recordControlEvent(state, 'recovery_detected', {
        row: index + 1,
        asin: targetAsin,
        stepBefore: previousStep,
        recoveryKind: 'reload_with_unfinished_row',
        recoveryEvidence: 'saved_step_' + previousStep + '_result_missing'
      });
    }
    state.pendingPauseRecoveryMs = null;
    var startedAt = new Date().toISOString();
    var navigationStartedAtMs = Number(state.currentNavigationStartedAtMs);
    var detailPageMs = ENABLE_TIER0_TELEMETRY && Number.isFinite(navigationStartedAtMs)
      ? Math.max(0, processStartedMs - navigationStartedAtMs)
      : null;
    var trafficChartMs = null;
    var dimensionsMs = null;
    var priceChartMs = null;
    var trafficTiming = { retryCount: 0, retryDecision: 'no_retry', retryReason: '' };
    var dimensions = { dimensions: '', itemDimensions: '', itemWeight: '', packageDimensions: '', packageWeight: '', dimensionsSource: '' };
    var priceTrend = buildPriceTrend([]);
    var priceTiming = { priceCollectionStatus: 'not_run', priceReadyWaitMs: null, priceRetryCount: 0 };
    var collectorPayload = { status: 'error', decision: 'review', weeksRead: 0, collectedAt: new Date().toISOString() };
    var errorMessage = '';
    var errorCode = '';
    var currentGate = mismatch ? 'asin' : 'traffic';
    var skippedSteps = [];

    try {
      if (!mismatch) {
        updateCurrentStep(state, 'traffic', 'Running Traffic Collector 0.4.6.');
        var trafficStartedMs = ENABLE_TIER0_TELEMETRY ? Date.now() : null;
        try {
          collectorPayload = await collectTraffic(ENABLE_TIER0_TELEMETRY ? trafficTiming : null, granularRow);
        } finally {
          if (ENABLE_TIER0_TELEMETRY) trafficChartMs = Date.now() - trafficStartedMs;
        }
        var collectedTraffic = parseTrafficCollector(collectorPayload, targetAsin, actualAsin);
        var trafficGate = evaluateTrafficGate(collectedTraffic, false);
        if (!trafficGate.pass) {
          skippedSteps = ['dimensions', 'price'];
        } else {
          currentGate = 'dimensions';
          updateCurrentStep(state, 'dimensions', 'Reading dimensions after traffic pass.');
          var dimensionsStartedMs = ENABLE_TIER0_TELEMETRY ? Date.now() : null;
          try {
            await waitFor(function () { return document.querySelector('#seller-sprite-extension-quick-view-listing,#productOverview_feature_div'); }, 15000, 250);
            dimensions = extractDimensions();
          } finally {
            if (ENABLE_TIER0_TELEMETRY) dimensionsMs = Date.now() - dimensionsStartedMs;
          }
          var dimensionsGate = evaluateDimensionsGate(dimensions.dimensions);
          if (!dimensionsGate.pass) {
            skippedSteps = ['price'];
          } else {
            currentGate = 'price';
            updateCurrentStep(state, 'price', 'Reading recent price trend after dimensions pass.');
            var priceStartedMs = ENABLE_TIER0_TELEMETRY ? Date.now() : null;
            try {
              priceTrend = await collectPriceTrend(priceTiming);
            } finally {
              if (ENABLE_TIER0_TELEMETRY) priceChartMs = Date.now() - priceStartedMs;
            }
          }
        }
      } else {
        skippedSteps = ['traffic', 'dimensions', 'price'];
      }
    } catch (error) {
      if (error && error.code === 'SS_SELLERSPRITE_ACCESS_BLOCKED') {
        state = loadBatch(hash) || state;
        var accessBlocker = error.accessBlocker || {
          code: 'seller_sprite_access_blocked',
          message: oneLine(error && error.message ? error.message : error)
        };
        applySellerSpriteAccessPause(state, index, targetAsin, accessBlocker, Date.now());
        recordControlEvent(state, 'seller_sprite_access_blocked', {
          row: index + 1,
          asin: targetAsin,
          stepBefore: currentGate,
          reason: accessBlocker.code
        });
        saveBatch(state);
        finalizeActiveGranular('seller_sprite_access_blocked', null);
        return;
      }
      errorCode = oneLine(error && error.code ? error.code : '');
      errorMessage = oneLine(error && error.message ? error.message : error);
      if (errorCode === 'SS_TRAFFIC_BLOCK_TIMEOUT') skippedSteps = ['dimensions', 'price'];
    }

    var traffic = parseTrafficCollector(collectorPayload, targetAsin, actualAsin);
    var trafficGate = evaluateTrafficGate(traffic, mismatch);
    var dimensionsGate = trafficGate.pass ? evaluateDimensionsGate(dimensions.dimensions) : { pass: false, stage: 'dimensions', rule: 'not_run', reason: 'traffic did not pass' };
    var priceGate = trafficGate.pass && dimensionsGate.pass
      ? evaluatePriceGate(priceTrend.priceTrendClass, priceTrend.currentPrice)
      : { pass: false, stage: 'price', rule: 'not_run', reason: 'prior gate did not pass' };
    var finalGate = errorMessage
      ? {
          pass: false,
          stage: currentGate,
          rule: errorCode === 'SS_TRAFFIC_BLOCK_TIMEOUT' ? 'traffic_block_timeout' : 'collection_error',
          reason: errorMessage
        }
      : (!trafficGate.pass ? trafficGate : (!dimensionsGate.pass ? dimensionsGate : priceGate));
    var strictDecision = finalGate.pass ? 'pass' : 'reject';
    var enrichmentStatus = strictDecision === 'pass' ? 'ok' : 'review';
    var result = Object.assign({
      row: index + 1,
      asinMismatch: mismatch,
      mismatchReason: mismatch ? 'amazon_variant_redirect' : '',
      url: location.href,
      startedAt: startedAt,
      finishedAt: new Date().toISOString(),
      enrichmentStatus: enrichmentStatus,
      enrichmentCollectedAt: new Date().toISOString(),
      strictDecision: strictDecision,
      qualified: strictDecision === 'pass',
      rejectionStage: strictDecision === 'pass' ? '' : finalGate.stage,
      rejectionRule: strictDecision === 'pass' ? '' : finalGate.rule,
      rejectionReason: strictDecision === 'pass' ? '' : finalGate.reason,
      skippedSteps: skippedSteps,
      error: errorMessage
    }, traffic, dimensions, priceTrend, priceTiming);
    if (granularRow) {
      granularRow.collectorVersion = result.collectorVersion || '';
      granularRow.completion.resultFinishedAtMs = Date.parse(result.finishedAt);
    }
    if (ENABLE_TIER0_TELEMETRY) {
      var timingMeasurements = {
        detailPageMs: detailPageMs,
        detailPageMsReason: detailPageMs == null ? 'navigation_start_not_recorded' : '',
        trafficChartMs: trafficChartMs,
        trafficChartMsReason: trafficChartMs == null ? (mismatch ? 'asin_mismatch_short_circuit' : 'not_run') : '',
        dimensionsMs: dimensionsMs,
        dimensionsMsReason: dimensionsMs == null ? 'not_run_due_to_prior_gate' : '',
        priceChartMs: priceChartMs,
        priceChartMsReason: priceChartMs == null ? 'not_run_due_to_prior_gate' : '',
        retryCount: trafficTiming.retryCount,
        retryDecision: trafficTiming.retryDecision,
        retryReason: trafficTiming.retryReason,
        totalMs: Date.now() - processStartedMs
      };
      attachRunnerTelemetry(result, timingMeasurements, state);
    }
    if (mismatch) result.note = oneLine(result.note + '; asin_mismatch_amazon_redirect');
    if (errorMessage) result.note = oneLine(result.note + '; ' + errorMessage);
    if (strictDecision !== 'pass') result.note = oneLine(result.note + '; short_circuit:' + finalGate.stage + ':' + finalGate.rule);

    state = loadBatch(hash) || state;
    state.message = targetAsin + ' ' + strictDecision + ' at ' + (strictDecision === 'pass' ? 'all_gates' : finalGate.stage) + ' in ' + Math.round((Date.now() - Date.parse(startedAt)) / 1000) + 's.';
    state = commitCompletedRow(state, index, result).state;

    state = loadBatch(hash) || state;
    if (state.status === 'paused') {
      recordControlEvent(state, 'paused_after_row', { row: index + 1, asin: targetAsin });
      finalizeActiveGranular('paused_after_row', null);
      return;
    }
    var decision = stopDecision(state);
    if (decision.stop) {
      state.stopAction = decision.action;
      finishBatch(
        state,
        decision.reason,
        decision.reason === 'operator_stop_after_current_row'
          ? 'Current row saved; operator stop requested.'
          : 'Target reached: ' + decision.passes + '/' + decision.control.effectiveStopBudget + ' browser passes.'
      );
      finalizeActiveGranular(decision.reason, null);
      return;
    }
    if (state.currentIndex >= state.queue.length) {
      finishBatch(state, 'queue_exhausted', 'Queue exhausted: ' + decision.passes + '/' + decision.control.effectiveStopBudget + ' browser passes.');
      finalizeActiveGranular('queue_exhausted', null);
      return;
    }
    await sleep(500);
    navigateToRow(state, state.currentIndex);
  }

  if (ENABLE_STORAGE_HARDENING) {
    try {
      reconcileStorageRecords(localStorage, null);
    } catch (startupStorageError) {
      LAST_STORAGE_ERROR = oneLine(startupStorageError && startupStorageError.message ? startupStorageError.message : startupStorageError);
    }
  }
  createPanel();
  setTimeout(function () {
    processAutoRow().catch(function (error) {
      if (error && error.code === 'SS_STORAGE_PERSISTENCE_FAILED') {
        ACTIVE_GRANULAR_CONTEXT = null;
        setPanelMessage('本地存储写入失败，自动跳转已停止；释放站点存储后刷新或继续，当前行会从最后成功状态恢复。');
        return;
      }
      var failedState = loadBatch(selectedHash());
      if (failedState) {
        recordControlEvent(failedState, 'auto_error', {
          reason: oneLine(error && error.message ? error.message : error)
        });
      }
      finalizeActiveGranular('auto_error', null);
      setPanelMessage('Auto error: ' + oneLine(error && error.message ? error.message : error));
    });
  }, 400);
})();
