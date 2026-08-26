from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "analyze_mcp_validation_task_pair.py"
ORCHESTRATOR = ROOT / "scripts" / "mcp_hybrid_prefetch_orchestrator.py"
PLAN_PATH = ROOT / "docs" / "mcp_hybrid_shadow_plan_20260729.json"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MOD = load_module("analyze_mcp_validation_task_pair_test", SCRIPT)
ORCH = load_module("mcp_hybrid_prefetch_orchestrator_pair_test", ORCHESTRATOR)


def make_baseline(plan: dict) -> dict:
    rows = []
    e_reject_used = False
    for index, sample in enumerate(plan["sample"]):
        outcome = sample["expectedOutcome"]
        gate_c = "pass"
        gate_d = "pass"
        gate_e = "pass"
        short_gate = ""
        trend = "stable"
        if outcome == "reject" and not e_reject_used:
            e_reject_used = True
            gate_e = "reject"
            short_gate = "E"
            trend = "declining"
        elif outcome == "reject":
            gate_c = "reject"
            gate_d = "not_run"
            gate_e = "not_run"
            short_gate = "C"
            trend = "no_data"
        product = {
            "asin": sample["asin"],
            "title": f"Sample product {index}",
            "brand": "SampleBrand",
            "price": 19.99,
            "rating": 4.5,
            "reviews": 10,
            "variationsCount": 1,
            "imageUrl": f"https://m.media-amazon.com/images/I/IMAGE{index:02d}._AC_US200_.jpg",
            "categoryPath": "Office Products > Sample",
            "itemDimensions": "10 x 8 x 2 inches",
            "dimensions": "10 x 8 x 2 inches",
            "packageDimensions": "11 x 9 x 3 inches",
            "itemWeight": "1 pound",
            "packageWeight": "1.2 pounds",
            "priceTrendClass": trend,
        }
        rows.append(
            {
                "asin": sample["asin"],
                "expectedOutcome": outcome,
                "sourceClass": sample["sourceClass"],
                "sourceRoot": sample["sourceRoot"],
                "browser": {
                    "gate": {
                        "asin": sample["asin"],
                        "outcome": outcome,
                        "shortCircuitGate": short_gate,
                        "gateA": "not_evaluated_in_runner",
                        "gateB": "not_evaluated_in_runner",
                        "gateC": gate_c,
                        "gateD": gate_d,
                        "gateE": gate_e,
                        "gateF": "not_evaluated_in_runner",
                        "currentPrice": "19.99" if gate_e in {"pass", "reject"} else "",
                        "priceTrendClass": trend,
                        "dimensions": "10 x 8 x 2 inches",
                    },
                    "timing": {"totalMs": "1000"},
                },
                "productSnapshot": product,
            }
        )
    return {
        "schemaVersion": MOD.BASELINE_SCHEMA,
        "planId": plan["planId"],
        "sampleSize": 30,
        "passCount": sum(row["expectedOutcome"] == "pass" for row in rows),
        "rejectCount": sum(row["expectedOutcome"] == "reject" for row in rows),
        "rows": rows,
    }


def provenance(tool: str, fields: dict, *, semantics: str = "shadow_advisory") -> dict:
    return {
        key: {
            "sourceTool": tool,
            "sourcePath": f"data.{key}",
            "semantics": semantics,
        }
        for key, value in fields.items()
        if key != "asin" and MOD.nonempty(value)
    }


def make_result(request: dict, fields: dict, *, status: str = "succeeded") -> dict:
    tool = request["tool"]
    target = request["targetAsin"]
    semantics = "traffic_structure_advisory_not_gate_c" if tool == "traffic_listing_stat" else "shadow_advisory"
    if tool == "product_research":
        semantics = "discovery_only_candidate_page"
    return {
        "schemaVersion": MOD.RESULT_SCHEMA,
        "taskId": request["taskId"],
        "runId": request["runId"],
        "requestId": request["requestId"],
        "requestHash": request["requestHash"],
        "claimId": request["result"]["claimId"],
        "tool": request["result"]["tool"],
        "targetAsin": target,
        "actualAsin": target,
        "status": status,
        "officialStatus": request["result"]["status"],
        "startedAt": "2026-07-29T10:00:00Z",
        "completedAt": "2026-07-29T10:00:01Z",
        "sourceResultSchema": MOD.OFFICIAL_RESULT_SCHEMA,
        "sourceResultSha256": request["resultSha256"],
        "derivedFromOfficialTaskResult": True,
        "rawResponse": {
            **request["rawResponseArchive"],
            "capturedAt": "2026-07-29T10:00:00Z",
        },
        "fields": fields,
        "fieldProvenance": provenance(tool, fields, semantics=semantics),
        "normalizationError": None,
        "error": None,
        "finalAuthority": False,
        "usableForFinal": False,
        "browserFallbackRequired": True,
    }


