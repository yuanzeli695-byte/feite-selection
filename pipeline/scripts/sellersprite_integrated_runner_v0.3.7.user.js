// ==UserScript==
// @name         SellerSprite Integrated Runner 0.3.7
// @namespace    amazon-products
// @version      0.3.7
// @description  Short-circuits hard-gate failures, derives only explicit zero traffic shares, and retries only readiness failures.
// @match        https://www.amazon.com/*
// @grant        GM_setClipboard
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  var VERSION = '0.3.7';
  var SCHEMA_VERSION = 'sellerSpriteIntegratedBatch/v0.3.0';
  var ENABLE_TIER0_TELEMETRY = true;
  var ENABLE_TIER2_2_CONDITIONAL_RETRY = true;
  var TIER2_RETRY_VERSION = 'tier2.2-conditional-retry-v1';
  var TELEMETRY_SCHEMA_VERSION = 'sellerSpriteTelemetry/v1';
  var STORAGE_PREFIX = 'ssIntegratedRunner:v0.3:';
  var PRICE_MIN_USD = 9.9;
  var PRICE_MAX_USD = 50;
  var INDEX_KEY = STORAGE_PREFIX + 'index';
  var SELECTED_KEY = STORAGE_PREFIX + 'selected';
  var STRICT_HISTORY_KEY = STORAGE_PREFIX + 'strict-qualified-history';
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
    'recent4AvgNaturalSharePct', 'recent4MinNaturalSharePct', 'dimensions',
    'dimensionsSource', 'currentPrice', 'priceTrendClass', 'rejectionRule',
    'rejectionReason', 'skippedSteps', 'url'
  ];
  var TIMING_LOG_COLUMNS = [
    'startedAt', 'finishedAt', 'batchName', 'queueHash', 'asin', 'runnerVersion', 'collectorVersion',
    'detailPageMs', 'detailPageMsReason', 'trafficChartMs', 'trafficChartMsReason',
    'dimensionsMs', 'dimensionsMsReason', 'priceChartMs', 'priceChartMsReason',
    'retryCount', 'retryDecision', 'retryReason', 'totalMs'
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
    if (!traffic || traffic.status !== 'ok') return { pass: false, stage: 'traffic', rule: 'traffic_error', reason: oneLine((traffic || {}).note || (traffic || {}).status || 'missing_traffic') };
    if (Number(traffic.weeksRead || 0) < 3) return { pass: false, stage: 'traffic', rule: 'traffic_weeks_insufficient', reason: 'weeksRead < 3' };
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
    return payload.shortCircuited === true
      || (Number.isFinite(latest) && latest < 70)
      || (Number.isFinite(avg) && avg < 70)
      || (Number.isFinite(min) && min < 70);
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
      dimensions: result.dimensions || '',
      dimensionsSource: result.dimensionsSource || '',
      currentPrice: typeof result.currentPrice === 'number' ? result.currentPrice : null,
      priceTrendClass: result.priceTrendClass || '',
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
    gateLogColumns: GATE_LOG_COLUMNS.slice(),
    timingLogColumns: TIMING_LOG_COLUMNS.slice(),
    telemetryEnabled: ENABLE_TIER0_TELEMETRY,
    tier22ConditionalRetryEnabled: ENABLE_TIER2_2_CONDITIONAL_RETRY,
    tier2RetryVersion: TIER2_RETRY_VERSION,
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
    localStorage.setItem(key, JSON.stringify(value));
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
    state.targetQualified = Number.isInteger(Number(state.targetQualified)) && Number(state.targetQualified) > 0 ? Number(state.targetQualified) : 20;
    state.qualifiedCount = summary.qualified;
    state.rejectedCount = summary.rejected;
    state.historySkippedCount = (state.historySkippedAsins || []).length;
    state.updatedAt = new Date().toISOString();
    writeJson(stateKey(state.queueHash), state);
    var index = getBatchIndex().filter(function (item) { return item.queueHash !== state.queueHash; });
    index.unshift({ queueHash: state.queueHash, batchName: state.batchName, createdAt: state.createdAt });
    writeJson(INDEX_KEY, index.slice(0, 30));
    localStorage.setItem(SELECTED_KEY, state.queueHash);
    renderPanel();
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
      '#ss-v3-panel pre{white-space:pre-wrap;background:#f3f4f6;border:1px solid #ddd;padding:6px;max-height:190px;overflow:auto}',
      '#ss-v3-message{color:#b45309;font-weight:700;margin-left:4px}',
      '#ss-v3-panel.ss-v3-collapsed .ss-v3-body{display:none}'
    ].join('\n');
    document.head.appendChild(style);

    var panel = document.createElement('div');
    panel.id = 'ss-v3-panel';
    panel.className = 'notranslate';
    var telemetryButtons = ENABLE_TIER0_TELEMETRY
      ? '<button id="ss-v3-copy-gate-tsv">Copy gate log TSV</button>' +
        '<button id="ss-v3-copy-timing-tsv">Copy timing log TSV</button>'
      : '';
    panel.innerHTML = [
      '<h3>SellerSprite Integrated Runner ' + VERSION + ' <button id="ss-v3-toggle">收起</button></h3>',
      '<div class="ss-v3-body">',
      '<label>Local batches</label><select id="ss-v3-picker"></select>',
       '<label>batchName</label><input id="ss-v3-name" value="strict20-integrated-' + new Date().toISOString().slice(0, 10) + '">',
       '<label>operator</label><input id="ss-v3-operator" value="liyuanze">',
       '<label>targetQualified</label><input id="ss-v3-target" type="number" min="1" value="20">',
       '<label>QUEUE input</label><textarea id="ss-v3-queue" placeholder="One ASIN per line"></textarea>',
      '<button id="ss-v3-generate">Generate</button><span id="ss-v3-message"></span><br>',
      '<button class="ss-v3-primary" id="ss-v3-start">Start</button>',
      '<button id="ss-v3-pause">Pause</button>',
      '<button id="ss-v3-resume">Resume</button>',
      '<button id="ss-v3-copy">Copy combined JSON</button>',
      '<button id="ss-v3-copy-enrichment">Copy enrichment JSON</button>',
      telemetryButtons,
      '<button id="ss-v3-clear">Clear batch</button>',
      '<pre id="ss-v3-status">No batch selected.</pre>',
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
    panel.querySelector('#ss-v3-copy').addEventListener('click', function () { copySelected(false); });
    panel.querySelector('#ss-v3-copy-enrichment').addEventListener('click', function () { copySelected(true); });
    if (ENABLE_TIER0_TELEMETRY) {
      panel.querySelector('#ss-v3-copy-gate-tsv').addEventListener('click', function () { copyTelemetry('gate'); });
      panel.querySelector('#ss-v3-copy-timing-tsv').addEventListener('click', function () { copyTelemetry('timing'); });
    }
    panel.querySelector('#ss-v3-clear').addEventListener('click', clearSelectedBatch);
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
    picker.innerHTML = '<option value="">No batch generated</option>' + index.map(function (item) {
      return '<option value="' + item.queueHash + '">' + item.batchName + ' (' + item.queueHash + ')</option>';
    }).join('');
    picker.value = selected;
    var state = loadBatch(selected);
    if (!state) {
      panel.querySelector('#ss-v3-status').textContent = 'No batch selected.\nHistorical strict-qualified ASINs: ' + historyCount + ' (auto-skip).';
      panel.querySelector('#ss-v3-output').value = '';
      return;
    }
    panel.querySelector('#ss-v3-name').value = state.batchName;
    panel.querySelector('#ss-v3-operator').value = state.operator;
    panel.querySelector('#ss-v3-target').value = state.targetQualified || 20;
    panel.querySelector('#ss-v3-queue').value = state.queue.join('\n');
    var summary = summarizeResults(state.results);
    panel.querySelector('#ss-v3-status').textContent = [
      'Batch: ' + state.batchName,
      'Queue hash: ' + state.queueHash,
      'Status: ' + state.status,
      'Progress: ' + summary.completed + '/' + state.queue.length,
      'Qualified: ' + summary.qualified + '/' + (state.targetQualified || 20),
      'Rejected: ' + summary.rejected,
      'History auto-skipped: ' + (state.historySkippedAsins || []).length,
      'Local strict-qualified history: ' + historyCount,
      'Current row: ' + (state.currentIndex + 1),
      'Current ASIN: ' + (state.queue[state.currentIndex] || ''),
      'Step: ' + (state.currentStep || 'idle'),
      'Message: ' + (state.message || '')
    ].join('\n');
    panel.querySelector('#ss-v3-output').value = JSON.stringify(exportBatch(state), null, 2);
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
    var targetQualified = Number(document.querySelector('#ss-v3-target').value);
    if (!Number.isInteger(targetQualified) || targetQualified < 1) targetQualified = 20;
    var hash = fnv1a(batchName + '\n' + operator + '\n' + targetQualified + '\n' + queue.join('\n'));
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
    state.message = message;
    saveBatch(state);
  }

  function navigateToRow(state, index) {
    var summary = summarizeResults(state.results);
    var targetQualified = state.targetQualified || 20;
    if (summary.qualified >= targetQualified) {
      finishBatch(state, 'target_reached', 'Target reached: ' + summary.qualified + '/' + targetQualified + ' qualified.');
      return;
    }
    if (index >= state.queue.length) {
      finishBatch(state, 'queue_exhausted', 'Queue exhausted: ' + summary.qualified + '/' + targetQualified + ' qualified.');
      return;
    }
    state.currentIndex = index;
    state.currentStep = 'navigate';
    state.message = 'Opening ' + state.queue[index];
    if (ENABLE_TIER0_TELEMETRY) state.currentNavigationStartedAtMs = Date.now();
    saveBatch(state);
    var url = new URL('https://www.amazon.com/dp/' + state.queue[index]);
    url.searchParams.set('th', '1');
    url.searchParams.set(AUTO_PARAM, '1');
    url.searchParams.set(HASH_PARAM, state.queueHash);
    url.searchParams.set(INDEX_PARAM, String(index));
    location.assign(url.href);
  }

  function startSelectedBatch() {
    var state = loadBatch(selectedHash());
    if (!state) return setPanelMessage('请先 Generate。');
    var index = firstMissingIndex(state);
    state.status = 'running';
    state.currentIndex = index;
    saveBatch(state);
    navigateToRow(state, index);
  }

  function pauseSelectedBatch() {
    var state = loadBatch(selectedHash());
    if (!state) return;
    state.status = 'paused';
    state.currentStep = 'paused';
    state.message = 'Pause requested; current row will be saved.';
    saveBatch(state);
  }

  function resumeSelectedBatch() {
    var state = loadBatch(selectedHash());
    if (!state) return;
    var index = firstMissingIndex(state);
    state.status = 'running';
    state.currentIndex = index;
    saveBatch(state);
    navigateToRow(state, index);
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
    if (!state) return setPanelMessage('No batch available for telemetry export.');
    var isGate = kind === 'gate';
    var rows = isGate ? gateLogRows(state) : timingLogRows(state);
    var columns = isGate ? GATE_LOG_COLUMNS : TIMING_LOG_COLUMNS;
    var text = rowsToTsv(rows, columns);
    await copyText(text);
    document.querySelector('#ss-v3-output').value = text;
    setPanelMessage((isGate ? 'Gate' : 'Timing') + ' telemetry TSV copied.');
  }

  function clearSelectedBatch() {
    var hash = selectedHash();
    if (!hash) return;
    if (!window.confirm('Clear selected Integrated Runner batch?')) return;
    localStorage.removeItem(stateKey(hash));
    writeJson(INDEX_KEY, getBatchIndex().filter(function (item) { return item.queueHash !== hash; }));
    localStorage.removeItem(SELECTED_KEY);
    renderPanel();
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

  async function collectPriceTrend() {
    clickExactText('Keepa插件替代');
    var module = await waitFor(function () {
      var element = document.querySelector('.keepa-module');
      return element && visible(element) ? element : null;
    }, 12000, 250);
    clickExactText('近1个月', module);
    await sleep(700);
    var canvases = Array.from(module.querySelectorAll('canvas')).filter(visible);
    canvases.sort(function (a, b) { return b.width * b.height - a.width * a.height; });
    var canvas = canvases[0];
    if (!canvas) return buildPriceTrend([]);
    var samples = [];
    for (var i = 0; i < 28; i += 1) {
      dispatchChartMove(canvas, 0.04 + (0.92 * i / 27), 0.28);
      await sleep(75);
      var text = visibleTooltip(module, /20\d{2}-\d{2}-\d{2}.*\$\s*\d/i);
      var parsed = parsePriceTooltip(text);
      if (parsed) samples.push(parsed);
    }
    dispatchChartLeave(canvas);
    return buildPriceTrend(samples);
  }

  async function runCollectorOnce() {
    await waitFor(function () { return document.querySelector('#ss-collector-run'); }, 18000, 250);
    clickExactText('流量洞察');
    await waitFor(function () {
      var box = document.querySelector('.echarts-trends-box');
      return box && visible(box) ? box : null;
    }, 15000, 250);
    var button = document.querySelector('#ss-collector-run');
    var status = document.querySelector('#ss-collector-status');
    var output = document.querySelector('#ss-collector-json');
    button.click();
    await waitFor(function () { return status && /Collecting/i.test(status.textContent || ''); }, 5000, 100);
    await waitFor(function () { return status && !/Collecting/i.test(status.textContent || ''); }, 45000, 250);
    return JSON.parse(output.value || '{}');
  }

  async function collectTraffic(telemetry) {
    if (telemetry) {
      telemetry.retryCount = 0;
      telemetry.retryDecision = 'no_retry';
      telemetry.retryReason = '';
    }
    var payload = await runCollectorOnce();
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
      var retry = await runCollectorOnce();
      if (retry.status === 'ok' && Number(retry.weeksRead || 0) >= Number(payload.weeksRead || 0)) payload = retry;
    }
    return payload;
  }

  function updateCurrentStep(state, step, message) {
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
    var collectorPayload = { status: 'error', decision: 'review', weeksRead: 0, collectedAt: new Date().toISOString() };
    var errorMessage = '';
    var currentGate = mismatch ? 'asin' : 'traffic';
    var skippedSteps = [];

    try {
      if (!mismatch) {
        updateCurrentStep(state, 'traffic', 'Running Traffic Collector 0.4.6.');
        var trafficStartedMs = ENABLE_TIER0_TELEMETRY ? Date.now() : null;
        try {
          collectorPayload = await collectTraffic(ENABLE_TIER0_TELEMETRY ? trafficTiming : null);
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
              priceTrend = await collectPriceTrend();
            } finally {
              if (ENABLE_TIER0_TELEMETRY) priceChartMs = Date.now() - priceStartedMs;
            }
          }
        }
      } else {
        skippedSteps = ['traffic', 'dimensions', 'price'];
      }
    } catch (error) {
      errorMessage = oneLine(error && error.message ? error.message : error);
    }

    var traffic = parseTrafficCollector(collectorPayload, targetAsin, actualAsin);
    var trafficGate = evaluateTrafficGate(traffic, mismatch);
    var dimensionsGate = trafficGate.pass ? evaluateDimensionsGate(dimensions.dimensions) : { pass: false, stage: 'dimensions', rule: 'not_run', reason: 'traffic did not pass' };
    var priceGate = trafficGate.pass && dimensionsGate.pass
      ? evaluatePriceGate(priceTrend.priceTrendClass, priceTrend.currentPrice)
      : { pass: false, stage: 'price', rule: 'not_run', reason: 'prior gate did not pass' };
    var finalGate = errorMessage
      ? { pass: false, stage: currentGate, rule: 'collection_error', reason: errorMessage }
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
    }, traffic, dimensions, priceTrend);
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
    var strictHistory = strictDecision === 'pass'
      ? recordStrictQualified(targetAsin, {
        qualifiedAt: result.finishedAt,
        batchName: state.batchName,
        queueHash: state.queueHash
      })
      : getStrictHistory();
    state.results[index] = result;
    state.currentIndex = index + 1;
    state.currentStep = 'saved';
    state.historyRegistryCount = strictHistoryCount(strictHistory);
    state.message = targetAsin + ' ' + strictDecision + ' at ' + (strictDecision === 'pass' ? 'all_gates' : finalGate.stage) + ' in ' + Math.round((Date.now() - Date.parse(startedAt)) / 1000) + 's.';
    saveBatch(state);

    if (state.status === 'paused') return;
    var summary = summarizeResults(state.results);
    if (summary.qualified >= (state.targetQualified || 20)) {
      finishBatch(state, 'target_reached', 'Target reached: ' + summary.qualified + '/' + state.targetQualified + ' qualified.');
      return;
    }
    if (state.currentIndex >= state.queue.length) {
      finishBatch(state, 'queue_exhausted', 'Queue exhausted: ' + summary.qualified + '/' + (state.targetQualified || 20) + ' qualified.');
      return;
    }
    await sleep(500);
    navigateToRow(state, state.currentIndex);
  }

  createPanel();
  setTimeout(function () {
    processAutoRow().catch(function (error) {
      setPanelMessage('Auto error: ' + oneLine(error && error.message ? error.message : error));
    });
  }, 400);
})();
