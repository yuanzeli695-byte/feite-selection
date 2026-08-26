# SellerSprite Excel to Runner queue

`scripts/prepare_runner_queue_from_sellersprite_export.mjs` converts a current SellerSprite Product Research XLSX export into an audited Runner queue.

The converter verifies that the export is no more than 24 hours old, retains the source file hash and query metadata, applies downward-only Gate A exclusions, and invokes the existing history dedupe and queue ranking pipeline. It writes `runner_queue.txt`, `runner_queue.json`, a source manifest, import rejects, and the normal strict candidate-pool audit files.

The Excel path enables `excel-source-optional-parent-child-sales-v1`. Parent and child sales may be absent because the user has declared both fields non-gating. The converter leaves absent values as `null`; it never substitutes one for the other. Roll back by omitting `--allow-missing-parent-child-sales` from the strict candidate-pool invocation.

Runner evidence remains non-authoritative. Collector evidence, offline replay, workbook generation, and `acceptance_checker.py` are still required before delivery.
