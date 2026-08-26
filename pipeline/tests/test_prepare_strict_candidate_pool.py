from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

from scripts import prepare_strict_candidate_pool as candidate_pool


ROOT = Path(__file__).resolve().parents[1]


def strict_query_url(**overrides) -> str:
    params = {
        "market": "US",
        "maxReviews": "100",
        "nodeIdPaths": json.dumps(["123456"]),
        "keywords": "storage organizer",
    }
    params.update({key: str(value) for key, value in overrides.items()})
    return "https://www.sellersprite.com/v3/product-research?" + urlencode(params)


def candidate(asin: str, title: str, **overrides) -> dict:
    row = {
        "asin": asin,
        "title": title,
        "brand": "TestBrand",
        "categoryPath": "Home & Kitchen > Storage",
        "price": 19.99,
        "rating": 4.5,
        "reviews": 10,
        "childSales": 100,
        "parentSales": 120,
        "launchDate": "2026-05-01",
        "variations": 1,
        "image": "https://example.com/image.png",
        "sourcePage": "storage organizer",
        "sellerSpriteUrl": strict_query_url(),
        "amazonUrl": f"https://www.amazon.com/dp/{asin}",
    }
    row.update(overrides)
    return row


def write_manifest(
    input_dir: Path,
    manifest_path: Path,
    *,
    captured_at: datetime | None = None,
    market: str = "US",
    query_url: str | None = None,
) -> dict:
    source_url = query_url or strict_query_url()
    inputs = []
    for path in sorted(input_dir.glob("query_*.json")):
        inputs.append(
            {
                "path": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "queryUrl": source_url,
            }
        )
    manifest = {
        "schemaVersion": candidate_pool.SOURCE_MANIFEST_SCHEMA_VERSION,
        "capturedAt": (captured_at or datetime.now(timezone.utc)).isoformat(),
        "market": market,
        "preset": {"name": "amazon-us-strict-v1"},
        "categoryScope": {
            "name": "Home & Kitchen > Storage & Organization",
            "nodeIdPaths": ["123456"],
        },
        "inputs": inputs,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def run_pool(
    input_dir: Path,
    output_dir: Path,
    *,
    queue_size: int = 1,
    source_manifest: Path | None = None,
    legacy: bool = False,
    extra: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "prepare_strict_candidate_pool.py"),
        "--input-dir",
        str(input_dir),
        "--project-root",
        str(input_dir.parent),
        "--output-dir",
        str(output_dir),
        "--queue-name",
        "test_queue",
        "--queue-size",
        str(queue_size),
        "--run-date",
        "2026-07-13",
    ]
    if source_manifest:
        command.extend(["--source-manifest", str(source_manifest)])
    if legacy:
        command.append("--allow-legacy-source")
    command.extend(extra or [])
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)


