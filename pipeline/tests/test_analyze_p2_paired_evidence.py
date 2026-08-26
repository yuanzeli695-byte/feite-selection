from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPRESENTATIVE_RUN_DIR = ROOT / "runs" / "strict20_live_20260714_084136"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from build_p2_pair_capture import build_capture  # noqa: E402
from test_build_p2_pair_capture import batch, result, review  # noqa: E402
from analyze_p2_paired_evidence import (  # noqa: E402
    ContractError,
    _paired_timing_delta_stats,
    compare_capture,
    load_representative_gate_logs,
    load_representative_run_dir,
    main,
    render_markdown,
)


def capture(*, reviewed: bool = False, pair_count: int = 30) -> dict[str, object]:
    old_rows = [result(i, False, old_timeout=20 <= i <= 24) for i in range(pair_count)]
    new_rows = [result(i, True, gate="pass" if 20 <= i <= 22 else "reject") for i in range(pair_count)]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        old_path = root / "old.json"
        new_path = root / "new.json"
        old_path.write_text(json.dumps(batch(old_rows, "old")), encoding="utf-8")
        new_path.write_text(json.dumps(batch(new_rows, "new")), encoding="utf-8")
        base = build_capture([old_path], [new_path])
        if not reviewed:
            return base
        persistent_review_root = (
            Path(tempfile.gettempdir()) / "seller_sprite_p2_review_fixtures"
        )
        return build_capture(
            [old_path],
            [new_path],
            recovery_review=review(
                base, [20, 21, 22, 23, 24], persistent_review_root
            ),
        )


