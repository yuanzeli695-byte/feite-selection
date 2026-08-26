// ==UserScript==
// @name         SellerSprite Integrated Runner 0.3.9 [P2 baseline OFF]
// @namespace    amazon-products
// @version      0.3.9-p2off
// @description  Paired-validation baseline with the P2 deadline protocol disabled.
// @match        https://www.amazon.com/*
// @grant        GM_setClipboard
// @run-at       document-idle
// ==/UserScript==

(function () {
  'use strict';

  var VERSION = '0.3.9';
  var SCHEMA_VERSION = 'sellerSpriteIntegratedBatch/v0.3.0';
  var ENABLE_TIER0_TELEMETRY = true;
  var ENABLE_TIER0_GRANULAR_TELEMETRY = true;
  var ENABLE_P1_CUMULATIVE_TARGET_CONTROL = true;
  var ENABLE_TIER2_2_CONDITIONAL_RETRY = true;
  var ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL = false;
  var ENABLE_P2_PAIR_SANDBOX_HISTORY = true;
  var TIER2_RETRY_VERSION = 'tier2.2-conditional-retry-v1';
  var TELEMETRY_SCHEMA_VERSION = 'sellerSpriteTelemetry/v1';
  var GRANULAR_TELEMETRY_SCHEMA_VERSION = 'sellerSpriteGranularTelemetry/v1';
  var GRANULAR_TELEMETRY_VERSION = 'tier0.2-granular-v1';
  var TARGET_CONTROL_VERSION = 'p1-cumulative-remaining-v1';
  var COLLECTOR_DEADLINE_PROTOCOL_NAME = 'p2-collector-owned-deadline-v1';
  var COLLECTOR_DEADLINE_PROTOCOL_VERSION = '2';
  var COLLECTOR_DEADLINE_OWNER = 'collector';
  var COLLECTOR_DEADLINE_VERSION = '0.4.7';
  var LEGACY_COLLECTOR_PROTOCOL_NAME = 'legacy_status_text_v1';
  var LEGACY_COLLECTOR_PROTOCOL_VERSION = '1';
  var LEGACY_COLLECTOR_DEADLINE_OWNER = 'runner';
  var COLLECTOR_DEADLINE_GRACE_MS = 5000;
  var COLLECTOR_HEARTBEAT_STALE_MS = 5000;
  var STORAGE_PREFIX = 'ssIntegratedRunner:v0.3:';
  var PRICE_MIN_USD = 9.9;
  var PRICE_MAX_USD = 50;
  var INDEX_KEY = STORAGE_PREFIX + 'index';
  var SELECTED_KEY = STORAGE_PREFIX + 'selected';
  var PRODUCTION_STRICT_HISTORY_KEY = STORAGE_PREFIX + 'strict-qualified-history';
  var P2_SANDBOX_HISTORY_VERSION = 'p2-paired-sandbox-history-v1';
  var P2_SANDBOX_HISTORY_SIDE = ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL ? 'on' : 'off';
  var P2_SANDBOX_HISTORY_KEY = STORAGE_PREFIX + 'p2-paired-sandbox-history:' + P2_SANDBOX_HISTORY_SIDE;
  var STRICT_HISTORY_KEY = ENABLE_P2_PAIR_SANDBOX_HISTORY ? P2_SANDBOX_HISTORY_KEY : PRODUCTION_STRICT_HISTORY_KEY;
  var GRANULAR_STORAGE_PREFIX = STORAGE_PREFIX + 'granular:v1:';
  var RUNNER_INJECTED_AT_MS = Date.now();
  var RUNNER_DOCUMENT_READY_STATE = typeof document === 'undefined' ? '' : document.readyState;
  var ACTIVE_ROW_TIMING = null;
  var ACTIVE_GRANULAR_CONTEXT = null;
  var LAST_GRANULAR_TELEMETRY_ERROR = '';
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
  var GRANULAR_TIMING_COLUMNS = [
    'row', 'asin', 'batchName', 'queueHash', 'runnerVersion', 'collectorVersion',
    'navigationIntentAtMs', 'navigationStartAtMs', 'amazonDomReadyAtMs', 'runnerInjectedAtMs',
    'autoProcessStartedAtMs', 'navigationType', 'preNavigationMs', 'navigationDomMs',
    'domToRunnerInjectionMs', 'runnerBootDelayMs', 'documentReadyState',
    'trafficTabClickAtMs', 'trafficTabClickFound', 'trafficChartReadyAtMs',
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

  function uniqueTextList(values) {
    var seen = {};
    return (Array.isArray(values) ? values : []).map(oneLine).filter(function (value) {
      if (!value || seen[value]) return false;
      seen[value] = true;
      return true;
    });
  }

  function pendingRecoverySummary(state) {
    state = state || {};
    var index = Number(state.currentIndex);
    var pending = state.status === 'paused'
      && Number.isInteger(index)
      && index >= 0
      && Array.isArray(state.results)
      && !state.results[index];
    var asin = pending && Array.isArray(state.queue) ? normalizeAsin(state.queue[index]) : '';
    return {
      schemaVersion: 'collectorProtocolPendingRecovery/v1',
      state: pending ? 'pending-recovery' : 'none',
      count: pending ? 1 : 0,
      asins: asin ? [asin] : [],
      pauseAttempts: pending ? Number(state.pendingCollectorProtocolPauseCount || 0) : 0,
      reasons: pending ? uniqueTextList(state.pendingCollectorProtocolPauseReasons) : []
    };
  }

  function batchFinishDecision(state) {
    var pending = pendingRecoverySummary(state);
    return pending.count > 0
      ? { allow: false, reason: 'pending_recovery_must_resume', pendingRecovery: pending }
      : { allow: true, reason: '', pendingRecovery: pending };
  }

  function buildProtocolRecoveryEvidence(state, payload, attempts) {
    state = state || {};
    payload = payload || {};
    attempts = Array.isArray(attempts) ? attempts : [];
    var pauseCount = Number(state.pendingCollectorProtocolPauseCount || 0);
    if (!Number.isInteger(pauseCount) || pauseCount < 0) pauseCount = 0;
    var staleRunIds = uniqueTextList(state.pendingCollectorProtocolStaleRunIds);
    var protocol = payload.deadlineProtocol || {};
    var payloadRunId = oneLine(payload.runId || '');
    var protocolRunId = oneLine(protocol.runId || '');
    var attemptRunId = '';
    for (var i = attempts.length - 1; i >= 0; i -= 1) {
      var candidateAttempt = attempts[i] || {};
      if (candidateAttempt.payloadAccepted === true && candidateAttempt.outcome === 'payload') {
        attemptRunId = oneLine(candidateAttempt.collectorRunId || '');
        break;
      }
    }
    var freshRunId = protocolRunId || payloadRunId || attemptRunId;
    var runIdentityConsistent = pauseCount === 0 || Boolean(
      payloadRunId
      && protocolRunId
      && attemptRunId
      && payloadRunId === protocolRunId
      && protocolRunId === attemptRunId
    );
    var freshRunIdVerified = pauseCount === 0
      ? true
      : Boolean(staleRunIds.length > 0 && runIdentityConsistent && staleRunIds.indexOf(freshRunId) < 0);
    return {
      schemaVersion: 'collectorProtocolRecoveryEvidence/v1',
      pauseCount: pauseCount,
      pauseReasons: uniqueTextList(state.pendingCollectorProtocolPauseReasons),
      staleRunIds: staleRunIds,
      freshRunId: freshRunId,
      payloadRunId: payloadRunId,
      protocolRunId: protocolRunId,
      attemptRunId: attemptRunId,
      runIdentityConsistent: runIdentityConsistent,
      freshRunIdVerified: freshRunIdVerified,
      quarantinedAttempts: collectorEvidenceSnapshot(state.pendingCollectorProtocolAttemptEvidence || []),
      pendingRecoveryState: pauseCount === 0 ? 'not_applicable' : (freshRunIdVerified ? 'recovered' : 'invalid'),
      recovered: pauseCount > 0 && freshRunIdVerified
    };
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
      'pendingPauseRecoveryMs',
      'pendingCollectorProtocolPauseCount',
      'pendingCollectorProtocolPauseReasons',
      'pendingCollectorProtocolStaleRunIds',
      'pendingCollectorProtocolAttemptEvidence'
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

  function protocolNumber(value) {
    if (value === null || value === undefined || value === '') return null;
    var number = Number(value);
    return Number.isFinite(number) && number >= 0 ? number : null;
  }

  function collectorProtocolCompatibility(snapshot) {
    snapshot = snapshot || {};
    if (snapshot.p2Enabled !== '1') {
      return { ok: false, reason: 'collector_p2_flag_mismatch' };
    }
    if (snapshot.collectorVersion !== COLLECTOR_DEADLINE_VERSION) {
      return { ok: false, reason: 'collector_version_mismatch' };
    }
    if (snapshot.protocolVersion !== COLLECTOR_DEADLINE_PROTOCOL_VERSION) {
      return { ok: false, reason: 'collector_protocol_version_mismatch' };
    }
    if (snapshot.protocolName !== COLLECTOR_DEADLINE_PROTOCOL_NAME) {
      return { ok: false, reason: 'collector_protocol_name_mismatch' };
    }
    if (snapshot.deadlineOwner !== COLLECTOR_DEADLINE_OWNER) {
      return { ok: false, reason: 'collector_deadline_owner_mismatch' };
    }
    return { ok: true, reason: '' };
  }

  function matchingCollectorProtocolResult(snapshot, payload, expectedRunId) {
    snapshot = snapshot || {};
    payload = payload || {};
    var protocol = payload.deadlineProtocol || {};
    var snapshotAcceptedAtMs = protocolNumber(snapshot.acceptedAtMs);
    var snapshotLastObservedAtMs = protocolNumber(snapshot.lastObservedAtMs);
    var protocolAcceptedAtMs = protocolNumber(protocol.acceptedAtMs);
    var protocolLastObservedAtMs = protocolNumber(protocol.lastObservedAtMs);
    return Boolean(
      expectedRunId
      && snapshot.runId === expectedRunId
      && snapshot.deadlineRunId === expectedRunId
      && snapshot.resultReady === '1'
      && snapshot.resultRunId === expectedRunId
      && snapshot.phase === 'result_ready'
      && snapshot.resultReadyAtMs !== null
      && payload.runId === expectedRunId
      && payload.collectorVersion === COLLECTOR_DEADLINE_VERSION
      && protocol.runId === expectedRunId
      && protocol.protocolName === COLLECTOR_DEADLINE_PROTOCOL_NAME
      && String(protocol.protocolVersion || '') === COLLECTOR_DEADLINE_PROTOCOL_VERSION
      && protocol.deadlineOwner === COLLECTOR_DEADLINE_OWNER
      && protocol.phase === 'result_ready'
      && protocolNumber(protocol.resultReadyAtMs) !== null
      && snapshotAcceptedAtMs !== null
      && snapshotLastObservedAtMs !== null
      && protocolAcceptedAtMs === snapshotAcceptedAtMs
      && protocolLastObservedAtMs === snapshotLastObservedAtMs
      && protocolLastObservedAtMs >= protocolAcceptedAtMs
      && !oneLine(protocol.clockAnomalyKind || '')
      && (protocol.clockAnomalyObservedAtMs === null || protocol.clockAnomalyObservedAtMs === undefined)
      && !oneLine(snapshot.clockAnomalyKind || '')
      && (snapshot.clockAnomalyObservedAtMs === null || snapshot.clockAnomalyObservedAtMs === undefined)
    );
  }

  function collectorClockAnomalyReason(snapshot, nowMs) {
    snapshot = snapshot || {};
    if (oneLine(snapshot.clockAnomalyKind || '') === 'wall_clock_backward'
      || (snapshot.clockAnomalyObservedAtMs !== null && snapshot.clockAnomalyObservedAtMs !== undefined)) {
      return 'wall_clock_backward';
    }
    var now = protocolNumber(nowMs);
    var accepted = protocolNumber(snapshot.acceptedAtMs);
    var phaseStarted = protocolNumber(snapshot.phaseStartAtMs);
    var heartbeat = protocolNumber(snapshot.heartbeatAtMs);
    var lastObserved = protocolNumber(snapshot.lastObservedAtMs);
    if (lastObserved !== null && accepted !== null && lastObserved < accepted) return 'wall_clock_backward';
    if (now !== null && [accepted, phaseStarted, heartbeat, lastObserved].some(function (value) {
      return value !== null && now < value;
    })) return 'wall_clock_backward';
    return '';
  }

  function classifyCollectorWatchdog(snapshot, nowMs, visibilityState) {
    snapshot = snapshot || {};
    var clockAnomaly = collectorClockAnomalyReason(snapshot, nowMs);
    if (clockAnomaly) return clockAnomaly;
    var now = protocolNumber(nowMs);
    var heartbeat = protocolNumber(snapshot.heartbeatAtMs);
    var currentVisibility = oneLine(visibilityState || 'unknown');
    var snapshotVisibility = oneLine(snapshot.visibilityState || 'unknown');
    if (snapshot.hiddenObservedAtMs !== null && snapshot.hiddenObservedAtMs !== undefined) return 'page_hidden_or_throttled';
    if (currentVisibility !== 'visible' || snapshotVisibility !== 'visible') return 'page_hidden_or_throttled';
    if (heartbeat === null) return 'collector_heartbeat_missing';
    if (now !== null && now - heartbeat > COLLECTOR_HEARTBEAT_STALE_MS) return 'collector_heartbeat_stale';
    if (snapshot.phase === 'tooltip_scan') return 'tooltip_scan_watchdog_exceeded_active';
    if (snapshot.phase === 'chart_wait') return 'chart_deadline_unresolved_active';
    return 'collector_phase_deadline_exceeded_active';
  }

  function collectorProtocolPreflightDecision(snapshot) {
    var compatibility = collectorProtocolCompatibility(snapshot);
    if (!compatibility.ok) return { action: 'pause', reason: compatibility.reason };
    if ((snapshot || {}).running === '1') return { action: 'pause', reason: 'collector_already_running' };
    return { action: 'click', reason: '' };
  }

  function collectorProtocolAcceptanceDecision(before, accepted, nowMs) {
    before = before || {};
    accepted = accepted || {};
    var compatibility = collectorProtocolCompatibility(accepted);
    if (!compatibility.ok) return { action: 'pause', reason: compatibility.reason };
    if (!accepted.runId || accepted.runId === before.runId) {
      return { action: 'pause', reason: 'collector_run_id_not_advanced' };
    }
    if (accepted.deadlineRunId !== accepted.runId) {
      return { action: 'pause', reason: 'collector_deadline_run_id_mismatch' };
    }
    if (accepted.running !== '1' || accepted.resultReady !== '0') {
      return { action: 'pause', reason: 'collector_run_not_synchronously_accepted' };
    }
    if (!accepted.phase || accepted.phaseDeadlineAtMs === null || accepted.acceptedAtMs === null) {
      return { action: 'pause', reason: 'collector_deadline_metadata_missing' };
    }
    var acceptanceObservedAtMs = protocolNumber(nowMs);
    if (acceptanceObservedAtMs === null) acceptanceObservedAtMs = protocolNumber(accepted.lastObservedAtMs);
    if (accepted.lastObservedAtMs === null || collectorClockAnomalyReason(accepted, acceptanceObservedAtMs)) {
      return { action: 'pause', reason: 'watchdog_wall_clock_backward' };
    }
    return { action: 'accepted', reason: '', runId: accepted.runId };
  }

  function collectorProtocolPollDecision(snapshot, payload, expectedRunId, nowMs, visibilityState) {
    snapshot = snapshot || {};
    var compatibility = collectorProtocolCompatibility(snapshot);
    if (!compatibility.ok) {
      return { action: 'pause', reason: compatibility.reason, watchdogClassification: '' };
    }
    if (snapshot.runId !== expectedRunId || snapshot.deadlineRunId !== expectedRunId) {
      return { action: 'pause', reason: 'collector_run_id_changed', watchdogClassification: '' };
    }
    var clockAnomaly = collectorClockAnomalyReason(snapshot, nowMs);
    if (clockAnomaly) {
      return { action: 'pause', reason: 'watchdog_' + clockAnomaly, watchdogClassification: clockAnomaly };
    }
    var currentVisibility = oneLine(visibilityState || 'unknown');
    var snapshotVisibility = oneLine(snapshot.visibilityState || 'unknown');
    if (snapshot.hiddenObservedAtMs !== null && snapshot.hiddenObservedAtMs !== undefined
      || currentVisibility !== 'visible'
      || snapshotVisibility !== 'visible') {
      return { action: 'pause', reason: 'watchdog_page_hidden_or_throttled', watchdogClassification: 'page_hidden_or_throttled' };
    }
    if (snapshot.resultReady === '1') {
      return matchingCollectorProtocolResult(snapshot, payload, expectedRunId)
        ? { action: 'payload', reason: '', watchdogClassification: '' }
        : { action: 'pause', reason: 'collector_result_identity_mismatch', watchdogClassification: '' };
    }
    if (snapshot.running !== '1') {
      return { action: 'pause', reason: 'collector_stopped_without_result', watchdogClassification: '' };
    }
    if (snapshot.phaseDeadlineAtMs === null) {
      return { action: 'pause', reason: 'collector_phase_deadline_missing', watchdogClassification: '' };
    }
    var graceMs = snapshot.phase === 'chart_wait' ? COLLECTOR_DEADLINE_GRACE_MS : 0;
    if (Number(nowMs) > snapshot.phaseDeadlineAtMs + graceMs) {
      var classification = classifyCollectorWatchdog(snapshot, nowMs, visibilityState);
      return { action: 'pause', reason: 'watchdog_' + classification, watchdogClassification: classification };
    }
    return { action: 'wait', reason: '', watchdogClassification: '' };
  }

  function collectorEvidenceSnapshot(payload) {
    try {
      return JSON.parse(JSON.stringify(payload || {}));
    } catch (error) {
      return {
        captureError: oneLine(error && error.message ? error.message : error),
        status: oneLine((payload || {}).status || ''),
        decision: oneLine((payload || {}).decision || '')
      };
    }
  }

  function collectorAttemptEvidence(payload, error, attempt) {
    return {
      schemaVersion: 'collectorAttemptEvidence/v1',
      outcome: error ? 'error' : 'payload',
      payload: payload ? collectorEvidenceSnapshot(payload) : null,
      error: error ? oneLine(error && error.message ? error.message : error) : '',
      errorCode: error ? oneLine(error.code || '') : '',
      attemptSnapshot: collectorEvidenceSnapshot(attempt || {})
    };
  }

  function collectorValidationIdentity(runnerP2Enabled, attempts) {
    attempts = Array.isArray(attempts) ? attempts : [];
    var observed = null;
    for (var i = attempts.length - 1; i >= 0; i -= 1) {
      var candidate = attempts[i] || {};
      if (candidate.collectorVersion || candidate.collectorP2Enabled !== '' || candidate.protocolVersion || candidate.protocolName || candidate.deadlineOwner) {
        observed = candidate;
        break;
      }
    }
    observed = observed || {};
    var collectorP2Enabled = observed.collectorP2Enabled === '1'
      ? true
      : (observed.collectorP2Enabled === '0' ? false : null);
    return {
      runnerP2Enabled: Boolean(runnerP2Enabled),
      collectorVersion: oneLine(observed.collectorVersion || ''),
      collectorP2Enabled: collectorP2Enabled,
      protocolName: oneLine(observed.protocolName || ''),
      protocolVersion: oneLine(observed.protocolVersion || ''),
      deadlineOwner: oneLine(observed.deadlineOwner || ''),
      attemptCount: attempts.length,
      complete: Boolean(
        observed.collectorVersion
        && collectorP2Enabled !== null
        && observed.protocolName
        && observed.protocolVersion
        && observed.deadlineOwner
      )
    };
  }

  function strictHistorySnapshot(history) {
    var asins = Object.keys((history || {}).asins || {}).map(normalizeAsin).filter(Boolean).sort();
    return {
      schemaVersion: 'strictQualifiedHistorySnapshot/v1',
      sourceSchemaVersion: oneLine((history || {}).schemaVersion || ''),
      asins: asins
    };
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
    pendingRecoverySummary: pendingRecoverySummary,
    batchFinishDecision: batchFinishDecision,
    buildProtocolRecoveryEvidence: buildProtocolRecoveryEvidence,
    gateLogColumns: GATE_LOG_COLUMNS.slice(),
    timingLogColumns: TIMING_LOG_COLUMNS.slice(),
    granularTimingColumns: GRANULAR_TIMING_COLUMNS.slice(),
    controlEventColumns: CONTROL_EVENT_COLUMNS.slice(),
    telemetryEnabled: ENABLE_TIER0_TELEMETRY,
    granularTelemetryEnabled: ENABLE_TIER0_GRANULAR_TELEMETRY,
    cumulativeTargetControlEnabled: ENABLE_P1_CUMULATIVE_TARGET_CONTROL,
    tier22ConditionalRetryEnabled: ENABLE_TIER2_2_CONDITIONAL_RETRY,
    collectorDeadlineProtocolEnabled: ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL,
    collectorDeadlineProtocolName: COLLECTOR_DEADLINE_PROTOCOL_NAME,
    collectorDeadlineProtocolVersion: COLLECTOR_DEADLINE_PROTOCOL_VERSION,
    collectorProtocolCompatibility: collectorProtocolCompatibility,
    matchingCollectorProtocolResult: matchingCollectorProtocolResult,
    collectorClockAnomalyReason: collectorClockAnomalyReason,
    classifyCollectorWatchdog: classifyCollectorWatchdog,
    collectorProtocolPreflightDecision: collectorProtocolPreflightDecision,
    collectorProtocolAcceptanceDecision: collectorProtocolAcceptanceDecision,
    collectorProtocolPollDecision: collectorProtocolPollDecision,
    collectorEvidenceSnapshot: collectorEvidenceSnapshot,
    collectorAttemptEvidence: collectorAttemptEvidence,
    collectorValidationIdentity: collectorValidationIdentity,
    strictHistorySnapshot: strictHistorySnapshot,
    historyIsolationSnapshot: historyIsolationSnapshot,
    p2PairSandboxHistoryEnabled: ENABLE_P2_PAIR_SANDBOX_HISTORY,
    productionStrictHistoryKey: PRODUCTION_STRICT_HISTORY_KEY,
    p2SandboxHistoryKey: P2_SANDBOX_HISTORY_KEY,
    tier2RetryVersion: TIER2_RETRY_VERSION,
    granularTelemetryVersion: GRANULAR_TELEMETRY_VERSION,
    targetControlVersion: TARGET_CONTROL_VERSION,
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

  function collectorProtocolSnapshot(panel) {
    function attr(name) {
      return panel ? panel.getAttribute(name) || '' : '';
    }
    return {
      collectorVersion: attr('data-ss-collector-version'),
      p2Enabled: attr('data-ss-p2-deadline-enabled'),
      protocolVersion: attr('data-ss-protocol-version'),
      protocolName: attr('data-ss-protocol-name') || attr('data-ss-deadline-protocol-version'),
      deadlineOwner: attr('data-ss-deadline-owner'),
      runId: attr('data-ss-run-id'),
      deadlineRunId: attr('data-ss-deadline-run-id'),
      resultRunId: attr('data-ss-result-run-id'),
      resultReady: attr('data-ss-result-ready'),
      running: attr('data-ss-running'),
      phase: attr('data-ss-deadline-phase'),
      acceptedAtMs: protocolNumber(attr('data-ss-deadline-accepted-at-ms')),
      phaseStartAtMs: protocolNumber(attr('data-ss-deadline-phase-started-at-ms')),
      phaseDeadlineAtMs: protocolNumber(attr('data-ss-deadline-at-ms')),
      chartDeadlineAtMs: protocolNumber(attr('data-ss-deadline-chart-ready-deadline-at-ms')),
      chartReadyAtMs: protocolNumber(attr('data-ss-deadline-chart-ready-at-ms')),
      resultReadyAtMs: protocolNumber(attr('data-ss-deadline-result-ready-at-ms')),
      heartbeatAtMs: protocolNumber(attr('data-ss-deadline-heartbeat-at-ms')),
      lastObservedAtMs: protocolNumber(attr('data-ss-deadline-last-observed-at-ms')),
      clockAnomalyKind: attr('data-ss-clock-anomaly-kind'),
      clockAnomalyObservedAtMs: protocolNumber(attr('data-ss-clock-anomaly-observed-at-ms')),
      terminalReason: attr('data-ss-deadline-terminal-reason'),
      deadlineOverrunMs: protocolNumber(attr('data-ss-deadline-exceeded-by-ms')),
      visibilityState: attr('data-ss-visibility-state'),
      hiddenObservedAtMs: protocolNumber(attr('data-ss-hidden-observed-at-ms'))
    };
  }

  function collectorProtocolPause(reason, snapshot) {
    var error = new Error('Collector deadline protocol paused: ' + reason);
    error.code = 'collector_protocol_pause';
    error.protocolReason = reason;
    error.protocolSnapshot = snapshot || {};
    return error;
  }

  function applyProtocolSnapshotToAttempt(attempt, snapshot) {
    snapshot = snapshot || {};
    attempt.collectorVersion = snapshot.collectorVersion || attempt.collectorVersion || '';
    attempt.collectorP2Enabled = snapshot.p2Enabled || attempt.collectorP2Enabled || '';
    attempt.protocolName = snapshot.protocolName || attempt.protocolName || '';
    attempt.protocolVersion = snapshot.protocolVersion || attempt.protocolVersion || '';
    attempt.deadlineOwner = snapshot.deadlineOwner || attempt.deadlineOwner || '';
    attempt.collectorRunId = snapshot.runId || attempt.collectorRunId || '';
    attempt.resultRunId = snapshot.resultRunId || attempt.resultRunId || '';
    attempt.resultReadyAttr = snapshot.resultReady || attempt.resultReadyAttr || '';
    attempt.runningAttr = snapshot.running || attempt.runningAttr || '';
    attempt.phase = snapshot.phase || attempt.phase || '';
    attempt.acceptedAtMs = snapshot.acceptedAtMs !== null ? snapshot.acceptedAtMs : attempt.acceptedAtMs;
    attempt.phaseStartAtMs = snapshot.phaseStartAtMs !== null ? snapshot.phaseStartAtMs : attempt.phaseStartAtMs;
    attempt.phaseDeadlineAtMs = snapshot.phaseDeadlineAtMs !== null ? snapshot.phaseDeadlineAtMs : attempt.phaseDeadlineAtMs;
    attempt.chartDeadlineAtMs = snapshot.chartDeadlineAtMs !== null ? snapshot.chartDeadlineAtMs : attempt.chartDeadlineAtMs;
    attempt.chartReadyAtMs = snapshot.chartReadyAtMs !== null ? snapshot.chartReadyAtMs : attempt.chartReadyAtMs;
    attempt.resultReadyAtMs = snapshot.resultReadyAtMs !== null ? snapshot.resultReadyAtMs : attempt.resultReadyAtMs;
    attempt.heartbeatAtMs = snapshot.heartbeatAtMs !== null ? snapshot.heartbeatAtMs : attempt.heartbeatAtMs;
    attempt.lastObservedAtMs = snapshot.lastObservedAtMs !== null ? snapshot.lastObservedAtMs : attempt.lastObservedAtMs;
    attempt.clockAnomalyKind = snapshot.clockAnomalyKind || attempt.clockAnomalyKind || '';
    attempt.clockAnomalyObservedAtMs = snapshot.clockAnomalyObservedAtMs !== null
      ? snapshot.clockAnomalyObservedAtMs
      : attempt.clockAnomalyObservedAtMs;
    attempt.terminalReason = snapshot.terminalReason || attempt.terminalReason || '';
    attempt.deadlineOverrunMs = snapshot.deadlineOverrunMs !== null ? snapshot.deadlineOverrunMs : attempt.deadlineOverrunMs;
    attempt.visibilityState = snapshot.visibilityState || attempt.visibilityState || '';
    attempt.hiddenObservedAtMs = snapshot.hiddenObservedAtMs !== null ? snapshot.hiddenObservedAtMs : attempt.hiddenObservedAtMs;
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
        trafficTabClickAtMs: null,
        trafficTabClickFound: null,
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
        trafficTabClickAtMs: sellerSprite.trafficTabClickAtMs,
        trafficTabClickFound: sellerSprite.trafficTabClickFound,
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

  function cloneJson(value) {
    try {
      return JSON.parse(JSON.stringify(value));
    } catch (error) {
      return null;
    }
  }

  function strictHistoryIsValid(history) {
    if (!history || typeof history !== 'object' || Array.isArray(history)) return false;
    if (history.schemaVersion !== 'strictQualifiedHistory/v1') return false;
    if (!history.asins || typeof history.asins !== 'object' || Array.isArray(history.asins)) return false;
    return Object.keys(history.asins).every(function (asin) {
      return normalizeAsin(asin) === asin;
    });
  }

  function getProductionStrictHistory() {
    var history = readJson(PRODUCTION_STRICT_HISTORY_KEY, null);
    if (!strictHistoryIsValid(history)) {
      throw new Error('p2_pair_production_history_missing_or_invalid');
    }
    return history;
  }

  function writeStrictHistory(history) {
    if (ENABLE_P2_PAIR_SANDBOX_HISTORY && STRICT_HISTORY_KEY === PRODUCTION_STRICT_HISTORY_KEY) {
      throw new Error('p2_pair_production_history_write_blocked');
    }
    return writeJson(STRICT_HISTORY_KEY, history);
  }

  function historyIsolationSnapshot(productionHistory, sandboxHistory) {
    return {
      schemaVersion: 'p2PairHistoryIsolation/v1',
      version: P2_SANDBOX_HISTORY_VERSION,
      mode: ENABLE_P2_PAIR_SANDBOX_HISTORY ? 'sandbox' : 'production',
      p2Side: P2_SANDBOX_HISTORY_SIDE,
      productionWriteProtected: ENABLE_P2_PAIR_SANDBOX_HISTORY,
      productionKey: PRODUCTION_STRICT_HISTORY_KEY,
      activeSandboxKey: ENABLE_P2_PAIR_SANDBOX_HISTORY ? P2_SANDBOX_HISTORY_KEY : '',
      productionSnapshot: strictHistorySnapshot(productionHistory),
      sandboxSeedSnapshot: strictHistorySnapshot(sandboxHistory)
    };
  }

  function seedP2SandboxHistory() {
    var production = getProductionStrictHistory();
    var sandbox = cloneJson(production);
    if (!strictHistoryIsValid(sandbox)) throw new Error('p2_pair_sandbox_history_clone_failed');
    sandbox.p2Sandbox = {
      schemaVersion: P2_SANDBOX_HISTORY_VERSION,
      side: P2_SANDBOX_HISTORY_SIDE,
      seededFrom: PRODUCTION_STRICT_HISTORY_KEY,
      seededAt: new Date().toISOString()
    };
    writeJson(P2_SANDBOX_HISTORY_KEY, sandbox);
    return { production: production, sandbox: sandbox };
  }

  function prepareP2SandboxHistoryForGenerate() {
    if (!ENABLE_P2_PAIR_SANDBOX_HISTORY) {
      var production = getStrictHistory();
      return { production: production, sandbox: production };
    }
    return seedP2SandboxHistory();
  }

  function getStrictHistory() {
    if (ENABLE_P2_PAIR_SANDBOX_HISTORY) {
      var sandbox = readJson(P2_SANDBOX_HISTORY_KEY, null);
      if (strictHistoryIsValid(sandbox)) return sandbox;
      return seedP2SandboxHistory().sandbox;
    }
    var history = readJson(PRODUCTION_STRICT_HISTORY_KEY, null);
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
      writeStrictHistory(history);
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
    writeStrictHistory(history);
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
    var stateWrite = writeJson(stateKey(state.queueHash), state);
    var index = getBatchIndex().filter(function (item) { return item.queueHash !== state.queueHash; });
    index.unshift({ queueHash: state.queueHash, batchName: state.batchName, createdAt: state.createdAt });
    var indexWrite = writeJson(INDEX_KEY, index.slice(0, 30));
    var selectedWriteStartedAtMs = Date.now();
    localStorage.setItem(SELECTED_KEY, state.queueHash);
    var selectedWriteMs = Date.now() - selectedWriteStartedAtMs;
    var persistenceMeasurement = {
      serializeMs: stateWrite.serializeMs + indexWrite.serializeMs,
      storageWriteMs: stateWrite.storageWriteMs + indexWrite.storageWriteMs + selectedWriteMs,
      totalMs: stateWrite.totalMs + indexWrite.totalMs + selectedWriteMs
    };
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
    var pendingRecovery = pendingRecoverySummary(state);
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
      pendingCollectorProtocolPauseCount: Number(state.pendingCollectorProtocolPauseCount || 0),
      pendingCollectorProtocolPauseReasons: state.pendingCollectorProtocolPauseReasons || [],
      pendingCollectorProtocolStaleRunIds: state.pendingCollectorProtocolStaleRunIds || [],
      pendingCollectorProtocolAttemptEvidence: state.pendingCollectorProtocolAttemptEvidence || [],
      pendingRecovery: pendingRecovery,
      qualifiedCount: state.qualifiedCount,
      rejectedCount: state.rejectedCount,
      historySkippedAsins: state.historySkippedAsins || [],
      historySkippedCount: (state.historySkippedAsins || []).length,
      historyRegistryCount: state.historyRegistryCount || 0,
      historySnapshotAtGeneration: state.historySnapshotAtGeneration || null,
      historyIsolation: state.historyIsolation || null,
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
    var granularButtons = ENABLE_TIER0_GRANULAR_TELEMETRY
      ? '<button id="ss-v3-copy-granular-json">Copy granular JSON</button>' +
        '<button id="ss-v3-copy-granular-tsv">Copy granular TSV</button>' +
        '<button id="ss-v3-copy-control-tsv">Copy control TSV</button>'
      : '';
    var targetControlFields = ENABLE_P1_CUMULATIVE_TARGET_CONTROL
      ? '<label>remainingTargetAtStart (offline replay snapshot, optional)</label><input id="ss-v3-remaining" type="number" min="0" placeholder="blank = legacy batch target">'
      : '';
    var stopRowButton = ENABLE_P1_CUMULATIVE_TARGET_CONTROL
      ? '<button id="ss-v3-stop-row">Stop after current row</button>'
      : '';
    panel.innerHTML = [
      '<h3>SellerSprite Integrated Runner ' + VERSION + ' P2 OFF <button id="ss-v3-toggle">收起</button></h3>',
      '<div class="ss-v3-body">',
      '<label>Local batches</label><select id="ss-v3-picker"></select>',
       '<label>batchName</label><input id="ss-v3-name" value="strict20-integrated-' + new Date().toISOString().slice(0, 10) + '">',
       '<label>operator</label><input id="ss-v3-operator" value="liyuanze">',
       '<label>targetQualified (final target)</label><input id="ss-v3-target" type="number" min="1" value="20">',
       targetControlFields,
       '<label>QUEUE input</label><textarea id="ss-v3-queue" placeholder="One ASIN per line"></textarea>',
      '<button id="ss-v3-generate">Generate</button><span id="ss-v3-message"></span><br>',
      '<button class="ss-v3-primary" id="ss-v3-start">Start</button>',
       '<button id="ss-v3-pause">Pause</button>',
       '<button id="ss-v3-resume">Resume</button>',
       stopRowButton,
      '<button id="ss-v3-copy">Copy combined JSON</button>',
      '<button id="ss-v3-copy-enrichment">Copy enrichment JSON</button>',
      '<button id="ss-v3-copy-history">Copy active sandbox history JSON</button>' +
      '<button id="ss-v3-copy-production-history">Copy production history JSON</button>',
       telemetryButtons,
       granularButtons,
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
    if (ENABLE_P1_CUMULATIVE_TARGET_CONTROL) {
      panel.querySelector('#ss-v3-stop-row').addEventListener('click', stopAfterCurrentRowSelectedBatch);
    }
    panel.querySelector('#ss-v3-copy').addEventListener('click', function () { copySelected(false); });
    panel.querySelector('#ss-v3-copy-enrichment').addEventListener('click', function () { copySelected(true); });
    panel.querySelector('#ss-v3-copy-history').addEventListener('click', function () {
      copyText(JSON.stringify(getStrictHistory(), null, 2));
      setPanelMessage('Active sandbox history JSON copied. Production history is read-only.');
    });
    panel.querySelector('#ss-v3-copy-production-history').addEventListener('click', function () {
      try {
        copyText(JSON.stringify(getProductionStrictHistory(), null, 2));
        setPanelMessage('Production history JSON copied read-only for external audit.');
      } catch (error) {
        setPanelMessage('Production history is missing or invalid; batch remains fail-closed.');
      }
    });
    if (ENABLE_TIER0_TELEMETRY) {
      panel.querySelector('#ss-v3-copy-gate-tsv').addEventListener('click', function () { copyTelemetry('gate'); });
      panel.querySelector('#ss-v3-copy-timing-tsv').addEventListener('click', function () { copyTelemetry('timing'); });
    }
    if (ENABLE_TIER0_GRANULAR_TELEMETRY) {
      panel.querySelector('#ss-v3-copy-granular-json').addEventListener('click', function () { copyGranularTelemetry('json'); });
      panel.querySelector('#ss-v3-copy-granular-tsv').addEventListener('click', function () { copyGranularTelemetry('timing'); });
      panel.querySelector('#ss-v3-copy-control-tsv').addEventListener('click', function () { copyGranularTelemetry('control'); });
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
    panel.querySelector('#ss-v3-target').value = state.requestedFinalTargetAtStart || state.targetQualified || 20;
    var remainingInput = panel.querySelector('#ss-v3-remaining');
    if (remainingInput) remainingInput.value = state.remainingTargetAtStart == null ? '' : state.remainingTargetAtStart;
    panel.querySelector('#ss-v3-queue').value = state.queue.join('\n');
    var summary = summarizeResults(state.results);
    var targetControl = normalizeTargetControl(state);
    panel.querySelector('#ss-v3-status').textContent = [
      'Batch: ' + state.batchName,
      'Queue hash: ' + state.queueHash,
      'Status: ' + state.status,
      'Progress: ' + summary.completed + '/' + state.queue.length,
      'Final target: ' + (state.targetQualified || 20),
      'Target control: ' + targetControl.mode + ' / effective stop ' + (targetControl.valid ? targetControl.effectiveStopBudget : 'INVALID'),
      'Remaining at start: ' + (state.remainingTargetAtStart == null ? 'n/a' : state.remainingTargetAtStart),
      'Browser passes this batch: ' + summary.qualified + '/' + (targetControl.valid ? targetControl.effectiveStopBudget : 'INVALID'),
      'Rejected: ' + summary.rejected,
      'Pending recovery: ' + pendingRecoverySummary(state).state + ' (' + pendingRecoverySummary(state).count + ')',
      'History auto-skipped: ' + (state.historySkippedAsins || []).length,
      'Local strict-qualified history: ' + historyCount,
      'History isolation: ' + (state.historyIsolation ? state.historyIsolation.mode + '/' + state.historyIsolation.p2Side : 'not_generated'),
      'Current row: ' + (state.currentIndex + 1),
      'Current ASIN: ' + (state.queue[state.currentIndex] || ''),
      'Step: ' + (state.currentStep || 'idle'),
      'Stop-after-row requested: ' + (state.stopAfterCurrentRowRequested ? 'yes' : 'no'),
      'Message: ' + (state.message || '')
    ].join('\n');
    var panelJsonStartedAtMs = Date.now();
    panel.querySelector('#ss-v3-output').value = JSON.stringify(exportBatch(state), null, 2);
    recordPanelJsonSerialize(Date.now() - panelJsonStartedAtMs);
  }

  function generateBatchFromPanel() {
    var inputQueue = uniqueAsins(document.querySelector('#ss-v3-queue').value);
    if (!inputQueue.length) {
      setPanelMessage('QUEUE 中没有有效 ASIN。');
      return;
    }
    var historyPair = prepareP2SandboxHistoryForGenerate();
    var productionHistory = historyPair.production;
    var history = historyPair.sandbox;
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
      setPanelMessage('remainingTargetAtStart must be a non-negative integer.');
      return;
    }
    if (ENABLE_P1_CUMULATIVE_TARGET_CONTROL && remainingTargetAtStart !== null && remainingTargetAtStart > requestedFinalTargetAtStart) {
      setPanelMessage('remainingTargetAtStart cannot exceed targetQualified.');
      return;
    }
    if (ENABLE_P1_CUMULATIVE_TARGET_CONTROL && remainingTargetAtStart === 0) {
      setPanelMessage('Offline replay already reached the target; no browser batch is generated.');
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
      pendingCollectorProtocolPauseCount: 0,
      pendingCollectorProtocolPauseReasons: [],
      pendingCollectorProtocolStaleRunIds: [],
      pendingCollectorProtocolAttemptEvidence: [],
      qualifiedCount: 0,
      rejectedCount: 0,
      historySkippedAsins: filtered.skipped,
      historyRegistryCount: strictHistoryCount(history),
      historySnapshotAtGeneration: strictHistorySnapshot(history),
      historyIsolation: historyIsolationSnapshot(productionHistory, history),
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
    var finishDecision = batchFinishDecision(state);
    if (!finishDecision.allow) {
      state.status = 'paused';
      state.currentStep = 'traffic';
      state.stoppedReason = '';
      state.stopReason = finishDecision.reason;
      state.message = 'Current row is pending recovery; Resume must finish it before the batch can be done.';
      saveBatch(state);
      return false;
    }
    state.status = 'done';
    state.currentStep = 'done';
    state.stoppedReason = reason;
    state.stopReason = reason;
    state.stopAction = state.stopAction || reason;
    state.message = message;
    saveBatch(state);
    return true;
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
          ? 'Current row saved; operator stop requested.'
          : 'Target control stopped batch: ' + decision.passes + '/' + targetLabel + ' browser passes.'
      );
      finalizeActiveGranular(decision.reason, null);
      return;
    }
    if (index >= state.queue.length) {
      finishBatch(state, 'queue_exhausted', 'Queue exhausted: ' + decision.passes + '/' + (decision.control.effectiveStopBudget || state.targetQualified || 20) + ' browser passes.');
      finalizeActiveGranular('queue_exhausted', null);
      return;
    }
    state.currentIndex = index;
    state.currentStep = 'navigate';
    state.message = 'Opening ' + state.queue[index];
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
    if (state && pendingRecoverySummary(state).count > 0) {
      setPanelMessage('Current row is pending recovery. Use Resume to create a fresh Collector run ID.');
      return;
    }
    if (!state) return setPanelMessage('请先 Generate。');
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
    state.message = 'Pause requested; current row will be saved.';
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
      finishBatch(state, 'operator_stop_after_current_row', 'Stop requested; no row was in flight.');
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
    if (!state) return setPanelMessage('No batch available for telemetry export.');
    var isGate = kind === 'gate';
    var rows = isGate ? gateLogRows(state) : timingLogRows(state);
    var columns = isGate ? GATE_LOG_COLUMNS : TIMING_LOG_COLUMNS;
    var text = rowsToTsv(rows, columns);
    await copyText(text);
    document.querySelector('#ss-v3-output').value = text;
    setPanelMessage((isGate ? 'Gate' : 'Timing') + ' telemetry TSV copied.');
  }

  async function copyGranularTelemetry(kind) {
    var state = loadBatch(selectedHash());
    if (!state) return setPanelMessage('No batch available for granular telemetry export.');
    var sidecar = readJson(granularKey(state.queueHash), null);
    if (!sidecar
        || sidecar.schemaVersion !== GRANULAR_TELEMETRY_SCHEMA_VERSION
        || sidecar.queueHash !== state.queueHash
        || (sidecar.batchCreatedAt || '') !== (state.createdAt || '')) {
      return setPanelMessage('Granular telemetry sidecar missing; no values were inferred.');
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
    setPanelMessage('Granular ' + kind + ' telemetry copied.');
  }

  function clearSelectedBatch() {
    var hash = selectedHash();
    if (!hash) return;
    if (!window.confirm('Clear selected Integrated Runner batch?')) return;
    localStorage.removeItem(stateKey(hash));
    clearGranularSidecar(hash);
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

  async function runCollectorOnce(granularRow, attemptNumber) {
    var attempt = {
      attempt: attemptNumber,
      handshakeMode: ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL ? COLLECTOR_DEADLINE_PROTOCOL_NAME : 'status_text_v1_observed',
      buttonWaitStartedAtMs: Date.now(),
      buttonObservedAtMs: null,
      trafficTabClickAtMs: null,
      trafficTabClickFound: null,
      chartWaitStartedAtMs: null,
      chartReadyAtMs: null,
      collectorClickAtMs: null,
      collectingObservedAtMs: null,
      completedObservedAtMs: null,
      jsonParsedAtMs: null,
      collectorRunId: '',
      collectorVersion: '',
      collectorP2Enabled: '',
      resultRunId: '',
      resultReadyAttr: '',
      runningAttr: '',
      startAckMs: null,
      resultWaitMs: null,
      totalObservedMs: null,
      collectorInternalChartWaitMs: null,
      collectorTooltipScanMs: null,
      collectorInternalTotalMs: null,
      protocolName: '',
      protocolVersion: '',
      deadlineOwner: '',
      acceptedAtMs: null,
      phase: '',
      phaseStartAtMs: null,
      phaseDeadlineAtMs: null,
      chartDeadlineAtMs: null,
      resultReadyAtMs: null,
      heartbeatAtMs: null,
      lastObservedAtMs: null,
      clockAnomalyKind: '',
      clockAnomalyObservedAtMs: null,
      terminalReason: '',
      deadlineOverrunMs: null,
      visibilityState: '',
      hiddenObservedAtMs: null,
      watchdogClassification: '',
      observedPayloadEvidence: null,
      payloadAccepted: false,
      payloadQuarantined: false,
      payloadStatus: '',
      outcome: '',
      reason: ''
    };
    try {
      await waitFor(function () { return document.querySelector('#ss-collector-run'); }, 18000, 250);
      attempt.buttonObservedAtMs = Date.now();
      var button = document.querySelector('#ss-collector-run');
      var status = document.querySelector('#ss-collector-status');
      var output = document.querySelector('#ss-collector-json');
      var collectorPanel = document.querySelector('#ss-collector-panel');
      var initialSnapshot = collectorProtocolSnapshot(collectorPanel);
      applyProtocolSnapshotToAttempt(attempt, initialSnapshot);

      if (!ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL) {
        attempt.trafficTabClickAtMs = Date.now();
        attempt.trafficTabClickFound = clickExactText('流量洞察');
        attempt.chartWaitStartedAtMs = Date.now();
        await waitFor(function () {
          var box = document.querySelector('.echarts-trends-box');
          return box && visible(box) ? box : null;
        }, 15000, 250);
        attempt.chartReadyAtMs = Date.now();
        attempt.collectorClickAtMs = Date.now();
        button.click();
        await waitFor(function () { return status && /Collecting/i.test(status.textContent || ''); }, 5000, 100);
        attempt.collectingObservedAtMs = Date.now();
        await waitFor(function () { return status && !/Collecting/i.test(status.textContent || ''); }, 45000, 250);
        attempt.completedObservedAtMs = Date.now();
        var legacyPayload = JSON.parse(output.value || '{}');
        attempt.observedPayloadEvidence = collectorEvidenceSnapshot(legacyPayload);
        attempt.jsonParsedAtMs = Date.now();
        attempt.collectorRunId = collectorPanel ? collectorPanel.getAttribute('data-ss-run-id') || '' : '';
        attempt.resultRunId = collectorPanel ? collectorPanel.getAttribute('data-ss-result-run-id') || '' : '';
        attempt.resultReadyAttr = collectorPanel ? collectorPanel.getAttribute('data-ss-result-ready') || '' : '';
        attempt.runningAttr = collectorPanel ? collectorPanel.getAttribute('data-ss-running') || '' : '';
        attempt.startAckMs = attempt.collectingObservedAtMs - attempt.collectorClickAtMs;
        attempt.resultWaitMs = attempt.completedObservedAtMs - attempt.collectingObservedAtMs;
        attempt.totalObservedMs = attempt.jsonParsedAtMs - attempt.collectorClickAtMs;
        var legacyInternal = legacyPayload && legacyPayload.telemetry && legacyPayload.telemetry.timing ? legacyPayload.telemetry.timing : {};
        attempt.collectorInternalChartWaitMs = Number.isFinite(Number(legacyInternal.chartWaitMs)) ? Number(legacyInternal.chartWaitMs) : null;
        attempt.collectorTooltipScanMs = Number.isFinite(Number(legacyInternal.tooltipScanMs)) ? Number(legacyInternal.tooltipScanMs) : null;
        attempt.collectorInternalTotalMs = Number.isFinite(Number(legacyInternal.totalMs)) ? Number(legacyInternal.totalMs) : null;
        attempt.payloadStatus = legacyPayload.status || '';
        attempt.payloadAccepted = true;
        attempt.outcome = 'payload';
        return legacyPayload;
      }

      var before = initialSnapshot;
      var preflight = collectorProtocolPreflightDecision(before);
      if (preflight.action === 'pause') throw collectorProtocolPause(preflight.reason, before);

      attempt.trafficTabClickAtMs = Date.now();
      attempt.trafficTabClickFound = clickExactText('流量洞察');
      attempt.chartWaitStartedAtMs = Date.now();
      var observedChart = document.querySelector('.echarts-trends-box');
      if (observedChart && visible(observedChart)) attempt.chartReadyAtMs = Date.now();

      attempt.collectorClickAtMs = Date.now();
      button.click();
      var accepted = collectorProtocolSnapshot(collectorPanel);
      applyProtocolSnapshotToAttempt(attempt, accepted);
      var acceptance = collectorProtocolAcceptanceDecision(before, accepted, Date.now());
      if (acceptance.action === 'pause') throw collectorProtocolPause(acceptance.reason, accepted);
      var expectedRunId = acceptance.runId;
      attempt.collectingObservedAtMs = Date.now();
      attempt.startAckMs = attempt.collectingObservedAtMs - attempt.collectorClickAtMs;

      while (true) {
        var snapshot = collectorProtocolSnapshot(collectorPanel);
        applyProtocolSnapshotToAttempt(attempt, snapshot);
        var payload = null;
        if (snapshot.resultReady === '1') {
          try {
            payload = JSON.parse(output.value || '{}');
            attempt.observedPayloadEvidence = collectorEvidenceSnapshot(payload);
          } catch (parseError) {
            throw collectorProtocolPause('collector_result_json_invalid', snapshot);
          }
        }
        var pollDecision = collectorProtocolPollDecision(
          snapshot,
          payload,
          expectedRunId,
          Date.now(),
          document.visibilityState
        );
        attempt.watchdogClassification = pollDecision.watchdogClassification || attempt.watchdogClassification;
        if (pollDecision.action === 'pause') {
          throw collectorProtocolPause(pollDecision.reason, snapshot);
        }
        if (pollDecision.action === 'payload') {
          attempt.completedObservedAtMs = Date.now();
          attempt.jsonParsedAtMs = Date.now();
          attempt.resultWaitMs = attempt.completedObservedAtMs - attempt.collectingObservedAtMs;
          attempt.totalObservedMs = attempt.jsonParsedAtMs - attempt.collectorClickAtMs;
          var internal = payload && payload.telemetry && payload.telemetry.timing ? payload.telemetry.timing : {};
          attempt.collectorInternalChartWaitMs = Number.isFinite(Number(internal.chartWaitMs)) ? Number(internal.chartWaitMs) : null;
          attempt.collectorTooltipScanMs = Number.isFinite(Number(internal.tooltipScanMs)) ? Number(internal.tooltipScanMs) : null;
          attempt.collectorInternalTotalMs = Number.isFinite(Number(internal.totalMs)) ? Number(internal.totalMs) : null;
          attempt.payloadStatus = payload.status || '';
          attempt.payloadAccepted = true;
          attempt.outcome = 'payload';
          return payload;
        }
        await sleep(250);
      }
    } catch (error) {
      attempt.outcome = 'error';
      attempt.reason = oneLine(error && error.message ? error.message : error);
      attempt.payloadQuarantined = Boolean(attempt.observedPayloadEvidence && !attempt.payloadAccepted);
      throw error;
    } finally {
      if (granularRow) {
        granularRow.collectorAttempts.push(attempt);
        granularRow.sellerSprite.collectorButtonObservedAtMs = granularRow.sellerSprite.collectorButtonObservedAtMs || attempt.buttonObservedAtMs;
        granularRow.sellerSprite.sellerSpriteUiFirstObservedAtMs = granularRow.sellerSprite.sellerSpriteUiFirstObservedAtMs || attempt.buttonObservedAtMs;
        granularRow.sellerSprite.trafficTabClickAtMs = granularRow.sellerSprite.trafficTabClickAtMs || attempt.trafficTabClickAtMs;
        granularRow.sellerSprite.trafficTabClickFound = attempt.trafficTabClickFound;
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
      telemetry.firstAttemptStatus = '';
      telemetry.firstAttemptWeeksRead = null;
      telemetry.secondAttemptStatus = '';
      telemetry.secondAttemptWeeksRead = null;
      telemetry.retryReplacedFirst = false;
      telemetry.retryRecoveryYield = null;
      telemetry.firstAttemptEvidence = null;
      telemetry.secondAttemptEvidence = null;
    }
    var payload;
    try {
      payload = await runCollectorOnce(granularRow, 1);
      if (telemetry) telemetry.firstAttemptEvidence = collectorAttemptEvidence(
        payload,
        null,
        granularRow && granularRow.collectorAttempts ? granularRow.collectorAttempts[granularRow.collectorAttempts.length - 1] : null
      );
    } catch (firstError) {
      if (telemetry) telemetry.firstAttemptEvidence = collectorAttemptEvidence(
        null,
        firstError,
        granularRow && granularRow.collectorAttempts ? granularRow.collectorAttempts[granularRow.collectorAttempts.length - 1] : null
      );
      throw firstError;
    }
    if (telemetry) {
      telemetry.firstAttemptStatus = payload.status || '';
      telemetry.firstAttemptWeeksRead = Number.isFinite(Number(payload.weeksRead)) ? Number(payload.weeksRead) : null;
    }
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
      var retry;
      try {
        retry = await runCollectorOnce(granularRow, 2);
        if (telemetry) telemetry.secondAttemptEvidence = collectorAttemptEvidence(
          retry,
          null,
          granularRow && granularRow.collectorAttempts ? granularRow.collectorAttempts[granularRow.collectorAttempts.length - 1] : null
        );
      } catch (secondError) {
        if (telemetry) {
          telemetry.secondAttemptEvidence = collectorAttemptEvidence(
            null,
            secondError,
            granularRow && granularRow.collectorAttempts ? granularRow.collectorAttempts[granularRow.collectorAttempts.length - 1] : null
          );
          telemetry.retryRecoveryYield = false;
        }
        throw secondError;
      }
      var replaceFirst = retry.status === 'ok' && Number(retry.weeksRead || 0) >= Number(payload.weeksRead || 0);
      if (telemetry) {
        telemetry.secondAttemptStatus = retry.status || '';
        telemetry.secondAttemptWeeksRead = Number.isFinite(Number(retry.weeksRead)) ? Number(retry.weeksRead) : null;
        telemetry.retryReplacedFirst = replaceFirst;
        telemetry.retryRecoveryYield = Boolean(
          (payload.status !== 'ok' || Number(payload.weeksRead || 0) < 3)
          && retry.status === 'ok'
          && Number(retry.weeksRead || 0) >= 3
        );
      }
      if (replaceFirst) payload = retry;
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
    var trafficTiming = {
      retryCount: 0,
      retryDecision: 'no_retry',
      retryReason: '',
      firstAttemptStatus: '',
      firstAttemptWeeksRead: null,
      secondAttemptStatus: '',
      secondAttemptWeeksRead: null,
      retryReplacedFirst: false,
      retryRecoveryYield: null,
      firstAttemptEvidence: null,
      secondAttemptEvidence: null
    };
    var dimensions = { dimensions: '', itemDimensions: '', itemWeight: '', packageDimensions: '', packageWeight: '', dimensionsSource: '' };
    var priceTrend = buildPriceTrend([]);
    var collectorPayload = { status: 'error', decision: 'review', weeksRead: 0, collectedAt: new Date().toISOString() };
    var errorMessage = '';
    var protocolPauseError = null;
    var currentGate = mismatch ? 'asin' : 'traffic';
    var skippedSteps = [];

    try {
      if (!mismatch) {
        updateCurrentStep(
          state,
          'traffic',
          ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL
            ? 'Running Traffic Collector 0.4.7 with Collector-owned deadlines.'
            : 'Running Traffic Collector 0.4.7 P2 OFF with legacy waits.'
        );
        var trafficStartedMs = ENABLE_TIER0_TELEMETRY ? Date.now() : null;
        try {
          collectorPayload = await collectTraffic(trafficTiming, granularRow);
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
      if (ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL && error && error.code === 'collector_protocol_pause') {
        protocolPauseError = error;
      } else {
        errorMessage = oneLine(error && error.message ? error.message : error);
      }
    }

    if (protocolPauseError) {
      state = loadBatch(hash) || state;
      state.status = 'paused';
      state.currentIndex = index;
      state.currentStep = 'traffic';
      state.pauseId = 'collector-protocol-' + Date.now();
      state.pausedAtMs = Date.now();
      state.pendingCollectorProtocolPauseCount = Number(state.pendingCollectorProtocolPauseCount || 0) + 1;
      state.pendingCollectorProtocolPauseReasons = (state.pendingCollectorProtocolPauseReasons || []).concat([
        protocolPauseError.protocolReason
      ]);
      var pausedProtocolSnapshot = protocolPauseError.protocolSnapshot || {};
      state.pendingCollectorProtocolStaleRunIds = uniqueTextList(
        (state.pendingCollectorProtocolStaleRunIds || []).concat([
          pausedProtocolSnapshot.runId,
          pausedProtocolSnapshot.deadlineRunId,
          pausedProtocolSnapshot.resultRunId
        ])
      );
      state.pendingCollectorProtocolAttemptEvidence = (state.pendingCollectorProtocolAttemptEvidence || []).concat([
        trafficTiming.firstAttemptEvidence || collectorAttemptEvidence(
          null,
          protocolPauseError,
          granularRow && granularRow.collectorAttempts ? granularRow.collectorAttempts[granularRow.collectorAttempts.length - 1] : null
        )
      ]);
      state.message = 'Collector protocol paused with the current row pending: ' + protocolPauseError.protocolReason;
      recordControlEvent(state, 'collector_protocol_pause', {
        row: index + 1,
        asin: targetAsin,
        stepBefore: 'traffic',
        statusBefore: 'running',
        pauseId: state.pauseId,
        recoveryKind: 'resume_same_row_with_new_collector_run',
        recoveryEvidence: protocolPauseError.protocolReason,
        reason: protocolPauseError.protocolReason
      });
      saveBatch(state);
      finalizeActiveGranular('collector_protocol_pause', null);
      return;
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
      error: errorMessage,
      collectorProtocolMode: ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL ? COLLECTOR_DEADLINE_PROTOCOL_NAME : 'legacy_status_text_v1',
      collectorValidationIdentity: collectorValidationIdentity(
        ENABLE_P2_COLLECTOR_DEADLINE_PROTOCOL,
        granularRow && Array.isArray(granularRow.collectorAttempts) ? granularRow.collectorAttempts : []
      ),
      collectorEvidence: collectorEvidenceSnapshot(collectorPayload),
      retryEvidence: {
        retryCount: trafficTiming.retryCount,
        retryDecision: trafficTiming.retryDecision,
        retryReason: trafficTiming.retryReason,
        firstAttemptStatus: trafficTiming.firstAttemptStatus,
        firstAttemptWeeksRead: trafficTiming.firstAttemptWeeksRead,
        secondAttemptStatus: trafficTiming.secondAttemptStatus,
        secondAttemptWeeksRead: trafficTiming.secondAttemptWeeksRead,
        retryReplacedFirst: trafficTiming.retryReplacedFirst,
        retryRecoveryYield: trafficTiming.retryRecoveryYield,
        firstAttemptEvidence: trafficTiming.firstAttemptEvidence,
        secondAttemptEvidence: trafficTiming.secondAttemptEvidence
      },
      protocolRecoveryEvidence: buildProtocolRecoveryEvidence(
        state,
        collectorPayload,
        granularRow && Array.isArray(granularRow.collectorAttempts) ? granularRow.collectorAttempts : []
      )
    }, traffic, dimensions, priceTrend);
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
    var strictHistory = strictDecision === 'pass'
      ? recordStrictQualified(targetAsin, {
        qualifiedAt: result.finishedAt,
        batchName: state.batchName,
        queueHash: state.queueHash
      })
      : getStrictHistory();
    state.results[index] = result;
    state.pendingCollectorProtocolPauseCount = 0;
    state.pendingCollectorProtocolPauseReasons = [];
    state.pendingCollectorProtocolStaleRunIds = [];
    state.pendingCollectorProtocolAttemptEvidence = [];
    state.currentIndex = index + 1;
    state.currentStep = 'saved';
    state.historyRegistryCount = strictHistoryCount(strictHistory);
    state.message = targetAsin + ' ' + strictDecision + ' at ' + (strictDecision === 'pass' ? 'all_gates' : finalGate.stage) + ' in ' + Math.round((Date.now() - Date.parse(startedAt)) / 1000) + 's.';
    saveBatch(state);

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

  createPanel();
  setTimeout(function () {
    processAutoRow().catch(function (error) {
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
