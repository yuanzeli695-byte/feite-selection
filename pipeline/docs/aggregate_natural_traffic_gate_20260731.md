# Aggregate Natural Traffic Gate

## Authorized Rule

For the most recent three to four valid SellerSprite weeks:

`aggregateNaturalSharePct = sum(naturalTraffic) / sum(totalTraffic) * 100`

The traffic gate passes only when:

- at least three weeks contain numeric natural traffic and positive numeric total traffic;
- each included natural value is between zero and that week's total traffic;
- the independently recomputed aggregate share is at least 70%;
- the reported and recomputed aggregate values agree;
- traffic status is `ok` and there is no unresolved ASIN mismatch.

Individual-week, recent-average, and recent-minimum shares remain in evidence for diagnostics, but they are no longer release thresholds in this mode.

## Versions

- Collector: `0.4.6.3`, feature `aggregate-weighted-share-v1`
- Runner: `0.3.8.6`, feature `aggregate-weighted-share-v1`
- Offline rules: `config/rules_aggregate_natural_traffic.json`
- Excel bridge: `scripts/selection_excel_bridge_aggregate_traffic.py`

## Rollback

Disable Collector `0.4.6.3` and Runner `0.3.8.6`, then re-enable Collector `0.4.6.2` and Runner `0.3.8.5`. Start the previous Excel bridge and use `config/rules.json`. No old file is overwritten.