class PrepareStrictCandidatePoolTests(unittest.TestCase):
    def test_a_source_prefilter_v2_matches_only_precise_confirmed_a_products(self):
        confirmed = {
            "B0IPAA0001": ("For Stitch Happy Birthday Banner", "ip_character_risk"),
            "B0AAAA0001": ("Solar Garden Gnome with Solar Lights", "electric_electronic"),
            "B0BBBB0002": ("45W Outdoor Flood Lights", "electric_electronic"),
            "B0CCCC0003": ("Socket Fan Light with Remote", "electric_electronic"),
            "B0DDDD0004": ("Incandescent Light Bulbs 6 Pack", "electric_electronic"),
            "B0EEEE0005": ("20 Inch 3-Speed Box Fan", "electric_electronic"),
            "B0FFFF0006": ("9 Colors Wood Filler Sticks", "chemical_consumable"),
        }
        for asin, (title, expected_rule) in confirmed.items():
            with self.subTest(title=title):
                hit = candidate_pool.a_source_hard_exclusion_hit(candidate(asin, title))
                self.assertIsNotNone(hit)
                self.assertEqual(hit["rule"], expected_rule)

        allowed = (
            "Cross Stitch Storage Organizer",
            "Solar System Classroom Poster",
            "Paper Fans Patriotic Party Decorations",
            "Lightweight Bulb Planter Basket",
            "Wood Furniture Repair Marker Organizer",
        )
        for index, title in enumerate(allowed, start=1):
            with self.subTest(title=title):
                self.assertIsNone(
                    candidate_pool.a_source_hard_exclusion_hit(
                        candidate(f"B0SAFE{index:04d}", title)
                    )
                )

    def test_cli_a_source_prefilter_v2_is_downward_only_and_has_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            enabled_output = root / "enabled"
            rollback_output = root / "rollback"
            input_dir.mkdir()
            (input_dir / "query_test.json").write_text(
                json.dumps(
                    [
                        candidate("B0AAAA0001", "Solar Garden Lights", brand="Alpha"),
                        candidate("B0BBBB0002", "Wood Filler Sticks", brand="Beta"),
                        candidate("B0CCCC0003", "Drawer Organizer", brand="Gamma"),
                        candidate("B0DDDD0004", "Shelf Organizer", brand="Delta"),
                    ]
                ),
                encoding="utf-8",
            )

            enabled = run_pool(input_dir, enabled_output, queue_size=2, legacy=True)
            rollback = run_pool(
                input_dir,
                rollback_output,
                queue_size=4,
                legacy=True,
                extra=["--disable-a-source-prefilter-v2"],
            )

            self.assertEqual(enabled.returncode, 0, enabled.stderr or enabled.stdout)
            self.assertEqual(rollback.returncode, 0, rollback.stderr or rollback.stdout)
            enabled_rows = json.loads(
                (enabled_output / "test_queue.json").read_text(encoding="utf-8")
            )
            rollback_candidates = json.loads(
                (rollback_output / "screened_candidates_all.json").read_text(encoding="utf-8")
            )
            enabled_summary = json.loads(
                (enabled_output / "summary_test_queue.json").read_text(encoding="utf-8")
            )
            rollback_summary = json.loads(
                (rollback_output / "summary_test_queue.json").read_text(encoding="utf-8")
            )

            self.assertEqual(
                {row["asin"] for row in enabled_rows},
                {"B0CCCC0003", "B0DDDD0004"},
            )
            self.assertEqual(len(rollback_candidates), 4)
            self.assertEqual(enabled_summary["aSourcePrefilter"]["rejectedCount"], 2)
            self.assertEqual(
                enabled_summary["aSourcePrefilter"]["ruleCounts"],
                {"electric_electronic": 1, "chemical_consumable": 1},
            )
            self.assertFalse(rollback_summary["aSourcePrefilter"]["enabled"])
            self.assertEqual(rollback_summary["aSourcePrefilter"]["rejectedCount"], 0)

    def test_default_requires_formal_manifest_and_legacy_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            input_dir.mkdir()
            (input_dir / "query_test.json").write_text(
                json.dumps([candidate("B0AAAA0001", "Storage organizer")]),
                encoding="utf-8",
            )

            missing_mode = run_pool(input_dir, root / "missing")
            legacy = run_pool(input_dir, root / "legacy", legacy=True)

            self.assertEqual(missing_mode.returncode, 2)
            self.assertIn("choose exactly one source mode", missing_mode.stderr)
            self.assertEqual(legacy.returncode, 0, legacy.stderr or legacy.stdout)
            summary = json.loads((root / "legacy" / "summary_test_queue.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["sourceContract"]["mode"], "legacy_opt_in")

    def test_formal_manifest_hash_freshness_market_and_query_contract(self):
        now = datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            input_dir.mkdir()
            source_path = input_dir / "query_test.json"
            source_path.write_text(
                json.dumps([candidate("B0AAAA0001", "Storage organizer")]),
                encoding="utf-8",
            )
            manifest_path = root / "source_manifest.json"
            write_manifest(input_dir, manifest_path, captured_at=now - timedelta(hours=23, minutes=59))

            contract = candidate_pool.validate_source_manifest(manifest_path, input_dir, now=now)
            self.assertEqual(contract["market"], "US")
            self.assertEqual(contract["inputs"]["query_test.json"]["sha256"], hashlib.sha256(source_path.read_bytes()).hexdigest())

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["capturedAt"] = (now - timedelta(hours=24, seconds=1)).isoformat()
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(candidate_pool.SourceContractError, "older than 24 hours"):
                candidate_pool.validate_source_manifest(manifest_path, input_dir, now=now)

            write_manifest(input_dir, manifest_path, captured_at=now + timedelta(minutes=6))
            with self.assertRaisesRegex(candidate_pool.SourceContractError, "more than 5 minutes"):
                candidate_pool.validate_source_manifest(manifest_path, input_dir, now=now)

            write_manifest(input_dir, manifest_path, captured_at=now, market="CA")
            with self.assertRaisesRegex(candidate_pool.SourceContractError, "market must be US"):
                candidate_pool.validate_source_manifest(manifest_path, input_dir, now=now)

            write_manifest(input_dir, manifest_path, captured_at=now)
            source_path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(candidate_pool.SourceContractError, "SHA256 mismatch"):
                candidate_pool.validate_source_manifest(manifest_path, input_dir, now=now)

        with self.assertRaisesRegex(candidate_pool.SourceContractError, "maxReviews must be <= 100"):
            candidate_pool.validate_query_url(strict_query_url(maxReviews="101"))
        with self.assertRaisesRegex(candidate_pool.SourceContractError, "nonempty"):
            candidate_pool.validate_query_url(strict_query_url(nodeIdPaths="[]"))
        with self.assertRaisesRegex(candidate_pool.SourceContractError, "market must be exactly US"):
            candidate_pool.validate_query_url(strict_query_url(market="CA"))

    def test_formal_row_requires_child_sales_and_never_uses_parent_sales(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            input_dir.mkdir()
            (input_dir / "query_test.json").write_text(
                json.dumps(
                    [
                        candidate("B0AAAA0001", "Parent-only organizer", childSales=None, parentSales=120),
                        candidate("B0AAAA0002", "Complete organizer"),
                    ]
                ),
                encoding="utf-8",
            )
            manifest_path = root / "source_manifest.json"
            write_manifest(input_dir, manifest_path)

            result = run_pool(input_dir, root / "output", source_manifest=manifest_path)

            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            selected = json.loads((root / "output" / "test_queue.json").read_text(encoding="utf-8"))
            rejected = json.loads((root / "output" / "screened_rejected.json").read_text(encoding="utf-8"))
            self.assertEqual([row["asin"] for row in selected], ["B0AAAA0002"])
            bad = next(row for row in rejected if row["asin"] == "B0AAAA0001")
            self.assertEqual(bad["stage"], "source_contract")
            self.assertIn("childSales", bad["fields"])

    def test_versioned_excel_override_keeps_missing_parent_child_sales_without_substitution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            input_dir.mkdir()
            row = candidate(
                "B0AAAA0001",
                "Organizer with optional sales fields",
                childSales=None,
                parentSales=None,
            )
            (input_dir / "query_test.json").write_text(
                json.dumps([row]),
                encoding="utf-8",
            )
            manifest_path = root / "source_manifest.json"
            write_manifest(input_dir, manifest_path)

            result = run_pool(
                input_dir,
                root / "output",
                source_manifest=manifest_path,
                extra=["--allow-missing-parent-child-sales"],
            )

            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            selected = json.loads((root / "output" / "test_queue.json").read_text(encoding="utf-8"))
            summary = json.loads((root / "output" / "summary_test_queue.json").read_text(encoding="utf-8"))
            self.assertEqual([item["asin"] for item in selected], ["B0AAAA0001"])
            self.assertIsNone(selected[0].get("childSales"))
            self.assertIsNone(selected[0].get("parentSales"))
            sales_contract = summary["sourceContract"]["optionalParentChildSales"]
            self.assertTrue(sales_contract["enabled"])
            self.assertEqual(
                sales_contract["version"],
                candidate_pool.OPTIONAL_PARENT_CHILD_SALES_VERSION,
            )

    def test_duplicate_rows_merge_complementary_evidence_but_conflicts_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            input_dir.mkdir()
            first = candidate("B0AAAA0001", "Storage organizer", dimensions=None)
            complementary = candidate("B0AAAA0001", "Storage organizer", dimensions="10 x 5 x 2 inches")
            first["sourceRow"] = 1
            complementary["sourceRow"] = 2
            conflicting = candidate("B0BBBB0002", "Conflicting organizer A")
            conflicting_other = candidate("B0BBBB0002", "Conflicting organizer B")
            good = candidate("B0CCCC0003", "Backup organizer", brand="OtherBrand")
            (input_dir / "query_test.json").write_text(
                json.dumps([first, complementary, conflicting, conflicting_other, good]),
                encoding="utf-8",
            )
            manifest_path = root / "source_manifest.json"
            write_manifest(input_dir, manifest_path)

            result = run_pool(input_dir, root / "output", queue_size=2, source_manifest=manifest_path)

            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            selected = json.loads((root / "output" / "test_queue.json").read_text(encoding="utf-8"))
            rejected = json.loads((root / "output" / "screened_rejected.json").read_text(encoding="utf-8"))
            merged = next(row for row in selected if row["asin"] == "B0AAAA0001")
            self.assertEqual(merged["dimensions"], "10 x 5 x 2 inches")
            self.assertEqual(len(merged["sourceEvidence"]), 2)
            conflict = next(row for row in rejected if row["asin"] == "B0BBBB0002")
            self.assertIn("duplicate_conflict", conflict["reason"])
            self.assertEqual(conflict["conflictingFields"], ["title"])

    def test_category_electronics_and_clothing_leaks_are_hard_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            input_dir.mkdir()
            (input_dir / "query_test.json").write_text(
                json.dumps(
                    [
                        candidate("B0AAAA0001", "Accessory holder", categoryPath="Electronics > Accessories"),
                        candidate("B0AAAA0002", "Accessory organizer", categoryPath="Clothing > Accessories"),
                        candidate("B0AAAA0003", "Storage organizer", brand="OtherBrand"),
                    ]
                ),
                encoding="utf-8",
            )

            result = run_pool(input_dir, root / "output", legacy=True)

            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            rejected = json.loads((root / "output" / "screened_rejected.json").read_text(encoding="utf-8"))
            reasons = {row["asin"]: row["reason"] for row in rejected}
            self.assertIn("electronics", reasons["B0AAAA0001"])
            self.assertIn("clothing", reasons["B0AAAA0002"])

    def test_ranking_v2_scores_age_81_to_90_at_maximum_with_v1_rollback(self):
        rules = json.loads((ROOT / "config" / "rules.json").read_text(encoding="utf-8"))
        row = candidate("B0AAAA0001", "Storage organizer", launchAgeDays=85)

        v2 = candidate_pool.probability_score_components(
            row,
            date(2026, 7, 13),
            0,
            rules,
            candidate_pool.PRIORITY_RANKING_VERSION_V2,
        )
        v1 = candidate_pool.probability_score_components(
            row,
            date(2026, 7, 13),
            0,
            rules,
            candidate_pool.PRIORITY_RANKING_VERSION_V1,
        )

        self.assertEqual(v2["launchAge"], 4)
        self.assertEqual(v1["launchAge"], 2)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            input_dir.mkdir()
            (input_dir / "query_test.json").write_text(
                json.dumps([candidate("B0AAAA0001", "Storage organizer", launchAgeDays=85)]),
                encoding="utf-8",
            )
            result = run_pool(
                input_dir,
                root / "output",
                legacy=True,
                extra=["--use-ranking-v1"],
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            summary = json.loads((root / "output" / "summary_test_queue.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["ranking"]["version"], candidate_pool.PRIORITY_RANKING_VERSION_V1)

    def test_probability_ranking_preserves_every_candidate(self):
        rules = json.loads((ROOT / "config" / "rules.json").read_text(encoding="utf-8"))
        rows = [
            candidate(
                "B0AAAA0001",
                "High probability organizer",
                brand="Alpha",
                launchAgeDays=50,
                childSales=100,
                reviews=5,
                variations=1,
                rating=4.8,
                preselectionWarnings=[],
            ),
            candidate(
                "B0AAAA0002",
                "Lower probability organizer",
                brand="Beta",
                launchAgeDays=25,
                childSales=1000,
                reviews=100,
                variations=25,
                rating=4.0,
                preselectionWarnings=[],
            ),
            candidate(
                "B0AAAA0003",
                "Medium probability organizer",
                brand="Gamma",
                launchAgeDays=60,
                childSales=300,
                reviews=50,
                variations=8,
                rating=4.5,
                preselectionWarnings=[],
            ),
        ]

        ranked = candidate_pool.probability_rank_candidates(rows, rules, date(2026, 7, 13))

        self.assertEqual(ranked[0]["asin"], "B0AAAA0001")
        self.assertEqual({row["asin"] for row in ranked}, {row["asin"] for row in rows})
        self.assertEqual(len(ranked), len(rows))
        self.assertEqual([row["rankingPosition"] for row in ranked], [1, 2, 3])
        self.assertTrue(all(row["rankingVersion"] == candidate_pool.PRIORITY_RANKING_VERSION for row in ranked))

    def test_probability_ranking_rotates_brands_within_equal_score(self):
        rules = json.loads((ROOT / "config" / "rules.json").read_text(encoding="utf-8"))
        shared = {
            "launchAgeDays": 50,
            "childSales": 100,
            "reviews": 10,
            "variations": 1,
            "rating": 4.5,
            "preselectionWarnings": [],
        }
        rows = [
            candidate("B0AAAA0001", "Alpha organizer one", brand="Alpha", **shared),
            candidate("B0AAAA0002", "Alpha organizer two", brand="Alpha", **shared),
            candidate("B0BBBB0001", "Beta organizer", brand="Beta", **shared),
        ]

        ranked = candidate_pool.probability_rank_candidates(rows, rules, date(2026, 7, 13))

        self.assertEqual([row["brand"] for row in ranked], ["Alpha", "Beta", "Alpha"])
        self.assertEqual(len({row["asin"] for row in ranked}), 3)

    def test_post_selection_reorder_preserves_multiset_and_demotes_future_planners(self):
        rows = [
            {
                "asin": "B0AAAA0001",
                "title": "2027 Weekly Planner and Calendar",
                "launchAgeDays": 85,
                "rankingScore": 19,
                "rankingPosition": 1,
            },
            {
                "asin": "B0BBBB0002",
                "title": "Storage organizer",
                "launchAgeDays": 60,
                "rankingScore": 19,
                "rankingPosition": 2,
            },
            {
                "asin": "B0CCCC0003",
                "title": "Furniture plug set",
                "launchAgeDays": 82,
                "rankingScore": 19,
                "rankingPosition": 3,
            },
            {
                "asin": "B0DDDD0004",
                "title": "Lower score organizer",
                "launchAgeDays": 89,
                "rankingScore": 18,
                "rankingPosition": 4,
            },
            {
                "asin": "B0EEEE0005",
                "title": "Second furniture plug set",
                "launchAgeDays": 82,
                "rankingScore": 19,
                "rankingPosition": 5,
            },
        ]

        reordered, audit = candidate_pool.post_selection_queue_reorder(
            rows,
            date(2026, 7, 28),
        )

        self.assertEqual(
            [row["asin"] for row in reordered],
            [
                "B0CCCC0003",
                "B0EEEE0005",
                "B0BBBB0002",
                "B0AAAA0001",
                "B0DDDD0004",
            ],
        )
        self.assertEqual(
            {row["asin"] for row in reordered},
            {row["asin"] for row in rows},
        )
        self.assertTrue(audit["asinMultisetPreserved"])
        self.assertTrue(audit["orderChanged"])
        self.assertEqual(audit["futureYearPlannerDemotedCount"], 1)
        self.assertNotEqual(audit["beforeOrderSha256"], audit["afterOrderSha256"])
        self.assertEqual(audit["beforeMultisetSha256"], audit["afterMultisetSha256"])
        self.assertEqual([row["queuePosition"] for row in reordered], [1, 2, 3, 4, 5])
        self.assertTrue(reordered[3]["futureYearPlannerDemoted"])

    def test_cli_can_rollback_post_selection_reorder_without_changing_selected_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            reordered_output = root / "reordered"
            rollback_output = root / "rollback"
            input_dir.mkdir()
            (input_dir / "query_test.json").write_text(
                json.dumps(
                    [
                        candidate(
                            "B0AAAA0001",
                            "Storage organizer",
                            brand="Alpha",
                            launchAgeDays=40,
                        ),
                        candidate(
                            "B0BBBB0002",
                            "2027 Weekly Planner Calendar",
                            brand="Beta",
                            launchAgeDays=85,
                        ),
                        candidate(
                            "B0CCCC0003",
                            "Furniture plug set",
                            brand="Gamma",
                            launchAgeDays=80,
                        ),
                        candidate(
                            "B0DDDD0004",
                            "Oldest non-planner organizer",
                            brand="Delta",
                            launchAgeDays=90,
                        ),
                    ]
                ),
                encoding="utf-8",
            )

            reordered_result = run_pool(
                input_dir,
                reordered_output,
                queue_size=3,
                legacy=True,
            )
            rollback_result = run_pool(
                input_dir,
                rollback_output,
                queue_size=3,
                legacy=True,
                extra=["--disable-post-selection-reorder"],
            )

            self.assertEqual(reordered_result.returncode, 0, reordered_result.stderr or reordered_result.stdout)
            self.assertEqual(rollback_result.returncode, 0, rollback_result.stderr or rollback_result.stdout)
            reordered_rows = json.loads(
                (reordered_output / "test_queue.json").read_text(encoding="utf-8")
            )
            rollback_rows = json.loads(
                (rollback_output / "test_queue.json").read_text(encoding="utf-8")
            )
            reordered_summary = json.loads(
                (reordered_output / "summary_test_queue.json").read_text(encoding="utf-8")
            )
            rollback_summary = json.loads(
                (rollback_output / "summary_test_queue.json").read_text(encoding="utf-8")
            )

            self.assertEqual(
                [row["asin"] for row in reordered_rows],
                ["B0CCCC0003", "B0AAAA0001", "B0BBBB0002"],
            )
            self.assertEqual(
                [row["asin"] for row in rollback_rows],
                ["B0AAAA0001", "B0BBBB0002", "B0CCCC0003"],
            )
            self.assertEqual(
                {row["asin"] for row in reordered_rows},
                {row["asin"] for row in rollback_rows},
            )
            self.assertNotIn("B0DDDD0004", {row["asin"] for row in reordered_rows})
            self.assertTrue(reordered_summary["queueReorder"]["asinMultisetPreserved"])
            self.assertEqual(
                reordered_summary["queueReorder"]["beforeMultisetSha256"],
                reordered_summary["queueReorder"]["afterMultisetSha256"],
            )
            self.assertNotIn("queueReorder", rollback_summary)
            self.assertTrue(all("queuePosition" in row for row in reordered_rows))
            self.assertTrue(all("queuePosition" not in row for row in rollback_rows))

    def test_cli_flag_restores_legacy_order_without_changing_candidate_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            ranked_output = root / "ranked"
            legacy_output = root / "legacy"
            input_dir.mkdir()
            (input_dir / "query_test.json").write_text(
                json.dumps(
                    [
                        candidate(
                            "B0AAAA0001",
                            "Legacy first organizer",
                            brand="Alpha",
                            launchAgeDays=25,
                            childSales=50,
                            parentSales=100,
                            reviews=5,
                            variations=1,
                            rating=4.0,
                            delivery="FBA",
                        ),
                        candidate(
                            "B0BBBB0002",
                            "Probability first organizer",
                            brand="Beta",
                            launchAgeDays=25,
                            childSales=50,
                            parentSales=500,
                            reviews=5,
                            variations=1,
                            rating=4.5,
                            delivery="FBM",
                        ),
                    ]
                ),
                encoding="utf-8",
            )

            base_command = [
                sys.executable,
                str(ROOT / "scripts" / "prepare_strict_candidate_pool.py"),
                "--input-dir",
                str(input_dir),
                "--project-root",
                str(root),
                "--queue-name",
                "test_queue",
                "--queue-size",
                "2",
                "--run-date",
                "2026-07-13",
                "--allow-legacy-source",
            ]
            ranked_result = subprocess.run(
                [*base_command, "--output-dir", str(ranked_output)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            legacy_result = subprocess.run(
                [
                    *base_command,
                    "--output-dir",
                    str(legacy_output),
                    "--disable-tier1-2-ranking",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(ranked_result.returncode, 0, ranked_result.stderr or ranked_result.stdout)
            self.assertEqual(legacy_result.returncode, 0, legacy_result.stderr or legacy_result.stdout)

            ranked_rows = json.loads((ranked_output / "test_queue.json").read_text(encoding="utf-8"))
            legacy_rows = json.loads((legacy_output / "test_queue.json").read_text(encoding="utf-8"))
            ranked_summary = json.loads((ranked_output / "summary_test_queue.json").read_text(encoding="utf-8"))
            legacy_summary = json.loads((legacy_output / "summary_test_queue.json").read_text(encoding="utf-8"))

            self.assertEqual([row["asin"] for row in ranked_rows], ["B0BBBB0002", "B0AAAA0001"])
            self.assertEqual([row["asin"] for row in legacy_rows], ["B0AAAA0001", "B0BBBB0002"])
            self.assertEqual({row["asin"] for row in ranked_rows}, {row["asin"] for row in legacy_rows})
            self.assertEqual(ranked_summary["ranking"]["version"], candidate_pool.PRIORITY_RANKING_VERSION)
            self.assertNotIn("ranking", legacy_summary)
            self.assertTrue(all("rankingScore" in row for row in ranked_rows))
            self.assertTrue(all("rankingScore" not in row for row in legacy_rows))

    def test_history_asin_is_skipped_before_queue_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            output_dir = root / "output"
            input_dir.mkdir()
            (input_dir / "query_test.json").write_text(
                json.dumps(
                    [
                        candidate("B0AAAA0001", "Already delivered storage organizer"),
                        candidate("B0AAAA0002", "Fresh storage organizer"),
                    ]
                ),
                encoding="utf-8",
            )
            history = root / "history.txt"
            history.write_text("B0AAAA0001\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "prepare_strict_candidate_pool.py"),
                    "--input-dir",
                    str(input_dir),
                    "--history",
                    str(history),
                    "--project-root",
                    str(root),
                    "--output-dir",
                    str(output_dir),
                    "--queue-name",
                    "test_queue",
                    "--queue-size",
                    "1",
                    "--run-date",
                    "2026-07-11",
                    "--allow-legacy-source",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            selected = json.loads((output_dir / "test_queue.json").read_text(encoding="utf-8"))
            rejected = json.loads((output_dir / "screened_rejected.json").read_text(encoding="utf-8"))
            summary = json.loads((output_dir / "summary_test_queue.json").read_text(encoding="utf-8"))
            self.assertEqual([row["asin"] for row in selected], ["B0AAAA0002"])
            history_row = next(row for row in rejected if row["asin"] == "B0AAAA0001")
            self.assertEqual(history_row["stage"], "dedupe_history")
            self.assertEqual(summary["historySkippedCount"], 1)

    def test_attempted_asin_is_skipped_and_audited_before_queue_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            output_dir = root / "output"
            input_dir.mkdir()
            (input_dir / "query_test.json").write_text(
                json.dumps(
                    [
                        candidate("B0AAAA0001", "Previously queued storage organizer"),
                        candidate("B0AAAA0002", "Fresh storage organizer"),
                    ]
                ),
                encoding="utf-8",
            )
            attempted = root / "first_queue.txt"
            attempted.write_text("B0AAAA0001\n", encoding="utf-8")

            result = run_pool(
                input_dir,
                output_dir,
                legacy=True,
                extra=["--attempted", str(attempted)],
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            selected = json.loads((output_dir / "test_queue.json").read_text(encoding="utf-8"))
            rejected = json.loads((output_dir / "screened_rejected.json").read_text(encoding="utf-8"))
            summary = json.loads((output_dir / "summary_test_queue.json").read_text(encoding="utf-8"))
            self.assertEqual([row["asin"] for row in selected], ["B0AAAA0002"])
            attempted_row = next(row for row in rejected if row["asin"] == "B0AAAA0001")
            self.assertEqual(attempted_row["stage"], "dedupe_attempted")
            self.assertEqual(summary["attemptedSkippedCount"], 1)
            self.assertTrue(summary["attemptedExclusion"]["enabled"])
            self.assertEqual(summary["attemptedExclusion"]["skippedCount"], 1)

    def test_hard_exclusion_precedes_commercial_prefilter(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            output_dir = root / "output"
            input_dir.mkdir()
            (input_dir / "query_test.json").write_text(
                json.dumps(
                    [
                        candidate("B0AAAA0001", "Super Mario Decorations", price=1.0),
                        candidate("B0AAAA0002", "Simple storage organizer"),
                    ]
                ),
                encoding="utf-8",
            )
            history = root / "history.txt"
            history.write_text("", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "prepare_strict_candidate_pool.py"),
                    "--input-dir",
                    str(input_dir),
                    "--history",
                    str(history),
                    "--output-dir",
                    str(output_dir),
                    "--queue-name",
                    "test_queue",
                    "--queue-size",
                    "1",
                    "--run-date",
                    "2026-07-11",
                    "--allow-legacy-source",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            rejected = json.loads((output_dir / "screened_rejected.json").read_text(encoding="utf-8"))
            mario = next(row for row in rejected if row["asin"] == "B0AAAA0001")
            self.assertEqual(mario["stage"], "exclusion")
            self.assertIn("super mario", mario["reason"])


if __name__ == "__main__":
    unittest.main()