def attach_review(data: dict[str, object], index: int) -> None:
    pair = data["pairs"][index]
    pair["recoveryReview"] = None
    binding = compare_capture(data)["pairs"][index]["reviewBinding"]
    evidence_path = (
        Path(tempfile.gettempdir())
        / "seller_sprite_p2_review_fixtures"
        / f"attached_{binding['evidenceSha256']}.json"
    )
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps({"reviewBinding": binding}), encoding="utf-8")
    evidence_raw = evidence_path.read_bytes()
    review_row = {
        "schemaVersion": "sellerSpriteP2RecoveryReview/v2",
        "asin": pair["asin"],
        "pairId": binding["pairId"],
        "reviewBinding": binding,
        "artifactsVerifiedByBuilder": True,
        "manualTooltipVerified": True,
        "offlineReplayOutcome": "pass",
        "acceptanceOutcome": "pass",
        "evidenceArtifacts": [
            {
                "path": str(evidence_path),
                "bytes": len(evidence_raw),
                "sha256": hashlib.sha256(evidence_raw).hexdigest(),
            }
        ],
        "verifiedBy": "fixture",
        "verifiedAt": "2026-07-15T00:00:00Z",
    }
    attestation_fields = (
        "schemaVersion",
        "asin",
        "pairId",
        "reviewBinding",
        "manualTooltipVerified",
        "offlineReplayOutcome",
        "acceptanceOutcome",
        "evidenceArtifacts",
        "verifiedBy",
        "verifiedAt",
    )
    review_row["reviewAttestationSha256"] = hashlib.sha256(
        json.dumps(
            {field: review_row[field] for field in attestation_fields},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    data["pairs"][index]["recoveryReview"] = review_row


def add_partial_recovery(
    data: dict[str, object], index: int = 3, *, gate: str = "reject", with_review: bool = False
) -> None:
    new_side = data["pairs"][index]["new"]
    third_week = copy.deepcopy(data["pairs"][4]["new"]["weeks"][2])
    new_side["weeks"].append(third_week)
    new_side["weeksRead"] = 3
    new_side["gateOutcome"] = gate
    new_side["firstAttempt"]["weeks"].append(copy.deepcopy(third_week))
    new_side["firstAttempt"]["weeksRead"] = 3
    if with_review:
        attach_review(data, index)


def representative_run() -> dict[str, object]:
    return {
        "schemaVersion": "sellerSpriteP2RepresentativeRun/v1",
        "sourceKind": "fixture",
        "runId": "strict20_live_20260714_084136",
        "sourceFiles": [],
        "browserVisits": 371,
        "qualifiedCount": 10,
        "rejectedCount": 361,
        "rejectionCounts": {
            "asin_mismatch": 9,
            "collection_error": 43,
            "price_current_missing": 29,
            "price_trend_not_allowed": 3,
            "traffic_error": 30,
            "traffic_recent4_avg_below_70": 5,
            "traffic_recent4_min_below_70": 28,
            "traffic_weeks_insufficient": 214,
        },
        "trafficWeeksInsufficientByWeeksRead": {"1": 165, "2": 49},
        "projectionCategoryCounts": {
            "traffic_weeks_insufficient_partial_1_2": 214,
            "collection_error": 43,
        },
    }


class P2PairedEvidenceTests(unittest.TestCase):
    def test_partitioned_semantics_without_review_is_reader_pass_release_pending(self) -> None:
        result_data = compare_capture(capture())
        self.assertTrue(result_data["readerValidationPassed"], result_data["errors"])
        self.assertFalse(result_data["releaseValidationComplete"])
        self.assertFalse(result_data["passed"])
        self.assertEqual(result_data["validation"]["oldTimeoutErrorCount"], 5)
        self.assertEqual(result_data["validation"]["genuineRecoveryCount"], 5)
        self.assertEqual(result_data["validation"]["releasePendingCount"], 5)
        self.assertEqual(len(result_data["recoveries"]), 5)

    def test_reviewed_genuine_recoveries_can_pass(self) -> None:
        result_data = compare_capture(capture(reviewed=True))
        self.assertTrue(result_data["passed"], result_data["errors"])
        self.assertEqual(result_data["validation"]["happyPathGateMismatchCount"], 0)
        self.assertEqual(result_data["validation"]["happyPathWeekMismatchCount"], 0)
        self.assertEqual(result_data["validation"]["falsePositiveCount"], 0)

    def test_partial_to_full_enters_review_path_only_with_exact_overlap(self) -> None:
        data = capture(reviewed=True)
        baseline = compare_capture(data)["metrics"]["valueRecovery"]
        self.assertEqual(baseline["oldTrafficWeeksInsufficientPartialRows"], 2)
        self.assertEqual(baseline["partialToFullConversionCount"], 0)
        self.assertEqual(baseline["oldCollectionErrorRows"], 5)
        self.assertEqual(baseline["collectionErrorRecoveryCandidateCount"], 5)
        self.assertEqual(baseline["collectionErrorRecoveryCount"], 5)

        add_partial_recovery(data, gate="pass")
        result_data = compare_capture(data)
        value = result_data["metrics"]["valueRecovery"]
        self.assertEqual(value["partialToFullCandidateCount"], 1)
        self.assertEqual(value["partialToFullConversionCount"], 1)
        self.assertEqual(value["partialToFullOnFirstAttemptCount"], 1)
        self.assertEqual(value["partialToFullRetryAssistedCount"], 0)
        self.assertFalse(value["diagnosticOnly"])
        self.assertTrue(value["recoveryEligible"])
        self.assertTrue(result_data["readerValidationPassed"], result_data["errors"])
        self.assertFalse(result_data["releaseValidationComplete"])
        self.assertEqual(result_data["validation"]["happyPathWeekMismatchCount"], 0)
        self.assertEqual(result_data["validation"]["partialRecoveryCandidateCount"], 1)
        self.assertEqual(result_data["pairs"][3]["partition"], "old_partial_recovery")
        self.assertTrue(result_data["pairs"][3]["recovery"]["overlapByteExact"])
        self.assertEqual(len(result_data["pairs"][3]["recovery"]["addedWeeks"]), 1)
        self.assertEqual(result_data["validation"]["falsePositiveCount"], 0)

        attach_review(data, 3)
        reviewed = compare_capture(data)
        self.assertTrue(reviewed["passed"], reviewed["errors"])
        self.assertEqual(
            reviewed["validation"]["releaseValidatedQualifiedPartialRecoveryCount"], 1
        )

    def test_partial_overlap_difference_or_dropped_week_is_a_hard_failure(self) -> None:
        data = capture(reviewed=True)
        add_partial_recovery(data, with_review=True)
        data["pairs"][3]["new"]["weeks"][0]["rawText"] += " changed"
        attach_review(data, 3)
        result_data = compare_capture(data, representative_run())
        self.assertFalse(result_data["readerValidationPassed"])
        self.assertEqual(result_data["validation"]["invalidPartialRecoveryCount"], 1)
        self.assertFalse(result_data["roi"]["available"])
        self.assertTrue(
            any("reader validation" in reason for reason in result_data["roi"]["unavailableReasons"])
        )
        self.assertTrue(
            any("overlapping weeks differ" in error for error in result_data["errors"]),
            result_data["errors"],
        )

        data = capture(reviewed=True)
        add_partial_recovery(data, with_review=True)
        replacement = copy.deepcopy(data["pairs"][3]["new"]["weeks"][2])
        replacement["weekSort"] = 202624
        replacement["weekLabel"] = "2026 W24"
        data["pairs"][3]["new"]["weeks"] = [
            data["pairs"][3]["new"]["weeks"][1],
            data["pairs"][3]["new"]["weeks"][2],
            replacement,
        ]
        data["pairs"][3]["new"]["firstAttempt"]["weeks"] = copy.deepcopy(
            data["pairs"][3]["new"]["weeks"]
        )
        attach_review(data, 3)
        result_data = compare_capture(data)
        self.assertFalse(result_data["readerValidationPassed"])
        self.assertTrue(
            any("dropped one or more old-side weeks" in error for error in result_data["errors"]),
            result_data["errors"],
        )

    def test_partial_metric_excludes_wrong_bucket_and_invalid_provenance(self) -> None:
        data = capture(reviewed=True)
        new_side = data["pairs"][3]["new"]
        third_week = copy.deepcopy(data["pairs"][4]["new"]["weeks"][2])
        third_week["tier2ReaderVersion"] = "unexpected-reader"
        new_side["weeks"].append(third_week)
        new_side["weeksRead"] = 3
        new_side["firstAttempt"]["weeks"].append(copy.deepcopy(third_week))
        new_side["firstAttempt"]["weeksRead"] = 3
        result_data = compare_capture(data)
        value = result_data["metrics"]["valueRecovery"]
        self.assertEqual(value["partialToFullCandidateCount"], 1)
        self.assertEqual(value["partialToFullConversionCount"], 0)

        data = capture(reviewed=True)
        data["pairs"][2]["old"]["rejectionRule"] = "some_other_rule"
        value = compare_capture(data)["metrics"]["valueRecovery"]
        self.assertEqual(value["oldTrafficWeeksInsufficientPartialRows"], 1)

    def test_retry_yield_is_recomputed_and_reported_as_a_fraction(self) -> None:
        data = capture(reviewed=True)
        recovered = data["pairs"][0]["new"]
        recovered["collectorIdentity"]["attemptCount"] = 2
        recovered["retryCount"] = 1
        recovered["recoveryYield"] = True
        recovered["secondAttempt"] = copy.deepcopy(recovered["firstAttempt"])
        recovered["firstAttempt"]["status"] = "no_chart_loaded"
        recovered["firstAttempt"]["weeksRead"] = 0
        recovered["firstAttempt"]["weeks"] = []

        not_recovered = data["pairs"][4]["new"]
        not_recovered["collectorIdentity"]["attemptCount"] = 2
        not_recovered["retryCount"] = 1
        not_recovered["recoveryYield"] = False
        not_recovered["secondAttempt"] = copy.deepcopy(not_recovered["firstAttempt"])

        result_data = compare_capture(data)
        retry = result_data["metrics"]["new"]["retry"]
        self.assertEqual(retry["rows"], 2)
        self.assertEqual(retry["recovered"], 1)
        self.assertEqual(retry["recoveryYieldPct"], 50.0)
        self.assertIsNone(result_data["metrics"]["old"]["retry"]["recoveryYieldPct"])
        markdown = render_markdown(result_data)
        self.assertIn("1/2 = 50.0%", markdown)
        self.assertIn("Retry-yield delta (new - old): n/a", markdown)

        data["pairs"][4]["new"]["recoveryYield"] = True
        invalid = compare_capture(data)
        self.assertTrue(any("recoveryYield does not match full attempt evidence" in error for error in invalid["errors"]))

    def test_paired_timing_delta_is_not_a_marginal_percentile_difference(self) -> None:
        pairs = {
            "a": ({"timing": {"totalMs": 0}}, {"timing": {"totalMs": 100}}),
            "b": ({"timing": {"totalMs": 100}}, {"timing": {"totalMs": 0}}),
        }
        paired = _paired_timing_delta_stats(pairs, "totalMs")
        self.assertEqual(paired["p50DeltaMs"], 0.0)
        self.assertEqual(paired["p90DeltaMs"], 80.0)
        self.assertEqual(paired["missing"], 0)

        data = compare_capture(capture(reviewed=True))
        self.assertEqual(data["metrics"]["comparison"]["pairedDelta"]["collectorMs"]["count"], 0)
        self.assertEqual(data["metrics"]["comparison"]["pairedDelta"]["collectorMs"]["missing"], 30)
        self.assertIn("positive values mean P2 is slower", render_markdown(data))

    @unittest.skipUnless(
        (REPRESENTATIVE_RUN_DIR / "run_summary.json").is_file(),
        "optional historical representative run is not included in the source package",
    )
    def test_representative_gate_logs_rederive_last_real_distribution(self) -> None:
        run_dir = REPRESENTATIVE_RUN_DIR
        baseline = load_representative_run_dir(run_dir)
        self.assertEqual(baseline["browserVisits"], 371)
        self.assertEqual(baseline["qualifiedCount"], 10)
        self.assertEqual(baseline["rejectedCount"], 361)
        self.assertEqual(baseline["visitsPerQualified"], 37.1)
        self.assertEqual(baseline["rejectionCounts"]["traffic_weeks_insufficient"], 214)
        self.assertEqual(baseline["rejectionCounts"]["collection_error"], 43)
        self.assertEqual(baseline["trafficWeeksInsufficientByWeeksRead"], {"1": 165, "2": 49})
        self.assertEqual(
            baseline["projectionCategoryCounts"]["traffic_weeks_insufficient_partial_1_2"],
            214,
        )
        self.assertEqual(sum(baseline["rejectionCounts"].values()), 361)
        self.assertEqual(len(baseline["sourceFiles"]), 6)
        self.assertEqual(
            baseline["sourceKind"], "raw_gate_tsv_rederived_complete_run"
        )
        self.assertEqual(len(baseline["runManifest"]["expectedGateFiles"]), 6)

    def test_roi_uses_category_weighting_and_release_validated_qualifiers(self) -> None:
        data = capture(reviewed=True)
        add_partial_recovery(data, gate="pass", with_review=True)
        result_data = compare_capture(data, representative_run())
        roi = result_data["roi"]
        self.assertTrue(result_data["passed"], result_data["errors"])
        self.assertTrue(roi["available"], roi["unavailableReasons"])
        self.assertEqual(
            roi["categories"]["traffic_weeks_insufficient"]["sampleEligible"], 2
        )
        self.assertEqual(
            roi["categories"]["traffic_weeks_insufficient"]
            ["sampleReleaseValidatedQualifiedRatePct"],
            50.0,
        )
        self.assertEqual(
            roi["categories"]["collection_error"]["sampleReleaseValidatedQualifiedRatePct"],
            60.0,
        )
        self.assertEqual(roi["projectedIncrementalQualified"], 132.8)
        self.assertEqual(roi["projectedVisitsPerQualified"], 2.598)
        markdown = render_markdown(result_data)
        self.assertIn("Projected visits per qualified: **2.598**", markdown)
        self.assertIn("raw overall yield is not representative", markdown)
        self.assertIn("sequential", roi["sequentialCaptureCaveat"].lower())
        self.assertIn("cannot create a false positive", roi["sequentialCaptureCaveat"])

    def test_roi_stays_unavailable_until_recovery_review_is_complete(self) -> None:
        data = capture(reviewed=True)
        add_partial_recovery(data, gate="pass")
        result_data = compare_capture(data, representative_run())
        self.assertTrue(result_data["readerValidationPassed"], result_data["errors"])
        self.assertFalse(result_data["releaseValidationComplete"])
        self.assertFalse(result_data["roi"]["available"])
        self.assertIsNone(result_data["roi"]["projectedVisitsPerQualified"])
        self.assertTrue(
            any("review/replay/acceptance" in reason for reason in result_data["roi"]["unavailableReasons"])
        )
        self.assertIn("**UNAVAILABLE**", render_markdown(result_data))

    @unittest.skipUnless(
        (REPRESENTATIVE_RUN_DIR / "run_summary.json").is_file(),
        "optional historical representative run is not included in the source package",
    )
    def test_formal_validation_requires_representative_roi(self) -> None:
        data = capture(reviewed=True)
        with self.assertRaisesRegex(ContractError, "manifest-complete raw"):
            compare_capture(data, require_roi=True)
        with self.assertRaisesRegex(ContractError, "manifest-complete raw"):
            compare_capture(data, representative_run(), require_roi=True)

        run_dir = REPRESENTATIVE_RUN_DIR
        with_baseline = compare_capture(
            data, load_representative_run_dir(run_dir), require_roi=True
        )
        self.assertTrue(with_baseline["passed"], with_baseline["errors"])
        markdown = render_markdown(with_baseline)
        self.assertIn('"runManifest"', markdown)
        self.assertIn('"evidenceArtifacts"', markdown)
        self.assertIn('"reviewAttestationSha256"', markdown)

        one_gate = load_representative_gate_logs(
            [sorted(run_dir.glob("gate_log_*.tsv"))[0]]
        )
        with self.assertRaisesRegex(ContractError, "manifest-complete raw"):
            compare_capture(data, one_gate, require_roi=True)
        forged_partial = copy.deepcopy(one_gate)
        complete = load_representative_run_dir(run_dir)
        forged_partial["sourceKind"] = "raw_gate_tsv_rederived_complete_run"
        forged_partial["runId"] = complete["runId"]
        forged_partial["runManifest"] = complete["runManifest"]
        with self.assertRaisesRegex(ContractError, "gate files are incomplete"):
            compare_capture(data, forged_partial, require_roi=True)

    def test_formal_cli_rejects_empty_representative_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture_path = root / "capture.json"
            empty_baseline = root / "empty-baseline"
            empty_baseline.mkdir()
            capture_path.write_text(json.dumps(capture(reviewed=True)), encoding="utf-8")
            self.assertEqual(
                main(
                    [
                        str(capture_path),
                        "--representative-run-dir",
                        str(empty_baseline),
                        "--format",
                        "json",
                    ]
                ),
                2,
            )

    def test_non_timeout_gate_or_week_mismatch_fails(self) -> None:
        data = capture(reviewed=True)
        data["pairs"][4]["new"]["gateOutcome"] = "pass"
        result_data = compare_capture(data)
        self.assertFalse(result_data["passed"])
        self.assertEqual(result_data["validation"]["happyPathGateMismatchCount"], 1)

        data = capture(reviewed=True)
        data["pairs"][4]["new"]["weeks"][0]["naturalTraffic"] = "79.99"
        result_data = compare_capture(data)
        self.assertFalse(result_data["passed"])
        self.assertEqual(result_data["validation"]["happyPathWeekMismatchCount"], 1)

    def test_partial_numeric_representation_mismatch_is_not_byte_exact(self) -> None:
        data = capture(reviewed=True)
        add_partial_recovery(data)
        original = data["pairs"][3]["new"]["weeks"][0]["totalTraffic"]
        data["pairs"][3]["new"]["weeks"][0]["totalTraffic"] = str(original) + ".0"
        result_data = compare_capture(data)
        self.assertFalse(result_data["readerValidationPassed"])
        self.assertFalse(result_data["pairs"][3]["weekComparison"]["overlapByteExact"])
        self.assertTrue(
            any(
                difference["field"] == "exactScalarEncodings"
                for difference in result_data["pairs"][3]["weekComparison"][
                    "overlapEvidenceDifferences"
                ]
            )
        )

    def test_stale_recovery_review_binding_is_rejected(self) -> None:
        data = capture(reviewed=True)
        data["pairs"][20]["new"]["weeks"][0]["rawText"] += " newly observed"
        result_data = compare_capture(data)
        self.assertFalse(result_data["passed"])
        self.assertTrue(
            any("evidence binding mismatch" in error for error in result_data["errors"]),
            result_data["errors"],
        )

    @unittest.skipUnless(
        (REPRESENTATIVE_RUN_DIR / "run_summary.json").is_file(),
        "optional historical representative run is not included in the source package",
    )
    def test_deleted_review_artifact_blocks_formal_release(self) -> None:
        data = capture(reviewed=True)
        artifact_path = Path(
            data["pairs"][20]["recoveryReview"]["evidenceArtifacts"][0]["path"]
        )
        artifact_path.unlink()
        run_dir = REPRESENTATIVE_RUN_DIR
        result_data = compare_capture(data, load_representative_run_dir(run_dir), require_roi=True)
        self.assertFalse(result_data["passed"])
        self.assertTrue(
            any("verified evidence file is missing" in error for error in result_data["errors"]),
            result_data["errors"],
        )

    def test_timeout_recovery_gate_mismatch_is_allowed_when_reviewed(self) -> None:
        data = capture(reviewed=True)
        data["pairs"][20]["new"]["gateOutcome"] = "pass"
        attach_review(data, 20)
        result_data = compare_capture(data)
        self.assertTrue(result_data["passed"], result_data["errors"])
        self.assertEqual(result_data["validation"]["globalGateOutcomeMismatchCount"], 3)

    def test_invalid_recovered_values_are_never_a_pass(self) -> None:
        data = capture(reviewed=True)
        week = data["pairs"][20]["new"]["weeks"][0]
        week["naturalShareSource"] = "missing"
        week["naturalShareDerived"] = False
        data["pairs"][20]["new"]["gateOutcome"] = "pass"
        attach_review(data, 20)
        result_data = compare_capture(data)
        self.assertFalse(result_data["passed"])
        self.assertGreaterEqual(result_data["validation"]["invalidRecoveryCount"], 1)
        self.assertGreaterEqual(result_data["validation"]["falsePositiveCount"], 1)

    def test_hidden_or_late_protocol_is_rejected(self) -> None:
        data = capture(reviewed=True)
        data["pairs"][20]["new"]["protocol"]["visibilityState"] = "hidden"
        result_data = compare_capture(data)
        self.assertFalse(result_data["passed"])
        self.assertTrue(any("hidden/throttled" in error for error in result_data["errors"]))

        data = capture(reviewed=True)
        protocol = data["pairs"][20]["new"]["protocol"]
        protocol["chartReadyAtMs"] = protocol["chartReadyDeadlineAtMs"] + 1
        result_data = compare_capture(data)
        self.assertFalse(result_data["passed"])
        self.assertTrue(any("60s hard deadline" in error for error in result_data["errors"]))

    def test_backward_wall_clock_protocol_is_rejected(self) -> None:
        data = capture(reviewed=True)
        protocol = data["pairs"][20]["new"]["protocol"]
        protocol["clockAnomalyKind"] = "wall_clock_backward"
        protocol["clockAnomalyObservedAtMs"] = protocol["acceptedAtMs"] - 1
        result_data = compare_capture(data)
        self.assertFalse(result_data["passed"])
        self.assertTrue(any("backward wall-clock" in error for error in result_data["errors"]))

    def test_stale_fresh_run_id_is_rejected(self) -> None:
        data = capture(reviewed=True)
        recovery = data["pairs"][20]["new"]["newProtocolRecovery"] if "newProtocolRecovery" in data["pairs"][20]["new"] else data["pairs"][20]["new"].get("protocolRecovery")
        # Builder emits zero-pause rows here; inject a completed recovery with stale identity.
        recovery["pauseCount"] = 1
        recovery["recovered"] = True
        recovery["pendingRecoveryState"] = "recovered"
        recovery["freshRunIdVerified"] = True
        recovery["runIdentityConsistent"] = True
        recovery["staleRunIds"] = [recovery["freshRunId"]]
        recovery["quarantinedAttempts"] = [{"outcome": "error"}]
        result_data = compare_capture(data)
        self.assertFalse(result_data["passed"])
        self.assertTrue(any("resumed row lacks verified fresh-run" in error for error in result_data["errors"]))

    def test_missing_first_attempt_fails_closed(self) -> None:
        data = capture(reviewed=True)
        data["pairs"][0]["old"]["firstAttempt"] = None
        result_data = compare_capture(data)
        self.assertFalse(result_data["passed"])
        self.assertTrue(any("firstAttempt" in error for error in result_data["errors"]))

    def test_timeout_sample_floor_is_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_rows = [result(i, False, old_timeout=i in (20, 21)) for i in range(30)]
            new_rows = [result(i, True, gate="pass" if i in (20, 21) else "reject") for i in range(30)]
            old_path, new_path = root / "old.json", root / "new.json"
            old_path.write_text(json.dumps(batch(old_rows, "old")), encoding="utf-8")
            new_path.write_text(json.dumps(batch(new_rows, "new")), encoding="utf-8")
            base = build_capture([old_path], [new_path])
            data = build_capture(
                [old_path],
                [new_path],
                recovery_review=review(base, [20, 21], root),
            )
        result_data = compare_capture(data)
        self.assertFalse(result_data["passed"])
        self.assertTrue(any("old timeout/error rows" in error for error in result_data["errors"]))

    def test_stratification_and_sandbox_history_are_reported(self) -> None:
        result_data = compare_capture(capture(reviewed=True))
        self.assertTrue(result_data["validation"]["stratificationComplete"])
        self.assertEqual(result_data["historyIsolation"]["mode"], "sandbox")
        self.assertTrue(result_data["historyIsolation"]["productionWriteProtected"])
        for name in ("explicitZero", "dashMarker", "missingRatio", "partial1to2Weeks", "slowPage"):
            self.assertTrue(result_data["stratification"][name]["covered"], name)


if __name__ == "__main__":
    unittest.main()
