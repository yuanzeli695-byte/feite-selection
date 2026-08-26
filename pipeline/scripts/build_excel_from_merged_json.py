#!/usr/bin/env python3
"""Build an accepted strict-selection workbook from merged Runner batch JSON files."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROJECT_ROOT = SCRIPT_DIR.parent
AUTOMATION_VERSION = "merged-json-to-excel-v1.1.0"
IMAGE_DOWNLOAD_POLICY = "bounded_parallel_image_cache_v1"
WORKBOOK_EXIT_POLICY = "force_exit_after_awaited_build_v1"
RESULT_SCHEMA = "sellerSpriteMergedJsonExcelResult/v1"
MANIFEST_SCHEMA = "sellerSpriteMergedJsonExcelEvidence/v1"
BATCH_SCHEMA = "sellerSpriteIntegratedBatch/v0.3.0"
ASIN_RE = re.compile(r"^B0[A-Z0-9]{8}$")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
SAFE_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


class AutomationError(RuntimeError):
    def __init__(self, message: str, *, stage: str = "validation", details: Any = None) -> None:
        super().__init__(message)
        self.stage = stage
        self.details = details


@dataclass(frozen=True)
class BatchEvidence:
    source_path: Path
    payload: dict[str, Any]
    batch_name: str
    queue_hash: str
    queue_asins: tuple[str, ...]
    result_asins: tuple[str, ...]
    strict_pass_asins: tuple[str, ...]
    runner_versions: frozenset[str]
    collector_versions: frozenset[str]


@dataclass(frozen=True)
class CandidateSource:
    path: Path
    rows: tuple[dict[str, Any], ...]
    by_asin: dict[str, dict[str, Any]]

    @property
    def asins(self) -> frozenset[str]:
        return frozenset(self.by_asin)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_asin(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text if ASIN_RE.fullmatch(text) else ""


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _number_like(value: Any) -> bool:
    if isinstance(value, bool) or value in (None, ""):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _candidate_row_is_formal(row: Any) -> bool:
    if not isinstance(row, dict) or not normalize_asin(row.get("asin")):
        return False
    title = str(row.get("title") or row.get("pageTitle") or "").strip()
    category = str(row.get("categoryPath") or row.get("category") or "").strip()
    image_url = str(row.get("image") or row.get("imageUrl") or "").strip()
    launch_date = str(row.get("launchDate") or "").strip()
    source_page = str(row.get("sourcePage") or "").strip()
    variations = row.get("variations") if row.get("variations") not in (None, "") else row.get("variationsCount")
    return bool(
        title
        and category
        and image_url.startswith(("https://", "http://"))
        and launch_date
        and source_page
        and _number_like(row.get("price"))
        and _number_like(row.get("rating"))
        and _number_like(variations)
    )


def load_candidate_source(path: Path) -> CandidateSource | None:
    try:
        payload = read_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, list) or not payload or any(not _candidate_row_is_formal(row) for row in payload):
        return None
    by_asin: dict[str, dict[str, Any]] = {}
    for row in payload:
        asin = normalize_asin(row.get("asin"))
        if asin in by_asin:
            return None
        by_asin[asin] = row
    return CandidateSource(path=path.resolve(), rows=tuple(payload), by_asin=by_asin)


def discover_candidate_sources(search_roots: list[Path]) -> list[CandidateSource]:
    sources: list[CandidateSource] = []
    seen: set[Path] = set()
    for root in search_roots:
        root = root.resolve()
        if not root.is_dir():
            raise AutomationError(f"Candidate search root does not exist: {root}", stage="candidate_discovery")
        for path in sorted(root.rglob("*.json")):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            source = load_candidate_source(resolved)
            if source is not None:
                sources.append(source)
    if not sources:
        raise AutomationError("No formal candidate JSON files were found", stage="candidate_discovery")
    return sources


def match_candidate_source(batch: BatchEvidence, sources: list[CandidateSource]) -> CandidateSource:
    required = set(batch.queue_asins)
    matches = [source for source in sources if required.issubset(source.asins)]
    if not matches:
        raise AutomationError(
            f"No candidate JSON covers the full queue for batch {batch.batch_name}",
            stage="candidate_mapping",
        )
    smallest_extra = min(len(source.asins - required) for source in matches)
    finalists = [source for source in matches if len(source.asins - required) == smallest_extra]
    if len(finalists) != 1:
        raise AutomationError(
            f"Ambiguous candidate JSON mapping for batch {batch.batch_name}",
            stage="candidate_mapping",
            details=[str(source.path) for source in finalists],
        )
    return finalists[0]


def validate_batch(
    path: Path,
    *,
    allowed_runner_versions: set[str],
    allowed_collector_versions: set[str],
    allow_running_snapshot: bool,
) -> BatchEvidence:
    path = path.resolve()
    if not path.is_file():
        raise AutomationError(f"Batch JSON does not exist: {path}")
    payload = read_json(path)
    if not isinstance(payload, dict) or payload.get("schemaVersion") != BATCH_SCHEMA:
        raise AutomationError(f"Unsupported batch schema in {path}: {getattr(payload, 'get', lambda *_: None)('schemaVersion')}")
    status = str(payload.get("status") or "").strip()
    if status != "done" and not (status == "running" and allow_running_snapshot):
        raise AutomationError(
            f"Batch status must be done; running snapshots require --allow-running-snapshot: {path}"
        )
    batch_name = str(payload.get("batchName") or "").strip()
    queue_hash = str(payload.get("queueHash") or "").strip()
    generated_at = str(payload.get("generatedAt") or payload.get("createdAt") or "").strip()
    queue = payload.get("queue")
    results = payload.get("results")
    if not batch_name or not queue_hash or not generated_at:
        raise AutomationError(f"batchName, queueHash, and generatedAt/createdAt are required: {path}")
    if not isinstance(queue, list) or not queue:
        raise AutomationError(f"Batch queue is empty: {path}")
    queue_asins = tuple(normalize_asin(value) for value in queue)
    if any(not asin for asin in queue_asins) or len(set(queue_asins)) != len(queue_asins):
        raise AutomationError(f"Batch queue contains invalid or duplicate ASINs: {path}")
    if not isinstance(results, list) or not results:
        raise AutomationError(f"Batch results are empty: {path}")

    result_asins: list[str] = []
    strict_pass_asins: list[str] = []
    runner_versions: set[str] = set()
    collector_versions: set[str] = set()
    queue_set = set(queue_asins)
    for index, row in enumerate(results, start=1):
        if not isinstance(row, dict):
            raise AutomationError(f"results[{index}] is not an object: {path}")
        asin = normalize_asin(row.get("targetAsin"))
        if not asin or asin not in queue_set:
            raise AutomationError(f"results[{index}] targetAsin is invalid or outside the queue: {path}")
        result_asins.append(asin)
        gate = ((row.get("telemetry") or {}).get("gate") or {})
        runner_version = str(gate.get("runnerVersion") or "").strip()
        collector_version = str(row.get("collectorVersion") or gate.get("collectorVersion") or "").strip()
        if not runner_version:
            raise AutomationError(f"results[{index}] is missing Runner version: {path}")
        if runner_version not in allowed_runner_versions:
            raise AutomationError(
                f"results[{index}] Runner version {runner_version} is not explicitly allowed: {path}"
            )
        runner_versions.add(runner_version)
        if collector_version:
            if collector_version not in allowed_collector_versions:
                raise AutomationError(
                    f"results[{index}] Collector version {collector_version} is not explicitly allowed: {path}"
                )
            collector_versions.add(collector_version)

        strict_pass = row.get("qualified") is True and str(row.get("strictDecision") or "").strip() == "pass"
        if (row.get("qualified") is True) != (str(row.get("strictDecision") or "").strip() == "pass"):
            raise AutomationError(f"results[{index}] qualified/strictDecision is inconsistent: {path}")
        if strict_pass:
            actual_asin = normalize_asin(row.get("actualAsin"))
            if str(row.get("status") or "") != "ok" or str(row.get("decision") or "") != "pass":
                raise AutomationError(f"results[{index}] strict pass lacks ok/pass evidence: {path}")
            if actual_asin != asin:
                raise AutomationError(f"results[{index}] strict pass has an ASIN mismatch: {path}")
            if not collector_version:
                raise AutomationError(f"results[{index}] strict pass is missing Collector version: {path}")
            strict_pass_asins.append(asin)

    if len(set(result_asins)) != len(result_asins):
        raise AutomationError(f"Batch results contain duplicate targetAsin values: {path}")
    return BatchEvidence(
        source_path=path,
        payload=payload,
        batch_name=batch_name,
        queue_hash=queue_hash,
        queue_asins=queue_asins,
        result_asins=tuple(result_asins),
        strict_pass_asins=tuple(strict_pass_asins),
        runner_versions=frozenset(runner_versions),
        collector_versions=frozenset(collector_versions),
    )


def collect_strict_pass_asins(batches: list[BatchEvidence]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for batch in batches:
        for asin in batch.strict_pass_asins:
            if asin not in seen:
                seen.add(asin)
                ordered.append(asin)
    return ordered


def validate_title_overrides(path: Path, required_asins: list[str]) -> dict[str, str]:
    if not path.is_file():
        raise AutomationError(f"Chinese title override JSON does not exist: {path}", stage="title_validation")
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise AutomationError("Chinese title override JSON must be an object", stage="title_validation")
    normalized = {
        normalize_asin(key): str(value or "").strip()
        for key, value in payload.items()
        if normalize_asin(key)
    }
    missing = [asin for asin in required_asins if not normalized.get(asin) or not CJK_RE.search(normalized[asin])]
    if missing:
        raise AutomationError(
            "Every strict-pass ASIN requires a non-empty Chinese title",
            stage="title_validation",
            details=missing,
        )
    return normalized


def _safe_fragment(value: str, fallback: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]", "", value)[:24]
    return text or fallback


def _run_command(
    command: list[str],
    *,
    project_root: Path,
    stage: str,
    timeout_seconds: int,
    node_modules: Path | None = None,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if node_modules is not None:
        current = env.get("NODE_PATH", "")
        env["NODE_PATH"] = str(node_modules) if not current else f"{node_modules}{os.pathsep}{current}"
    if env_overrides:
        env.update(env_overrides)
    try:
        completed = subprocess.run(
            command,
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise AutomationError(f"{stage} timed out", stage=stage) from error
    if completed.returncode != 0:
        raise AutomationError(
            f"{stage} failed with exit code {completed.returncode}",
            stage=stage,
            details={"stdout": completed.stdout[-4000:], "stderr": completed.stderr[-4000:]},
        )
    return completed


def _default_node_exe() -> Path | None:
    bundled = (
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "node"
        / "bin"
        / "node.exe"
    )
    if bundled.is_file():
        return bundled
    system_node = shutil.which("node")
    return Path(system_node).resolve() if system_node else None


def _node_modules_for(node_exe: Path) -> Path | None:
    candidate = node_exe.resolve().parent.parent / "node_modules"
    return candidate if candidate.is_dir() else None


def execute(args: argparse.Namespace) -> dict[str, Any]:
    project_root = args.project_root.resolve()
    output_dir = args.output_dir.resolve()
    if not project_root.is_dir():
        raise AutomationError(f"Project root does not exist: {project_root}", stage="startup")
    if is_within(output_dir, project_root):
        raise AutomationError(
            "Output must be outside the canonical project root to protect formal history scanning",
            stage="startup",
        )
    if output_dir.exists():
        raise AutomationError(f"Output directory already exists: {output_dir}", stage="startup")
    if not SAFE_RUN_ID_RE.fullmatch(args.run_id):
        raise AutomationError("run-id must contain only ASCII letters, digits, dot, underscore, or hyphen", stage="startup")
    try:
        date.fromisoformat(args.run_date)
    except ValueError as error:
        raise AutomationError("run-date must use YYYY-MM-DD", stage="startup") from error
    if args.image_workers < 1 or args.image_workers > 8:
        raise AutomationError("image-workers must be between 1 and 8", stage="startup")
    if args.image_cache_ttl_minutes < 1:
        raise AutomationError("image-cache-ttl-minutes must be positive", stage="startup")

    node_exe = args.node_exe.resolve() if args.node_exe else _default_node_exe()
    if node_exe is None or not node_exe.is_file():
        raise AutomationError("Node.js executable was not found; pass --node-exe", stage="startup")
    node_modules = args.node_modules.resolve() if args.node_modules else _node_modules_for(node_exe)
    if node_modules is None or not node_modules.is_dir():
        raise AutomationError("Artifact-tool node_modules was not found; pass --node-modules", stage="startup")

    allowed_runner_versions = {str(value).strip() for value in args.allow_runner_version if str(value).strip()}
    allowed_collector_versions = {str(value).strip() for value in args.allow_collector_version if str(value).strip()}
    batches = [
        validate_batch(
            path,
            allowed_runner_versions=allowed_runner_versions,
            allowed_collector_versions=allowed_collector_versions,
            allow_running_snapshot=args.allow_running_snapshot,
        )
        for path in args.batch_json
    ]
    strict_pass_asins = collect_strict_pass_asins(batches)
    if not strict_pass_asins:
        raise AutomationError("The supplied batches contain no strict-pass ASINs")
    target = args.target if args.target is not None else len(strict_pass_asins)
    if target < 1 or target > len(strict_pass_asins):
        raise AutomationError(
            f"target must be between 1 and the strict-pass count ({len(strict_pass_asins)})"
        )
    title_overrides = validate_title_overrides(args.title_overrides.resolve(), strict_pass_asins)

    search_roots = [path.resolve() for path in (args.candidate_search_root or [project_root / "runs"])]
    candidate_sources = discover_candidate_sources(search_roots)
    matches = [match_candidate_source(batch, candidate_sources) for batch in batches]

    output_dir.mkdir(parents=True, exist_ok=False)
    evidence_dir = output_dir / "evidence"
    image_dir = output_dir / "images"
    replay_dir = output_dir / "replay"
    sandbox_root = output_dir / "sandbox_project"
    evidence_dir.mkdir()
    image_dir.mkdir()
    (sandbox_root / "history").mkdir(parents=True)

    history_source = project_root / "history" / "strict_qualified_asins.json"
    if not history_source.is_file():
        raise AutomationError(f"Formal strict history does not exist: {history_source}", stage="history_snapshot")
    production_history_sha256 = file_sha256(history_source)
    shutil.copy2(history_source, sandbox_root / "history" / "strict_qualified_asins.json")

    evidence_pairs: list[tuple[Path, Path]] = []
    evidence_batches: list[dict[str, Any]] = []
    for index, (batch, candidate) in enumerate(zip(batches, matches), start=1):
        fragment = _safe_fragment(batch.queue_hash, f"batch{index}")
        batch_copy = evidence_dir / f"batch_{index:03d}_{fragment}.json"
        candidate_copy = evidence_dir / f"candidate_{index:03d}_{fragment}.json"
        shutil.copy2(batch.source_path, batch_copy)
        shutil.copy2(candidate.path, candidate_copy)
        evidence_pairs.append((batch_copy, candidate_copy))
        evidence_batches.append(
            {
                "sequence": index,
                "batchName": batch.batch_name,
                "status": batch.payload.get("status"),
                "queueHash": batch.queue_hash,
                "queueCount": len(batch.queue_asins),
                "resultCount": len(batch.result_asins),
                "strictPassAsins": list(batch.strict_pass_asins),
                "runnerVersions": sorted(batch.runner_versions),
                "collectorVersions": sorted(batch.collector_versions),
                "batchSourcePath": str(batch.source_path),
                "batchEvidencePath": str(batch_copy),
                "batchSha256": file_sha256(batch_copy),
                "candidateSourcePath": str(candidate.path),
                "candidateEvidencePath": str(candidate_copy),
                "candidateSha256": file_sha256(candidate_copy),
                "candidateExtraAsinCount": len(candidate.asins - set(batch.queue_asins)),
            }
        )

    copied_titles = evidence_dir / "zh_title_overrides.json"
    write_json(copied_titles, {asin: title_overrides[asin] for asin in strict_pass_asins})
    pass_rows: list[dict[str, Any]] = []
    for asin in strict_pass_asins:
        rows = [candidate.by_asin[asin] for candidate in matches if asin in candidate.by_asin]
        if not rows:
            raise AutomationError(f"No candidate row found for strict-pass ASIN {asin}", stage="candidate_mapping")
        pass_rows.append(rows[0])
    image_candidates_path = evidence_dir / "strict_pass_image_candidates.json"
    write_json(image_candidates_path, pass_rows)

    manifest_path = output_dir / "evidence_manifest.json"
    manifest = {
        "schemaVersion": MANIFEST_SCHEMA,
        "automationVersion": AUTOMATION_VERSION,
        "createdAt": now_iso(),
        "runId": args.run_id,
        "runDate": args.run_date,
        "target": target,
        "strictPassAsins": strict_pass_asins,
        "allowRunningSnapshot": bool(args.allow_running_snapshot),
        "allowedRunnerVersions": sorted(allowed_runner_versions),
        "allowedCollectorVersions": sorted(allowed_collector_versions),
        "productionHistoryWriteProtected": True,
        "productionHistorySha256": production_history_sha256,
        "imageDownloadPolicy": {
            "name": IMAGE_DOWNLOAD_POLICY,
            "workers": args.image_workers,
            "cacheEnabled": not args.disable_image_cache_v1,
            "cacheDir": None if args.disable_image_cache_v1 else str(args.image_cache_dir.resolve()),
            "cacheTtlMinutes": args.image_cache_ttl_minutes,
        },
        "workbookExitPolicy": (
            "natural_event_loop" if args.disable_workbook_force_exit_v1 else WORKBOOK_EXIT_POLICY
        ),
        "titleOverridesPath": str(copied_titles),
        "titleOverridesSha256": file_sha256(copied_titles),
        "imageCandidatesPath": str(image_candidates_path),
        "batches": evidence_batches,
    }
    write_json(manifest_path, manifest)

    image_command = [
        sys.executable,
        str(project_root / "scripts" / "download_candidate_images.py"),
        str(image_candidates_path),
        str(image_dir),
        "--report",
        str(output_dir / "image_download_report.json"),
        "--workers",
        str(args.image_workers),
        "--cache-ttl-minutes",
        str(args.image_cache_ttl_minutes),
    ]
    if not args.disable_image_cache_v1:
        image_command.extend(["--cache-dir", str(args.image_cache_dir.resolve())])
    _run_command(
        image_command,
        project_root=project_root,
        stage="image_download",
        timeout_seconds=args.command_timeout_seconds,
    )

    replay_command = [sys.executable, str(project_root / "scripts" / "replay_existing_batch.py")]
    for batch_copy, candidate_copy in evidence_pairs:
        replay_command.extend(["--batch-json", str(batch_copy), "--candidates-json", str(candidate_copy)])
    replay_command.extend(
        [
            "--image-dir",
            str(image_dir),
            "--run-id",
            args.run_id,
            "--run-dir",
            str(replay_dir),
            "--run-date",
            args.run_date,
            "--target",
            str(target),
            "--max-attempts",
            str(sum(len(batch.result_asins) for batch in batches) + 10),
            "--project-root",
            str(sandbox_root),
            "--title-overrides",
            str(copied_titles),
            "--runner-current-price-v1",
        ]
    )
    _run_command(
        replay_command,
        project_root=project_root,
        stage="replay",
        timeout_seconds=args.command_timeout_seconds,
    )
    summary = read_json(replay_dir / "run_summary.json")
    if not summary.get("completedTarget") or int(summary.get("qualifiedCount") or 0) != target:
        result = {
            "schemaVersion": RESULT_SCHEMA,
            "automationVersion": AUTOMATION_VERSION,
            "accepted": False,
            "stage": "target_incomplete",
            "machineAcceptancePassed": False,
            "visualAcceptanceRequired": False,
            "productionHistoryUpdated": False,
            "target": target,
            "qualifiedCount": int(summary.get("qualifiedCount") or 0),
            "strictPassAsins": strict_pass_asins,
            "evidenceManifest": str(manifest_path),
            "replayDir": str(replay_dir),
            "createdAt": now_iso(),
        }
        write_json(output_dir / "automation_result.json", result)
        return result

    final_rows = read_json(replay_dir / "final_candidates_data.json")
    final_asins = [normalize_asin(row.get("asin")) for row in final_rows if isinstance(row, dict)]
    if len(final_asins) != target or len(set(final_asins)) != target:
        raise AutomationError("Replay output does not contain the exact unique target", stage="replay_validation")
    unexpected = [asin for asin in final_asins if asin not in strict_pass_asins]
    if unexpected:
        raise AutomationError(
            "Replay qualified ASINs that were not strict-pass rows in the supplied snapshots",
            stage="replay_validation",
            details=unexpected,
        )
    for row in final_rows:
        asin = normalize_asin(row.get("asin"))
        if row.get("cnTitle") != title_overrides.get(asin):
            raise AutomationError(f"Chinese title override was not preserved for {asin}", stage="replay_validation")

    _run_command(
        [str(node_exe), str(project_root / "scripts" / "build_replay_workbooks.mjs"), str(replay_dir)],
        project_root=project_root,
        stage="workbook",
        timeout_seconds=args.command_timeout_seconds,
        node_modules=node_modules,
        env_overrides=(
            None
            if args.disable_workbook_force_exit_v1
            else {"SELLERSPRITE_WORKBOOK_FORCE_EXIT_V1": "1"}
        ),
    )
    _run_command(
        [sys.executable, str(project_root / "scripts" / "acceptance_checker.py"), str(replay_dir)],
        project_root=project_root,
        stage="acceptance",
        timeout_seconds=args.command_timeout_seconds,
    )
    if file_sha256(history_source) != production_history_sha256:
        raise AutomationError("Formal strict history changed during automation", stage="history_protection")

    build_report = read_json(replay_dir / "workbook_build_report.json")
    expected_exit_policy = "natural_event_loop" if args.disable_workbook_force_exit_v1 else WORKBOOK_EXIT_POLICY
    if build_report.get("workbookExitPolicy") != expected_exit_policy:
        raise AutomationError("Workbook exit policy was not recorded as requested", stage="publish")
    final_workbook = Path(build_report.get("finalXlsx") or "").resolve()
    audit_workbook = Path(build_report.get("auditXlsx") or "").resolve()
    acceptance_report = replay_dir / "acceptance_report.md"
    for path, label in ((final_workbook, "final workbook"), (audit_workbook, "audit workbook")):
        if not is_within(path, replay_dir) or not path.is_file():
            raise AutomationError(f"Untrusted or missing {label}: {path}", stage="publish")
    if not acceptance_report.is_file():
        raise AutomationError("Acceptance report is missing", stage="publish")

    previews = {
        key: str(Path(value).resolve())
        for key, value in build_report.items()
        if key.endswith("Preview") and isinstance(value, str) and Path(value).is_file()
    }
    result = {
        "schemaVersion": RESULT_SCHEMA,
        "automationVersion": AUTOMATION_VERSION,
        "accepted": True,
        "machineAcceptancePassed": True,
        "visualAcceptanceRequired": True,
        "visualAcceptancePassed": False,
        "productionHistoryUpdated": False,
        "imageDownloadPolicy": manifest["imageDownloadPolicy"],
        "workbookExitPolicy": expected_exit_policy,
        "runId": args.run_id,
        "runDate": args.run_date,
        "target": target,
        "qualifiedCount": len(final_asins),
        "qualifiedAsins": final_asins,
        "strictPassAsins": strict_pass_asins,
        "evidenceManifest": str(manifest_path),
        "replayDir": str(replay_dir),
        "finalWorkbook": str(final_workbook),
        "finalWorkbookSha256": file_sha256(final_workbook),
        "auditWorkbook": str(audit_workbook),
        "auditWorkbookSha256": file_sha256(audit_workbook),
        "acceptanceReport": str(acceptance_report),
        "previews": previews,
        "createdAt": now_iso(),
    }
    write_json(output_dir / "automation_result.json", result)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert one or more merged SellerSprite Runner JSON snapshots into an accepted Excel workbook."
    )
    parser.add_argument("--batch-json", action="append", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--title-overrides", required=True, type=Path)
    parser.add_argument("--allow-runner-version", action="append", required=True)
    parser.add_argument("--allow-collector-version", action="append", required=True)
    parser.add_argument("--allow-running-snapshot", action="store_true")
    parser.add_argument("--candidate-search-root", action="append", type=Path)
    parser.add_argument("--target", type=int)
    parser.add_argument("--run-id", default=f"merged_json_excel_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    parser.add_argument("--run-date", default=date.today().isoformat())
    parser.add_argument("--project-root", type=Path, default=DEFAULT_PROJECT_ROOT)
    parser.add_argument("--node-exe", type=Path)
    parser.add_argument("--node-modules", type=Path)
    parser.add_argument("--image-workers", type=int, default=4)
    parser.add_argument(
        "--image-cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "amazon-products" / "candidate-images-v1",
    )
    parser.add_argument("--image-cache-ttl-minutes", type=int, default=60)
    parser.add_argument("--disable-image-cache-v1", action="store_true")
    parser.add_argument("--disable-workbook-force-exit-v1", action="store_true")
    parser.add_argument("--command-timeout-seconds", type=int, default=900)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = execute(args)
    except (AutomationError, json.JSONDecodeError, OSError) as error:
        if isinstance(error, AutomationError):
            payload = {"accepted": False, "stage": error.stage, "message": str(error), "details": error.details}
        else:
            payload = {"accepted": False, "stage": "input", "message": str(error)}
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("accepted") is True else 3


if __name__ == "__main__":
    raise SystemExit(main())