def make_execution(plan: dict, task: dict, baseline: dict, source_files: dict) -> dict:
    baseline_by_asin = {row["asin"]: row for row in baseline["rows"]}
    replay_final = json.loads(Path(source_files["finalCandidates"]["path"]).read_text(encoding="utf-8"))
    replay_rejected = json.loads(Path(source_files["rejectedAudit"]["path"]).read_text(encoding="utf-8"))
    replay_by_asin = {
        row["asin"]: ("pass", row) for row in replay_final
    } | {
        row["asin"]: ("reject", row) for row in replay_rejected
    }
    results = []
    for request in task["requests"]:
        tool = request["tool"]
        asin = request["targetAsin"]
        if tool == "product_research":
            product = baseline["rows"][0]["productSnapshot"]
            fields = {
                "candidates": [
                    {
                        "asin": product["asin"],
                        "title": product["title"],
                        "brand": product["brand"],
                        "price": 19.99,
                        "rating": 4.5,
                        "reviews": 10,
                        "variations": 1,
                        "amzUnit": 100,
                        "imageUrl": product["imageUrl"],
                    }
                ]
            }
        elif tool == "asin_detail":
            product = baseline_by_asin[asin]["productSnapshot"]
            fields = {
                "asin": asin,
                "title": product["title"],
                "brand": product["brand"],
                "price": product["price"],
                "rating": product["rating"],
                "reviews": product["reviews"],
                "variations": product["variationsCount"],
                "imageUrl": product["imageUrl"],
                "categoryPath": product["categoryPath"],
                "dimensions": product["itemDimensions"],
                "packageDimensions": product["packageDimensions"],
                "itemWeight": product["itemWeight"],
                "packageWeight": product["packageWeight"],
                "parentAsin": None,
            }
        elif tool == "asin_sales_trend":
            trend = baseline_by_asin[asin]["browser"]["gate"]["priceTrendClass"]
            if trend == "no_data":
                trend = "stable"
            fields = {"asin": asin, "priceTrendClass": trend, "pricePointCount": 3}
        else:
            fields = {
                "asin": asin,
                "freeTrafficCount": 80,
                "paidTrafficCount": 20,
                "freeTrafficShare": 0.8,
                "paidTrafficShare": 0.2,
                "relationCounts": {"organic": 80, "sp": 20},
            }
        results.append(make_result(request, fields))
    paired_rows = [
        {
            "asin": row["asin"],
            "baselineOutcome": row["expectedOutcome"],
            "hybridOutcome": row["expectedOutcome"],
            "baselineEvidenceSha256": MOD.payload_sha256(baseline_by_asin[row["asin"]]),
            "hybridEvidenceSha256": MOD.payload_sha256(replay_by_asin[row["asin"]][1]),
            "outcomeDerivedFrom": (
                "final_candidates_data" if row["expectedOutcome"] == "pass" else "rejected_audit_data"
            ),
            "mcpFinalAuthority": False,
            "browserReplayAuthoritative": True,
        }
        for row in baseline["rows"]
    ]
    return {
        "schemaVersion": MOD.RESULTS_SCHEMA,
        "taskId": task["taskId"],
        "runId": task["runId"],
        "finalAuthority": False,
        "usableForFinal": False,
        "sourceIntegrity": {
            "officialTaskValidated": True,
            "taskFinalized": True,
            "officialSummaryVerified": True,
            "rawArchiveCount": 91,
            "rawArchivesVerified": True,
            "officialManifestHashes": {
                "claimManifestSha256": "1" * 64,
                "resultManifestSha256": "2" * 64,
                "rawManifestSha256": "3" * 64,
            },
            "pairedOutcomesDerived": True,
            "liveSmokeDerived": True,
            "files": source_files,
            "finalAuthority": False,
        },
        "results": results,
        "pairedOutcomes": {
            "schemaVersion": MOD.PAIRED_OUTCOMES_SCHEMA,
            "planId": plan["planId"],
            "authoritySource": "current_replay_and_acceptance",
            "aToFReplayed": True,
            "derivedFromReplayArtifacts": True,
            "sourceFiles": {
                "finalCandidates": source_files["finalCandidates"],
                "rejectedAudit": source_files["rejectedAudit"],
                "runSummary": source_files["runSummary"],
                "browserBaseline": source_files["baseline"],
            },
            "finalAuthority": False,
            "rows": paired_rows,
        },
        "liveSmoke": {
            "completed": True,
            "passed": True,
            "sourceDerived": True,
            "evidenceHashVerified": True,
            "screenshotHashVerified": True,
            "asinInSample": True,
            "taskBound": True,
            "currentCombination": True,
            "collectorEnabled": True,
            "runnerEnabled": True,
            "browserReplayRequired": True,
            "queueUnchanged": True,
            "auditsPersisted": True,
            "batchGenerated": False,
            "strictHistoryBefore": 57,
            "strictHistoryAfter": 57,
            "providerCallsBefore": 36,
            "providerCallsAfter": 36,
            "sourceFiles": {
                "smoke": source_files["smoke"],
                "hashManifest": source_files["hashManifest"],
                "screenshot": source_files["screenshot"],
            },
            "finalAuthority": False,
            "gateBypassAuthorized": False,
        },
    }


class ValidationTaskPairAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        cls.baseline = make_baseline(cls.plan)
        discovery = {
            "request": {
                "marketplace": "US",
                "page": 1,
                "size": 60,
                "nodeIdPaths": ["1055398", "228013", "1064954"],
                "minAmzUnit": 50,
                "maxAmzUnit": 300,
                "minPrice": 9.9,
                "maxPrice": 50,
                "minRating": 4,
                "maxRatings": 100,
                "minVariations": 1,
                "maxVariations": 25,
            }
        }
        cls.task = ORCH.plan_validation_task(
            cls.plan,
            sample_sha256=MOD.file_sha256(PLAN_PATH),
            discovery_request=discovery,
            run_id="mcp-validate-task-pair-test",
            created_at=datetime(2026, 7, 29, tzinfo=timezone.utc),
        )
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT)
        cls.temp_root = Path(cls.temp.name)
        raw_root = cls.temp_root / "raw_responses"
        raw_root.mkdir()
        for index, request in enumerate(cls.task["requests"]):
            payload = json.dumps(
                {"fixture": True, "requestId": request["requestId"]},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            sha = hashlib.sha256(payload).hexdigest()
            raw_path = raw_root / f"{request['requestId']}.{sha}.json"
            raw_path.write_bytes(payload)
            official = {
                "schemaVersion": MOD.OFFICIAL_RESULT_SCHEMA,
                "taskId": cls.task["taskId"],
                "runId": cls.task["runId"],
                "requestId": request["requestId"],
                "requestHash": request["requestHash"],
                "claimId": f"claim-{index:03d}",
                "targetAsin": request.get("targetAsin"),
                "actualAsin": request.get("targetAsin"),
                "tool": {"name": request["tool"], "version": "fixture-1"},
                "status": "succeeded",
                "startedAt": "2026-07-29T10:00:00Z",
                "completedAt": "2026-07-29T10:00:01Z",
                "rawResponse": {"sha256": sha, "byteLength": len(payload), "capturedAt": "2026-07-29T10:00:00Z"},
                "responseMetadata": {},
                "error": None,
                "usableForFinal": False,
                "finalAuthority": False,
            }
            request.update(
                {
                    "status": "succeeded",
                    "attemptsRecorded": 1,
                    "result": official,
                    "resultSha256": MOD.payload_sha256(official),
                    "rawResponseArchive": {"path": str(raw_path), "sha256": sha, "byteLength": len(payload)},
                }
            )
        cls.task["status"] = "finalized"
        cls.task["finalization"] = {"finalAuthority": False}
        source_values = {
            "plan": {"name": "plan"},
            "task": {"name": "task"},
            "summary": {"name": "summary"},
            "baseline": cls.baseline,
            "finalCandidates": [
                {"asin": row["asin"], "fixture": "pass"}
                for row in cls.baseline["rows"]
                if row["expectedOutcome"] == "pass"
            ],
            "rejectedAudit": [
                {"asin": row["asin"], "fixture": "reject"}
                for row in cls.baseline["rows"]
                if row["expectedOutcome"] == "reject"
            ],
            "runSummary": {
                "attempts": 30,
                "qualifiedCount": sum(row["expectedOutcome"] == "pass" for row in cls.baseline["rows"]),
                "rejectedCount": sum(row["expectedOutcome"] == "reject" for row in cls.baseline["rows"]),
            },
            "smoke": {"fixture": "smoke"},
            "hashManifest": {"fixture": "hashes"},
            "screenshot": {"fixture": "screenshot"},
        }
        cls.source_files = {}
        for name, value in source_values.items():
            path = cls.temp_root / f"{name}.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            cls.source_files[name] = {
                "path": str(path),
                "sha256": MOD.file_sha256(path),
                "byteLength": path.stat().st_size,
            }

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def report(self, execution: dict) -> dict:
        return MOD.build_report(
            self.plan,
            self.task,
            self.baseline,
            execution,
            plan_sha256=MOD.file_sha256(PLAN_PATH),
        )

    def test_safe_complete_pair_passes_shadow_but_never_authorizes_af(self) -> None:
        report = self.report(make_execution(self.plan, self.task, self.baseline, self.source_files))
        self.assertEqual(report["shadowPairedAcceptance"], "PASS")
        self.assertTrue(report["zeroFalsePositive"]["pass"])
        self.assertEqual(report["trafficListingStat"]["gateCComparable"], 0)
        self.assertFalse(report["trafficListingStat"]["gateCSubstitutionAuthorized"])
        self.assertEqual(report["toolRoles"]["product_research"]["role"], "discovery_only")
        self.assertFalse(report["formalRunAuthorized"])
        self.assertFalse(report["gateBypassAuthorized"])

    def test_gate_e_advisory_false_positive_blocks_acceptance(self) -> None:
        execution = make_execution(self.plan, self.task, self.baseline, self.source_files)
        rejected_asin = next(
            row["asin"]
            for row in self.baseline["rows"]
            if row["browser"]["gate"]["gateE"] == "reject"
        )
        trend = next(
            row
            for row in execution["results"]
            if MOD.tool_name(row["tool"]) == "asin_sales_trend" and row["targetAsin"] == rejected_asin
        )
        trend["fields"]["priceTrendClass"] = "stable"
        report = self.report(execution)
        self.assertEqual(report["shadowPairedAcceptance"], "FAIL")
        self.assertEqual(report["gateAdvisoryChecks"]["E"]["unsafeFalsePositive"], 1)
        self.assertFalse(report["zeroFalsePositive"]["pass"])

    def test_traffic_listing_stat_gate_c_claim_is_rejected(self) -> None:
        execution = make_execution(self.plan, self.task, self.baseline, self.source_files)
        traffic = next(
            row for row in execution["results"] if MOD.tool_name(row["tool"]) == "traffic_listing_stat"
        )
        traffic["fields"]["weeksRead"] = 4
        traffic["fieldProvenance"]["weeksRead"] = {
            "sourceTool": "traffic_listing_stat",
            "sourcePath": "data.weeksRead",
            "semantics": "traffic_structure_advisory_not_gate_c",
        }
        report = self.report(execution)
        self.assertEqual(report["shadowPairedAcceptance"], "FAIL")
        self.assertEqual(report["trafficListingStat"]["gateCClaimCount"], 1)
        self.assertEqual(report["mcpGateCoverage"]["C"]["comparable"], 0)
        self.assertFalse(report["formalRunAuthorized"])

    def test_product_research_positive_authority_claim_is_rejected(self) -> None:
        execution = make_execution(self.plan, self.task, self.baseline, self.source_files)
        research = next(
            row for row in execution["results"] if MOD.tool_name(row["tool"]) == "product_research"
        )
        research["fields"]["candidates"][0]["strictQualified"] = True
        report = self.report(execution)
        self.assertEqual(report["shadowPairedAcceptance"], "FAIL")
        self.assertGreater(report["zeroFalsePositive"]["authorityViolationCount"], 0)
        self.assertFalse(report["productResearch"]["discoveryContractPass"])

    def test_missing_request_is_counted_as_tool_error(self) -> None:
        execution = make_execution(self.plan, self.task, self.baseline, self.source_files)
        removed = execution["results"].pop()
        report = self.report(execution)
        tool = MOD.tool_name(removed["tool"])
        self.assertEqual(report["shadowPairedAcceptance"], "FAIL")
        self.assertEqual(report["toolMetrics"][tool]["missing"], 1)
        self.assertGreater(report["toolMetrics"][tool]["errorPct"], 0)
        self.assertFalse(report["checks"]["exact91ResultSet"])


if __name__ == "__main__":
    unittest.main()
