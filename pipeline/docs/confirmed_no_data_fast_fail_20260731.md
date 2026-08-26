# Confirmed SellerSprite No-Data Fast Fail

## Behavior

Collector `0.4.6.4` adds the versioned feature `confirmed-no-data-fast-fail-v1` on top of `0.4.6.3`.

- Detection is scoped to the visible SellerSprite traffic chart and its two nearest ancestors.
- Only exact visible empty-state phrases are eligible: `暂无数据`, `无数据`, `没有数据`, `暂无流量数据`, `没有流量数据`, `No data`, or `No traffic data`.
- The same normalized phrase must remain visible for 600 ms.
- A confirmed result is emitted as `status=no_data_confirmed`, `decision=fail`, `retryable=false`, and `shortCircuitReason=seller_sprite_explicit_no_data`.
- The raw phrase, element hint, observation timestamps, and stable duration are retained in `noDataEvidence` and Collector gate telemetry.

Runner `0.3.8.7` treats `no_data_confirmed` as a known traffic failure, records `traffic_no_data_confirmed`, skips dimensions and price, and never retries the Collector. Ambiguous `no_data` keeps the existing single conditional retry.

The aggregate natural-traffic threshold, minimum valid-week count, dimensions gate, price gate, replay authority, acceptance authority, and Excel logic are unchanged.

## Deployment

Enable exactly one pair:

- `scripts/sellersprite_traffic_collector_v0.4.6.4_zh_no_data_fast_fail.user.js`
- `scripts/sellersprite_integrated_runner_v0.3.8.7_zh_no_data_fast_fail.user.js`

Disable all older Collector and Runner versions, refresh one Amazon detail page, and run an isolated explicit-no-data ASIN smoke before a formal batch. Confirm that the row rejects with `traffic_no_data_confirmed`, has `retryCount=0`, and retains `noDataEvidence`.

This is a Class B candidate. A formal deployment decision still requires at least 30 paired real ASINs, 100% final gate-outcome agreement, zero false positives, and a live smoke.

## Rollback

Disable `0.4.6.4/0.3.8.7` and re-enable the unchanged `0.4.6.3/0.3.8.6` pair. No storage or data migration is required.
