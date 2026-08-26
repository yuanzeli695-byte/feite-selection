# SellerSprite MCP Provider Contract Gaps

Please answer this handoff as an implementation contract. Do not spend live MCP quota to produce the explanation; use schemas, source code, or offline fixtures.

## 1. Exact ASIN product lookup

The validation request supplied 30 exact ASINs to `competitor_lookup`, but the response returned five unrelated ASINs.

Provide:

- the exact request shape for filtering by a list of ASINs;
- whether the filter is exact or fuzzy;
- the response pagination behavior when 1-40 ASINs are supplied;
- a guarantee that every returned row includes `targetAsin` and `actualAsin`, or an equivalent binding;
- an explicit missing-row/error representation for requested ASINs that are not found;
- an offline fixture showing two requested ASINs and no unrelated rows.

## 2. Gate C weekly natural-share evidence

`traffic_extend` is a keyword-expansion endpoint. It returned zero rows and does not expose the weekly total/natural traffic shares required by the strict Gate C contract.

Provide the endpoint and schema that can return, for one or more exact ASINs:

- week identifier and timezone;
- weekly total traffic;
- weekly natural traffic;
- natural traffic share percentage;
- at least the latest three weeks, preferably four;
- target/actual ASIN binding;
- collection timestamp and source timestamp;
- missing, partial, stale, timeout, mismatch, and zero-total semantics.

The existing hard gate requires at least three weeks and evaluates the recent-four-week average and minimum against the 70% floor. MCP evidence cannot be authoritative until the data semantics match that contract exactly.

## 3. Product-field semantics

For each returned field, document its source, unit, timestamp, and parent/child scope:

- current child-ASIN price;
- rating and review count;
- child monthly sales;
- variation count;
- launch/available date;
- item and package dimensions/weight;
- image URL;
- price history.

Parent sales must never be substituted for missing child sales. Null, zero, not-found, not-collected, and unsupported must be distinguishable.

## 4. Quota and reliability

Document:

- what counts as one monthly call;
- whether pagination, retries, failures, or timeouts consume quota;
- maximum ASINs per call for every relevant endpoint;
- rate limits and concurrency limits;
- stable error codes;
- response-size limits;
- data freshness/TTL guidance.

The local integration enforces an absolute per-task ceiling and an immutable call ledger. Retries are not permitted unless separately predeclared.

## 5. Required offline acceptance fixture

Provide JSON fixtures and expected outputs for:

- exact match;
- missing ASIN;
- ASIN mismatch;
- stale response;
- partial weeks;
- traffic below average threshold;
- traffic below minimum threshold;
- current price missing;
- volatile/declining price;
- null child sales with parent sales present.

Once this contract is supplied, the same frozen 30-ASIN baseline can be re-analyzed without browser-history writes. A one-ASIN browser smoke is allowed only after 100% final-decision isolation, zero false positives, exact ASIN binding, and complete Gate C evidence are demonstrated offline.
