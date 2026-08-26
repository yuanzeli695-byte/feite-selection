from __future__ import annotations

import argparse
import base64
import binascii
import copy
import ctypes
from ctypes import wintypes
import json
import os
import re
import shutil
import hashlib
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlencode, urlparse


CONSOLE_ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = CONSOLE_ROOT.parent
PROJECT_ROOT = Path(
    os.environ.get("AMAZON_CONSOLE_PROJECT_ROOT")
    or (WORKSPACE_ROOT / "pipeline")
).expanduser().resolve()
DATA_DIR = CONSOLE_ROOT / "data"
STATE_PATH = DATA_DIR / "batches.json"
STATIC_DIR = CONSOLE_ROOT / "static"
PYTHON_EXE = Path(os.environ.get("AMAZON_CONSOLE_PYTHON_EXE") or sys.executable).expanduser().resolve()
NODE_EXE = Path(os.environ.get("AMAZON_CONSOLE_NODE_EXE") or shutil.which("node") or "node").expanduser()
PREPARE_SCRIPT = PROJECT_ROOT / "scripts" / "prepare_runner_queue_from_sellersprite_export.mjs"
SELLERSPRITE_PIPELINE_SCRIPT = CONSOLE_ROOT / "sellersprite_api_pipeline.py"
BROWSER_EXPORT_PIPELINE_SCRIPT = CONSOLE_ROOT / "sellersprite_browser_export_pipeline.py"
SELLERSPRITE_CREDENTIAL = Path.home() / ".codex" / "secrets" / "sellersprite-open-api.credential.xml"
DIRECT_IMPORT_SCRIPT = WORKSPACE_ROOT / "direct_import_batch_to_replay.mjs"
BUILD_SCRIPT = PROJECT_ROOT / "scripts" / "build_replay_workbooks.mjs"
PREFLIGHT_SCRIPT = Path(
    os.environ.get("AMAZON_CONSOLE_PREFLIGHT_SCRIPT")
    or (PROJECT_ROOT / "scripts" / "preflight.py")
).expanduser().resolve()

ALLOWED_BROWSER_STATUSES = {"waiting", "running", "paused", "completed", "needs_attention"}
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
APPROVED_COLLECTOR_VERSION = "0.4.6.4"
APPROVED_RUNNER_VERSION = "0.3.8.13"
APPROVED_BROWSER_BRIDGE_VERSION = "2.1.3"
APPROVED_BROWSER_BRIDGE_SCRIPT_VERSION = "2.1.6"
ACTIVE_COLLECTOR_SCRIPT = PROJECT_ROOT / "scripts" / "sellersprite_traffic_collector_v0.4.6.4_zh_no_data_fast_fail.user.js"
ACTIVE_RUNNER_SCRIPT = PROJECT_ROOT / "scripts" / "sellersprite_integrated_runner_v0.3.8.13_zh_keepa_passive_30s.user.js"
PROTECTED_SCRIPT_HASHES = {
    "bridge": "0BEA21250B8342AA7249D035D6EDB3A1D1F49775C53DF343B110C1BBADE6CC82",
    "collector": "9ED48DFAFC4E71CCB36A2982EC48D99BAA75372BC809DE19752DEF36D3A1D7D3",
    "runner": "0350FC1CDCA11E36FF3318FA947DED835C1D2B9DDEBC0CC7D9EDA15D5EC87E0C",
}
BROWSER_PAIR_RELEASE_STATUS = "candidate_pending_live_smoke_and_paired30"
DEFAULT_CANDIDATE_SOURCE_MODE = "browser_export"
DB_PATH = DATA_DIR / "console.db"
PAIRING_PATH = DATA_DIR / "browser_pairing.json"
MAX_REQUEST_BYTES = 24 * 1024 * 1024
CONTROL_PLANE_VERSION = "thread-control-v1.0.0"
ENABLE_THREAD_CONTROL_PLANE = os.environ.get("AMAZON_CONSOLE_THREAD_CONTROL", "1") == "1"
SUBPROCESS_WINDOW_POLICY_VERSION = "windows-no-console-v1.0.0"
ENABLE_WINDOWS_NO_CONSOLE = os.environ.get("AMAZON_CONSOLE_WINDOWS_NO_CONSOLE", "1") == "1"
SUBPROCESS_CREATION_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if ENABLE_WINDOWS_NO_CONSOLE else 0
PREFLIGHT_CACHE_VERSION = "preflight-cache-v1.0.0"
ENABLE_PREFLIGHT_CACHE = os.environ.get("AMAZON_CONSOLE_PREFLIGHT_CACHE", "1") == "1"
try:
    PREFLIGHT_CACHE_TTL_SECONDS = max(15, int(os.environ.get("AMAZON_CONSOLE_PREFLIGHT_CACHE_TTL", "45")))
except ValueError:
    PREFLIGHT_CACHE_TTL_SECONDS = 45
PREFLIGHT_CACHE_ERROR_BACKOFF_SECONDS = 10
LOCAL_JOB_RECOVERY_VERSION = "local-job-recovery-v1.0.0"
LOCAL_JOB_ACTIVE_STATUSES = ("starting", "running")
SELLERSPRITE_BRIDGE_VERSION = "sellerSprite-bridge-v1.0.0"
ENABLE_SELLERSPRITE_BRIDGE = os.environ.get("AMAZON_CONSOLE_SELLERSPRITE_BRIDGE", "1") == "1"
SELLERSPRITE_BRIDGE_MAX_BYTES = 16 * 1024 * 1024
COMMAND_DELIVERY_LEASE_SECONDS = 10
BRIDGE_HEARTBEAT_LEASE_SECONDS = 30
STOP_COMMAND_ACK_TIMEOUT_SECONDS = 30
MAX_AUTOMATIC_STOP_RETRIES = 2
THREAD_STATUS_VALUES = {"idle", "queued", "running", "needs_attention", "completed", "unavailable"}
CATEGORY_REPOSITORY_VERSION = "category-repository-v1.1.0"
ENABLE_CATEGORY_REPOSITORY = os.environ.get("AMAZON_CONSOLE_CATEGORY_REPOSITORY_V1", "1") == "1"
CATEGORY_MARKETPLACE = "Amazon US"
CATEGORY_SCREENING_SCOPE = "console_completed_runner_unaccepted"
ARCHIVE_REQUEST_VERSION = "archive-request-v1.0.0"
ARCHIVE_REQUEST_ACTIVE_STATUSES = ("requested", "cancelling", "waiting")
ARCHIVE_REQUEST_TIMEOUT_SECONDS = max(30, int(os.environ.get("AMAZON_CONSOLE_ARCHIVE_REQUEST_TIMEOUT", "60")))
CONSOLE_INSTANCE_ID = uuid.uuid4().hex
THREAD_ASSIGNMENTS = (
    {
        "order": 1,
        "stage": "candidates",
        "threadId": "019fb762-cbea-7aa2-b83d-3be19117dea4",
        "title": "01 \u751f\u6210 ASIN \u5bfc\u5165 Runner",
        "role": "\u5019\u9009\u4e0e\u961f\u5217",
        "defaultStatus": "idle",
        "defaultSummary": "\u6700\u8fd1\u5b8c\u6210 Health & Household 182 \u4e2a Runner ASIN \u961f\u5217\u3002",
        "defaultBlocker": "\u7b49\u5f85 Beauty & Personal Care \u7684 SellerSprite \u5bfc\u51fa\u6587\u4ef6\u548c\u5b8c\u6574\u7b5b\u9009 URL\u3002",
    },
    {
        "order": 2,
        "stage": "browser",
        "threadId": "019f5e0f-8bef-7c92-928f-17e8c24f9cda",
        "title": "02 \u4f18\u5316\u6d4f\u89c8\u5668\u9009\u54c1\u811a\u672c",
        "role": "Collector / Runner",
        "defaultStatus": "needs_attention",
        "defaultSummary": "Amazon \u9875\u9762\u53ef\u8bbf\u95ee\uff0c\u4f46 Runner \u4e0e Collector \u9762\u677f\u672a\u6ce8\u5165\u3002",
        "defaultBlocker": "\u7b49\u5f85\u91cd\u542f ScriptCat \u540e\u53f0\uff1b\u82e5\u4ecd\u5931\u8d25\uff0c\u9700\u8981 Service Worker \u7ea2\u8272\u9519\u8bef\u622a\u56fe\u3002",
    },
    {
        "order": 3,
        "stage": "excel",
        "threadId": "019fb736-617a-72b3-b901-72cae619a804",
        "title": "03 \u5c06\u901a\u8fc7\u9879\u5bfc\u5165 Excel",
        "role": "Excel \u4ea4\u4ed8",
        "defaultStatus": "completed",
        "defaultSummary": "\u6700\u8fd1\u5b8c\u6210 8.5_02\uff0c\u76f4\u63a5\u5bfc\u5165 4 \u4e2a\u901a\u8fc7\u9879\u548c 4 \u5f20\u4e3b\u56fe\u3002",
        "defaultBlocker": "",
    },
)
THREAD_BY_STAGE = {item["stage"]: item for item in THREAD_ASSIGNMENTS}
THREAD_BY_ID = {item["threadId"]: item for item in THREAD_ASSIGNMENTS}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def local_pid_alive(pid: int | None) -> bool:
    """Return a conservative liveness hint; never treats it as ownership proof."""
    try:
        value = int(pid or 0)
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    if os.name == "nt":
        # `os.kill(pid, 0)` is not a read-only probe on Windows. Query the
        # process handle instead, and treat access denial as alive so retry
        # remains fail-closed.
        process_query_limited_information = 0x1000
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(process_query_limited_information, False, value)
        if not handle:
            error = ctypes.get_last_error()
            return error in {5, 6}  # access denied / invalid handle race
        exit_code = ctypes.c_ulong()
        try:
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(value, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def slug(value: str, fallback: str = "batch") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "").strip()).strip("_-")
    return (cleaned[:60] or fallback)


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(json_bytes(value) + b"\n")
    temp.replace(path)


def valid_file(value: str, suffixes: tuple[str, ...] = ()) -> Path:
    path = Path(str(value or "").strip()).expanduser()
    if not path.is_file():
        raise ValueError(f"文件不存在: {path}")
    if suffixes and path.suffix.lower() not in suffixes:
        raise ValueError(f"文件类型不支持: {path.suffix}")
    return path.resolve()


def validate_sellersprite_url(raw: str) -> str:
    parsed = urlparse(str(raw or "").strip())
    if parsed.scheme != "https" or not (parsed.hostname or "").lower().endswith("sellersprite.com"):
        raise ValueError("筛选 URL 必须是 HTTPS SellerSprite URL")
    query = parse_qs(parsed.query)
    if query.get("market", [""])[0].upper() != "US":
        raise ValueError("筛选 URL 的 market 必须为 US")
    try:
        max_reviews = float(query.get("maxReviews", [""])[0])
    except ValueError as exc:
        raise ValueError("筛选 URL 缺少 maxReviews") from exc
    if not 0 <= max_reviews <= 100:
        raise ValueError("筛选 URL 的 maxReviews 必须不超过 100")
    node_value = query.get("nodeIdPaths", [""])[0]
    try:
        nodes = json.loads(node_value)
    except json.JSONDecodeError as exc:
        raise ValueError("筛选 URL 的 nodeIdPaths 不是有效 JSON 数组") from exc
    if not isinstance(nodes, list) or not nodes or any(not str(node).strip() for node in nodes):
        raise ValueError("筛选 URL 必须包含非空 nodeIdPaths")
    return parsed.geturl()


def parse_json_file(path: Path) -> Any:
    try:
        return read_json(path)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 无法解析: {path.name}: {exc}") from exc


def safe_child(root: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def browser_pairing_token() -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if PAIRING_PATH.is_file():
        try:
            value = str(read_json(PAIRING_PATH).get("token") or "")
            if value:
                return value
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    value = secrets.token_urlsafe(32)
    atomic_json_write(PAIRING_PATH, {"schemaVersion": "browserPairing/v1", "token": value, "createdAt": now_iso()})
    return value


BROWSER_PAIRING_TOKEN = browser_pairing_token()


DEFAULT_QUERY_FILTERS = {
    "minPrice": 9.9,
    "maxPrice": 50,
    "minRating": 4,
    "minReviews": 0,
    "maxReviews": 100,
    "minChildSales": 50,
    "maxChildSales": 300,
    "minVariations": 0,
    "maxVariations": 25,
    "availableMonth": 3,
    "perCategoryLimit": 200,
}


def normalize_query_filters(payload: Any) -> dict[str, Any]:
    value = payload if isinstance(payload, dict) else {}
    filters = {**DEFAULT_QUERY_FILTERS, **value}
    numeric = {
        "minPrice": float,
        "maxPrice": float,
        "minRating": float,
        "minReviews": int,
        "maxReviews": int,
        "minChildSales": int,
        "maxChildSales": int,
        "minVariations": int,
        "maxVariations": int,
        "availableMonth": int,
        "perCategoryLimit": int,
    }
    for key, cast in numeric.items():
        filters[key] = cast(filters[key])
    if filters["minPrice"] < 9.9 or filters["maxPrice"] > 50 or filters["minPrice"] > filters["maxPrice"]:
        raise ValueError("价格范围必须位于 9.90-50.00")
    if filters["minRating"] < 4:
        raise ValueError("最低评分不得低于 4.0")
    if filters["maxReviews"] > 100 or filters["minReviews"] > filters["maxReviews"]:
        raise ValueError("评论数上限不得超过 100")
    if filters["maxVariations"] > 25 or filters["minVariations"] > filters["maxVariations"]:
        raise ValueError("变体数上限不得超过 25")
    if not 1 <= filters["availableMonth"] <= 3:
        raise ValueError("上架月份必须为 1-3")
    if not 1 <= filters["perCategoryLimit"] <= 2000:
        raise ValueError("每类目候选上限必须为 1-2000")
    return filters


def normalize_category_name(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def category_pool_rows(raw: str, *, deduplicate: bool = True) -> list[dict[str, Any]]:
    rows = []
    seen = set()
    for number, source in enumerate(str(raw or "").splitlines(), 1):
        value = source.strip()
        if not value or value.startswith("#"):
            continue
        duplicate_key = value.casefold()
        if deduplicate and duplicate_key in seen:
            continue
        seen.add(duplicate_key)
        parts = [part.strip() for part in re.split(r"[|\t]", value, maxsplit=1)]
        label = parts[0]
        node_id_path = parts[1] if len(parts) == 2 else ""
        url_source = node_id_path or (label if len(parts) == 1 else "")
        url_match = re.search(r"https://(?:www\.)?sellersprite\.com/[^\s)\]]+", url_source, re.IGNORECASE)
        if url_match:
            query = parse_qs(urlparse(url_match.group(0)).query, keep_blank_values=True)
            market_values = [
                value
                for key, values in query.items()
                if key.casefold() == "market"
                for value in values
            ]
            if market_values and any(str(market).strip().upper() != "US" for market in market_values):
                raise ValueError(f"第 {number} 行 SellerSprite 链接必须显式属于 Amazon US")
            node_values = [
                value
                for key, values in query.items()
                if key.casefold() == "nodeidpaths"
                for value in values
            ]
            try:
                nodes = json.loads(node_values[0] if len(node_values) == 1 else "")
            except json.JSONDecodeError as exc:
                raise ValueError(f"第 {number} 行 SellerSprite 链接的 nodeIdPaths 无效") from exc
            if not isinstance(nodes, list) or len(nodes) != 1:
                raise ValueError(f"第 {number} 行 SellerSprite 链接必须只包含一个类目节点")
            node_id_path = str(nodes[0]).strip()
        if not node_id_path and re.fullmatch(r"\d+(?::\d+)*", label):
            node_id_path = label
        if node_id_path and not re.fullmatch(r"\d+(?::\d+)*", node_id_path):
            raise ValueError(f"第 {number} 行 nodeIdPath 必须是数字路径，例如 1064954")
        rows.append({
            "line": number,
            "input": value,
            "label": label,
            "nodeIdPath": node_id_path,
            "status": "pending",
        })
    return rows


def category_pool_preview_rows(raw: str) -> list[dict[str, Any]]:
    rows = []
    for number, source in enumerate(str(raw or "").splitlines(), 1):
        value = source.strip()
        if not value or value.startswith("#"):
            continue
        try:
            parsed = category_pool_rows(value, deduplicate=False)
            row = parsed[0]
            row["line"] = number
            row["parseError"] = ""
        except ValueError as exc:
            parts = [part.strip() for part in re.split(r"[|\t]", value, maxsplit=1)]
            message = re.sub(r"^第\s+\d+\s+行", f"第 {number} 行", str(exc))
            row = {
                "line": number,
                "input": value,
                "label": parts[0] if parts else "",
                "nodeIdPath": "",
                "status": "pending",
                "parseError": message,
            }
        rows.append(row)
    return rows


def category_import_item_key(row: dict[str, Any]) -> str:
    content = f"{CATEGORY_MARKETPLACE}\0{row['line']}\0{row['input']}"
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:24]
    return f"line:{row['line']}:{digest}"


def sellersprite_web_query_url(node_id_path: str, filters: dict[str, Any]) -> str:
    if not node_id_path:
        return ""
    params = {
        "market": "US",
        "page": 1,
        "size": 60,
        # SellerSprite's v3 page needs these state parameters to hydrate the
        # result grid when opened directly.  Without them the URL is accepted
        # but the page renders no result toolbar, so Bridge cannot export.
        "symbolFlag": "true",
        "monthName": "bsr_sales_nearly",
        "selectType": 2,
        "filterSub": "false",
        "weightUnit": "g",
        "order[field]": "amz_unit",
        "order[desc]": "true",
        "productTags": "[]",
        "nodeIdPaths": json.dumps([node_id_path], separators=(",", ":")),
        "sellerTypes": "[]",
        "eligibility": "[]",
        "pkgDimensionTypeList": "[]",
        "sellerNationList": "[]",
        "lowPrice": "N",
        "salesGrowthType": "30d",
        "video": "",
        "minPrice": filters["minPrice"],
        "maxPrice": filters["maxPrice"],
        "minReviews": filters["minReviews"],
        "maxReviews": filters["maxReviews"],
        "minReviewRating": filters["minRating"],
        "minAmzUnit": filters["minChildSales"],
        "maxAmzUnit": filters["maxChildSales"],
        "minVariations": filters["minVariations"],
        "maxVariations": filters["maxVariations"],
        "putawayMonth": filters["availableMonth"],
    }
    return "https://www.sellersprite.com/v3/product-research?" + urlencode(params)


def browser_export_tasks(batch: dict[str, Any]) -> list[dict[str, Any]]:
    uploaded = {item.get("categoryInput"): item for item in batch.get("browserExports", [])}
    tasks = []
    for row in batch.get("categoryPool", []):
        export = uploaded.get(row.get("input")) or {}
        tasks.append({
            "categoryInput": row.get("input"),
            "label": row.get("label") or row.get("input"),
            "nodeIdPath": row.get("nodeIdPath") or "",
            "queryUrl": export.get("queryUrl") or sellersprite_web_query_url(row.get("nodeIdPath") or "", batch.get("queryFilters") or DEFAULT_QUERY_FILTERS),
            "uploaded": bool(export.get("path")),
            "fileName": export.get("fileName") or "",
            "capturedAt": export.get("capturedAt") or "",
            "sha256": export.get("sha256") or "",
        })
    return tasks


class WorkflowStore:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.jobs: dict[str, subprocess.Popen[str]] = {}
        self.cancel_flags: set[str] = set()
        self.batches: dict[str, dict[str, Any]] = {}
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if STATE_PATH.exists():
            try:
                payload = read_json(STATE_PATH)
                self.batches = {item["id"]: item for item in payload.get("batches", [])}
            except (OSError, json.JSONDecodeError, KeyError):
                self.batches = {}


class SQLiteWorkflowStore(WorkflowStore):
    """Durable store for the orchestration layer.

    The in-memory snapshot keeps the existing execution code simple, while SQLite
    is the authoritative recovery record for runs, commands, events and artifacts.
    """

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.jobs: dict[str, subprocess.Popen[str]] = {}
        self.cancel_flags: set[str] = set()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL,
                at TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                details TEXT,
                FOREIGN KEY(batch_id) REFERENCES runs(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS commands (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                action TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                delivered_at TEXT,
                acknowledged_at TEXT,
                FOREIGN KEY(batch_id) REFERENCES runs(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS asin_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL,
                asin TEXT,
                row_index INTEGER,
                event_type TEXT NOT NULL,
                gate TEXT,
                decision TEXT,
                payload TEXT NOT NULL,
                at TEXT NOT NULL,
                FOREIGN KEY(batch_id) REFERENCES runs(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL,
                artifact_key TEXT NOT NULL,
                path TEXT NOT NULL,
                sha256 TEXT,
                kind TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(batch_id, artifact_key, path),
                FOREIGN KEY(batch_id) REFERENCES runs(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS bridge_sessions (
                batch_id TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL,
                script_version TEXT,
                command_id TEXT,
                execution_mode TEXT,
                collector_version TEXT,
                runner_version TEXT,
                queue_hash TEXT,
                status TEXT NOT NULL,
                last_heartbeat TEXT,
                FOREIGN KEY(batch_id) REFERENCES runs(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS stage_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                attempt INTEGER NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                exit_code INTEGER,
                input_hash TEXT,
                log_path TEXT,
                FOREIGN KEY(batch_id) REFERENCES runs(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS local_job_leases (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                attempt INTEGER NOT NULL,
                pid INTEGER,
                argv_sha256 TEXT NOT NULL,
                executable TEXT NOT NULL,
                run_dir TEXT NOT NULL,
                stdout_path TEXT,
                stderr_path TEXT,
                owner_instance_id TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                ended_at TEXT,
                exit_code INTEGER,
                recovery_reason TEXT,
                FOREIGN KEY(batch_id) REFERENCES runs(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS interventions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                payload TEXT,
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                FOREIGN KEY(batch_id) REFERENCES runs(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS thread_snapshots (
                thread_id TEXT PRIMARY KEY,
                stage TEXT NOT NULL,
                status TEXT NOT NULL,
                summary TEXT NOT NULL,
                blocker TEXT NOT NULL,
                source TEXT NOT NULL,
                synced_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS thread_dispatches (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                prompt TEXT NOT NULL,
                note TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(batch_id) REFERENCES runs(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS category_pool_items (
                id TEXT PRIMARY KEY,
                input TEXT NOT NULL,
                normalized_key TEXT NOT NULL UNIQUE,
                label TEXT NOT NULL,
                node_id_path TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('available', 'assigned', 'completed')),
                batch_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(batch_id) REFERENCES runs(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS batch_archive_state (
                batch_id TEXT PRIMARY KEY,
                archived_at TEXT,
                restored_at TEXT,
                updated_at TEXT NOT NULL,
                feature_version TEXT NOT NULL,
                FOREIGN KEY(batch_id) REFERENCES runs(id) ON DELETE RESTRICT
            );
            CREATE TABLE IF NOT EXISTS batch_archive_requests (
                request_id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL UNIQUE,
                idempotency_key TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL CHECK(status IN ('requested','cancelling','waiting','archived','failed')),
                phase TEXT NOT NULL,
                requested_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                attempt INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(batch_id) REFERENCES runs(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS screened_categories (
                marketplace TEXT NOT NULL,
                node_id_path TEXT NOT NULL,
                display_name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                scope TEXT NOT NULL CHECK(scope = 'console_completed_runner_unaccepted'),
                first_completed_at TEXT NOT NULL,
                last_completed_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                feature_version TEXT NOT NULL,
                PRIMARY KEY(marketplace, node_id_path)
            );
            CREATE TABLE IF NOT EXISTS screened_category_completions (
                marketplace TEXT NOT NULL,
                node_id_path TEXT NOT NULL,
                batch_id TEXT NOT NULL,
                display_name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                registration_source TEXT NOT NULL CHECK(registration_source IN ('completion_hook', 'startup_backfill')),
                created_at TEXT NOT NULL,
                feature_version TEXT NOT NULL,
                PRIMARY KEY(marketplace, node_id_path, batch_id),
                UNIQUE(batch_id),
                FOREIGN KEY(marketplace, node_id_path) REFERENCES screened_categories(marketplace, node_id_path) ON DELETE RESTRICT,
                FOREIGN KEY(batch_id) REFERENCES runs(id) ON DELETE RESTRICT
            );
            CREATE TABLE IF NOT EXISTS feature_audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feature_key TEXT NOT NULL,
                feature_version TEXT NOT NULL,
                action TEXT NOT NULL,
                subject_type TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                outcome TEXT NOT NULL,
                details TEXT NOT NULL,
                at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_batch_archive_archived_at
                ON batch_archive_state(archived_at);
            CREATE INDEX IF NOT EXISTS idx_batch_archive_requests_status
                ON batch_archive_requests(status, updated_at);
            CREATE INDEX IF NOT EXISTS idx_screened_categories_name
                ON screened_categories(marketplace, normalized_name);
            CREATE INDEX IF NOT EXISTS idx_screened_completions_batch
                ON screened_category_completions(batch_id);
            CREATE INDEX IF NOT EXISTS idx_feature_audit_subject
                ON feature_audit_events(feature_key, subject_type, subject_id, at);
            CREATE INDEX IF NOT EXISTS idx_local_job_leases_batch_stage
                ON local_job_leases(batch_id, stage, status, started_at);
            """
        )
        bridge_session_columns = {row["name"] for row in self.db.execute("PRAGMA table_info(bridge_sessions)")}
        if "script_version" not in bridge_session_columns:
            self.db.execute("ALTER TABLE bridge_sessions ADD COLUMN script_version TEXT")
        if "command_id" not in bridge_session_columns:
            self.db.execute("ALTER TABLE bridge_sessions ADD COLUMN command_id TEXT")
        if "execution_mode" not in bridge_session_columns:
            self.db.execute("ALTER TABLE bridge_sessions ADD COLUMN execution_mode TEXT")
        self.db.execute("DROP VIEW IF EXISTS browser_sessions")
        self.db.execute("""CREATE VIEW browser_sessions AS
            SELECT batch_id, token_hash, script_version, command_id, execution_mode, collector_version, runner_version,
                   queue_hash, status, last_heartbeat FROM bridge_sessions""")
        self.db.commit()
        self._seed_thread_snapshots()
        self.batches = {}
        migrated_bridge = False
        for row in self.db.execute("SELECT payload FROM runs ORDER BY updated_at DESC"):
            try:
                payload = json.loads(row["payload"])
                if not payload.get("bridgeToken"):
                    payload["bridgeToken"] = secrets.token_urlsafe(32)
                    payload["bridgeProtocol"] = "browser-bridge-v1"
                    migrated_bridge = True
                self.batches[payload["id"]] = payload
            except (KeyError, json.JSONDecodeError):
                continue
        if migrated_bridge:
            self.persist()
        if not self.batches and STATE_PATH.exists():
            try:
                legacy = read_json(STATE_PATH)
                self.batches = {item["id"]: item for item in legacy.get("batches", [])}
                self.persist()
            except (OSError, json.JSONDecodeError, KeyError):
                pass
        self._reconcile_local_jobs_on_startup()
        if ENABLE_CATEGORY_REPOSITORY:
            self._backfill_screened_categories()

    def persist(self) -> None:
        with self.db:
            for batch in self.batches.values():
                self.db.execute(
                    """INSERT INTO runs(id,payload,created_at,updated_at) VALUES(?,?,?,?)
                       ON CONFLICT(id) DO UPDATE SET payload=excluded.payload, updated_at=excluded.updated_at""",
                    (batch["id"], json.dumps(batch, ensure_ascii=False), batch["createdAt"], batch["updatedAt"]),
                )

    def _local_job_attempt_locked(self, batch_id: str, stage: str) -> int:
        row = self.db.execute(
            "SELECT COALESCE(MAX(attempt),0) AS attempt FROM local_job_leases WHERE batch_id=? AND stage=?",
            (batch_id, stage),
        ).fetchone()
        return int(row["attempt"] or 0) + 1

    def _active_local_jobs_locked(self, batch_id: str, stage: str | None = None) -> list[sqlite3.Row]:
        params: list[Any] = [batch_id, *LOCAL_JOB_ACTIVE_STATUSES]
        query = """SELECT * FROM local_job_leases
                   WHERE batch_id=? AND status IN (?,?)"""
        if stage:
            query += " AND stage=?"
            params.append(stage)
        query += " ORDER BY started_at DESC"
        return self.db.execute(query, tuple(params)).fetchall()

    def _insert_local_job_locked(
        self,
        job_id: str,
        batch_id: str,
        stage: str,
        attempt: int,
        argv_sha256: str,
        executable: str,
        run_dir: str,
        stdout_path: str,
        stderr_path: str,
        started_at: str,
    ) -> None:
        with self.db:
            self.db.execute(
                """INSERT INTO local_job_leases(
                       id,batch_id,stage,attempt,pid,argv_sha256,executable,run_dir,
                       stdout_path,stderr_path,owner_instance_id,status,started_at,last_seen_at
                   ) VALUES(?,?,?,?,NULL,?,?,?,?,?,?,'starting',?,?)""",
                (
                    job_id, batch_id, stage, attempt, argv_sha256, executable, run_dir,
                    stdout_path, stderr_path, CONSOLE_INSTANCE_ID, started_at, started_at,
                ),
            )

    def _update_local_job_locked(
        self,
        job_id: str,
        *,
        status: str | None = None,
        pid: int | None = None,
        ended_at: str | None = None,
        exit_code: int | None = None,
        recovery_reason: str | None = None,
    ) -> None:
        values: list[Any] = []
        assignments = ["last_seen_at=?"]
        values.append(now_iso())
        if status is not None:
            assignments.append("status=?")
            values.append(status)
        if pid is not None:
            assignments.append("pid=?")
            values.append(int(pid))
        if ended_at is not None:
            assignments.append("ended_at=?")
            values.append(ended_at)
        if exit_code is not None:
            assignments.append("exit_code=?")
            values.append(int(exit_code))
        if recovery_reason is not None:
            assignments.append("recovery_reason=?")
            values.append(recovery_reason)
        values.append(job_id)
        with self.db:
            self.db.execute(
                f"UPDATE local_job_leases SET {', '.join(assignments)} WHERE id=?",
                tuple(values),
            )

    def _append_recovery_event_locked(
        self,
        batch: dict[str, Any],
        message: str,
        details: dict[str, Any],
    ) -> None:
        at = now_iso()
        event = {"at": at, "level": "warning", "message": message, "details": details}
        events = batch.setdefault("events", [])
        events.append(event)
        batch["events"] = events[-200:]
        self.db.execute(
            "INSERT INTO events(batch_id,at,level,message,details) VALUES(?,?,?,?,?)",
            (batch["id"], at, "warning", message, json.dumps(details, ensure_ascii=False)),
        )

    def _mark_stage_recovery_locked(
        self,
        batch: dict[str, Any],
        stage: str,
        recovery: dict[str, Any],
    ) -> bool:
        stage_data = batch.get("stages", {}).get(stage)
        if not isinstance(stage_data, dict) or stage_data.get("status") not in {"running", "stopping"}:
            return False
        previous_status = str(stage_data.get("status") or "running")
        message = (
            "服务重启后发现旧任务进程仍可能运行，未自动接管；请确认后重试"
            if recovery.get("processAlive")
            else "服务重启导致本地任务中断，可从当前阶段安全重试"
        )
        recovery = {
            **recovery,
            "version": LOCAL_JOB_RECOVERY_VERSION,
            "previousStatus": previous_status,
            "canRetry": True,
        }
        artifacts = stage_data.setdefault("artifacts", {})
        artifacts["recovery"] = recovery
        stage_data["recovery"] = recovery
        stage_data["status"] = "needs_attention"
        stage_data["message"] = message
        stage_data.pop("completedAt", None)
        batch["overallStatus"] = "needs_attention"
        batch.setdefault("recovery", {})[stage] = recovery
        batch["updatedAt"] = now_iso()
        self._record_stage_run(batch["id"], stage, "needs_attention", stage_data)
        self._append_recovery_event_locked(
            batch,
            "服务重启，本地任务未自动接管",
            {"stage": stage, **recovery},
        )
        return True

    def _reconcile_local_jobs_on_startup(self) -> None:
        """Close this instance's lost local leases without guessing ownership."""
        with self.lock:
            changed = False
            handled: set[tuple[str, str]] = set()
            active_rows = self.db.execute(
                "SELECT * FROM local_job_leases WHERE status IN (?,?) ORDER BY started_at",
                LOCAL_JOB_ACTIVE_STATUSES,
            ).fetchall()
            for row in active_rows:
                batch = self.batches.get(str(row["batch_id"]))
                pid = row["pid"]
                process_alive = local_pid_alive(pid)
                lease_status = "orphaned" if process_alive else "interrupted"
                reason = "service_restart_process_alive" if process_alive else "service_restart_process_missing"
                ended_at = None if process_alive else now_iso()
                with self.db:
                    self.db.execute(
                        """UPDATE local_job_leases
                           SET status=?,last_seen_at=?,ended_at=?,recovery_reason=?
                           WHERE id=? AND status IN (?,?)""",
                        (lease_status, now_iso(), ended_at, reason, row["id"], *LOCAL_JOB_ACTIVE_STATUSES),
                    )
                changed = True
                if not batch or self._batch_is_archived_locked(batch["id"]):
                    continue
                stage = str(row["stage"] or "")
                if stage not in {"candidates", "excel"}:
                    continue
                handled.add((batch["id"], stage))
                if terminal_batch_status(batch):
                    continue
                recovery = {
                    "jobId": str(row["id"]),
                    "status": lease_status,
                    "reason": reason,
                    "processAlive": process_alive,
                    "lastKnownPid": int(pid) if pid else None,
                    "attempt": int(row["attempt"]),
                    "argvSha256": str(row["argv_sha256"] or ""),
                    "runDir": str(row["run_dir"] or ""),
                    "stdout": str(row["stdout_path"] or ""),
                    "stderr": str(row["stderr_path"] or ""),
                    "recoveredAt": now_iso(),
                }
                if self._mark_stage_recovery_locked(batch, stage, recovery):
                    changed = True

            # Older databases have no local lease. A running local stage is still
            # unsafe to display as active, so create a synthetic interrupted record.
            for batch in self.batches.values():
                if self._batch_is_archived_locked(batch["id"]) or terminal_batch_status(batch):
                    continue
                for stage in ("candidates", "excel"):
                    stage_data = batch.get("stages", {}).get(stage, {})
                    if not isinstance(stage_data, dict) or stage_data.get("status") not in {"running", "stopping"}:
                        continue
                    if (batch["id"], stage) in handled:
                        continue
                    job_id = f"recovery-{uuid.uuid4().hex}"
                    started_at = str(stage_data.get("startedAt") or batch.get("updatedAt") or now_iso())
                    attempt = self._local_job_attempt_locked(batch["id"], stage)
                    with self.db:
                        self.db.execute(
                            """INSERT INTO local_job_leases(
                                   id,batch_id,stage,attempt,pid,argv_sha256,executable,run_dir,
                                   stdout_path,stderr_path,owner_instance_id,status,started_at,
                                   last_seen_at,ended_at,recovery_reason
                               ) VALUES(?,?,?,?,NULL,'','','','','',?,'interrupted',?,?,?,?)""",
                            (
                                job_id, batch["id"], stage, attempt, CONSOLE_INSTANCE_ID,
                                started_at, now_iso(), now_iso(), "service_restart_missing_lease",
                            ),
                        )
                    recovery = {
                        "jobId": job_id,
                        "status": "interrupted",
                        "reason": "service_restart_missing_lease",
                        "processAlive": False,
                        "lastKnownPid": None,
                        "attempt": attempt,
                        "argvSha256": "",
                        "runDir": str(batch.get("runDir") or ""),
                        "stdout": str(stage_data.get("artifacts", {}).get("stdout") or ""),
                        "stderr": str(stage_data.get("artifacts", {}).get("stderr") or ""),
                        "recoveredAt": now_iso(),
                    }
                    if self._mark_stage_recovery_locked(batch, stage, recovery):
                        changed = True
            if changed:
                self.persist()
                self.db.commit()

    def _audit_feature_locked(
        self,
        action: str,
        subject_type: str,
        subject_id: str,
        outcome: str,
        details: Any = None,
    ) -> None:
        self.db.execute(
            """INSERT INTO feature_audit_events(
                   feature_key,feature_version,action,subject_type,subject_id,outcome,details,at
               ) VALUES(?,?,?,?,?,?,?,?)""",
            (
                "category_repository",
                CATEGORY_REPOSITORY_VERSION,
                action,
                subject_type,
                subject_id,
                outcome,
                json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
                now_iso(),
            ),
        )

    def _completed_category(self, batch: dict[str, Any]) -> dict[str, str] | None:
        if not verified_completed_workflow(batch):
            return None
        candidates: list[tuple[str, str]] = []
        for row in batch.get("categoryPool") or []:
            if not isinstance(row, dict):
                return None
            node_id_path = str(row.get("nodeIdPath") or "").strip()
            if not node_id_path:
                continue
            if not re.fullmatch(r"\d+(?::\d+)*", node_id_path):
                return None
            display_name = str(
                row.get("label")
                or row.get("nodeLabelPathLocale")
                or row.get("nodeLabelPath")
                or batch.get("category")
                or batch.get("name")
                or node_id_path
            ).strip()
            candidates.append((node_id_path, display_name))

        source_url = str(batch.get("sourceUrl") or "").strip()
        if source_url:
            parsed = urlparse(source_url)
            query = parse_qs(parsed.query)
            if query.get("market", [""])[0].upper() == "US":
                try:
                    source_nodes = json.loads(query.get("nodeIdPaths", [""])[0])
                except json.JSONDecodeError:
                    source_nodes = []
                if isinstance(source_nodes, list) and len(source_nodes) == 1:
                    source_node = str(source_nodes[0]).strip()
                    if re.fullmatch(r"\d+(?::\d+)*", source_node):
                        candidates.append((
                            source_node,
                            str(batch.get("category") or batch.get("sourcePage") or batch.get("name") or source_node).strip(),
                        ))

        distinct_nodes = {node for node, _name in candidates}
        if len(distinct_nodes) != 1:
            return None
        node_id_path = next(iter(distinct_nodes))
        display_name = next((name for node, name in candidates if node == node_id_path and name), node_id_path)
        normalized_name = normalize_category_name(display_name)
        if not normalized_name:
            return None
        completed_at = str(
            batch.get("stages", {}).get("excel", {}).get("completedAt")
            or batch.get("updatedAt")
            or batch.get("createdAt")
            or now_iso()
        )
        return {
            "marketplace": CATEGORY_MARKETPLACE,
            "nodeIdPath": node_id_path,
            "displayName": display_name,
            "normalizedName": normalized_name,
            "completedAt": completed_at,
        }

    def _register_screened_category(self, batch: dict[str, Any], source: str) -> bool:
        if not ENABLE_CATEGORY_REPOSITORY:
            return False
        category = self._completed_category(batch)
        if not category:
            return False
        batch_id = str(batch.get("id") or "")
        with self.db:
            exists = self.db.execute(
                "SELECT 1 FROM screened_category_completions WHERE batch_id=?",
                (batch_id,),
            ).fetchone()
            if exists:
                return False
            registered_at = now_iso()
            self.db.execute(
                """INSERT INTO screened_categories(
                       marketplace,node_id_path,display_name,normalized_name,scope,
                       first_completed_at,last_completed_at,created_at,updated_at,feature_version
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(marketplace,node_id_path) DO UPDATE SET
                       display_name=excluded.display_name,
                       normalized_name=excluded.normalized_name,
                       first_completed_at=MIN(screened_categories.first_completed_at,excluded.first_completed_at),
                       last_completed_at=MAX(screened_categories.last_completed_at,excluded.last_completed_at),
                       updated_at=excluded.updated_at,
                       feature_version=excluded.feature_version""",
                (
                    category["marketplace"], category["nodeIdPath"], category["displayName"],
                    category["normalizedName"], CATEGORY_SCREENING_SCOPE, category["completedAt"],
                    category["completedAt"], registered_at, registered_at, CATEGORY_REPOSITORY_VERSION,
                ),
            )
            self.db.execute(
                """INSERT INTO screened_category_completions(
                       marketplace,node_id_path,batch_id,display_name,normalized_name,completed_at,
                       registration_source,created_at,feature_version
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    category["marketplace"], category["nodeIdPath"], batch_id, category["displayName"],
                    category["normalizedName"], category["completedAt"], source, registered_at,
                    CATEGORY_REPOSITORY_VERSION,
                ),
            )
            self._audit_feature_locked(
                "screened_category_registered" if source == "completion_hook" else "screened_category_backfilled",
                "batch",
                batch_id,
                "completed",
                {"marketplace": category["marketplace"], "nodeIdPath": category["nodeIdPath"], "scope": CATEGORY_SCREENING_SCOPE},
            )
        return True

    def _backfill_screened_categories(self) -> None:
        for batch in self.batches.values():
            if verified_completed_workflow(batch):
                self._register_screened_category(batch, "startup_backfill")

    def _seed_thread_snapshots(self) -> None:
        at = now_iso()
        with self.db:
            for assignment in THREAD_ASSIGNMENTS:
                self.db.execute(
                    """INSERT OR IGNORE INTO thread_snapshots(thread_id,stage,status,summary,blocker,source,synced_at)
                       VALUES(?,?,?,?,?,?,?)""",
                    (
                        assignment["threadId"], assignment["stage"], assignment["defaultStatus"],
                        assignment["defaultSummary"], assignment["defaultBlocker"], "codex_task_snapshot", at,
                    ),
                )

    def list_threads(self) -> list[dict[str, Any]]:
        if not ENABLE_THREAD_CONTROL_PLANE:
            return []
        rows = {row["thread_id"]: row for row in self.db.execute("SELECT * FROM thread_snapshots")}
        result = []
        for assignment in THREAD_ASSIGNMENTS:
            row = rows.get(assignment["threadId"])
            pending = self.db.execute(
                "SELECT COUNT(*) AS count FROM thread_dispatches WHERE thread_id=? AND status IN ('prepared','sent')",
                (assignment["threadId"],),
            ).fetchone()["count"]
            latest = self.db.execute(
                "SELECT id,batch_id,status,created_at FROM thread_dispatches WHERE thread_id=? ORDER BY created_at DESC LIMIT 1",
                (assignment["threadId"],),
            ).fetchone()
            result.append({
                **assignment,
                "codexUrl": f"codex://threads/{assignment['threadId']}",
                "status": row["status"] if row else assignment["defaultStatus"],
                "summary": row["summary"] if row else assignment["defaultSummary"],
                "blocker": row["blocker"] if row else assignment["defaultBlocker"],
                "source": row["source"] if row else "default",
                "syncedAt": row["synced_at"] if row else None,
                "pendingDispatchCount": pending,
                "latestDispatch": dict(latest) if latest else None,
            })
        return result

    def update_thread_snapshot(self, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            assignment = THREAD_BY_ID.get(thread_id)
            if not assignment:
                raise ValueError("\u672a\u77e5\u7684 Codex \u4efb\u52a1")
            current = self.db.execute("SELECT * FROM thread_snapshots WHERE thread_id=?", (thread_id,)).fetchone()
            status = str(payload.get("status") or (current["status"] if current else assignment["defaultStatus"]))
            if status not in THREAD_STATUS_VALUES:
                raise ValueError(f"\u4efb\u52a1\u72b6\u6001\u5fc5\u987b\u662f: {', '.join(sorted(THREAD_STATUS_VALUES))}")
            summary = str(payload.get("summary") if "summary" in payload else (current["summary"] if current else "")).strip()
            blocker = str(payload.get("blocker") if "blocker" in payload else (current["blocker"] if current else "")).strip()
            at = now_iso()
            with self.db:
                self.db.execute(
                    """INSERT INTO thread_snapshots(thread_id,stage,status,summary,blocker,source,synced_at)
                       VALUES(?,?,?,?,?,?,?) ON CONFLICT(thread_id) DO UPDATE SET
                       status=excluded.status,summary=excluded.summary,blocker=excluded.blocker,source=excluded.source,synced_at=excluded.synced_at""",
                    (thread_id, assignment["stage"], status, summary, blocker, str(payload.get("source") or "manual_console"), at),
                )
            return next(item for item in self.list_threads() if item["threadId"] == thread_id)

    def prepare_dispatch(self, batch_id: str, stage: str, note: str = "") -> dict[str, Any]:
        if not ENABLE_THREAD_CONTROL_PLANE:
            raise ValueError("Codex thread control plane is disabled")
        assignment = THREAD_BY_STAGE.get(stage)
        if not assignment:
            raise ValueError("stage \u5fc5\u987b\u662f candidates\u3001browser \u6216 excel")
        with self.lock:
            self._assert_batch_not_archived_locked(batch_id)
            batch = self.get(batch_id)
            gate = dispatch_gate(batch, stage)
            if not gate["allowed"]:
                raise ValueError(gate["reason"])
            prompt = build_dispatch_prompt(batch, stage, note, gate)
            dispatch_id = uuid.uuid4().hex
            at = now_iso()
            with self.db:
                self.db.execute(
                    """INSERT INTO thread_dispatches(id,batch_id,thread_id,stage,prompt,note,status,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (dispatch_id, batch_id, assignment["threadId"], stage, prompt, note.strip(), "prepared", at, at),
                )
            self.event(batch_id, f"\u5df2\u4e3a\u4efb\u52a1 {assignment['title']} \u51c6\u5907\u8c03\u5ea6\u6307\u4ee4", "info", {"dispatchId": dispatch_id, "stage": stage})
            return {
                "id": dispatch_id, "batchId": batch_id, "threadId": assignment["threadId"],
                "stage": stage, "status": "prepared", "prompt": prompt,
                "codexUrl": f"codex://threads/{assignment['threadId']}", "gate": gate, "createdAt": at,
            }

    def list_dispatches(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT * FROM thread_dispatches ORDER BY created_at DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
        return [{
            "id": row["id"], "batchId": row["batch_id"], "threadId": row["thread_id"],
            "stage": row["stage"], "prompt": row["prompt"], "note": row["note"],
            "status": row["status"], "createdAt": row["created_at"], "updatedAt": row["updated_at"],
        } for row in rows]

    def update_dispatch_status(self, dispatch_id: str, status: str) -> dict[str, Any]:
        if status not in {"prepared", "sent", "acknowledged", "cancelled"}:
            raise ValueError("\u8c03\u5ea6\u72b6\u6001\u65e0\u6548")
        with self.lock:
            row = self.db.execute("SELECT * FROM thread_dispatches WHERE id=?", (dispatch_id,)).fetchone()
            if not row:
                raise KeyError(dispatch_id)
            batch_id = str(row["batch_id"])
            pending = self._active_archive_request_locked(batch_id)
            allow_archive_request = ""
            if pending and status in {"acknowledged", "cancelled"}:
                allow_archive_request = str(pending["request_id"])
            self._assert_batch_not_archived_locked(batch_id, allow_archive_request=allow_archive_request)
            at = now_iso()
            with self.db:
                self.db.execute("UPDATE thread_dispatches SET status=?,updated_at=? WHERE id=?", (status, at, dispatch_id))
            if status == "sent":
                self.update_thread_snapshot(row["thread_id"], {"status": "queued", "source": "console_dispatch"})
            return next(item for item in self.list_dispatches() if item["id"] == dispatch_id)

    def event(
        self,
        batch_id: str,
        message: str,
        level: str = "info",
        details: Any = None,
        allow_archive_request: str = "",
    ) -> None:
        def apply(batch: dict[str, Any]) -> None:
            events = batch.setdefault("events", [])
            events.append({"at": now_iso(), "level": level, "message": message, "details": details})
            batch["events"] = events[-200:]
        with self.lock:
            self._assert_batch_not_archived_locked(batch_id, allow_archive_request=allow_archive_request)
            if allow_archive_request:
                self.update(batch_id, apply, allow_archive_request=allow_archive_request)
            else:
                self.update(batch_id, apply)
            with self.db:
                self.db.execute("INSERT INTO events(batch_id,at,level,message,details) VALUES(?,?,?,?,?)", (batch_id, now_iso(), level, message, json.dumps(details, ensure_ascii=False) if details is not None else None))

    def enqueue_command(self, batch_id: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        with self.lock:
            self._assert_batch_not_archived_locked(batch_id)
            batch = self.get(batch_id)
            if terminal_batch_status(batch) or batch.get("overallStatus") == "stopping":
                raise ValueError("批次已结束或正在停止，不能再排队浏览器命令")
            return self._enqueue_command_locked(batch_id, action, payload)

    def _enqueue_command_locked(self, batch_id: str, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self._assert_batch_not_archived_locked(batch_id)
        command = {"id": uuid.uuid4().hex, "batchId": batch_id, "action": action, "payload": payload or {}, "status": "pending", "createdAt": now_iso()}
        with self.db:
            self.db.execute("INSERT INTO commands(id,batch_id,action,payload,status,created_at) VALUES(?,?,?,?,?,?)", (command["id"], batch_id, action, json.dumps(command["payload"], ensure_ascii=False), "pending", command["createdAt"]))
        self.event(batch_id, f"已排队浏览器命令: {action}")
        return command

    def register_bridge(
        self,
        batch_id: str,
        token: str,
        protocol: str,
        bridge_version: str,
        collector_version: str,
        runner_version: str,
        batch_name: str,
        queue_hash: str,
        command_id: str,
        execution_mode: str,
        script_version: str = APPROVED_BROWSER_BRIDGE_SCRIPT_VERSION,
    ) -> dict[str, Any]:
        with self.lock:
            pending_request = self._active_archive_request_locked(batch_id)
            allow_archive_request = str(pending_request["request_id"]) if pending_request else ""
            self._assert_batch_not_archived_locked(batch_id, allow_archive_request=allow_archive_request)
            batch = self.get(batch_id)
            expected = str(batch.get("bridgeToken") or "")
            if not expected or not secrets.compare_digest(expected, token):
                raise ValueError("Browser Bridge token 无效")
            if protocol != "browser-bridge-v2":
                raise ValueError("Browser Bridge protocol 必须为 browser-bridge-v2")
            if bridge_version != APPROVED_BROWSER_BRIDGE_VERSION:
                raise ValueError(f"Browser Bridge 版本必须为 {APPROVED_BROWSER_BRIDGE_VERSION}")
            if script_version != APPROVED_BROWSER_BRIDGE_SCRIPT_VERSION:
                raise ValueError(f"Browser Bridge 脚本必须为 {APPROVED_BROWSER_BRIDGE_SCRIPT_VERSION}")
            if collector_version != APPROVED_COLLECTOR_VERSION or runner_version != APPROVED_RUNNER_VERSION:
                raise ValueError(f"版本不匹配，要求 Collector {APPROVED_COLLECTOR_VERSION} + Runner {APPROVED_RUNNER_VERSION}")
            expected_batch_name = str(batch.get("runnerBatchName") or "")
            if not expected_batch_name or not secrets.compare_digest(expected_batch_name, batch_name):
                raise ValueError("Browser Bridge batchName 与当前批次不一致")
            if not re.fullmatch(r"[0-9a-f]{8}", queue_hash):
                raise ValueError("Browser Bridge queueHash 必须是 Runner 生成的 8 位十六进制值")

            terminal_status = terminal_batch_status(batch)
            if terminal_status:
                raise ValueError("批次已结束，拒绝重新连接 Browser Bridge")
            if not re.fullmatch(r"[0-9a-f]{32}", command_id):
                raise ValueError("Browser Bridge commandId 必须是本次 Start 命令")
            if execution_mode not in {"generated_for_command", "adopted_existing"}:
                raise ValueError("Browser Bridge executionMode 无效")
            start_command = self.db.execute(
                "SELECT action,status FROM commands WHERE id=? AND batch_id=?",
                (command_id, batch_id),
            ).fetchone()
            if not start_command or start_command["action"] != "start":
                raise ValueError("Browser Bridge Start 命令不存在或不属于当前批次")
            own_session = self.db.execute(
                "SELECT status,command_id,execution_mode FROM bridge_sessions WHERE batch_id=?",
                (batch_id,),
            ).fetchone()
            if own_session and (
                str(own_session["command_id"] or "") != command_id
                or str(own_session["execution_mode"] or "") != execution_mode
            ):
                raise ValueError("Browser Bridge 会话与本次 Start 命令不一致")
            reconnecting_while_stopping = bool(
                batch.get("overallStatus") == "stopping"
                and own_session
                and own_session["status"] == "stopping"
            )
            if pending_request and not reconnecting_while_stopping:
                raise ValueError("批次正在删除收尾，只允许恢复原有停止中的 Browser Bridge 会话")
            valid_start_status = start_command["status"] in {"delivered", "accepted"}
            stopping_reconnect_status = reconnecting_while_stopping and start_command["status"] == "cancelled"
            if not valid_start_status and not stopping_reconnect_status:
                raise ValueError("Browser Bridge Start 命令尚未送达或已经失效")
            if batch.get("overallStatus") == "stopping" and not reconnecting_while_stopping:
                raise ValueError("批次正在停止，拒绝启动新的 Browser Bridge 会话")

            at = now_iso()
            active = self.db.execute(
                "SELECT batch_id,status,last_heartbeat FROM bridge_sessions WHERE batch_id<>? AND status IN ('connected','stopping')",
                (batch_id,),
            ).fetchall()
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=BRIDGE_HEARTBEAT_LEASE_SECONDS)
            for row in active:
                if row["status"] == "stopping":
                    raise ValueError(f"Browser Bridge 正在停止批次 {row['batch_id']}，尚未释放")
                heartbeat_value = row["last_heartbeat"]
                if not heartbeat_value:
                    continue
                try:
                    heartbeat_at = datetime.fromisoformat(str(heartbeat_value).replace("Z", "+00:00"))
                except ValueError:
                    continue
                if heartbeat_at >= cutoff:
                    raise ValueError(f"Browser Bridge 已被批次 {row['batch_id']} 占用")

            session_status = "stopping" if reconnecting_while_stopping else "connected"
            with self.db:
                self.db.execute("""INSERT INTO bridge_sessions(batch_id,token_hash,script_version,command_id,execution_mode,collector_version,runner_version,queue_hash,status,last_heartbeat)
                    VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(batch_id) DO UPDATE SET token_hash=excluded.token_hash,script_version=excluded.script_version,command_id=excluded.command_id,execution_mode=excluded.execution_mode,collector_version=excluded.collector_version,runner_version=excluded.runner_version,queue_hash=excluded.queue_hash,status=excluded.status,last_heartbeat=excluded.last_heartbeat""", (batch_id, hashlib.sha256(token.encode()).hexdigest(), script_version, command_id, execution_mode, collector_version, runner_version, queue_hash, session_status, at))

            def apply_connection(current: dict[str, Any]) -> None:
                stage = current["stages"]["browser"]
                if reconnecting_while_stopping:
                    stage["status"] = "stopping"
                    stage["message"] = "正在等待 Runner 完成当前 ASIN 后停止"
                elif stage.get("status") not in {"running", "needs_attention", "completed"}:
                    stage["status"] = "waiting"
                stage["connection"] = {"status": session_status, "bridgeVersion": bridge_version, "scriptVersion": script_version, "commandId": command_id, "executionMode": execution_mode, "collectorVersion": collector_version, "runnerVersion": runner_version, "batchName": batch_name, "queueHash": queue_hash, "lastHeartbeat": at}

            updated = self.update(batch_id, apply_connection, allow_archive_request=allow_archive_request)
            event_message = "Browser Bridge 已在停止过程中重新连接" if reconnecting_while_stopping else "Browser Bridge 已连接"
            self.event(batch_id, event_message, "info" if reconnecting_while_stopping else "success", {"bridgeVersion": bridge_version, "scriptVersion": script_version, "commandId": command_id, "executionMode": execution_mode, "collectorVersion": collector_version, "runnerVersion": runner_version, "batchName": batch_name, "queueHash": queue_hash}, allow_archive_request=allow_archive_request)
            checkpoint = updated.get("stages", {}).get("browser", {}).get("stats", {})
            return {"ok": True, "batchId": batch_id, "serverTime": at, "checkpoint": checkpoint, "approvedPair": {"bridge": APPROVED_BROWSER_BRIDGE_VERSION, "collector": APPROVED_COLLECTOR_VERSION, "runner": APPROVED_RUNNER_VERSION}}

    def bridge_batch(self, batch_id: str, token: str, allow_archive_request: str = "") -> sqlite3.Row:
        with self.lock:
            row = self.db.execute("SELECT token_hash,script_version,command_id,execution_mode,queue_hash FROM bridge_sessions WHERE batch_id=?", (batch_id,)).fetchone()
            if not row or not secrets.compare_digest(row["token_hash"], hashlib.sha256(token.encode()).hexdigest()):
                raise ValueError("Browser Bridge 身份验证失败")
            if str(row["script_version"] or "") != APPROVED_BROWSER_BRIDGE_SCRIPT_VERSION:
                raise ValueError(f"Browser Bridge 会话脚本已过期，要求 {APPROVED_BROWSER_BRIDGE_SCRIPT_VERSION}")
            self._assert_batch_not_archived_locked(batch_id, allow_archive_request=allow_archive_request)
            return row

    def validate_bridge_runner_identity(
        self,
        batch_id: str,
        token: str,
        payload: dict[str, Any],
        allow_archive_request: str = "",
    ) -> None:
        row = self.bridge_batch(batch_id, token, allow_archive_request=allow_archive_request)
        if str(payload.get("protocol") or "") != "browser-bridge-v2":
            raise ValueError("Browser Bridge protocol 必须为 browser-bridge-v2")
        if str(payload.get("bridgeVersion") or "") != APPROVED_BROWSER_BRIDGE_VERSION:
            raise ValueError(f"Browser Bridge 版本必须为 {APPROVED_BROWSER_BRIDGE_VERSION}")
        if str(payload.get("scriptVersion") or "") != APPROVED_BROWSER_BRIDGE_SCRIPT_VERSION:
            raise ValueError(f"Browser Bridge 脚本必须为 {APPROVED_BROWSER_BRIDGE_SCRIPT_VERSION}")
        expected_command_id = str(row["command_id"] or "")
        actual_command_id = str(payload.get("commandId") or "")
        if not expected_command_id or not secrets.compare_digest(expected_command_id, actual_command_id):
            raise ValueError("拒绝非本次 Start 命令的 Browser Bridge 数据")
        expected_execution_mode = str(row["execution_mode"] or "")
        actual_execution_mode = str(payload.get("executionMode") or "")
        if not expected_execution_mode or not secrets.compare_digest(expected_execution_mode, actual_execution_mode):
            raise ValueError("拒绝执行来源不一致的 Browser Bridge 数据")
        expected_batch_name = str(self.get(batch_id).get("runnerBatchName") or "")
        actual_batch_name = str(payload.get("batchName") or "")
        if not expected_batch_name or not secrets.compare_digest(expected_batch_name, actual_batch_name):
            raise ValueError("拒绝非当前批次的 Browser Bridge 数据")
        expected_queue_hash = str(row["queue_hash"] or "")
        actual_queue_hash = str(payload.get("queueHash") or "")
        if not expected_queue_hash or not secrets.compare_digest(expected_queue_hash, actual_queue_hash):
            raise ValueError("拒绝非当前队列的 Browser Bridge 数据")

    def heartbeat(self, batch_id: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
        status = str(payload.get("status") or "running")
        if status not in {"waiting", "running", "paused", "needs_attention", "done"}:
            raise ValueError("Runner 心跳状态无效")
        allow_archive_request = ""
        with self.lock:
            pending_request = self._active_archive_request_locked(batch_id)
            if pending_request:
                allow_archive_request = str(pending_request["request_id"])
        self.validate_bridge_runner_identity(
            batch_id,
            token,
            payload,
            allow_archive_request=allow_archive_request,
        )
        if allow_archive_request and status != "done":
            raise ValueError("批次正在删除收尾，仅接受 Runner 完成停止回执")
        at = now_iso()
        allowed_stats = {
            "status", "batchName", "queueHash", "total", "completed", "qualifiedCount", "rejectedCount",
            "errorCount", "rowIndex", "asin", "gate", "decision", "message", "bridgeVersion",
            "runnerVersion", "collectorVersion",
        }
        previous = {key: value for key, value in self.get(batch_id)["stages"]["browser"].get("stats", {}).items() if key in allowed_stats or key == "lastHeartbeat"}
        current_stats = {key: payload.get(key) for key in allowed_stats if key in payload}
        stats = {**previous, **current_stats, "lastHeartbeat": at}
        def apply(batch: dict[str, Any]) -> None:
            stage = batch["stages"]["browser"]
            terminal_status = terminal_batch_status(batch)
            stopping = batch.get("overallStatus") == "stopping"
            session_status = terminal_status or ("cancelled" if stopping and status == "done" else "stopping" if stopping else "connected")
            with self.db:
                self.db.execute(
                    "UPDATE bridge_sessions SET status=?,last_heartbeat=? WHERE batch_id=?",
                    (session_status, at, batch_id),
                )
            if terminal_status:
                batch["overallStatus"] = terminal_status
                stage["connection"] = {
                    "status": terminal_status,
                    "lastHeartbeat": at,
                    "bridgeVersion": payload.get("bridgeVersion", ""),
                    "collectorVersion": payload.get("collectorVersion", ""),
                    "runnerVersion": payload.get("runnerVersion", ""),
                    "batchName": payload.get("batchName", ""),
                    "queueHash": payload.get("queueHash", ""),
                }
                return
            if stopping:
                stage["stats"] = stats
                if status == "done":
                    batch["overallStatus"] = "cancelled"
                    batch.pop("cancelCommandId", None)
                    batch.pop("cancelRetryCount", None)
                    stage["status"] = "cancelled"
                    stage["message"] = "Runner 已完成当前行并停止"
                    stage["connection"] = {"status": "cancelled", "lastHeartbeat": at, "bridgeVersion": payload.get("bridgeVersion", ""), "collectorVersion": payload.get("collectorVersion", ""), "runnerVersion": payload.get("runnerVersion", ""), "batchName": payload.get("batchName", ""), "queueHash": payload.get("queueHash", "")}
                else:
                    stage["status"] = "stopping"
                    stage["message"] = "正在等待 Runner 完成当前 ASIN 后停止"
                    stage["connection"] = {"status": "stopping", "lastHeartbeat": at, "bridgeVersion": payload.get("bridgeVersion", ""), "collectorVersion": payload.get("collectorVersion", ""), "runnerVersion": payload.get("runnerVersion", ""), "batchName": payload.get("batchName", ""), "queueHash": payload.get("queueHash", "")}
                return
            verified_json = bool(batch.get("jsonHandoff", {}).get("sourceSha256"))
            stage["status"] = "needs_attention" if status in {"paused", "needs_attention"} else ("completed" if status == "done" and verified_json else "running")
            stage["message"] = ("Runner 已完成，合并 JSON 已校验" if verified_json else "Runner 已完成，等待校验合并 JSON") if status == "done" else str(payload.get("message") or "浏览器正在采集")
            stage["stats"] = stats
            stage["connection"] = {"status": "connected", "lastHeartbeat": at, "bridgeVersion": payload.get("bridgeVersion", ""), "collectorVersion": payload.get("collectorVersion", ""), "runnerVersion": payload.get("runnerVersion", ""), "batchName": payload.get("batchName", ""), "queueHash": payload.get("queueHash", "")}
            if stage["status"] == "completed":
                batch["overallStatus"] = "excel_ready"
            elif stage["status"] == "needs_attention":
                batch["overallStatus"] = "needs_attention"
            else:
                batch["overallStatus"] = "running"
        result = (
            self.update(batch_id, apply, allow_archive_request=allow_archive_request)
            if allow_archive_request
            else self.update(batch_id, apply)
        )
        if result.get("overallStatus") == "cancelled":
            self.complete_stop_commands(batch_id, allow_archive_request=allow_archive_request)
            if allow_archive_request:
                self.reconcile_archive_requests()
        asin = str(payload.get("asin") or "")
        if asin and not allow_archive_request and asin != str(previous.get("asin") or ""):
            self.record_asin_event(batch_id, asin, payload.get("rowIndex"), "heartbeat", payload.get("gate"), payload.get("decision"), stats)
        # Browser Bridge executes commands only from the authenticated global control poll.
        # Returning pending commands here would mark them delivered without executing them.
        return {"ok": True, "serverTime": at, "commands": []}

    def poll_commands(self, batch_id: str, token: str) -> list[dict[str, Any]]:
        with self.lock:
            now = now_iso()
            if self._batch_is_archived_locked(batch_id):
                with self.db:
                    self.db.execute(
                        """UPDATE commands SET status='cancelled',acknowledged_at=?
                           WHERE batch_id=? AND status IN ('pending','delivered','accepted')""",
                        (now, batch_id),
                    )
                return []
            self.bridge_batch(batch_id, token)
            batch = self.get(batch_id)
            rows = self.db.execute("SELECT * FROM commands WHERE batch_id=? AND status='pending' ORDER BY created_at LIMIT 20", (batch_id,)).fetchall()
            if terminal_batch_status(batch) or batch.get("overallStatus") == "stopping":
                with self.db:
                    self.db.execute(
                        "UPDATE commands SET status='cancelled',acknowledged_at=? WHERE batch_id=? AND status='pending'",
                        (now, batch_id),
                    )
                return []
            commands = []
            with self.db:
                for row in rows:
                    self.db.execute("UPDATE commands SET status='delivered',delivered_at=? WHERE id=?", (now, row["id"]))
                    commands.append({"id": row["id"], "action": row["action"], "payload": json.loads(row["payload"]), "createdAt": row["created_at"]})
            return commands

    def poll_global_commands(
        self,
        pairing_token: str,
        protocol: str = "",
        bridge_version: str = "",
        script_version: str = APPROVED_BROWSER_BRIDGE_SCRIPT_VERSION,
    ) -> list[dict[str, Any]]:
        if not secrets.compare_digest(BROWSER_PAIRING_TOKEN, pairing_token):
            raise ValueError("Browser Bridge 配对码无效")
        if (
            protocol != "browser-bridge-v2"
            or bridge_version != APPROVED_BROWSER_BRIDGE_VERSION
            or script_version != APPROVED_BROWSER_BRIDGE_SCRIPT_VERSION
        ):
            raise ValueError(
                f"请先将 Browser Bridge 更新到协议 {APPROVED_BROWSER_BRIDGE_VERSION} / 脚本 {APPROVED_BROWSER_BRIDGE_SCRIPT_VERSION}"
            )
        with self.lock:
            for batch_id in list(self.batches):
                self._reconcile_stale_stopping_locked(batch_id, control_active=True)
            retry_before = (datetime.now(timezone.utc) - timedelta(seconds=COMMAND_DELIVERY_LEASE_SECONDS)).isoformat(timespec="seconds")
            rows = self.db.execute(
                """SELECT * FROM commands
                   WHERE action NOT LIKE 'seller_export%'
                     AND (status='pending' OR (status='delivered' AND delivered_at<=?))
                   ORDER BY created_at LIMIT 1""",
                (retry_before,),
            ).fetchall()
            commands = []
            delivered_at = now_iso()
            with self.db:
                for row in rows:
                    batch = self.get(row["batch_id"])
                    if batch.get("archived"):
                        self.db.execute("UPDATE commands SET status='cancelled',acknowledged_at=? WHERE id=?", (delivered_at, row["id"]))
                        continue
                    terminal_status = terminal_batch_status(batch)
                    if terminal_status:
                        terminal_command_status = "completed" if row["action"] == "stop_after_current" and terminal_status == "cancelled" else "cancelled"
                        self.db.execute("UPDATE commands SET status=?,acknowledged_at=? WHERE id=?", (terminal_command_status, delivered_at, row["id"]))
                        continue
                    if batch.get("overallStatus") == "stopping" and (
                        row["action"] != "stop_after_current"
                        or batch.get("cancelCommandId") != row["id"]
                    ):
                        self.db.execute("UPDATE commands SET status='cancelled',acknowledged_at=? WHERE id=?", (delivered_at, row["id"]))
                        continue
                    self.db.execute("UPDATE commands SET status='delivered',delivered_at=? WHERE id=?", (delivered_at, row["id"]))
                    commands.append({
                        "id": row["id"],
                        "batchId": row["batch_id"],
                        "batchToken": batch.get("bridgeToken", ""),
                        "protocol": batch.get("bridgeProtocol", "browser-bridge-v2"),
                        "action": row["action"],
                        "payload": json.loads(row["payload"]),
                        "createdAt": row["created_at"],
                    })
            return commands

    def enqueue_sellersprite_command(self, batch_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Queue one source-export job while keeping duplicate polls idempotent."""
        with self.lock:
            self._assert_batch_not_archived_locked(batch_id)
            batch = self.get(batch_id)
            if terminal_batch_status(batch) or batch.get("overallStatus") == "stopping":
                return None
            category_input = str(payload.get("categoryInput") or "").strip()
            if not category_input:
                raise ValueError("SellerSprite 导出命令缺少 categoryInput")
            rows = self.db.execute(
                "SELECT action,payload,status FROM commands WHERE batch_id=? AND action='seller_export' AND status IN ('pending','delivered','accepted')",
                (batch_id,),
            ).fetchall()
            for row in rows:
                try:
                    existing = json.loads(row["payload"])
                except json.JSONDecodeError:
                    continue
                if str(existing.get("categoryInput") or "") == category_input:
                    return None
            command = {
                "id": uuid.uuid4().hex,
                "batchId": batch_id,
                "action": "seller_export",
                "payload": payload,
                "status": "pending",
                "createdAt": now_iso(),
            }
            with self.db:
                self.db.execute(
                    "INSERT INTO commands(id,batch_id,action,payload,status,created_at) VALUES(?,?,?,?,?,?)",
                    (command["id"], batch_id, command["action"], json.dumps(payload, ensure_ascii=False), "pending", command["createdAt"]),
                )
            self.event(batch_id, f"已下发 SellerSprite 导出命令: {category_input}", "info", {"commandId": command["id"]})
            return command

    def poll_sellersprite_commands(self, pairing_token: str) -> list[dict[str, Any]]:
        if not ENABLE_SELLERSPRITE_BRIDGE or not secrets.compare_digest(BROWSER_PAIRING_TOKEN, pairing_token):
            raise ValueError("SellerSprite Bridge 配对码无效或功能未启用")
        with self.lock:
            retry_before = (datetime.now(timezone.utc) - timedelta(seconds=COMMAND_DELIVERY_LEASE_SECONDS)).isoformat(timespec="seconds")
            rows = self.db.execute(
                """SELECT * FROM commands
                   WHERE action='seller_export'
                     AND (status='pending' OR (status='delivered' AND delivered_at<=?))
                   ORDER BY created_at LIMIT 1""",
                (retry_before,),
            ).fetchall()
            commands = []
            delivered_at = now_iso()
            with self.db:
                for row in rows:
                    batch = self.get(row["batch_id"])
                    if batch.get("archived"):
                        self.db.execute("UPDATE commands SET status='cancelled',acknowledged_at=? WHERE id=?", (delivered_at, row["id"]))
                        continue
                    if terminal_batch_status(batch) or batch.get("overallStatus") == "stopping":
                        self.db.execute("UPDATE commands SET status='cancelled',acknowledged_at=? WHERE id=?", (delivered_at, row["id"]))
                        continue
                    self.db.execute("UPDATE commands SET status='delivered',delivered_at=? WHERE id=?", (delivered_at, row["id"]))
                    commands.append({
                        "id": row["id"],
                        "batchId": row["batch_id"],
                        "batchToken": batch.get("bridgeToken", ""),
                        "action": row["action"],
                        "payload": json.loads(row["payload"]),
                        "createdAt": row["created_at"],
                    })
            return commands

    def acknowledge_sellersprite_command(self, pairing_token: str, batch_id: str, command_id: str, status: str, message: str = "") -> None:
        if not ENABLE_SELLERSPRITE_BRIDGE or not secrets.compare_digest(BROWSER_PAIRING_TOKEN, pairing_token):
            raise ValueError("SellerSprite Bridge 配对码无效或功能未启用")
        if status not in {"accepted", "completed", "failed"}:
            raise ValueError("SellerSprite 导出命令回执状态无效")
        with self.lock:
            row = self.db.execute("SELECT action FROM commands WHERE id=? AND batch_id=?", (command_id, batch_id)).fetchone()
            if not row or row["action"] != "seller_export":
                raise ValueError("SellerSprite 导出命令不存在")
            pending = self._active_archive_request_locked(batch_id)
            allow_archive_request = str(pending["request_id"]) if pending and status in {"completed", "failed"} else ""
            self._assert_batch_not_archived_locked(batch_id, allow_archive_request=allow_archive_request)
            batch = self.get(batch_id)
            mutable = not terminal_batch_status(batch) and batch.get("overallStatus") != "stopping"
            effective_status = status if mutable else "cancelled"
            with self.db:
                self.db.execute("UPDATE commands SET status=?,acknowledged_at=? WHERE id=? AND batch_id=?", (effective_status, now_iso(), command_id, batch_id))
            if status == "failed" and mutable:
                self.update(batch_id, lambda b: (set_stage(b, "candidates", "needs_attention", message or "SellerSprite 自动导出失败", {"sellerSpriteBridge": {"status": "needs_attention", "message": message}}), b.update({"overallStatus": "needs_attention"})))
            self.event(batch_id, f"SellerSprite 导出命令 {command_id[:8]}: {status}", "warning" if status == "failed" else "info", message or None, allow_archive_request=allow_archive_request)

    def acknowledge_command(self, batch_id: str, token: str, command_id: str, status: str, message: str = "") -> None:
        with self.lock:
            if self._batch_is_archived_locked(batch_id):
                self._assert_batch_not_archived_locked(batch_id)
            row = self.db.execute("SELECT action FROM commands WHERE id=? AND batch_id=?", (command_id, batch_id)).fetchone()
            if not row:
                raise ValueError("浏览器命令不存在")
            pending = self._active_archive_request_locked(batch_id)
            allow_archive_request = str(pending["request_id"]) if pending and row["action"] == "stop_after_current" and status in {"accepted", "completed", "failed", "cancelled"} else ""
            self._assert_batch_not_archived_locked(batch_id, allow_archive_request=allow_archive_request)
            self.bridge_batch(batch_id, token, allow_archive_request=allow_archive_request)
            with self.db:
                self.db.execute("UPDATE commands SET status=?,acknowledged_at=? WHERE id=? AND batch_id=?", (status, now_iso(), command_id, batch_id))
            self.event(batch_id, f"浏览器命令 {command_id[:8]}: {status}", "warning" if status == "failed" else "info", message or None, allow_archive_request=allow_archive_request)

    def acknowledge_global_command(self, pairing_token: str, batch_id: str, command_id: str, status: str, message: str = "") -> None:
        if not secrets.compare_digest(BROWSER_PAIRING_TOKEN, pairing_token):
            raise ValueError("Browser Bridge 配对码无效")
        if status not in {"accepted", "completed", "failed"}:
            raise ValueError("浏览器命令回执状态无效")
        with self.lock:
            row = self.db.execute("SELECT action FROM commands WHERE id=? AND batch_id=?", (command_id, batch_id)).fetchone()
            if not row:
                raise ValueError("浏览器命令不存在")
            pending = self._active_archive_request_locked(batch_id)
            allow_archive_request = str(pending["request_id"]) if pending and row["action"] == "stop_after_current" else ""
            self._assert_batch_not_archived_locked(batch_id, allow_archive_request=allow_archive_request)
            batch = self.get(batch_id)
            owns_active_stop = bool(
                row["action"] == "stop_after_current"
                and status == "failed"
                and batch.get("overallStatus") == "stopping"
                and batch.get("cancelCommandId") == command_id
            )
            terminal_status = terminal_batch_status(batch)
            if row["action"] == "stop_after_current" and terminal_status == "cancelled":
                effective_status = "completed"
            elif terminal_status or (batch.get("overallStatus") == "stopping" and row["action"] != "stop_after_current"):
                effective_status = "cancelled"
            else:
                effective_status = status
            with self.db:
                self.db.execute("UPDATE commands SET status=?,acknowledged_at=? WHERE id=? AND batch_id=?", (effective_status, now_iso(), command_id, batch_id))
            if owns_active_stop:
                retry_count = int(batch.get("cancelRetryCount") or 0)
                # An archive request owns the fence; do not enqueue a new
                # command behind it after a late stop failure. The durable
                # request will wait for an explicit done/terminal signal or
                # fail closed on timeout.
                replacement = (
                    self._enqueue_command_locked(batch_id, "stop_after_current", {})
                    if not allow_archive_request and retry_count < MAX_AUTOMATIC_STOP_RETRIES
                    else None
                )

                def preserve_stop_intent(current: dict[str, Any]) -> None:
                    if current.get("overallStatus") != "stopping" or current.get("cancelCommandId") != command_id:
                        return
                    current["overallStatus"] = "stopping"
                    current["stages"]["browser"]["status"] = "stopping"
                    if replacement:
                        current["cancelCommandId"] = replacement["id"]
                        current["cancelRequestedAt"] = now_iso()
                        current["cancelRetryCount"] = retry_count + 1
                        current["stages"]["browser"]["message"] = "Runner 停止命令执行失败，已自动重新发送"
                    else:
                        current["stages"]["browser"]["message"] = message or "Runner 停止命令连续失败；停止意图仍锁定，请重试停止"
                    connection = current["stages"]["browser"].get("connection")
                    if isinstance(connection, dict):
                        connection["status"] = "stopping"

                self.update(batch_id, preserve_stop_intent, allow_archive_request=allow_archive_request)
                with self.db:
                    self.db.execute("UPDATE bridge_sessions SET status='stopping' WHERE batch_id=?", (batch_id,))
                if replacement:
                    self.event(batch_id, "Runner 停止命令失败，已使用新命令重新发送", "warning", {"previousCommandId": command_id[:8], "commandId": replacement["id"][:8], "retry": retry_count + 1}, allow_archive_request=allow_archive_request)
            event_details = message or None
            if effective_status != status:
                event_details = {"requestedStatus": status, "effectiveStatus": effective_status, "message": message}
            self.event(batch_id, f"浏览器命令 {command_id[:8]}: {effective_status}", "warning" if effective_status in {"failed", "cancelled"} else "info", event_details, allow_archive_request=allow_archive_request)

    def complete_stop_commands(self, batch_id: str, allow_archive_request: str = "") -> None:
        with self.lock:
            self._assert_batch_not_archived_locked(batch_id, allow_archive_request=allow_archive_request)
            with self.db:
                self.db.execute(
                    "UPDATE commands SET status='completed',acknowledged_at=? WHERE batch_id=? AND action='stop_after_current' AND status IN ('pending','delivered','accepted')",
                    (now_iso(), batch_id),
                )

    def record_asin_event(self, batch_id: str, asin: str, row_index: Any, event_type: str, gate: Any, decision: Any, payload: Any) -> None:
        with self.lock:
            self._assert_batch_not_archived_locked(batch_id)
            with self.db:
                self.db.execute("INSERT INTO asin_events(batch_id,asin,row_index,event_type,gate,decision,payload,at) VALUES(?,?,?,?,?,?,?,?)", (batch_id, asin, int(row_index) if str(row_index or "").isdigit() else None, event_type, gate or None, decision or None, json.dumps(payload or {}, ensure_ascii=False), now_iso()))

    def register_artifact(self, batch_id: str, key: str, path_value: str, kind: str = "") -> dict[str, Any]:
        with self.lock:
            self._assert_batch_not_archived_locked(batch_id)
            path = Path(path_value).resolve()
            if not path.is_file() or (not safe_child(PROJECT_ROOT, path) and not safe_child(WORKSPACE_ROOT, path)):
                raise ValueError("Bridge 产物路径不在允许目录或文件不存在")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.db:
                self.db.execute("INSERT OR IGNORE INTO artifacts(batch_id,artifact_key,path,sha256,kind,created_at) VALUES(?,?,?,?,?,?)", (batch_id, key, str(path), digest, kind, now_iso()))
            self.event(batch_id, f"已登记浏览器产物: {key}", "success", {"path": str(path), "sha256": digest})
            return {"key": key, "path": str(path), "sha256": digest, "kind": kind}

    def _legacy_persist(self) -> None:
        atomic_json_write(STATE_PATH, {"schemaVersion": "amazonSelectionConsole/v1", "batches": list(self.batches.values())})

    def _archive_request_row_locked(self, batch_id: str) -> sqlite3.Row | None:
        return self.db.execute(
            "SELECT * FROM batch_archive_requests WHERE batch_id=?",
            (batch_id,),
        ).fetchone()

    def _active_archive_request_locked(self, batch_id: str) -> sqlite3.Row | None:
        row = self._archive_request_row_locked(batch_id)
        return row if row and row["status"] in ARCHIVE_REQUEST_ACTIVE_STATUSES else None

    def _archive_request_snapshot_locked(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if not row:
            return None
        return {
            "requestId": str(row["request_id"]),
            "batchId": str(row["batch_id"]),
            "idempotencyKey": str(row["idempotency_key"] or ""),
            "status": str(row["status"]),
            "phase": str(row["phase"]),
            "requestedAt": str(row["requested_at"]),
            "updatedAt": str(row["updated_at"]),
            "attempt": int(row["attempt"] or 0),
            "lastError": str(row["last_error"] or ""),
        }

    def _assert_batch_not_archived_locked(self, batch_id: str, allow_archive_request: str = "") -> None:
        if self._batch_is_archived_locked(batch_id):
            raise ValueError("批次已删除，请先恢复后再操作")
        pending = self._active_archive_request_locked(batch_id)
        if pending and str(pending["request_id"]) != str(allow_archive_request or ""):
            raise ValueError("批次正在删除收尾，请等待收尾完成")

    def snapshot(self, batch: dict[str, Any]) -> dict[str, Any]:
        result = copy.deepcopy(batch)
        if not ENABLE_CATEGORY_REPOSITORY:
            result["archived"] = False
            result["archivedAt"] = ""
            result["archiveEligible"] = False
            result["archiveBlockedReason"] = "类目仓库功能未启用"
            result["archiveRequestEligible"] = False
            result["archiveRequestBlockedReason"] = "类目仓库功能未启用"
            result["archiveRequest"] = None
            result.pop("restoredAt", None)
            return result
        archive = self.db.execute(
            "SELECT archived_at,restored_at FROM batch_archive_state WHERE batch_id=?",
            (batch["id"],),
        ).fetchone()
        archived_at = str(archive["archived_at"] or "") if archive else ""
        result["archived"] = bool(archived_at)
        result["archivedAt"] = archived_at
        if archive and archive["restored_at"]:
            result["restoredAt"] = str(archive["restored_at"])
        request = self._archive_request_row_locked(str(batch["id"]))
        result["archiveRequest"] = self._archive_request_snapshot_locked(request)
        blocked_reason = "批次已删除" if archived_at else self._archive_blocked_reason_locked(batch)
        result["archiveEligible"] = not bool(blocked_reason)
        result["archiveBlockedReason"] = blocked_reason
        request_blocked = "批次已删除" if archived_at else self._archive_requestable_reason_locked(batch)
        result["archiveRequestEligible"] = not bool(request_blocked)
        result["archiveRequestBlockedReason"] = request_blocked
        return result

    def _batch_is_archived_locked(self, batch_id: str) -> bool:
        if not ENABLE_CATEGORY_REPOSITORY:
            return False
        row = self.db.execute(
            "SELECT archived_at FROM batch_archive_state WHERE batch_id=?",
            (batch_id,),
        ).fetchone()
        return bool(row and row["archived_at"])

    def _archive_blocked_reason_locked(self, batch: dict[str, Any]) -> str:
        batch_id = str(batch.get("id") or "")
        if batch_id in self.jobs:
            return "批次仍有任务运行（本地任务），请先停止"
        durable_job = self.db.execute(
            """SELECT stage,status,pid FROM local_job_leases
               WHERE batch_id=? AND status IN ('starting','running')
               ORDER BY started_at LIMIT 1""",
            (batch_id,),
        ).fetchone()
        if durable_job:
            return f"批次仍有持久化本地任务记录（{durable_job['stage']}），请先确认恢复状态"
        orphaned_jobs = self.db.execute(
            """SELECT id,stage,pid FROM local_job_leases
               WHERE batch_id=? AND status='orphaned' AND pid IS NOT NULL
               ORDER BY started_at""",
            (batch_id,),
        ).fetchall()
        for orphaned_job in orphaned_jobs:
            if local_pid_alive(orphaned_job["pid"]):
                return (
                    f"批次仍有未确认归属的遗留本地进程（{orphaned_job['stage']}，PID {int(orphaned_job['pid'])}），"
                    "请先结束该进程后再删除"
                )
            self._update_local_job_locked(
                str(orphaned_job["id"]),
                status="interrupted",
                ended_at=now_iso(),
                recovery_reason="orphan_process_missing_before_archive",
            )
        if terminal_batch_status(batch):
            return ""
        if str(batch.get("overallStatus") or "") in {"running", "stopping"}:
            return "批次正在运行或停止中，请等待停止完成"
        if any(
            str(stage.get("status") or "") in {"running", "stopping"}
            for stage in (batch.get("stages") or {}).values()
            if isinstance(stage, dict)
        ):
            return "批次仍有流程阶段运行或停止中，请先停止"
        active_command = self.db.execute(
            """SELECT action,status FROM commands
               WHERE batch_id=? AND status IN ('pending','delivered','accepted')
               ORDER BY created_at LIMIT 1""",
            (batch_id,),
        ).fetchone()
        if active_command:
            return f"批次仍有活跃浏览器命令 {active_command['action']}（{active_command['status']}），请先停止"
        bridge_session = self.db.execute(
            "SELECT status FROM bridge_sessions WHERE batch_id=? AND status IN ('connected','stopping')",
            (batch_id,),
        ).fetchone()
        if bridge_session:
            return f"批次仍有活跃 Browser Bridge 会话（{bridge_session['status']}），请先停止"
        dispatch = self.db.execute(
            """SELECT status FROM thread_dispatches
               WHERE batch_id=? AND status IN ('prepared','sent')
               ORDER BY created_at LIMIT 1""",
            (batch_id,),
        ).fetchone()
        if dispatch:
            return f"批次仍有外部任务派发（{dispatch['status']}），请先结束任务"
        return ""

    def _revoke_stale_terminal_activity_locked(self, batch: dict[str, Any], archived_at: str) -> dict[str, int]:
        terminal_status = terminal_batch_status(batch)
        if not terminal_status:
            return {"commands": 0, "bridgeSessions": 0, "dispatches": 0}
        commands = self.db.execute(
            """UPDATE commands SET status='cancelled',acknowledged_at=?
               WHERE batch_id=? AND status IN ('pending','delivered','accepted')""",
            (archived_at, batch["id"]),
        ).rowcount
        bridge_sessions = self.db.execute(
            """UPDATE bridge_sessions SET status=?
               WHERE batch_id=? AND status IN ('connected','stopping')""",
            (terminal_status, batch["id"]),
        ).rowcount
        dispatches = self.db.execute(
            """UPDATE thread_dispatches SET status='cancelled',updated_at=?
               WHERE batch_id=? AND status IN ('prepared','sent')""",
            (archived_at, batch["id"]),
        ).rowcount
        return {
            "commands": max(0, int(commands)),
            "bridgeSessions": max(0, int(bridge_sessions)),
            "dispatches": max(0, int(dispatches)),
        }

    def archive_batches(self, batch_ids: list[str], archive_request_id: str = "") -> dict[str, Any]:
        if not ENABLE_CATEGORY_REPOSITORY:
            raise ValueError("类目仓库功能未启用")
        if not isinstance(batch_ids, list) or not batch_ids:
            raise ValueError("batchIds 必须是非空数组")
        normalized_ids: list[str] = []
        seen: set[str] = set()
        for value in batch_ids:
            batch_id = str(value or "").strip()
            if not re.fullmatch(r"[a-f0-9]{12}", batch_id):
                raise ValueError("batchIds 包含无效批次 ID")
            if batch_id not in seen:
                seen.add(batch_id)
                normalized_ids.append(batch_id)
        if len(normalized_ids) > 500:
            raise ValueError("单次最多删除 500 个批次")
        with self.lock:
            batches: list[dict[str, Any]] = []
            already_archived: set[str] = set()
            blockers: list[str] = []
            for batch_id in normalized_ids:
                batch = self.batches.get(batch_id)
                if not batch:
                    raise KeyError(batch_id)
                batches.append(batch)
                existing = self.db.execute(
                    "SELECT archived_at FROM batch_archive_state WHERE batch_id=?",
                    (batch_id,),
                ).fetchone()
                if existing and existing["archived_at"]:
                    already_archived.add(batch_id)
                    continue
                request = self._active_archive_request_locked(batch_id)
                if request and str(request["request_id"]) != str(archive_request_id or ""):
                    blockers.append(f"{batch.get('name') or batch_id}: 批次正在删除收尾，请等待当前请求")
                    continue
                blocked_reason = self._archive_blocked_reason_locked(batch)
                if blocked_reason:
                    blockers.append(f"{batch.get('name') or batch_id}: {blocked_reason}")
            if blockers:
                raise ValueError("存在不可删除的批次，未执行任何删除：" + "；".join(blockers))

            archived_at = now_iso()
            with self.db:
                for batch in batches:
                    batch_id = batch["id"]
                    if batch_id in already_archived:
                        continue
                    revoked_activity = self._revoke_stale_terminal_activity_locked(batch, archived_at)
                    retained_pool_item_id = str(batch.get("categoryPoolItemId") or "")
                    self.db.execute(
                        """INSERT INTO batch_archive_state(batch_id,archived_at,restored_at,updated_at,feature_version)
                           VALUES(?,?,NULL,?,?)
                           ON CONFLICT(batch_id) DO UPDATE SET
                               archived_at=excluded.archived_at,restored_at=NULL,
                               updated_at=excluded.updated_at,feature_version=excluded.feature_version""",
                        (batch_id, archived_at, archived_at, CATEGORY_REPOSITORY_VERSION),
                    )
                    self._audit_feature_locked(
                        "batch_archived", "batch", batch_id, "archived",
                        {
                            "overallStatus": batch.get("overallStatus"),
                            "completedWorkflow": verified_completed_workflow(batch),
                            "archivedAt": archived_at,
                            "retainedCategoryPoolItemId": retained_pool_item_id,
                            "revokedStaleActivity": revoked_activity,
                            "requestCount": len(normalized_ids),
                        },
                    )
            return {
                "schemaVersion": "batchArchiveResult/v2",
                "archivedCount": len(normalized_ids) - len(already_archived),
                "requestedCount": len(normalized_ids),
                "batchIds": normalized_ids,
                "batches": [self.snapshot(batch) for batch in batches],
            }

    def archive_completed_batch(self, batch_id: str, archive_request_id: str = "") -> dict[str, Any]:
        """Backward-compatible single-batch entry point for recoverable archive."""
        return self.archive_batches([batch_id], archive_request_id=archive_request_id)["batches"][0]

    def _archive_requestable_reason_locked(self, batch: dict[str, Any]) -> str:
        """Return only blockers that make it unsafe to even request cancellation."""
        if self._batch_is_archived_locked(str(batch.get("id") or "")):
            return "批次已删除"
        existing = self._active_archive_request_locked(str(batch.get("id") or ""))
        if existing:
            return "批次正在删除收尾"
        owned_process = self.jobs.get(batch["id"])
        owned_job_ids = {
            str(stage.get("artifacts", {}).get("localJobId") or "")
            for stage in (batch.get("stages") or {}).values()
            if isinstance(stage, dict)
        }
        for row in self.db.execute(
            """SELECT id,stage,pid,status FROM local_job_leases
               WHERE batch_id=? AND status IN ('starting','running','orphaned')
               ORDER BY started_at""",
            (batch["id"],),
        ).fetchall():
            row_status = str(row["status"] or "")
            if row_status == "orphaned":
                if local_pid_alive(row["pid"]):
                    pid = f"，PID {int(row['pid'])}" if row["pid"] else ""
                    return f"批次有无法安全接管的本地任务（{row['stage']}{pid}），请先确认进程已结束"
                continue
            # A lease owned by this console can be terminated by cancel(); only
            # an unowned live/unknown lease must fail closed before requesting.
            row_pid = int(row["pid"]) if row["pid"] is not None else None
            if owned_process is not None and str(row["id"]) in owned_job_ids:
                continue
            if row_status in {"starting", "running"} and (not row_pid or local_pid_alive(row_pid)):
                pid = f"，PID {row_pid}" if row_pid else ""
                return f"批次有无法安全接管的本地任务（{row['stage']}{pid}），请先确认进程已结束"
        return ""

    def _insert_archive_request_locked(self, batch_id: str, idempotency_key: str = "") -> sqlite3.Row:
        now = now_iso()
        request_id = uuid.uuid4().hex
        self.db.execute(
            """INSERT INTO batch_archive_requests(
                   request_id,batch_id,idempotency_key,status,phase,requested_at,updated_at,attempt,last_error
               ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (request_id, batch_id, idempotency_key, "requested", "requested", now, now, 1, ""),
        )
        return self._archive_request_row_locked(batch_id)

    def _record_archive_request_failure_locked(
        self,
        batch_id: str,
        idempotency_key: str,
        phase: str,
        message: str,
    ) -> dict[str, Any]:
        """Persist a rejected request so the UI can explain and retry it."""
        existing = self._archive_request_row_locked(batch_id)
        if not existing:
            existing = self._insert_archive_request_locked(batch_id, idempotency_key)
        else:
            with self.db:
                self.db.execute(
                    "UPDATE batch_archive_requests SET idempotency_key=? WHERE request_id=?",
                    (idempotency_key, str(existing["request_id"])),
                )
        self._mark_archive_request_locked(
            str(existing["request_id"]),
            "failed",
            phase,
            message,
            int(existing["attempt"] or 0),
        )
        return self._archive_request_snapshot_locked(self._archive_request_row_locked(batch_id))

    def _mark_archive_request_locked(
        self,
        request_id: str,
        status: str,
        phase: str,
        last_error: str = "",
        attempt: int | None = None,
    ) -> None:
        if status not in {"requested", "cancelling", "waiting", "archived", "failed"}:
            raise ValueError("删除请求状态无效")
        updated_at = now_iso()
        values: list[Any] = [status, phase, updated_at, str(last_error or "")]
        assignments = ["status=?", "phase=?", "updated_at=?", "last_error=?"]
        if status == "requested":
            # A retry starts a fresh timeout window instead of inheriting the
            # failed request's original age.
            assignments.append("requested_at=?")
            values.append(updated_at)
        if attempt is not None:
            assignments.append("attempt=?")
            values.append(int(attempt))
        values.append(request_id)
        self.db.execute(
            f"UPDATE batch_archive_requests SET {', '.join(assignments)} WHERE request_id=?",
            tuple(values),
        )

    def _cancel_dispatches_for_archive_locked(self, batch_id: str) -> None:
        """Cancel only dispatches whose remote side has not accepted delivery."""
        self.db.execute(
            """UPDATE thread_dispatches SET status='cancelled',updated_at=?
               WHERE batch_id=? AND status='prepared'""",
            (now_iso(), batch_id),
        )

    def _reconcile_archive_requests_locked(self) -> None:
        rows = self.db.execute(
            """SELECT * FROM batch_archive_requests
               WHERE status IN ('requested','cancelling','waiting')
               ORDER BY requested_at""",
        ).fetchall()
        for request in rows:
            batch_id = str(request["batch_id"])
            batch = self.batches.get(batch_id)
            if not batch:
                self._mark_archive_request_locked(str(request["request_id"]), "failed", "missing_batch", "批次不存在")
                continue
            if self._batch_is_archived_locked(batch_id):
                self._mark_archive_request_locked(str(request["request_id"]), "archived", "archived")
                continue
            request_id = str(request["request_id"])
            self._cancel_dispatches_for_archive_locked(batch_id)
            blocked = self._archive_blocked_reason_locked(batch)
            if not blocked:
                try:
                    self.archive_batches([batch_id], archive_request_id=request_id)
                except Exception as exc:  # noqa: BLE001
                    self._mark_archive_request_locked(request_id, "failed", "finalize_failed", str(exc))
                else:
                    self._mark_archive_request_locked(request_id, "archived", "archived")
                continue
            try:
                requested_at = datetime.fromisoformat(str(request["requested_at"]).replace("Z", "+00:00"))
            except ValueError:
                requested_at = datetime.now(timezone.utc)
            age = (datetime.now(timezone.utc) - requested_at).total_seconds()
            if age >= ARCHIVE_REQUEST_TIMEOUT_SECONDS:
                self._mark_archive_request_locked(
                    request_id,
                    "failed",
                    "needs_attention",
                    f"删除收尾超时，仍需人工确认：{blocked}",
                    attempt=int(request["attempt"] or 0) + 1,
                )
            else:
                phase = "cancelling" if batch.get("overallStatus") == "stopping" else "waiting"
                self._mark_archive_request_locked(request_id, phase, phase, blocked)

    def reconcile_archive_requests(self) -> None:
        if not ENABLE_CATEGORY_REPOSITORY:
            return
        with self.lock:
            self._reconcile_archive_requests_locked()
            self.db.commit()

    def list_archive_requests(self) -> list[dict[str, Any]]:
        with self.lock:
            self._reconcile_archive_requests_locked()
            return [
                self._archive_request_snapshot_locked(row)
                for row in self.db.execute(
                    "SELECT * FROM batch_archive_requests ORDER BY requested_at DESC"
                ).fetchall()
            ]

    def request_archive_batches(self, batch_ids: list[str], idempotency_key: str = "") -> dict[str, Any]:
        """Request graceful cancellation followed by recoverable archive.

        Final archive remains fail-closed in ``archive_batches``. Active batches
        receive a durable request and are only removed after all leases, commands,
        sessions and external dispatches have reached a known terminal state.
        """
        if not ENABLE_CATEGORY_REPOSITORY:
            raise ValueError("类目仓库功能未启用")
        if not isinstance(batch_ids, list) or not batch_ids:
            raise ValueError("batchIds 必须是非空数组")
        normalized: list[str] = []
        seen: set[str] = set()
        for value in batch_ids:
            batch_id = str(value or "").strip()
            if not re.fullmatch(r"[a-f0-9]{12}", batch_id):
                raise ValueError("batchIds 包含无效批次 ID")
            if batch_id not in seen:
                seen.add(batch_id)
                normalized.append(batch_id)
        if len(normalized) > 500:
            raise ValueError("单次最多删除 500 个批次")
        key = str(idempotency_key or "").strip()[:160]
        requests: list[dict[str, Any]] = []
        archived: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        with self.lock:
            # Validate the whole selection before issuing any cancellation or
            # writing request rows; a stale mixed selection must be side-effect free.
            missing = [batch_id for batch_id in normalized if batch_id not in self.batches]
            if missing:
                raise KeyError(missing[0])
            for batch_id in normalized:
                batch = self.batches.get(batch_id)
                if self._batch_is_archived_locked(batch_id):
                    archived.append(self.snapshot(batch))
                    continue
                existing = self._archive_request_row_locked(batch_id)
                if existing and existing["status"] in ARCHIVE_REQUEST_ACTIVE_STATUSES:
                    requests.append(self._archive_request_snapshot_locked(existing))
                    continue
                if existing and existing["status"] == "failed" and key and key == str(existing["idempotency_key"] or ""):
                    requests.append(self._archive_request_snapshot_locked(existing))
                    continue
                blocked_request = self._archive_requestable_reason_locked(batch)
                if blocked_request and "正在删除收尾" not in blocked_request:
                    failed.append(self._record_archive_request_failure_locked(batch_id, key, "blocked", blocked_request))
                    continue
                # Request cancellation before inserting the fence. The store lock
                # prevents another writer from starting between these two steps.
                try:
                    if batch.get("overallStatus") not in {"stopping", "cancelled", "completed", "failed"}:
                        self.cancel(batch_id)
                except Exception as exc:  # noqa: BLE001
                    failed.append(self._record_archive_request_failure_locked(batch_id, key, "cancel_failed", str(exc)))
                    continue
                if existing:
                    with self.db:
                        self._mark_archive_request_locked(
                            str(existing["request_id"]), "requested", "requested", "", int(existing["attempt"] or 0) + 1
                        )
                        self.db.execute(
                            "UPDATE batch_archive_requests SET idempotency_key=? WHERE request_id=?",
                            (key, str(existing["request_id"])),
                        )
                else:
                    with self.db:
                        existing = self._insert_archive_request_locked(batch_id, key)
                self._cancel_dispatches_for_archive_locked(batch_id)
                requests.append(self._archive_request_snapshot_locked(existing))
            self._reconcile_archive_requests_locked()
            self.db.commit()
            final_requests = []
            for batch_id in normalized:
                row = self._archive_request_row_locked(batch_id)
                if row:
                    final_requests.append(self._archive_request_snapshot_locked(row))
                batch = self.batches.get(batch_id)
                if batch and self._batch_is_archived_locked(batch_id):
                    archived.append(self.snapshot(batch))
            # De-duplicate batches that became archived during reconciliation.
            archived = list({row["id"]: row for row in archived}.values())
            pending_count = sum(1 for row in final_requests if row["status"] in ARCHIVE_REQUEST_ACTIVE_STATUSES)
            return {
                "schemaVersion": "batchArchiveRequest/v1",
                "requestedCount": len(normalized),
                "pendingCount": pending_count,
                "archivedCount": len(archived),
                "requests": final_requests,
                "failed": failed,
                "batches": [self.snapshot(self.batches[batch_id]) for batch_id in normalized if batch_id in self.batches],
            }

    def restore_batch(self, batch_id: str) -> dict[str, Any]:
        if not ENABLE_CATEGORY_REPOSITORY:
            raise ValueError("类目仓库功能未启用")
        with self.lock:
            batch = self.batches.get(batch_id)
            if not batch:
                raise KeyError(batch_id)
            existing = self.db.execute(
                "SELECT archived_at FROM batch_archive_state WHERE batch_id=?",
                (batch_id,),
            ).fetchone()
            if not existing or not existing["archived_at"]:
                return self.snapshot(batch)
            restored_at = now_iso()
            with self.db:
                self.db.execute(
                    """UPDATE batch_archive_state
                       SET archived_at=NULL,restored_at=?,updated_at=?,feature_version=?
                       WHERE batch_id=?""",
                    (restored_at, restored_at, CATEGORY_REPOSITORY_VERSION, batch_id),
                )
                self._audit_feature_locked(
                    "batch_restored", "batch", batch_id, "active", {"restoredAt": restored_at},
                )
            return self.snapshot(batch)

    def get(self, batch_id: str) -> dict[str, Any]:
        with self.lock:
            batch = self.batches.get(batch_id)
            if not batch:
                raise KeyError(batch_id)
            self._reconcile_stale_stopping_locked(batch_id)
            return self.snapshot(batch)

    def _reconcile_stale_stopping_locked(self, batch_id: str, control_active: bool = False) -> None:
        batch = self.batches.get(batch_id)
        if not batch or self._batch_is_archived_locked(batch_id) or batch.get("overallStatus") != "stopping":
            return
        # A durable archive request owns the stop/drain lifecycle. The normal
        # stale-stop retry path must not create new commands behind its fence.
        archive_request = self._archive_request_row_locked(batch_id)
        if archive_request and archive_request["status"] != "archived":
            return
        session = self.db.execute(
            "SELECT status,last_heartbeat FROM bridge_sessions WHERE batch_id=?",
            (batch_id,),
        ).fetchone()
        heartbeat_at = None
        if session and session["last_heartbeat"]:
            try:
                heartbeat_at = datetime.fromisoformat(str(session["last_heartbeat"]).replace("Z", "+00:00"))
            except ValueError:
                heartbeat_at = None
        command_id = str(batch.get("cancelCommandId") or "")
        command = self.db.execute(
            "SELECT status FROM commands WHERE id=? AND batch_id=?",
            (command_id, batch_id),
        ).fetchone() if command_id else None
        requested_at = None
        if batch.get("cancelRequestedAt"):
            try:
                requested_at = datetime.fromisoformat(str(batch["cancelRequestedAt"]).replace("Z", "+00:00"))
            except ValueError:
                requested_at = None
        now = datetime.now(timezone.utc)
        heartbeat_fresh = bool(
            heartbeat_at
            and heartbeat_at >= now - timedelta(seconds=BRIDGE_HEARTBEAT_LEASE_SECONDS)
        )
        acknowledgement_timed_out = bool(
            requested_at
            and requested_at < now - timedelta(seconds=STOP_COMMAND_ACK_TIMEOUT_SECONDS)
            and (not command or command["status"] in {"pending", "delivered"})
        )
        if not acknowledgement_timed_out and heartbeat_fresh:
            return

        if acknowledgement_timed_out:
            retry_count = int(batch.get("cancelRetryCount") or 0)
            if (heartbeat_fresh or control_active) and retry_count < MAX_AUTOMATIC_STOP_RETRIES:
                with self.db:
                    if command_id:
                        self.db.execute(
                            "UPDATE commands SET status='failed',acknowledged_at=? WHERE id=? AND status IN ('pending','delivered')",
                            (now_iso(), command_id),
                        )
                replacement = self._enqueue_command_locked(batch_id, "stop_after_current", {})

                def apply_retry(current: dict[str, Any]) -> None:
                    if current.get("overallStatus") != "stopping" or str(current.get("cancelCommandId") or "") != command_id:
                        return
                    current["cancelCommandId"] = replacement["id"]
                    current["cancelRequestedAt"] = now_iso()
                    current["cancelRetryCount"] = retry_count + 1
                    current["stages"]["browser"].update({"status": "stopping", "message": "停止命令未确认，已自动重新发送"})

                self.update(batch_id, apply_retry)
                self.event(batch_id, "停止命令未确认，已使用新命令重新发送", "warning", {"previousCommandId": command_id[:8], "commandId": replacement["id"][:8], "retry": retry_count + 1})
                return
            message = "停止命令连续未确认；停止意图与 Bridge 租约保持锁定，请点击重试停止"
        else:
            message = "Browser Bridge 心跳已中断；停止意图与租约保持锁定，等待 Bridge 恢复"

        stage = batch.get("stages", {}).get("browser", {})
        connection = stage.get("connection") if isinstance(stage, dict) else None
        connection_status = "stopping" if heartbeat_fresh else "disconnected"
        if stage.get("message") == message and (not isinstance(connection, dict) or connection.get("status") == connection_status):
            return

        def mark_unconfirmed(current: dict[str, Any]) -> None:
            if current.get("overallStatus") != "stopping" or str(current.get("cancelCommandId") or "") != command_id:
                return
            current["stages"]["browser"].update({"status": "stopping", "message": message})
            current_connection = current["stages"]["browser"].get("connection")
            if isinstance(current_connection, dict):
                current_connection["status"] = connection_status

        self.update(batch_id, mark_unconfirmed)
        self.event(batch_id, message, "warning", {"commandId": command_id[:8]})

    def update(self, batch_id: str, callback, allow_archive_request: str = "") -> dict[str, Any]:
        with self.lock:
            self._assert_batch_not_archived_locked(batch_id, allow_archive_request=allow_archive_request)
            batch = self.batches[batch_id]
            before = {key: value.get("status") for key, value in batch.get("stages", {}).items()}
            callback(batch)
            batch["updatedAt"] = now_iso()
            self.persist()
            if batch.get("categoryPoolItemId") and verified_completed_workflow(batch):
                with self.db:
                    self.db.execute(
                        "UPDATE category_pool_items SET status='completed',updated_at=? WHERE id=? AND batch_id=?",
                        (batch["updatedAt"], batch["categoryPoolItemId"], batch_id),
                    )
            if verified_completed_workflow(batch):
                self._register_screened_category(batch, "completion_hook")
            for stage, stage_data in batch.get("stages", {}).items():
                status = stage_data.get("status")
                if status != before.get(stage):
                    self._record_stage_run(batch_id, stage, status, stage_data if isinstance(stage_data, dict) else {})
            return self.snapshot(batch)

    def _record_stage_run(self, batch_id: str, stage: str, status: str, stage_data: dict[str, Any]) -> None:
        previous = self.db.execute("SELECT COALESCE(MAX(attempt),0) AS attempt FROM stage_runs WHERE batch_id=? AND stage=?", (batch_id, stage)).fetchone()["attempt"]
        started = stage_data.get("startedAt") or now_iso()
        ended = stage_data.get("completedAt") if status in {"completed", "failed", "cancelled"} else None
        artifacts = stage_data.get("artifacts") or {}
        log_path = artifacts.get("stdout") or artifacts.get("log")
        with self.db:
            self.db.execute("INSERT INTO stage_runs(batch_id,stage,attempt,status,started_at,ended_at,exit_code,input_hash,log_path) VALUES(?,?,?,?,?,?,?,?,?)", (batch_id, stage, int(previous) + 1, status, started, ended, stage_data.get("exitCode"), stage_data.get("inputHash"), log_path))

    def list_events(self, batch_id: str, after: int = 0, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT id,at,level,message,details FROM events WHERE batch_id=? AND id>? ORDER BY id LIMIT ?", (batch_id, int(after), max(1, min(limit, 1000)))).fetchall()
        return [{"id": row["id"], "at": row["at"], "level": row["level"], "message": row["message"], "details": json.loads(row["details"]) if row["details"] else None} for row in rows]

    def add_intervention(self, batch_id: str, kind: str, message: str, payload: Any = None) -> dict[str, Any]:
        with self.lock:
            self._assert_batch_not_archived_locked(batch_id)
            record = {"batchId": batch_id, "kind": kind, "status": "open", "message": message, "payload": payload, "createdAt": now_iso()}
            with self.db:
                self.db.execute("INSERT INTO interventions(batch_id,kind,status,message,payload,created_at) VALUES(?,?,?,?,?,?)", (batch_id, kind, "open", message, json.dumps(payload, ensure_ascii=False) if payload is not None else None, record["createdAt"]))
            self.event(batch_id, message, "warning", {"intervention": kind, "payload": payload})
            return record

    def _legacy_event(self, batch_id: str, message: str, level: str = "info", details: Any = None) -> None:
        def apply(batch: dict[str, Any]) -> None:
            events = batch.setdefault("events", [])
            events.append({"at": now_iso(), "level": level, "message": message, "details": details})
            batch["events"] = events[-200:]
        self.update(batch_id, apply)

    def list_category_pool(self) -> list[dict[str, Any]]:
        with self.lock:
            if ENABLE_CATEGORY_REPOSITORY:
                rows = self.db.execute(
                    """SELECT item.id,item.input,item.label,item.node_id_path,item.status,item.batch_id,
                              item.created_at,item.updated_at
                       FROM category_pool_items AS item
                       WHERE NOT EXISTS (
                           SELECT 1 FROM batch_archive_state AS archive
                           WHERE archive.batch_id=item.batch_id AND archive.archived_at IS NOT NULL
                       )
                       ORDER BY CASE item.status WHEN 'available' THEN 0 WHEN 'assigned' THEN 1 ELSE 2 END,
                                item.created_at,item.id"""
                ).fetchall()
            else:
                rows = self.db.execute(
                    """SELECT id,input,label,node_id_path,status,batch_id,created_at,updated_at
                       FROM category_pool_items
                       ORDER BY CASE status WHEN 'available' THEN 0 WHEN 'assigned' THEN 1 ELSE 2 END, created_at, id"""
                ).fetchall()
            return [
                {
                    "id": row["id"],
                    "input": row["input"],
                    "label": row["label"],
                    "nodeIdPath": row["node_id_path"],
                    "status": row["status"],
                    "batchId": row["batch_id"] or "",
                    "batchName": (self.batches.get(row["batch_id"]) or {}).get("name", "") if row["batch_id"] else "",
                    "createdAt": row["created_at"],
                    "updatedAt": row["updated_at"],
                }
                for row in rows
            ]

    def category_pool_overview(self) -> dict[str, Any]:
        items = self.list_category_pool()
        counts = {"total": len(items), "available": 0, "assigned": 0, "completed": 0}
        for item in items:
            counts[item["status"]] += 1
        return {"items": items, "counts": counts}

    def category_repository_overview(self, search: str = "") -> dict[str, Any]:
        if not ENABLE_CATEGORY_REPOSITORY:
            return {
                "schemaVersion": "screenedCategoryRepository/v1",
                "enabled": False,
                "featureVersion": CATEGORY_REPOSITORY_VERSION,
                "marketplace": CATEGORY_MARKETPLACE,
                "scope": CATEGORY_SCREENING_SCOPE,
                "search": str(search or ""),
                "counts": {"categories": 0, "completions": 0, "matched": 0},
                "items": [],
            }
        normalized_search = normalize_category_name(search)
        with self.lock:
            categories = self.db.execute(
                """SELECT marketplace,node_id_path,display_name,normalized_name,scope,
                          first_completed_at,last_completed_at,created_at,updated_at,feature_version
                   FROM screened_categories ORDER BY last_completed_at DESC,node_id_path"""
            ).fetchall()
            completions = self.db.execute(
                """SELECT marketplace,node_id_path,batch_id,display_name,normalized_name,
                          completed_at,registration_source,created_at,feature_version
                   FROM screened_category_completions ORDER BY completed_at,batch_id"""
            ).fetchall()
            by_category: dict[tuple[str, str], list[sqlite3.Row]] = {}
            for completion in completions:
                by_category.setdefault((completion["marketplace"], completion["node_id_path"]), []).append(completion)
            items = []
            for category in categories:
                key = (category["marketplace"], category["node_id_path"])
                source_rows = by_category.get(key, [])
                normalized_names = {category["normalized_name"], *(row["normalized_name"] for row in source_rows)}
                if normalized_search and (
                    normalized_search not in normalize_category_name(category["node_id_path"])
                    and not any(normalized_search in name for name in normalized_names)
                ):
                    continue
                completion_items = []
                for row in source_rows:
                    archived = self.db.execute(
                        "SELECT archived_at FROM batch_archive_state WHERE batch_id=?",
                        (row["batch_id"],),
                    ).fetchone()
                    archived_at = str(archived["archived_at"] or "") if archived else ""
                    completion_items.append({
                        "batchId": row["batch_id"],
                        "batchName": (self.batches.get(row["batch_id"]) or {}).get("name", ""),
                        "displayName": row["display_name"],
                        "completedAt": row["completed_at"],
                        "registrationSource": row["registration_source"],
                        "archived": bool(archived_at),
                        "archivedAt": archived_at,
                    })
                items.append({
                    "key": f"{category['marketplace']}|{category['node_id_path']}",
                    "marketplace": category["marketplace"],
                    "nodeIdPath": category["node_id_path"],
                    "displayName": category["display_name"],
                    "nameAliases": sorted({row["display_name"] for row in source_rows if row["display_name"]}),
                    "scope": category["scope"],
                    "firstCompletedAt": category["first_completed_at"],
                    "lastCompletedAt": category["last_completed_at"],
                    "completionCount": len(completion_items),
                    "completions": completion_items,
                })
            return {
                "schemaVersion": "screenedCategoryRepository/v1",
                "enabled": ENABLE_CATEGORY_REPOSITORY,
                "featureVersion": CATEGORY_REPOSITORY_VERSION,
                "marketplace": CATEGORY_MARKETPLACE,
                "scope": CATEGORY_SCREENING_SCOPE,
                "search": str(search or ""),
                "counts": {"categories": len(categories), "completions": len(completions), "matched": len(items)},
                "items": items,
            }

    def _screened_node_match(self, node_id_path: str) -> dict[str, Any] | None:
        row = self.db.execute(
            """SELECT marketplace,node_id_path,display_name,first_completed_at,last_completed_at
               FROM screened_categories WHERE marketplace=? AND node_id_path=?""",
            (CATEGORY_MARKETPLACE, node_id_path),
        ).fetchone()
        if not row:
            return None
        completion_count = self.db.execute(
            """SELECT COUNT(*) AS count FROM screened_category_completions
               WHERE marketplace=? AND node_id_path=?""",
            (CATEGORY_MARKETPLACE, node_id_path),
        ).fetchone()["count"]
        return {
            "marketplace": row["marketplace"],
            "nodeIdPath": row["node_id_path"],
            "displayName": row["display_name"],
            "completionCount": completion_count,
            "lastCompletedAt": row["last_completed_at"],
        }

    def _screened_name_matches(self, normalized_name: str) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """SELECT DISTINCT c.marketplace,c.node_id_path,s.display_name,s.last_completed_at
               FROM screened_category_completions c
               JOIN screened_categories s
                 ON s.marketplace=c.marketplace AND s.node_id_path=c.node_id_path
               WHERE c.marketplace=? AND c.normalized_name=?
               ORDER BY c.node_id_path""",
            (CATEGORY_MARKETPLACE, normalized_name),
        ).fetchall()
        return [
            {
                "marketplace": row["marketplace"],
                "nodeIdPath": row["node_id_path"],
                "displayName": row["display_name"],
                "lastCompletedAt": row["last_completed_at"],
            }
            for row in rows
        ]

    def _legacy_import_category_pool(self, raw: str) -> dict[str, Any]:
        parsed = category_pool_rows(raw)
        if not parsed:
            raise ValueError("请至少输入一个有效类目")
        submitted_count = sum(1 for line in str(raw or "").splitlines() if line.strip() and not line.strip().startswith("#"))
        added = 0
        created = now_iso()
        with self.lock, self.db:
            for row in parsed:
                cursor = self.db.execute(
                    """INSERT OR IGNORE INTO category_pool_items(
                           id,input,normalized_key,label,node_id_path,status,batch_id,created_at,updated_at
                       ) VALUES(?,?,?,?,?,'available',NULL,?,?)""",
                    (
                        uuid.uuid4().hex[:12], row["input"], row["input"].casefold(), row["label"],
                        row["nodeIdPath"], created, created,
                    ),
                )
                added += cursor.rowcount
        return {
            **self.category_pool_overview(),
            "submittedCount": submitted_count,
            "addedCount": added,
            "duplicateCount": submitted_count - added,
        }

    def _legacy_preview_category_pool_import(self, raw: str) -> dict[str, Any]:
        parsed = category_pool_rows(raw, deduplicate=False)
        if not parsed:
            raise ValueError("请至少输入一个有效类目")
        items = []
        for row in parsed:
            items.append({
                **row,
                "key": category_import_item_key(row),
                "marketplace": CATEGORY_MARKETPLACE,
                "normalizedName": normalize_category_name(row.get("label")),
                "status": "ready",
                "tone": "green",
                "selectedByDefault": True,
                "matchMethod": "legacy_unchecked",
                "duplicateOf": "",
                "parseError": "",
                "error": "",
                "inPool": False,
                "poolItemIds": [],
                "matches": [],
            })
        return {
            "schemaVersion": "categoryPoolImportPreview/legacy-v1",
            "enabled": False,
            "featureVersion": CATEGORY_REPOSITORY_VERSION,
            "marketplace": CATEGORY_MARKETPLACE,
            "scope": "legacy_unchecked",
            "counts": {
                "submitted": len(items),
                "ready": len(items),
                "screened": 0,
                "ambiguous": 0,
                "duplicate": 0,
                "in_pool": 0,
                "invalid": 0,
            },
            "selectedKeys": [item["key"] for item in items],
            "overrideScreenedKeys": [],
            "items": items,
        }

    def preview_category_pool_import(self, raw: str) -> dict[str, Any]:
        if not ENABLE_CATEGORY_REPOSITORY:
            return self._legacy_preview_category_pool_import(raw)
        parsed = category_pool_preview_rows(raw)
        if not parsed:
            raise ValueError("请至少输入一个有效类目")
        with self.lock:
            active_pool = self.db.execute(
                """SELECT id,input,label,node_id_path,status,batch_id
                   FROM category_pool_items WHERE status IN ('available','assigned')"""
            ).fetchall()
            pool_nodes: dict[str, list[sqlite3.Row]] = {}
            pool_names: dict[str, list[sqlite3.Row]] = {}
            for pool_row in active_pool:
                node_id_path = str(pool_row["node_id_path"] or "")
                if node_id_path:
                    pool_nodes.setdefault(node_id_path, []).append(pool_row)
                pool_names.setdefault(normalize_category_name(pool_row["label"]), []).append(pool_row)

            seen: dict[str, str] = {}
            items = []
            for row in parsed:
                item_key = category_import_item_key(row)
                node_id_path = str(row.get("nodeIdPath") or "").strip()
                normalized_name = normalize_category_name(row.get("label"))
                matched_categories: list[dict[str, Any]] = []
                match_method = ""
                duplicate_of = ""
                parse_error = str(row.get("parseError") or "")
                identity = f"node:{node_id_path}" if node_id_path else f"name:{normalized_name}"
                pool_matches = pool_nodes.get(node_id_path, []) if node_id_path else pool_names.get(normalized_name, [])
                if parse_error or (not node_id_path and not normalized_name):
                    status = "invalid"
                    tone = "gray"
                    match_method = "invalid"
                    parse_error = parse_error or f"第 {row['line']} 行类目名和 nodeIdPath 不能同时为空"
                else:
                    duplicate_of = seen.get(identity, "")
                if duplicate_of:
                    status = "duplicate"
                    tone = "yellow"
                    match_method = "same_import"
                elif parse_error:
                    pass
                elif pool_matches:
                    status = "in_pool"
                    tone = "yellow"
                    match_method = "active_pool_node_exact" if node_id_path else "active_pool_name_exact"
                elif node_id_path:
                    screened = self._screened_node_match(node_id_path)
                    if screened:
                        status = "screened"
                        tone = "red"
                        match_method = "node_exact"
                        matched_categories = [screened]
                    else:
                        status = "ready"
                        tone = "green"
                        match_method = "node_unseen"
                else:
                    matched_categories = self._screened_name_matches(normalized_name)
                    if len(matched_categories) > 1:
                        status = "ambiguous"
                        tone = "yellow"
                        match_method = "name_ambiguous"
                    elif len(matched_categories) == 1:
                        status = "screened"
                        tone = "red"
                        match_method = "name_unique"
                    else:
                        status = "ready"
                        tone = "green"
                        match_method = "name_unseen"
                if not parse_error:
                    seen.setdefault(identity, item_key)
                items.append({
                    **row,
                    "key": item_key,
                    "marketplace": CATEGORY_MARKETPLACE,
                    "normalizedName": normalized_name,
                    "status": status,
                    "tone": tone,
                    "selectedByDefault": tone == "green",
                    "matchMethod": match_method,
                    "duplicateOf": duplicate_of,
                    "error": parse_error,
                    "inPool": bool(pool_matches),
                    "poolItemIds": [pool_row["id"] for pool_row in pool_matches],
                    "matches": matched_categories,
                })
            status_counts = {
                status: sum(1 for item in items if item["status"] == status)
                for status in ("ready", "screened", "ambiguous", "duplicate", "in_pool", "invalid")
            }
            preview = {
                "schemaVersion": "categoryPoolImportPreview/v1",
                "enabled": True,
                "featureVersion": CATEGORY_REPOSITORY_VERSION,
                "marketplace": CATEGORY_MARKETPLACE,
                "scope": CATEGORY_SCREENING_SCOPE,
                "counts": {"submitted": len(items), **status_counts},
                "selectedKeys": [item["key"] for item in items if item["selectedByDefault"]],
                "overrideScreenedKeys": [],
                "items": items,
            }
            return preview

    def _legacy_import_category_pool_selection(
        self,
        raw: str,
        selected_keys: Any,
        override_screened_keys: Any,
    ) -> dict[str, Any]:
        preview = self._legacy_preview_category_pool_import(raw)
        by_key = {item["key"]: item for item in preview["items"]}
        if selected_keys is None:
            selected = set(preview["selectedKeys"])
        else:
            if not isinstance(selected_keys, list) or any(not isinstance(key, str) for key in selected_keys):
                raise ValueError("selectedKeys 必须是字符串数组")
            selected = set(selected_keys)
            unknown = selected - set(by_key)
            if unknown:
                raise ValueError(f"selectedKeys 包含未知条目: {', '.join(sorted(unknown))}")
        if override_screened_keys not in (None, []):
            raise ValueError("旧版导入模式不接受 overrideScreenedKeys")

        selected_rows = [item for item in preview["items"] if item["key"] in selected]
        if selected_rows:
            legacy = self._legacy_import_category_pool("\n".join(item["input"] for item in selected_rows))
        else:
            legacy = {**self.category_pool_overview(), "addedCount": 0, "duplicateCount": 0}
        added = int(legacy.get("addedCount") or 0)
        return {
            **legacy,
            "schemaVersion": "categoryPoolImport/legacy-v2",
            "submittedCount": len(preview["items"]),
            "selectedCount": len(selected_rows),
            "addedCount": added,
            "skippedCount": len(preview["items"]) - added,
            "duplicateCount": max(0, len(selected_rows) - added),
            "outcomes": [
                {
                    "key": item["key"],
                    "line": item["line"],
                    "previewStatus": item["status"],
                    "outcome": "selected" if item["key"] in selected else "skipped",
                    "reason": "legacy_selected" if item["key"] in selected else "not_selected",
                }
                for item in preview["items"]
            ],
            "preview": preview,
        }

    def import_category_pool(
        self,
        raw: str,
        selected_keys: Any = None,
        override_screened_keys: Any = None,
    ) -> dict[str, Any]:
        if not ENABLE_CATEGORY_REPOSITORY:
            return self._legacy_import_category_pool_selection(raw, selected_keys, override_screened_keys)
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                result = self._import_category_pool_transaction_locked(
                    raw,
                    selected_keys,
                    override_screened_keys,
                )
                self.db.commit()
            except Exception as exc:
                self.db.rollback()
                with self.db:
                    self._audit_feature_locked(
                        "category_pool_import_failed",
                        "import",
                        hashlib.sha256(str(raw or "").encode("utf-8")).hexdigest(),
                        "rejected",
                        {
                            "selectedKeys": selected_keys if isinstance(selected_keys, list) else None,
                            "overrideScreenedKeys": override_screened_keys if isinstance(override_screened_keys, list) else None,
                            "errorType": type(exc).__name__,
                            "error": str(exc),
                        },
                    )
                raise
            return result

    def _import_category_pool_transaction_locked(
        self,
        raw: str,
        selected_keys: Any,
        override_screened_keys: Any,
    ) -> dict[str, Any]:
        preview = self.preview_category_pool_import(raw)
        by_key = {item["key"]: item for item in preview["items"]}
        known_keys = set(by_key)
        if selected_keys is None:
            selected = set(preview["selectedKeys"])
        else:
            if not isinstance(selected_keys, list) or any(not isinstance(key, str) for key in selected_keys):
                raise ValueError("selectedKeys 必须是字符串数组")
            selected = set(selected_keys)
            unknown = selected - known_keys
            if unknown:
                raise ValueError(f"selectedKeys 包含未知条目: {', '.join(sorted(unknown))}")
        if override_screened_keys is None:
            overrides: set[str] = set()
        else:
            if not isinstance(override_screened_keys, list) or any(not isinstance(key, str) for key in override_screened_keys):
                raise ValueError("overrideScreenedKeys 必须是字符串数组")
            overrides = set(override_screened_keys)
            unknown = overrides - known_keys
            if unknown:
                raise ValueError(f"overrideScreenedKeys 包含未知条目: {', '.join(sorted(unknown))}")
        unused_overrides = overrides - selected
        if unused_overrides:
            raise ValueError("overrideScreenedKeys 只能授权同时出现在 selectedKeys 中的条目")
        invalid_overrides = [key for key in overrides if by_key[key]["status"] != "screened"]
        if invalid_overrides:
            raise ValueError("overrideScreenedKeys 只能授权红色 screened 条目")
        blocked = [by_key[key] for key in selected if by_key[key]["status"] in {"ambiguous", "duplicate", "in_pool", "invalid"}]
        if blocked:
            summary = ", ".join(f"第 {item['line']} 行 {item['status']}" for item in blocked)
            raise ValueError(f"所选条目不可导入: {summary}")
        missing_overrides = [by_key[key] for key in selected if by_key[key]["status"] == "screened" and key not in overrides]
        if missing_overrides:
            summary = ", ".join(f"第 {item['line']} 行" for item in missing_overrides)
            raise ValueError(f"重新导入 screened 条目需要 overrideScreenedKeys 独立授权: {summary}")
        selected_rows = [item for item in preview["items"] if item["key"] in selected]
        created = now_iso()
        imported: dict[str, str] = {}
        audited_items: list[dict[str, Any]] = []
        with self.lock:
            for row in selected_rows:
                normalized_key = row["input"].casefold()
                released_pool_item_id = ""
                conflict = self.db.execute(
                    "SELECT id,status FROM category_pool_items WHERE normalized_key=?",
                    (normalized_key,),
                ).fetchone()
                if conflict:
                    if row["status"] != "screened" or row["key"] not in overrides:
                        raise ValueError(f"第 {row['line']} 行与现有类目池条目冲突")
                    if conflict["status"] != "completed":
                        raise ValueError(f"第 {row['line']} 行对应类目池条目仍为活跃状态，不可释放")
                    released_key = (
                        f"completed:{conflict['id']}:"
                        f"{hashlib.sha256(normalized_key.encode('utf-8')).hexdigest()[:16]}"
                    )
                    released = self.db.execute(
                        """UPDATE category_pool_items SET normalized_key=?
                           WHERE id=? AND status='completed' AND normalized_key=?""",
                        (released_key, conflict["id"], normalized_key),
                    )
                    if released.rowcount != 1:
                        raise ValueError(f"第 {row['line']} 行历史类目池键释放失败")
                    released_pool_item_id = str(conflict["id"])
                pool_item_id = uuid.uuid4().hex[:12]
                self.db.execute(
                    """INSERT INTO category_pool_items(
                           id,input,normalized_key,label,node_id_path,status,batch_id,created_at,updated_at
                       ) VALUES(?,?,?,?,?,'available',NULL,?,?)""",
                    (
                        pool_item_id,
                        row["input"],
                        normalized_key,
                        row["label"],
                        row["nodeIdPath"],
                        created,
                        created,
                    ),
                )
                imported[row["key"]] = pool_item_id
                audited_items.append({
                    "key": row["key"],
                    "line": row["line"],
                    "nodeIdPath": row["nodeIdPath"],
                    "previewStatus": row["status"],
                    "authorization": "screened_override" if row["status"] == "screened" else "ready_selected",
                    "releasedPoolItemId": released_pool_item_id,
                    "createdPoolItemId": pool_item_id,
                    "outcome": "imported",
                })
            self._audit_feature_locked(
                "category_pool_imported",
                "import",
                hashlib.sha256(str(raw or "").encode("utf-8")).hexdigest(),
                "imported",
                {
                    "selectedCount": len(selected_rows),
                    "overrideScreenedCount": len(overrides),
                    "addedCount": len(imported),
                    "statuses": preview["counts"],
                    "items": audited_items,
                },
            )
        outcomes = []
        for item in preview["items"]:
            pool_item_id = imported.get(item["key"], "")
            if pool_item_id:
                outcome = "imported"
                reason = "screened_override" if item["status"] == "screened" else "selected"
            else:
                outcome = "skipped"
                if item["status"] == "screened":
                    reason = "screened_override_required"
                elif item["status"] in {"ambiguous", "duplicate", "in_pool", "invalid"}:
                    reason = f"blocked_{item['status']}"
                else:
                    reason = "not_selected"
            outcomes.append({
                "key": item["key"],
                "line": item["line"],
                "input": item["input"],
                "previewStatus": item["status"],
                "outcome": outcome,
                "reason": reason,
                "poolItemId": pool_item_id,
            })
        added = len(imported)
        skipped = len(preview["items"]) - added
        overview = self.category_pool_overview()
        return {
            **overview,
            "schemaVersion": "categoryPoolImport/v3",
            "featureVersion": CATEGORY_REPOSITORY_VERSION,
            "submittedCount": len(preview["items"]),
            "selectedCount": len(selected_rows),
            "overrideScreenedCount": len(overrides),
            "addedCount": added,
            "skippedCount": skipped,
            "duplicateCount": preview["counts"]["duplicate"],
            "screenedCount": preview["counts"]["screened"],
            "ambiguousCount": preview["counts"]["ambiguous"],
            "inPoolCount": preview["counts"]["in_pool"],
            "invalidCount": preview["counts"]["invalid"],
            "outcomes": outcomes,
            "preview": preview,
        }

    def _available_category_pool_item(self, item_id: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT id,input,label,node_id_path,status FROM category_pool_items WHERE id=?",
            (item_id,),
        ).fetchone()
        if not row:
            raise ValueError("类目池条目不存在")
        if row["status"] != "available":
            raise ValueError("该类目已被其他批次领取")
        return {
            "id": row["id"],
            "input": row["input"],
            "label": row["label"],
            "nodeIdPath": row["node_id_path"],
        }

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        category_pool_item_id = str(payload.get("categoryPoolItemId") or "").strip()
        selected_pool_item = None
        if category_pool_item_id:
            with self.lock:
                selected_pool_item = self._available_category_pool_item(category_pool_item_id)
        name = str(payload.get("name") or (selected_pool_item or {}).get("label") or "").strip()
        if not name:
            raise ValueError("批次名称不能为空")
        categories_text = selected_pool_item["input"] if selected_pool_item else str(payload.get("categories") or "").strip()
        category_pool = category_pool_rows(categories_text)
        if len(category_pool) > 1:
            raise ValueError("每个批次只能运行一个类目；请先导入全局类目池再逐个创建")
        source_xlsx_value = str(payload.get("sourceXlsx") or "").strip()
        source_url_value = str(payload.get("sourceUrl") or "").strip()
        if category_pool:
            source_xlsx = valid_file(source_xlsx_value, (".xlsx",)) if source_xlsx_value else None
            source_url = validate_sellersprite_url(source_url_value) if source_url_value else ""
        else:
            source_xlsx = valid_file(source_xlsx_value, (".xlsx",))
            source_url = validate_sellersprite_url(source_url_value)
        filters = normalize_query_filters(payload.get("filters"))
        candidate_source_mode = str(payload.get("candidateSourceMode") or DEFAULT_CANDIDATE_SOURCE_MODE).strip()
        if candidate_source_mode not in {"browser_export", "official_api"}:
            raise ValueError("candidateSourceMode must be browser_export or official_api")
        queue_size = int(payload.get("queueSize") or 400)
        part_size = int(payload.get("partSize") or 64)
        target = int(payload.get("targetQualified") or 20)
        if not 1 <= queue_size <= 5000 or not 1 <= part_size <= 500 or not 1 <= target <= 5000:
            raise ValueError("队列、分片和目标数量必须是合理的正整数")
        batch_id = uuid.uuid4().hex[:12]
        created = now_iso()
        run_id = f"console_{slug(name)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{batch_id[:6]}"
        batch = {
            "id": batch_id,
            "name": name,
            "category": str(payload.get("category") or (category_pool[0]["input"] if len(category_pool) == 1 else f"{len(category_pool)} 个类目" if category_pool else "")).strip(),
            "operator": str(payload.get("operator") or "Codex").strip(),
            "categories": categories_text,
            "categoryPool": category_pool,
            "categoryPoolItemId": category_pool_item_id,
            "queryFilters": filters,
            "candidateSourceMode": candidate_source_mode,
            "browserExports": [],
            "sourceXlsx": str(source_xlsx) if source_xlsx else "",
            "sourceUrl": source_url,
            "sourcePage": str(payload.get("sourcePage") or name).strip(),
            "queueSize": queue_size,
            "partSize": part_size,
            "targetQualified": target,
            "runId": run_id,
            "runDate": datetime.now().date().isoformat(),
            "runDir": str(PROJECT_ROOT / "runs" / run_id),
            "candidateJsonPath": "",
            "mergedJsonPath": "",
            "titleOverridesPath": "",
            "imagesDir": "",
            "jsonHandoff": {"sourceSha256": "", "copiedAt": "", "pastedSha256": "", "pasteVerified": False},
            "mode": "direct_browser_import",
            "bridgeToken": secrets.token_urlsafe(32),
            "bridgeProtocol": "browser-bridge-v2",
            "createdAt": created,
            "updatedAt": created,
            "overallStatus": "created",
            "stages": {
                "candidates": {"status": "idle", "artifacts": {}, "message": "等待从类目池准备候选 ASIN"},
                "browser": {"status": "waiting", "artifacts": {}, "message": "等待 Chrome / Runner 采集", "stats": {}},
                "excel": {"status": "idle", "artifacts": {}, "message": "等待合并 JSON", "stats": {}},
            },
            "events": [{"at": created, "level": "info", "message": "批次已创建", "details": None}],
        }
        with self.lock:
            if selected_pool_item:
                selected_pool_item = self._available_category_pool_item(category_pool_item_id)
            self.batches[batch_id] = batch
            self.persist()
            if selected_pool_item:
                with self.db:
                    cursor = self.db.execute(
                        """UPDATE category_pool_items
                           SET status='assigned',batch_id=?,updated_at=?
                           WHERE id=? AND status='available'""",
                        (batch_id, created, category_pool_item_id),
                    )
                if cursor.rowcount != 1:
                    self.batches.pop(batch_id, None)
                    with self.db:
                        self.db.execute("DELETE FROM runs WHERE id=?", (batch_id,))
                    raise ValueError("该类目已被其他批次领取")
        return self.snapshot(batch)

    def list_all(self) -> list[dict[str, Any]]:
        with self.lock:
            self._reconcile_archive_requests_locked()
            for batch_id in list(self.batches):
                self._reconcile_stale_stopping_locked(batch_id)
            return [self.snapshot(item) for item in sorted(self.batches.values(), key=lambda x: x["updatedAt"], reverse=True)]

    def list(self) -> list[dict[str, Any]]:
        batches = self.list_all()
        if not ENABLE_CATEGORY_REPOSITORY:
            return batches
        return [batch for batch in batches if not batch.get("archived")]

    def list_archived(self) -> list[dict[str, Any]]:
        if not ENABLE_CATEGORY_REPOSITORY:
            return []
        return [batch for batch in self.list_all() if batch.get("archived")]

    def batch_counts(self) -> dict[str, int]:
        batches = self.list_all()
        if not ENABLE_CATEGORY_REPOSITORY:
            return {"active": len(batches), "archived": 0, "total": len(batches)}
        archived = sum(1 for batch in batches if batch.get("archived"))
        return {"active": len(batches) - archived, "archived": archived, "total": len(batches)}

    def _prepare_local_retry_locked(self, batch_id: str, stage: str) -> None:
        """Release a stale lease only after its PID is no longer alive."""
        rows = self.db.execute(
            """SELECT * FROM local_job_leases
               WHERE batch_id=? AND stage=? AND status IN ('starting','running','orphaned')
               ORDER BY started_at DESC""",
            (batch_id, stage),
        ).fetchall()
        for row in rows:
            pid = row["pid"]
            if local_pid_alive(pid):
                raise ValueError(
                    f"服务重启后仍检测到 {stage} 遗留进程（PID {int(pid)}），未安全接管；请先结束该进程后再重试"
                )
            self._update_local_job_locked(
                str(row["id"]),
                status="interrupted",
                ended_at=str(row["ended_at"] or now_iso()),
                recovery_reason="operator_confirmed_process_not_running",
            )

    def _local_job_is_current_locked(self, job_id: str) -> bool:
        row = self.db.execute(
            "SELECT owner_instance_id,status FROM local_job_leases WHERE id=?",
            (job_id,),
        ).fetchone()
        return bool(
            row
            and row["owner_instance_id"] == CONSOLE_INSTANCE_ID
            and row["status"] in {"starting", "running", "exited"}
        )

    def launch(self, batch_id: str, stage: str, argv: list[str], log_prefix: str, on_success, completion_status: str = "completed", completion_message: str | None = None) -> None:
        with self.lock:
            self._assert_batch_not_archived_locked(batch_id)
            if batch_id in self.jobs:
                raise ValueError("该批次已有任务正在运行")
            if stage not in {"candidates", "excel"}:
                raise ValueError("本地任务阶段必须是 candidates 或 excel")
            self._prepare_local_retry_locked(batch_id, stage)
            batch = self.batches[batch_id]
            if batch.get("overallStatus") in {"completed", "cancelled", "stopping"}:
                raise ValueError("批次已停止，不能启动新任务")
            run_dir = Path(batch["runDir"])
            run_dir.mkdir(parents=True, exist_ok=True)
            stdout_path = run_dir / f"console_{log_prefix}_stdout.log"
            stderr_path = run_dir / f"console_{log_prefix}_stderr.log"
            stdout_file = stdout_path.open("w", encoding="utf-8")
            stderr_file = stderr_path.open("w", encoding="utf-8")
            job_id = uuid.uuid4().hex
            started_at = now_iso()
            argv_sha256 = hashlib.sha256(json.dumps([str(value) for value in argv], ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
            executable = Path(str(argv[0])).name if argv else ""
            attempt = self._local_job_attempt_locked(batch_id, stage)
            self._insert_local_job_locked(
                job_id, batch_id, stage, attempt, argv_sha256, executable, str(run_dir),
                str(stdout_path), str(stderr_path), started_at,
            )
            try:
                process = subprocess.Popen(argv, cwd=str(PROJECT_ROOT), stdout=stdout_file, stderr=stderr_file, text=True, encoding="utf-8", errors="replace", creationflags=SUBPROCESS_CREATION_FLAGS)
                self._update_local_job_locked(job_id, status="running", pid=process.pid)
            except Exception:
                ended_at = now_iso()
                self._update_local_job_locked(job_id, status="failed", ended_at=ended_at, recovery_reason="process_start_failed")
                stdout_file.close()
                stderr_file.close()
                raise
            self.jobs[batch_id] = process
            self.update(batch_id, lambda b: set_stage(b, stage, "running", f"正在执行 {log_prefix}", {
                "stdout": str(stdout_path),
                "stderr": str(stderr_path),
                "localJobId": job_id,
                "localJobAttempt": attempt,
                "localJobPid": process.pid,
                "localJobArgvSha256": argv_sha256,
                "localJobRecoveryVersion": LOCAL_JOB_RECOVERY_VERSION,
            }))
            self.event(batch_id, f"已启动 {log_prefix}")

        def wait_for_process() -> None:
            try:
                return_code = process.wait()
                stdout_file.close()
                stderr_file.close()
                with self.lock:
                    cancelled = batch_id in self.cancel_flags
                    current = self._local_job_is_current_locked(job_id)
                    if current:
                        self._update_local_job_locked(
                            job_id,
                            status="cancelled" if cancelled else "failed" if return_code != 0 else "exited",
                            ended_at=now_iso(),
                            exit_code=return_code,
                        )
                if not current:
                    try:
                        self.event(batch_id, f"已忽略旧本地任务 {log_prefix} 的迟到回调", "warning", {"jobId": job_id[:8]})
                    except ValueError:
                        pass
                    return
                if cancelled:
                    try:
                        self.update(batch_id, lambda b: set_stage(b, stage, "cancelled", "已停止当前任务", {}))
                        self.event(batch_id, f"{log_prefix} 已停止", "warning")
                    except ValueError:
                        with self.lock:
                            if not self._active_archive_request_locked(batch_id):
                                raise
                    return
                if return_code != 0:
                    try:
                        updated = self.update(batch_id, lambda b: set_stage_if_mutable(b, stage, "failed", f"{log_prefix} 失败，退出码 {return_code}", {"exitCode": return_code, "stdout": str(stdout_path), "stderr": str(stderr_path)}))
                    except ValueError:
                        with self.lock:
                            if self._active_archive_request_locked(batch_id):
                                return
                            raise
                    if updated["stages"][stage].get("status") == "failed":
                        try:
                            self.event(batch_id, f"{log_prefix} 失败", "error", {"exitCode": return_code})
                        except ValueError:
                            pass
                    else:
                        try:
                            self.event(batch_id, f"已忽略终态批次的迟到 {log_prefix} 失败回调", "warning", {"exitCode": return_code})
                        except ValueError:
                            pass
                    return
                if self.get(batch_id).get("overallStatus") in {"completed", "cancelled", "stopping"}:
                    return
                try:
                    result = on_success(Path(batch["runDir"]))
                except Exception as exc:  # noqa: BLE001
                    with self.lock:
                        self._update_local_job_locked(job_id, status="failed", ended_at=now_iso(), exit_code=return_code, recovery_reason="success_callback_failed")
                    try:
                        updated = self.update(batch_id, lambda b: set_stage_if_mutable(b, stage, "failed", str(exc), {"exitCode": return_code}))
                    except ValueError:
                        with self.lock:
                            if self._active_archive_request_locked(batch_id):
                                return
                            raise
                    level = "error" if updated["stages"][stage].get("status") == "failed" else "warning"
                    try:
                        self.event(batch_id, f"{log_prefix} 产物解析失败" if level == "error" else f"已忽略终态批次的迟到 {log_prefix} 解析回调", level, str(exc))
                    except ValueError:
                        pass
                    return
                message = completion_message or f"{log_prefix} 已完成"
                try:
                    updated = self.update(batch_id, lambda b: set_stage_if_mutable(b, stage, completion_status, message, result or {}))
                except ValueError:
                    with self.lock:
                        if self._active_archive_request_locked(batch_id):
                            return
                        raise
                with self.lock:
                    self._update_local_job_locked(
                        job_id,
                        status="completed" if updated["stages"][stage].get("status") == completion_status else "exited",
                        ended_at=now_iso(),
                        exit_code=return_code,
                    )
                if updated["stages"][stage].get("status") == completion_status:
                    try:
                        self.event(batch_id, message, "success" if completion_status == "completed" else "info", result or {})
                    except ValueError:
                        pass
                else:
                    try:
                        self.event(batch_id, f"已忽略终态批次的迟到 {log_prefix} 完成回调", "warning", result or {})
                    except ValueError:
                        pass
            finally:
                if not stdout_file.closed:
                    stdout_file.close()
                if not stderr_file.closed:
                    stderr_file.close()
                with self.lock:
                    row = self.db.execute("SELECT status FROM local_job_leases WHERE id=?", (job_id,)).fetchone()
                    if row and row["status"] in LOCAL_JOB_ACTIVE_STATUSES:
                        self._update_local_job_locked(job_id, status="interrupted", ended_at=now_iso(), recovery_reason="waiter_finished_without_terminal_update")
                    if self.jobs.get(batch_id) is process:
                        self.jobs.pop(batch_id, None)
                    self.cancel_flags.discard(batch_id)
                    if self._active_archive_request_locked(batch_id):
                        self._reconcile_archive_requests_locked()
                        self.db.commit()

        threading.Thread(target=wait_for_process, name=f"console-{stage}-{batch_id}", daemon=True).start()

    def cancel(self, batch_id: str) -> dict[str, Any]:
        with self.lock:
            if batch_id not in self.batches:
                raise KeyError(batch_id)
            self._assert_batch_not_archived_locked(batch_id)
            batch = self.snapshot(self.batches[batch_id])
            if terminal_batch_status(batch) == "completed":
                updated = self.update(batch_id, lambda current: current.update({"overallStatus": "completed"}))
                if batch.get("overallStatus") != "completed":
                    self.event(batch_id, "批次已完成，无需停止", "info")
                return updated
            if batch.get("overallStatus") == "cancelled":
                return batch
            if batch.get("overallStatus") == "stopping":
                previous_command_id = str(batch.get("cancelCommandId") or "")
                with self.db:
                    if previous_command_id:
                        self.db.execute(
                            "UPDATE commands SET status='failed',acknowledged_at=? WHERE id=? AND status IN ('pending','delivered','accepted')",
                            (now_iso(), previous_command_id),
                        )
                replacement = self._enqueue_command_locked(batch_id, "stop_after_current", {})
                retry_count = int(batch.get("cancelRetryCount") or 0) + 1

                def apply_manual_retry(current: dict[str, Any]) -> None:
                    if current.get("overallStatus") != "stopping":
                        return
                    current["cancelCommandId"] = replacement["id"]
                    current["cancelRequestedAt"] = now_iso()
                    current["cancelRetryCount"] = retry_count
                    current["stages"]["browser"].update({"status": "stopping", "message": "已重新发送停止命令，等待 Runner 完成当前 ASIN"})

                self.update(batch_id, apply_manual_retry)
                self.event(batch_id, "已手动重新发送 Runner 停止命令", "warning", {"previousCommandId": previous_command_id[:8], "commandId": replacement["id"][:8], "retry": retry_count})
                return self.get(batch_id)

            session = self.db.execute(
                "SELECT status FROM bridge_sessions WHERE batch_id=?",
                (batch_id,),
            ).fetchone()
            durable_jobs = self.db.execute(
                """SELECT * FROM local_job_leases
                   WHERE batch_id=? AND status IN ('starting','running','orphaned')
                   ORDER BY started_at DESC""",
                (batch_id,),
            ).fetchall()
            unmanaged_alive = [
                row for row in durable_jobs
                if batch_id not in self.jobs and local_pid_alive(row["pid"])
            ]
            if unmanaged_alive:
                for row in unmanaged_alive:
                    self._update_local_job_locked(
                        str(row["id"]),
                        status="orphaned",
                        recovery_reason="stop_blocked_unverified_process",
                    )
                    stage = str(row["stage"] or "")
                    recovery = {
                        "jobId": str(row["id"]),
                        "status": "orphaned",
                        "reason": "stop_blocked_unverified_process",
                        "processAlive": True,
                        "lastKnownPid": int(row["pid"]),
                        "attempt": int(row["attempt"]),
                        "argvSha256": str(row["argv_sha256"] or ""),
                        "runDir": str(row["run_dir"] or ""),
                        "stdout": str(row["stdout_path"] or ""),
                        "stderr": str(row["stderr_path"] or ""),
                        "recoveredAt": now_iso(),
                    }
                    self._mark_stage_recovery_locked(self.batches[batch_id], stage, recovery)
                self.persist()
                self.db.commit()
                self.event(batch_id, "检测到无法安全确认归属的遗留本地进程，停止操作已暂停", "warning", {
                    "pids": [int(row["pid"]) for row in unmanaged_alive],
                })
                return self.get(batch_id)
            for row in durable_jobs:
                if not local_pid_alive(row["pid"]):
                    self._update_local_job_locked(
                        str(row["id"]),
                        status="interrupted",
                        ended_at=str(row["ended_at"] or now_iso()),
                        recovery_reason="process_not_running_before_stop",
                    )
            should_signal_runner = bool(
                session
                and session["status"] == "connected"
                and str(batch.get("stages", {}).get("browser", {}).get("stats", {}).get("status") or "") != "done"
            )
            with self.db:
                self.db.execute(
                    """UPDATE commands SET status='cancelled',acknowledged_at=?
                       WHERE batch_id=? AND action NOT LIKE 'seller_export%'
                         AND action<>'stop_after_current' AND status IN ('pending','delivered','accepted')""",
                    (now_iso(), batch_id),
                )
            command = self.enqueue_command(batch_id, "stop_after_current", {}) if should_signal_runner else None
            process = self.jobs.get(batch_id)
            if process and process.poll() is None:
                self.cancel_flags.add(batch_id)
                process.terminate()

            def apply_cancel(current: dict[str, Any]) -> None:
                current["overallStatus"] = "stopping" if command else "cancelled"
                current["cancelRequestedAt"] = now_iso()
                if command:
                    current["cancelCommandId"] = command["id"]
                    current["cancelRetryCount"] = 0
                else:
                    current.pop("cancelCommandId", None)
                    current.pop("cancelRetryCount", None)
                stages = current.get("stages", {})
                if stages.get("browser", {}).get("status") in {"waiting", "running", "paused", "needs_attention"} and current.get("runnerBatchName"):
                    stages["browser"]["status"] = "stopping" if command else "cancelled"
                    stages["browser"]["message"] = "已请求 Runner 在当前 ASIN 完成后停止" if command else "浏览器任务已停止"
                    connection = stages["browser"].get("connection")
                    if isinstance(connection, dict):
                        connection["status"] = "stopping" if command else "cancelled"
                elif stages.get("candidates", {}).get("status") not in TERMINAL_STATUSES:
                    stages["candidates"]["status"] = "cancelled"
                    stages["candidates"]["message"] = "候选准备已停止"
                elif stages.get("excel", {}).get("status") not in TERMINAL_STATUSES:
                    stages["excel"]["status"] = "cancelled"
                    stages["excel"]["message"] = "Excel 任务已停止"

            self.update(batch_id, apply_cancel)
            with self.db:
                self.db.execute("UPDATE bridge_sessions SET status=? WHERE batch_id=?", ("stopping" if command else "cancelled", batch_id))
                self.db.execute(
                    "UPDATE commands SET status='cancelled',acknowledged_at=? WHERE batch_id=? AND action='seller_export' AND status IN ('pending','delivered','accepted')",
                    (now_iso(), batch_id),
                )
                if not command:
                    self.db.execute(
                        "UPDATE commands SET status='cancelled',acknowledged_at=? WHERE batch_id=? AND action='stop_after_current' AND status IN ('pending','delivered','accepted')",
                        (now_iso(), batch_id),
                    )
            self.event(batch_id, "已请求 Runner 当前行完成后停止" if command else "批次已停止", "warning")
            return self.get(batch_id)


def set_stage(batch: dict[str, Any], stage: str, status: str, message: str, artifacts: dict[str, Any]) -> None:
    stage_data = batch["stages"][stage]
    existing_artifacts = stage_data.get("artifacts", {})
    if status == "running":
        existing_artifacts = {
            key: value
            for key, value in existing_artifacts.items()
            if key not in {"exitCode", "stdout", "stderr"}
        }
    stage_data["status"] = status
    stage_data["message"] = message
    stage_data["artifacts"] = {**existing_artifacts, **artifacts}
    if status == "running":
        stage_data["startedAt"] = now_iso()
        stage_data.pop("completedAt", None)
    if status in TERMINAL_STATUSES or status == "completed":
        stage_data["completedAt"] = now_iso()
    statuses = [value["status"] for value in batch["stages"].values()]
    if status == "failed":
        batch["overallStatus"] = "failed"
    elif all(value == "completed" for value in statuses):
        batch["overallStatus"] = "completed"
    elif "running" in statuses:
        batch["overallStatus"] = "running"
    elif "needs_attention" in statuses or "paused" in statuses:
        batch["overallStatus"] = "needs_attention"
    elif stage == "candidates" and status == "completed":
        batch["overallStatus"] = "browser_waiting"
    elif stage == "browser" and status == "completed":
        batch["overallStatus"] = "excel_ready"


def terminal_batch_status(batch: dict[str, Any]) -> str:
    stages = batch.get("stages", {})
    if stages and all(stage.get("status") == "completed" for stage in stages.values()):
        return "completed"
    status = str(batch.get("overallStatus") or "")
    return status if status in {"completed", "failed", "cancelled"} else ""


def verified_completed_workflow(batch: dict[str, Any]) -> bool:
    stages = batch.get("stages")
    if not isinstance(stages, dict) or str(batch.get("overallStatus") or "") != "completed":
        return False
    return all(
        isinstance(stages.get(stage), dict) and stages[stage].get("status") == "completed"
        for stage in ("candidates", "browser", "excel")
    )


PREFLIGHT_EXECUTION_LOCK = threading.Lock()


def set_stage_if_mutable(batch: dict[str, Any], stage: str, status: str, message: str, artifacts: dict[str, Any]) -> None:
    if batch.get("overallStatus") in {"completed", "cancelled", "stopping"}:
        return
    set_stage(batch, stage, status, message, artifacts)


def protected_script_integrity() -> dict[str, Any]:
    paths = {
        "bridge": CONSOLE_ROOT / "browser_bridge_v2.user.js",
        "collector": ACTIVE_COLLECTOR_SCRIPT,
        "runner": ACTIVE_RUNNER_SCRIPT,
    }
    actual: dict[str, str | None] = {}
    errors: list[str] = []
    for name, path in paths.items():
        try:
            actual[name] = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        except OSError as exc:
            actual[name] = None
            errors.append(f"{name}: {exc}")
    matches = {
        name: actual.get(name) == expected
        for name, expected in PROTECTED_SCRIPT_HASHES.items()
    }
    return {
        "ok": not errors and all(matches.values()),
        "expected": PROTECTED_SCRIPT_HASHES,
        "actual": actual,
        "matches": matches,
        "paths": {name: str(path) for name, path in paths.items()},
        "errors": errors,
    }


def preflight() -> dict[str, Any]:
    with PREFLIGHT_EXECUTION_LOCK:
        if not PREFLIGHT_SCRIPT.exists():
            return {"ok": False, "message": f"找不到预检脚本: {PREFLIGHT_SCRIPT}"}
        result = subprocess.run([str(PYTHON_EXE), str(PREFLIGHT_SCRIPT), "--project-root", str(PROJECT_ROOT)], cwd=str(PROJECT_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, creationflags=SUBPROCESS_CREATION_FLAGS)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            payload = {"ok": False, "message": (result.stderr or result.stdout).strip()}
        payload["exitCode"] = result.returncode
        payload["sellerSpriteApi"] = {
            "configured": SELLERSPRITE_CREDENTIAL.is_file(),
            "credentialProtection": "windows_dpapi" if SELLERSPRITE_CREDENTIAL.is_file() else "missing",
            "apiBase": "https://api.sellersprite.com",
            "required": False,
            "activeCandidateSource": DEFAULT_CANDIDATE_SOURCE_MODE,
        }
        script_integrity = protected_script_integrity()
        pair_checks = {
            "collectorFile": ACTIVE_COLLECTOR_SCRIPT.is_file(),
            "runnerFile": ACTIVE_RUNNER_SCRIPT.is_file(),
            "protectedScriptHashes": script_integrity["ok"],
            "collectorVersion": False,
            "runnerVersion": False,
            "collectorFailClosedFlags": False,
            "runnerFailClosedFlags": False,
            "runnerDeferredJsonContract": False,
        }
        if pair_checks["collectorFile"]:
            collector_source = ACTIVE_COLLECTOR_SCRIPT.read_text(encoding="utf-8")
            pair_checks["collectorVersion"] = f'var VERSION = "{APPROVED_COLLECTOR_VERSION}"' in collector_source
            pair_checks["collectorFailClosedFlags"] = all(marker in collector_source for marker in (
                "ENABLE_TIER2_1_ZERO_SHARE_DERIVATION = true",
                "ENABLE_AGGREGATE_NATURAL_TRAFFIC_GATE = true",
                "ENABLE_CONFIRMED_NO_DATA_FAST_FAIL = true",
            ))
        if pair_checks["runnerFile"]:
            runner_source = ACTIVE_RUNNER_SCRIPT.read_text(encoding="utf-8")
            pair_checks["runnerVersion"] = f"var VERSION = '{APPROVED_RUNNER_VERSION}'" in runner_source
            pair_checks["runnerFailClosedFlags"] = all(marker in runner_source for marker in (
                "ENABLE_TIER2_2_CONDITIONAL_RETRY = true",
                "ENABLE_AGGREGATE_NATURAL_TRAFFIC_GATE = true",
                "ENABLE_CONFIRMED_NO_DATA_FAST_FAIL = true",
                "ENABLE_KEEPA_PASSIVE_WAIT_PROTOCOL = true",
            ))
            pair_checks["runnerDeferredJsonContract"] = all(marker in runner_source for marker in (
                "ENABLE_DEFERRED_FULL_JSON = true",
                "ssIntegratedRunner:v0.3:",
                "function exportBatch(state)",
            ))
        pair_ok = all(pair_checks.values())
        payload["configuredBrowserPair"] = {
            "ok": pair_ok,
            "collector": APPROVED_COLLECTOR_VERSION,
            "runner": APPROVED_RUNNER_VERSION,
            "collectorPath": str(ACTIVE_COLLECTOR_SCRIPT),
            "runnerPath": str(ACTIVE_RUNNER_SCRIPT),
            "checks": pair_checks,
            "scriptIntegrity": script_integrity,
            "technicalReady": pair_ok,
            "formalRunAuthorized": False,
            "releaseStatus": BROWSER_PAIR_RELEASE_STATUS,
            "pendingEvidence": ["one_asin_live_smoke", "paired_30_real_asins"],
        }
        payload["ok"] = bool(payload.get("ok")) and pair_ok
        return payload


PREFLIGHT_CACHE_LOCK = threading.RLock()
PREFLIGHT_CACHE_PAYLOAD: dict[str, Any] | None = None
PREFLIGHT_CACHE_CHECKED_AT: float | None = None
PREFLIGHT_CACHE_STARTED_AT: float | None = None
PREFLIGHT_CACHE_ERROR = ""
PREFLIGHT_CACHE_RETRY_AFTER: float | None = None
PREFLIGHT_CACHE_IN_FLIGHT = False
PREFLIGHT_CACHE_GENERATION = 0


def _preflight_cache_placeholder() -> dict[str, Any]:
    return {
        "schemaVersion": "amazonStrictSelectionPreflight/v1",
        "ok": False,
        "requiredFilesMissing": [],
        "approvedRuleDrift": [],
        "userscripts": {},
        "strictQualifiedHistoryCount": None,
        "warnings": [],
        "errors": ["预检尚未完成"],
        "configuredBrowserPair": {
            "ok": False,
            "collector": APPROVED_COLLECTOR_VERSION,
            "runner": APPROVED_RUNNER_VERSION,
            "checks": {},
            "technicalReady": False,
            "formalRunAuthorized": False,
            "releaseStatus": BROWSER_PAIR_RELEASE_STATUS,
            "pendingEvidence": ["one_asin_live_smoke", "paired_30_real_asins"],
        },
        "sellerSpriteApi": {
            "configured": SELLERSPRITE_CREDENTIAL.is_file(),
            "credentialProtection": "windows_dpapi" if SELLERSPRITE_CREDENTIAL.is_file() else "missing",
            "apiBase": "https://api.sellersprite.com",
            "required": False,
            "activeCandidateSource": DEFAULT_CANDIDATE_SOURCE_MODE,
        },
    }


def _preflight_cache_iso(timestamp: float | None) -> str:
    if timestamp is None:
        return ""
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec="seconds")


def _preflight_cache_meta_locked(now: float | None = None) -> dict[str, Any]:
    current = time.time() if now is None else now
    age = None if PREFLIGHT_CACHE_CHECKED_AT is None else max(0.0, current - PREFLIGHT_CACHE_CHECKED_AT)
    if PREFLIGHT_CACHE_PAYLOAD is None:
        status = "checking" if PREFLIGHT_CACHE_IN_FLIGHT else ("failed" if PREFLIGHT_CACHE_ERROR else "unknown")
    elif PREFLIGHT_CACHE_IN_FLIGHT:
        status = "refreshing" if age is not None and age <= PREFLIGHT_CACHE_TTL_SECONDS else "stale"
    elif age is not None and age <= PREFLIGHT_CACHE_TTL_SECONDS:
        status = "ready"
    else:
        status = "failed" if PREFLIGHT_CACHE_ERROR else "stale"
    return {
        "version": PREFLIGHT_CACHE_VERSION,
        "status": status,
        "enabled": ENABLE_PREFLIGHT_CACHE,
        "ttlSeconds": PREFLIGHT_CACHE_TTL_SECONDS,
        "checkedAt": _preflight_cache_iso(PREFLIGHT_CACHE_CHECKED_AT),
        "startedAt": _preflight_cache_iso(PREFLIGHT_CACHE_STARTED_AT),
        "ageSeconds": round(age, 1) if age is not None else None,
        "lastError": PREFLIGHT_CACHE_ERROR,
        "retryAfter": _preflight_cache_iso(PREFLIGHT_CACHE_RETRY_AFTER),
        "generation": PREFLIGHT_CACHE_GENERATION,
    }


def _store_preflight_cache_result(payload: dict[str, Any] | None = None, error: str = "") -> None:
    global PREFLIGHT_CACHE_PAYLOAD, PREFLIGHT_CACHE_CHECKED_AT, PREFLIGHT_CACHE_ERROR, PREFLIGHT_CACHE_RETRY_AFTER
    with PREFLIGHT_CACHE_LOCK:
        if payload is not None:
            PREFLIGHT_CACHE_PAYLOAD = copy.deepcopy(payload)
            PREFLIGHT_CACHE_CHECKED_AT = time.time()
            PREFLIGHT_CACHE_ERROR = ""
            PREFLIGHT_CACHE_RETRY_AFTER = None
        elif error:
            PREFLIGHT_CACHE_ERROR = error
            PREFLIGHT_CACHE_RETRY_AFTER = time.time() + PREFLIGHT_CACHE_ERROR_BACKOFF_SECONDS


def _run_preflight_cache_refresh(generation: int) -> None:
    global PREFLIGHT_CACHE_IN_FLIGHT
    try:
        _store_preflight_cache_result(preflight())
    except Exception as exc:  # noqa: BLE001
        _store_preflight_cache_result(error=str(exc) or "预检失败")
    finally:
        with PREFLIGHT_CACHE_LOCK:
            PREFLIGHT_CACHE_IN_FLIGHT = False


def _request_preflight_cache_refresh() -> bool:
    global PREFLIGHT_CACHE_IN_FLIGHT, PREFLIGHT_CACHE_STARTED_AT, PREFLIGHT_CACHE_GENERATION
    with PREFLIGHT_CACHE_LOCK:
        if PREFLIGHT_CACHE_IN_FLIGHT:
            return False
        PREFLIGHT_CACHE_IN_FLIGHT = True
        PREFLIGHT_CACHE_STARTED_AT = time.time()
        PREFLIGHT_CACHE_GENERATION += 1
        generation = PREFLIGHT_CACHE_GENERATION
        worker = threading.Thread(
            target=_run_preflight_cache_refresh,
            args=(generation,),
            name="amazon-console-preflight",
            daemon=True,
        )
        worker.start()
        return True


def preflight_snapshot() -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a non-blocking readiness snapshot for the overview UI.

    This cache is display-only. Formal dispatch functions continue to call the
    synchronous ``preflight`` function so a stale result can never authorize a
    strict-selection task.
    """
    if not ENABLE_PREFLIGHT_CACHE:
        payload = preflight()
        return payload, {"version": PREFLIGHT_CACHE_VERSION, "status": "ready", "enabled": False, "ttlSeconds": 0, "checkedAt": now_iso(), "startedAt": now_iso(), "ageSeconds": 0, "lastError": "", "generation": 0}
    with PREFLIGHT_CACHE_LOCK:
        now = time.time()
        age = None if PREFLIGHT_CACHE_CHECKED_AT is None else now - PREFLIGHT_CACHE_CHECKED_AT
        retry_blocked = bool(PREFLIGHT_CACHE_RETRY_AFTER and now < PREFLIGHT_CACHE_RETRY_AFTER)
        should_refresh = (PREFLIGHT_CACHE_PAYLOAD is None or age is None or age > PREFLIGHT_CACHE_TTL_SECONDS) and not retry_blocked
        payload = copy.deepcopy(PREFLIGHT_CACHE_PAYLOAD or _preflight_cache_placeholder())
        meta = _preflight_cache_meta_locked(now)
    if should_refresh:
        _request_preflight_cache_refresh()
        with PREFLIGHT_CACHE_LOCK:
            meta = _preflight_cache_meta_locked()
    return payload, meta


def refresh_preflight_cache_sync() -> dict[str, Any]:
    """Run an explicit operator-requested check and update the UI snapshot."""
    payload = preflight()
    _store_preflight_cache_result(payload)
    with PREFLIGHT_CACHE_LOCK:
        return copy.deepcopy(payload)


def _reset_preflight_cache_for_tests() -> None:
    global PREFLIGHT_CACHE_PAYLOAD, PREFLIGHT_CACHE_CHECKED_AT, PREFLIGHT_CACHE_STARTED_AT, PREFLIGHT_CACHE_ERROR, PREFLIGHT_CACHE_RETRY_AFTER, PREFLIGHT_CACHE_IN_FLIGHT, PREFLIGHT_CACHE_GENERATION
    with PREFLIGHT_CACHE_LOCK:
        PREFLIGHT_CACHE_PAYLOAD = None
        PREFLIGHT_CACHE_CHECKED_AT = None
        PREFLIGHT_CACHE_STARTED_AT = None
        PREFLIGHT_CACHE_ERROR = ""
        PREFLIGHT_CACHE_RETRY_AFTER = None
        PREFLIGHT_CACHE_IN_FLIGHT = False
        PREFLIGHT_CACHE_GENERATION = 0


def dispatch_gate(batch: dict[str, Any], stage: str) -> dict[str, Any]:
    if stage == "candidates":
        check = preflight()
        if not check.get("ok"):
            return {"allowed": False, "reason": "\u6b63\u5f0f\u9884\u68c0\u672a\u901a\u8fc7\uff0c\u4e0d\u80fd\u6d3e\u53d1\u5019\u9009\u961f\u5217\u4efb\u52a1\u3002", "stage": stage}
        return {
            "allowed": True,
            "reason": "\u6b63\u5f0f\u9884\u68c0\u901a\u8fc7\u3002",
            "stage": stage,
            "inputs": {"sourceXlsx": batch["sourceXlsx"], "sourceUrl": batch["sourceUrl"]},
        }

    if stage == "browser":
        candidate_stage = batch["stages"]["candidates"]
        queue_path = candidate_stage.get("artifacts", {}).get("queuePath")
        if candidate_stage.get("status") != "completed" or not queue_path or not Path(queue_path).is_file():
            return {"allowed": False, "reason": "ASIN \u961f\u5217\u5c1a\u672a\u5b8c\u6210\u5e76\u843d\u76d8\uff0c\u4e0d\u80fd\u6d3e\u53d1\u6d4f\u89c8\u5668\u4efb\u52a1\u3002", "stage": stage}
        browser_check = preflight().get("configuredBrowserPair", {})
        if not browser_check.get("technicalReady") or not browser_check.get("formalRunAuthorized"):
            return {
                "allowed": False,
                "reason": "\u5f53\u524d Collector / Runner \u7ec4\u5408\u4ec5\u5b8c\u6210\u6280\u672f\u9002\u914d\uff1b\u5355 ASIN \u73b0\u573a smoke \u4e0e 30-ASIN \u914d\u5bf9\u8bc1\u636e\u5b8c\u6210\u524d\uff0c\u7981\u6b62\u6b63\u5f0f\u6d4f\u89c8\u5668\u6d3e\u53d1\u3002",
                "stage": stage,
            }
        return {
            "allowed": True,
            "reason": "ASIN \u961f\u5217\u5df2\u5b8c\u6210\u3002",
            "stage": stage,
            "inputs": {"queuePath": queue_path, "queueCount": candidate_stage.get("artifacts", {}).get("queueCount")},
        }

    if stage == "excel":
        browser_stage = batch["stages"]["browser"]
        merged_path = batch.get("mergedJsonPath")
        if browser_stage.get("status") != "completed" or not merged_path or not Path(merged_path).is_file():
            return {"allowed": False, "reason": "Runner \u5408\u5e76 JSON \u5c1a\u672a\u5b8c\u6210\u5e76\u767b\u8bb0\uff0c\u4e0d\u80fd\u6d3e\u53d1 Excel \u4efb\u52a1\u3002", "stage": stage}
        return {
            "allowed": True,
            "reason": "Runner \u5408\u5e76 JSON \u5df2\u767b\u8bb0\u3002",
            "stage": stage,
            "inputs": {"mergedJsonPath": merged_path, "qualifiedCount": browser_stage.get("stats", {}).get("qualifiedCount")},
        }

    return {"allowed": False, "reason": "\u672a\u77e5\u9636\u6bb5\u3002", "stage": stage}


def build_dispatch_prompt(batch: dict[str, Any], stage: str, note: str, gate: dict[str, Any]) -> str:
    queue_count = gate.get("inputs", {}).get("queueCount") or "以文件实际数量为准"
    qualified_count = gate.get("inputs", {}).get("qualifiedCount") or "以 JSON 实际数量为准"
    header = [
        f"\u63a7\u5236\u53f0\u8c03\u5ea6\u6279\u6b21\uff1a{batch['name']} (batchId: {batch['id']})",
        f"\u6b63\u5f0f\u9879\u76ee\uff1a{PROJECT_ROOT}",
        "\u4ec5\u5904\u7406\u672c\u9636\u6bb5\uff0c\u4e0d\u7ee7\u7eed\u8fdb\u5165\u4e0b\u4e00\u9636\u6bb5\uff1b\u5b8c\u6210\u540e\u62a5\u544a\u5b9e\u9645\u4ea7\u7269\u8def\u5f84\u3001\u6570\u91cf\u3001\u7248\u672c\u548c\u963b\u585e\u9879\u3002",
    ]
    if stage == "candidates":
        body = [
            "\u804c\u8d23\uff1a\u751f\u6210\u53ef\u5bfc\u5165 Runner \u7684 ASIN \u961f\u5217\u3002",
            f"SellerSprite \u5bfc\u51fa\uff1a{batch['sourceXlsx']}",
            f"\u5b8c\u6574\u7b5b\u9009 URL\uff1a{batch['sourceUrl']}",
            f"\u961f\u5217\u4e0a\u9650\uff1a{batch['queueSize']}; Runner \u5206\u7247\uff1a{batch['partSize']}.",
            "\u5fc5\u987b\u5148\u6267\u884c\u6b63\u5f0f\u9884\u68c0\uff0c\u4fdd\u7559\u6765\u6e90\u5b57\u6bb5\u3001\u786c\u6392\u9664\u3001\u5386\u53f2\u53bb\u91cd\u548c\u5931\u8d25\u5ba1\u8ba1\uff1b\u4e0d\u5f97\u653e\u5bbd A-F \u95e8\u69db\u3002",
            "\u8f93\u51fa runner_queue.txt, runner_queue.json, \u5b9e\u9645\u6570\u91cf\u3001\u6765\u6e90\u8282\u70b9\u548c SHA-256.",
        ]
    elif stage == "browser":
        body = [
            "\u804c\u8d23\uff1a\u4f7f\u7528\u5df2\u6279\u51c6\u7684 Collector / Runner \u5b8c\u6210\u5f53\u524d\u6d4f\u89c8\u5668\u91c7\u96c6\u3002",
            f"ASIN \u961f\u5217\uff1a{gate['inputs']['queuePath']}",
            f"队列数量：{queue_count}.",
            f"\u8981\u6c42\u7248\u672c\uff1aCollector {APPROVED_COLLECTOR_VERSION} / Runner {APPROVED_RUNNER_VERSION}; Amazon \u5fc5\u987b\u662f\u7f8e\u56fd\u914d\u9001\u5730\u5740\u3002",
            "\u82e5\u51fa\u73b0 ScriptCat \u672a\u6ce8\u5165\u3001CAPTCHA\u3001\u767b\u5f55\u5931\u6548\u3001\u7ad9\u70b9\u5b58\u50a8\u6ee1\u6216\u8bc1\u636e\u7f3a\u5931\uff0c\u6807\u8bb0 needs_attention \u5e76\u505c\u6b62\uff0c\u4e0d\u5f97\u5224\u4e3a\u901a\u8fc7\u3002",
            "\u5b8c\u6210\u540e\u5bfc\u51fa Runner \u5408\u5e76 JSON\uff0c\u62a5\u544a\u8fd0\u884c\u6570\u3001\u901a\u8fc7\u6570\u3001\u5931\u8d25\u6570\u3001\u7248\u672c\u548c JSON \u8def\u5f84\uff1b\u4e0d\u8981\u751f\u6210 Excel\u3002",
        ]
    else:
        body = [
            "\u804c\u8d23\uff1a\u628a Runner JSON \u5f53\u524d\u6807\u8bb0\u901a\u8fc7\u7684\u5546\u54c1\u76f4\u63a5\u5bfc\u5165 Excel\u3002",
            f"Runner \u5408\u5e76 JSON\uff1a{gate['inputs']['mergedJsonPath']}",
            f"浏览器通过数：{qualified_count}.",
            "\u8f93\u51fa\u5fc5\u987b\u6807\u8bb0 direct_import\uff0c\u4e0d\u5f97\u5ba3\u79f0\u4e3a A-F \u6700\u7ec8\u4e25\u683c\u9a8c\u6536\u8868\uff0c\u4e0d\u505a\u989d\u5916\u4ea7\u54c1\u6dd8\u6c70\u3002",
            "\u5339\u914d\u5019\u9009\u6807\u9898\u4e0e\u4e3b\u56fe\uff0c\u5199\u5165\u4e2d\u6587\u54c1\u540d\uff0c\u6838\u5bf9\u5bfc\u5165\u884c\u6570\u3001\u5d4c\u5165\u56fe\u7247\u6570\u548c\u5de5\u4f5c\u7c3f\u8def\u5f84\u3002",
            "\u4e0d\u5f97\u66f4\u65b0\u6b63\u5f0f\u4e25\u683c\u5386\u53f2\u53f0\u8d26\u3002",
        ]
    if note.strip():
        body.append(f"\u672c\u6b21\u8865\u5145\u8981\u6c42\uff1a{note.strip()}")
    return "\n".join(header + [""] + body)


STORE = SQLiteWorkflowStore()


def prepare_browser_export_tasks(batch_id: str) -> dict[str, Any]:
    def apply(batch: dict[str, Any]) -> None:
        if batch.get("overallStatus") in {"completed", "cancelled", "stopping"}:
            raise ValueError("批次已停止，不能重新准备 SellerSprite 导出")
        tasks = browser_export_tasks(batch)
        bridge_status = "queued" if ENABLE_SELLERSPRITE_BRIDGE else "manual_required"
        message = (
            "等待 SellerSprite Bridge 自动查询、导出和回传"
            if ENABLE_SELLERSPRITE_BRIDGE
            else "请逐个类目打开 SellerSprite 查询并上传当前导出文件"
        )
        set_stage(
            batch,
            "candidates",
            "needs_attention",
            message,
            {
                "exportTasks": tasks,
                "uploadedExportCount": sum(1 for item in tasks if item["uploaded"]),
                "sellerSpriteBridge": {
                    "status": bridge_status,
                    "version": SELLERSPRITE_BRIDGE_VERSION,
                    "queuedCount": 0,
                    "totalCount": len(tasks),
                },
            },
        )

    updated = STORE.update(batch_id, apply)
    tasks = updated["stages"]["candidates"]["artifacts"].get("exportTasks", [])
    queued = 0
    for task in tasks:
        if task["uploaded"]:
            continue
        command = STORE.enqueue_sellersprite_command(batch_id, {
            "categoryInput": task["categoryInput"],
            "sourcePage": task["label"],
            "nodeIdPath": task["nodeIdPath"],
            "queryUrl": task["queryUrl"],
            "filters": updated.get("queryFilters") or DEFAULT_QUERY_FILTERS,
            "bridgeVersion": SELLERSPRITE_BRIDGE_VERSION,
        })
        queued += 1 if command else 0
    if queued:
        STORE.update(batch_id, lambda b: b["stages"]["candidates"].setdefault("artifacts", {}).setdefault("sellerSpriteBridge", {}).update({"status": "queued", "version": SELLERSPRITE_BRIDGE_VERSION, "queuedCount": queued, "totalCount": len(tasks)}))
    STORE.event(batch_id, "SellerSprite 浏览器导出任务已准备", "info", {"taskCount": len(tasks), "queuedCount": queued, "bridgeVersion": SELLERSPRITE_BRIDGE_VERSION})
    return STORE.get(batch_id)


def auto_prepare_browser_export_batch(batch: dict[str, Any]) -> dict[str, Any]:
    """Queue Bridge work as part of browser-export batch creation.

    Batch creation must remain durable even when the Bridge is unavailable.  In
    that case the batch is returned in ``needs_attention`` with the reason saved
    in its event log instead of turning a recoverable setup issue into a lost run.
    """
    if not ENABLE_SELLERSPRITE_BRIDGE or batch.get("candidateSourceMode") != "browser_export" or not batch.get("categoryPool"):
        return batch
    try:
        return prepare_browser_export_tasks(batch["id"])
    except Exception as exc:  # noqa: BLE001
        message = f"SellerSprite Bridge 自动任务准备失败：{exc}"
        def mark_failure(current: dict[str, Any]) -> None:
            if terminal_batch_status(current) or current.get("overallStatus") == "stopping":
                return
            set_stage(current, "candidates", "needs_attention", message, {"sellerSpriteBridge": {"status": "needs_attention", "version": SELLERSPRITE_BRIDGE_VERSION, "message": message}})

        STORE.update(batch["id"], mark_failure)
        STORE.event(batch["id"], message, "error")
        return STORE.get(batch["id"])


def store_browser_export(batch_id: str, query: dict[str, list[str]], headers: Any, raw: bytes) -> dict[str, Any]:
    with STORE.lock:
        STORE._assert_batch_not_archived_locked(batch_id)
        return _store_browser_export_locked(batch_id, query, headers, raw)


def _store_browser_export_locked(batch_id: str, query: dict[str, list[str]], headers: Any, raw: bytes) -> dict[str, Any]:
    batch = STORE.get(batch_id)
    if terminal_batch_status(batch) or batch.get("overallStatus") == "stopping":
        raise ValueError("批次已停止，不再接收 SellerSprite 导出")
    if batch.get("candidateSourceMode") != "browser_export":
        raise ValueError("该批次不是浏览器导出模式")
    category_input = str(query.get("categoryInput", [""])[0]).strip()
    valid_categories = {item.get("input") for item in batch.get("categoryPool", [])}
    if not category_input or category_input not in valid_categories:
        raise ValueError("上传文件没有匹配到批次类目")
    query_url = validate_sellersprite_url(str(query.get("queryUrl", [""])[0]))
    try:
        try:
            from .sellersprite_browser_export_pipeline import PipelineError as BrowserPipelineError
            from .sellersprite_browser_export_pipeline import validate_query_contract
        except ImportError:
            from sellersprite_browser_export_pipeline import PipelineError as BrowserPipelineError
            from sellersprite_browser_export_pipeline import validate_query_contract
        query_contract = validate_query_contract(query_url, batch.get("queryFilters") or DEFAULT_QUERY_FILTERS)
    except BrowserPipelineError as exc:
        raise ValueError(str(exc)) from exc
    expected_node = next((str(item.get("nodeIdPath") or "") for item in batch.get("categoryPool", []) if item.get("input") == category_input), "")
    if expected_node and expected_node not in query_contract.get("nodeIdPaths", []):
        raise ValueError("上传文件的 SellerSprite 类目与批次类目不一致")
    encoded_name = str(headers.get("X-File-Name") or "")
    original_name = Path(unquote(encoded_name)).name
    suffix = Path(original_name).suffix.lower()
    if suffix not in {".xlsx", ".csv", ".tsv"}:
        raise ValueError("只支持 SellerSprite .xlsx、.csv 或 .tsv 导出")
    if not raw:
        raise ValueError("上传文件为空")
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(original_name).stem).strip("._")[:80] or "sellersprite_export"
    upload_dir = Path(batch["runDir"]) / "browser_exports"
    upload_dir.mkdir(parents=True, exist_ok=True)
    export_id = uuid.uuid4().hex[:12]
    path = upload_dir / f"{export_id}_{safe_name}{suffix}"
    path.write_bytes(raw)
    captured_at = str(query.get("capturedAt", [""])[0]).strip() or now_iso()
    try:
        captured_dt = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("capturedAt 必须是 ISO 时间") from exc
    if captured_dt.tzinfo is None:
        raise ValueError("capturedAt 必须包含时区")
    age_seconds = (datetime.now(timezone.utc) - captured_dt.astimezone(timezone.utc)).total_seconds()
    if age_seconds < -300 or age_seconds > 24 * 60 * 60:
        raise ValueError("SellerSprite 导出文件必须在最近 24 小时内采集")
    record = {
        "id": export_id,
        "categoryInput": category_input,
        "sourcePage": str(query.get("sourcePage", [category_input])[0]).strip() or category_input,
        "queryUrl": query_url,
        "path": str(path),
        "fileName": original_name,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "capturedAt": captured_dt.astimezone(timezone.utc).isoformat(),
    }

    def apply(current: dict[str, Any]) -> None:
        if terminal_batch_status(current) or current.get("overallStatus") == "stopping":
            raise ValueError("批次已停止，不再接收 SellerSprite 导出")
        exports = [item for item in current.get("browserExports", []) if item.get("categoryInput") != category_input]
        exports.append(record)
        current["browserExports"] = exports
        tasks = browser_export_tasks(current)
        current["stages"]["candidates"].setdefault("artifacts", {}).update({
            "exportTasks": tasks,
            "uploadedExportCount": sum(1 for item in tasks if item["uploaded"]),
        })
        current["stages"]["candidates"]["message"] = f"已上传 {len(exports)}/{len(tasks)} 个类目导出"

    updated = STORE.update(batch_id, apply)
    STORE.event(batch_id, f"已上传 SellerSprite 导出：{category_input}", "success", {"fileName": original_name, "sha256": record["sha256"]})
    return updated


def maybe_start_browser_export_pipeline(batch_id: str) -> dict[str, Any]:
    """Start strict candidate generation once every Bridge export is staged.

    The upload endpoint is intentionally idempotent: a late duplicate callback or
    two categories finishing together may both reach this function.  The launch
    guard in ``STORE.launch`` remains authoritative for the actual subprocess.
    """
    batch = STORE.get(batch_id)
    if terminal_batch_status(batch) or batch.get("overallStatus") == "stopping":
        return batch
    if batch.get("candidateSourceMode") != "browser_export" or not batch.get("categoryPool"):
        return batch
    tasks = browser_export_tasks(batch)
    if not tasks or any(not item["uploaded"] for item in tasks):
        return batch
    stage = batch["stages"]["candidates"]
    artifacts = stage.get("artifacts", {})
    if artifacts.get("queuePath") or stage.get("status") in {"running", "completed", "failed", "cancelled", "stopping"}:
        return batch

    def mark_processing(current: dict[str, Any]) -> None:
        if terminal_batch_status(current) or current.get("overallStatus") == "stopping":
            return
        current_stage = current["stages"]["candidates"]
        current_stage["message"] = "所有 SellerSprite 导出已回传，正在生成 ASIN 队列"
        current_stage.setdefault("artifacts", {}).setdefault("sellerSpriteBridge", {}).update({
            "status": "processing",
            "version": SELLERSPRITE_BRIDGE_VERSION,
            "uploadedCount": len(tasks),
            "totalCount": len(tasks),
        })

    STORE.update(batch_id, mark_processing)
    try:
        start_candidates(batch_id)
    except Exception as exc:  # noqa: BLE001
        latest = STORE.get(batch_id)
        if terminal_batch_status(latest) or latest.get("overallStatus") == "stopping":
            return latest
        if "已有任务正在运行" not in str(exc):
            message = f"自动生成 ASIN 队列失败：{exc}"

            def mark_attention(current: dict[str, Any]) -> None:
                if terminal_batch_status(current) or current.get("overallStatus") == "stopping":
                    return
                set_stage(
                    current,
                    "candidates",
                    "needs_attention",
                    message,
                    {
                        "sellerSpriteBridge": {
                            "status": "needs_attention",
                            "version": SELLERSPRITE_BRIDGE_VERSION,
                            "uploadedCount": len(tasks),
                            "totalCount": len(tasks),
                            "message": message,
                        }
                    },
                )

            STORE.update(batch_id, mark_attention)
            STORE.event(batch_id, message, "error")
    return STORE.get(batch_id)


def store_sellersprite_export(payload: dict[str, Any]) -> dict[str, Any]:
    if not ENABLE_SELLERSPRITE_BRIDGE:
        raise ValueError("SellerSprite Bridge 功能未启用")
    pairing_token = str(payload.get("pairingToken") or "")
    if not secrets.compare_digest(BROWSER_PAIRING_TOKEN, pairing_token):
        raise ValueError("SellerSprite Bridge 配对码无效")
    return _store_sellersprite_export(payload)


def _store_sellersprite_export(payload: dict[str, Any]) -> dict[str, Any]:
    pairing_token = str(payload.get("pairingToken") or "")
    batch_id = str(payload.get("batchId") or "")
    with STORE.lock:
        STORE._assert_batch_not_archived_locked(batch_id)
        batch = STORE.get(batch_id)
        batch_token = str(payload.get("batchToken") or "")
        if not batch_token or not secrets.compare_digest(str(batch.get("bridgeToken") or ""), batch_token):
            raise ValueError("SellerSprite 批次令牌无效")
        if terminal_batch_status(batch) or batch.get("overallStatus") == "stopping":
            command_id = str(payload.get("commandId") or "")
            if command_id:
                with STORE.db:
                    STORE.db.execute(
                        "UPDATE commands SET status='cancelled',acknowledged_at=? WHERE id=? AND batch_id=? AND action='seller_export'",
                        (now_iso(), command_id, batch_id),
                    )
            STORE.event(batch_id, "已忽略停止批次的迟到 SellerSprite 回传", "warning", {"commandId": command_id or None})
            return STORE.get(batch_id)
    content = str(payload.get("contentBase64") or "")
    if not content:
        raise ValueError("SellerSprite 导出内容为空")
    try:
        raw = base64.b64decode(content, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("SellerSprite 导出内容不是有效 Base64") from exc
    if not raw or len(raw) > SELLERSPRITE_BRIDGE_MAX_BYTES:
        raise ValueError("SellerSprite 导出文件为空或超过 16 MB 限制")
    query = {
        "categoryInput": [str(payload.get("categoryInput") or "")],
        "sourcePage": [str(payload.get("sourcePage") or payload.get("categoryInput") or "")],
        "queryUrl": [str(payload.get("queryUrl") or "")],
        "capturedAt": [str(payload.get("capturedAt") or "")],
    }
    file_name = str(payload.get("fileName") or "seller_sprite_export.xlsx")
    result = store_browser_export(batch_id, query, {"X-File-Name": file_name}, raw)
    command_id = str(payload.get("commandId") or "")
    with STORE.lock:
        STORE._assert_batch_not_archived_locked(batch_id)
        latest = STORE.get(batch_id)
        if terminal_batch_status(latest) or latest.get("overallStatus") == "stopping":
            if command_id:
                with STORE.db:
                    STORE.db.execute(
                        "UPDATE commands SET status='cancelled',acknowledged_at=? WHERE id=? AND batch_id=? AND action='seller_export'",
                        (now_iso(), command_id, batch_id),
                    )
            STORE.event(batch_id, "已保留取消并忽略迟到 SellerSprite 桥接状态", "warning", {"commandId": command_id or None})
            return STORE.get(batch_id)
        if command_id:
            STORE.acknowledge_sellersprite_command(pairing_token, batch_id, command_id, "completed", "导出文件已回传并通过来源校验")

        def mark_uploaded(current: dict[str, Any]) -> None:
            if terminal_batch_status(current) or current.get("overallStatus") == "stopping":
                return
            current["stages"]["candidates"].setdefault("artifacts", {}).setdefault("sellerSpriteBridge", {}).update({"status": "uploaded", "version": SELLERSPRITE_BRIDGE_VERSION, "lastCategory": query["categoryInput"][0], "lastFile": file_name, "uploadedCount": current["stages"]["candidates"].get("artifacts", {}).get("uploadedExportCount", 0), "totalCount": len(current.get("categoryPool", []))})

        STORE.update(batch_id, mark_uploaded)
    return maybe_start_browser_export_pipeline(batch_id)


def candidate_success(run_dir: Path) -> dict[str, Any]:
    imports = list(run_dir.glob("excel_import_*/runner_queue.txt"))
    queue_path = imports[0] if imports else next(run_dir.glob("**/runner_queue.txt"), None)
    if not queue_path or not queue_path.exists():
        raise ValueError("没有找到 runner_queue.txt")
    queue_json = queue_path.with_suffix(".json")
    if not queue_json.exists():
        raise ValueError("没有找到 runner_queue.json")
    count = len([line for line in queue_path.read_text(encoding="ascii").splitlines() if line.strip()])
    return {"queuePath": str(queue_path), "queueJsonPath": str(queue_json), "queueCount": count, "runDir": str(run_dir)}


def seller_sprite_candidate_success(batch_id: str, run_dir: Path) -> dict[str, Any]:
    result_path = run_dir / "candidate_pipeline_result.json"
    result = parse_json_file(result_path)
    required = ["queuePath", "queueJsonPath", "analysisWorkbookPath", "imagesDir", "titleOverridesPath"]
    if not isinstance(result, dict) or any(not result.get(key) for key in required):
        raise ValueError("SellerSprite 候选流水线产物不完整")
    for key in required:
        path = Path(result[key])
        if key == "imagesDir":
            if not path.is_dir():
                raise ValueError("候选主图目录不存在")
        elif not path.is_file():
            raise ValueError(f"候选产物不存在: {key}")

    def apply(batch: dict[str, Any]) -> None:
        batch["candidateJsonPath"] = result["queueJsonPath"]
        batch["titleOverridesPath"] = result["titleOverridesPath"]
        batch["imagesDir"] = result["imagesDir"]
        by_input = {item.get("input"): item for item in result.get("resolvedCategories", [])}
        batch["categoryPool"] = [{**row, **by_input.get(row.get("input"), {})} for row in batch.get("categoryPool", [])]
        batch["stages"]["candidates"].setdefault("artifacts", {}).setdefault("sellerSpriteBridge", {}).update({
            "status": "asin_ready",
            "version": SELLERSPRITE_BRIDGE_VERSION,
            "queueCount": result.get("queueCount", 0),
        })

    STORE.update(batch_id, apply)
    return result


def approve_candidate_queue(batch_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    with STORE.lock:
        STORE._assert_batch_not_archived_locked(batch_id)
        batch = STORE.get(batch_id)
        if terminal_batch_status(batch) or batch.get("overallStatus") == "stopping":
            raise ValueError("批次已结束或正在停止，不能确认 Runner 队列")
        if batch.get("runnerBatchName"):
            raise ValueError("Runner 批次已生成，不能再修改已批准队列")
        stage = batch["stages"]["candidates"]
        proposal_path = Path(stage.get("artifacts", {}).get("queuePath") or "")
        queue_json_path = Path(stage.get("artifacts", {}).get("queueJsonPath") or "")
        if stage.get("status") not in {"needs_attention", "completed"} or not proposal_path.is_file() or not queue_json_path.is_file():
            raise ValueError("候选分析尚未完成")
        proposed = [line.strip().upper() for line in proposal_path.read_text(encoding="ascii").splitlines() if line.strip()]
        selected_value = payload.get("selectedAsins")
        selected = [str(value).strip().upper() for value in selected_value] if isinstance(selected_value, list) else [line.strip().upper() for line in str(selected_value or "").splitlines() if line.strip()]
        if not selected:
            raise ValueError("Runner 队列不能为空；请加载候选并至少保留一个 ASIN")
        selected = list(dict.fromkeys(selected))
        invalid = [asin for asin in selected if not re.fullmatch(r"[A-Z0-9]{10}", asin) or asin not in proposed]
        if invalid:
            raise ValueError(f"确认队列包含无效或未提议 ASIN: {', '.join(invalid[:5])}")
        approved_path = Path(batch["runDir"]) / "candidate_pool" / "runner_queue_approved.txt"
        approved_path.parent.mkdir(parents=True, exist_ok=True)
        approved_path.write_text("\n".join(selected) + "\n", encoding="ascii")
        digest = hashlib.sha256(approved_path.read_bytes()).hexdigest()

        def apply(current: dict[str, Any]) -> None:
            if terminal_batch_status(current) or current.get("overallStatus") == "stopping":
                raise ValueError("批次已结束或正在停止，不能确认 Runner 队列")
            if current.get("runnerBatchName"):
                raise ValueError("Runner 批次已生成，不能再修改已批准队列")
            set_stage(current, "candidates", "completed", f"已确认 {len(selected)} 个 Runner ASIN", {
                "queuePath": str(approved_path),
                "proposalQueuePath": str(proposal_path),
                "queueJsonPath": str(queue_json_path),
                "queueCount": len(selected),
                "queueSha256": digest,
            })

        updated = STORE.update(batch_id, apply)
        STORE.event(batch_id, f"Runner 队列已确认: {len(selected)} 个 ASIN", "success", {"queueSha256": digest})
        return updated


def runner_command_payload(batch: dict[str, Any]) -> dict[str, Any]:
    stage = batch["stages"]["candidates"]
    queue_path = Path(stage.get("artifacts", {}).get("queuePath") or "")
    if stage.get("status") != "completed" or not queue_path.is_file():
        raise ValueError("请先完成并确认 ASIN 队列")
    queue = [line.strip().upper() for line in queue_path.read_text(encoding="ascii").splitlines() if line.strip()]
    if not queue:
        raise ValueError("Runner ASIN 队列为空")
    batch_name = f"{batch['runDate'].replace('-', '')}_{slug(batch.get('category') or batch['name'])}_{batch['id'][:4]}"
    return {
        "batchName": batch_name,
        "operator": batch.get("operator") or "operator",
        "targetQualified": batch.get("targetQualified") or 20,
        "queueAsins": queue,
        "queueSha256": hashlib.sha256(("\n".join(queue) + "\n").encode("ascii")).hexdigest(),
        "deliveryZip": batch.get("deliveryZip") or "10010",
        "approvedCollectorVersion": APPROVED_COLLECTOR_VERSION,
        "approvedRunnerVersion": APPROVED_RUNNER_VERSION,
    }


def reset_browser_for_start(batch_id: str, command_payload: dict[str, Any]) -> dict[str, Any]:
    """Reset orchestration state before generating or adopting exact Runner evidence."""
    with STORE.lock:
        STORE._assert_batch_not_archived_locked(batch_id)
        batch = STORE.get(batch_id)
        if batch.get("overallStatus") in {"completed", "cancelled", "stopping"}:
            raise ValueError("批次已结束或正在停止，不能启动 Runner")
        if batch.get("stages", {}).get("browser", {}).get("status") == "completed" or batch.get("jsonHandoff", {}).get("sourcePath"):
            raise ValueError("Runner 原始 JSON 已回传，不能重复启动；请继续 JSON 交接")
        with STORE.db:
            STORE.db.execute("DELETE FROM bridge_sessions WHERE batch_id=?", (batch_id,))

        def apply(current: dict[str, Any]) -> None:
            if current.get("overallStatus") in {"completed", "cancelled", "stopping"}:
                raise ValueError("批次已结束或正在停止，不能启动 Runner")
            current["runnerQueueSha256"] = command_payload["queueSha256"]
            current["runnerBatchName"] = command_payload["batchName"]
            current["mergedJsonPath"] = ""
            current["jsonHandoff"] = {"sourceSha256": "", "copiedAt": "", "pastedSha256": "", "pasteVerified": False}
            current["stages"]["browser"] = {
                "status": "waiting",
                "artifacts": {},
                "message": f"等待 Browser Bridge {APPROVED_BROWSER_BRIDGE_VERSION} 接管或生成当前 Runner 批次",
                "stats": {},
                "connection": {"status": "disconnected", "batchName": command_payload["batchName"], "queueHash": ""},
            }
            current["stages"]["excel"] = {"status": "idle", "artifacts": {}, "message": "等待当前 Runner 批次的合并 JSON", "stats": {}}
            current["overallStatus"] = "browser_waiting"

        updated = STORE.update(batch_id, apply)
        STORE.event(batch_id, "已重置浏览器阶段并等待接管或生成当前 Runner 批次", "info", {"batchName": command_payload["batchName"], "queueSha256": command_payload["queueSha256"]})
        return updated


def normalize_merged_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"合并 JSON 无法解析: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("results"), list):
        raise ValueError("合并 JSON 顶层必须是对象并包含 results 数组")
    if str(value.get("runnerVersion") or "") != APPROVED_RUNNER_VERSION:
        raise ValueError(f"合并 JSON Runner 版本必须是 {APPROVED_RUNNER_VERSION}")
    if str(value.get("collectorVersion") or "") != APPROVED_COLLECTOR_VERSION:
        raise ValueError(f"合并 JSON Collector 版本必须是 {APPROVED_COLLECTOR_VERSION}")
    return value


def validate_merged_bridge_execution(merged: dict[str, Any], payload: dict[str, Any]) -> None:
    merged_execution = merged.get("bridgeExecution")
    if not isinstance(merged_execution, dict):
        raise ValueError("Runner 合并 JSON 缺少 Bridge 执行来源")
    if (
        str(merged_execution.get("commandId") or "") != str(payload.get("commandId") or "")
        or str(merged_execution.get("mode") or "") != str(payload.get("executionMode") or "")
    ):
        raise ValueError("Runner 合并 JSON 的执行来源与当前 Bridge 会话不一致")


def store_merged_json(batch_id: str, value: Any, source: str) -> dict[str, Any]:
    merged = normalize_merged_payload(value)
    if source == "browser" and str(merged.get("status") or "") != "done":
        raise ValueError("Runner 合并 JSON 仅在 status=done 后接收")
    serialized = json_bytes(merged) + b"\n"
    digest = hashlib.sha256(serialized).hexdigest()
    with STORE.lock:
        STORE._assert_batch_not_archived_locked(batch_id)
        batch = STORE.get(batch_id)
        if source != "browser" and (terminal_batch_status(batch) or batch.get("overallStatus") == "stopping"):
            raise ValueError("终态批次不再接收人工 JSON 交接")
        if source == "browser" and batch.get("stages", {}).get("excel", {}).get("status") == "running":
            handoff = batch.get("jsonHandoff", {})
            existing_digest = str(handoff.get("sourceSha256") or "")
            if not existing_digest or not secrets.compare_digest(existing_digest, digest):
                raise ValueError("Excel 正在使用已锁定的 Runner JSON，拒绝替换原始结果")
            existing_path = Path(handoff.get("sourcePath") or "")
            if not existing_path.is_file() or not secrets.compare_digest(
                hashlib.sha256(existing_path.read_bytes()).hexdigest(), existing_digest
            ):
                raise ValueError("Excel 构建期间 Runner 原始 JSON 文件指纹异常")
            artifact = browser_artifact(existing_path, batch_id)
            artifact["sha256"] = existing_digest
            STORE.event(batch_id, "Excel 构建期间收到相同 Runner JSON，已按幂等请求忽略", "info", {"sha256": existing_digest})
            return {"batch": batch, "artifact": artifact}
        expected_name = str(batch.get("runnerBatchName") or "")
        if expected_name and str(merged.get("batchName") or "") != expected_name:
            raise ValueError("合并 JSON 的 batchName 与当前批次不一致")
        if source != "browser":
            source_hash = str(batch.get("jsonHandoff", {}).get("sourceSha256") or "")
            if not source_hash or not secrets.compare_digest(source_hash, digest):
                raise ValueError("粘贴 JSON 与 Runner 导出的原始 JSON 不一致")
        folder = Path(batch["runDir"]) / ("browser" if source == "browser" else "manual_handoff")
        folder.mkdir(parents=True, exist_ok=True)
        received_terminal_status = "cancelled" if batch.get("overallStatus") == "stopping" else terminal_batch_status(batch)
        audit_only = source == "browser" and bool(received_terminal_status)
        if audit_only:
            audit_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            path = folder / f"merged_{received_terminal_status}_audit_{audit_stamp}.json"
        else:
            path = folder / ("merged_source.json" if source == "browser" else "merged_pasted.json")
        atomic_json_write(path, merged)
        if not secrets.compare_digest(digest, hashlib.sha256(path.read_bytes()).hexdigest()):
            raise RuntimeError("合并 JSON 原子写入后的指纹校验失败")
        artifact = browser_artifact(path, batch_id)
        artifact["sha256"] = digest

        def apply(current: dict[str, Any]) -> None:
            handoff = current.setdefault("jsonHandoff", {})
            if source == "browser":
                current_terminal = terminal_batch_status(current)
                if current.get("overallStatus") == "stopping" or current_terminal:
                    audit_status = "cancelled" if current.get("overallStatus") == "stopping" else current_terminal
                    handoff.update({f"{audit_status}SourceSha256": digest, f"{audit_status}SourcePath": str(path), f"{audit_status}SourceAt": now_iso()})
                    if current.get("overallStatus") == "stopping":
                        current["overallStatus"] = "cancelled"
                        current.pop("cancelCommandId", None)
                        current.pop("cancelRetryCount", None)
                        current["stages"]["browser"].update({"status": "cancelled", "message": "Runner 已完成当前行并停止", "artifacts": {**current["stages"]["browser"].get("artifacts", {}), "cancelledMergedJson": str(path), "cancelledMergedJsonSha256": digest}})
                    return
                handoff.update({"sourceSha256": digest, "sourcePath": str(path), "pastedSha256": "", "pasteVerified": False})
                current["stages"]["browser"].update({"status": "completed", "message": "Runner 已完成，合并 JSON 可复制", "artifacts": {**current["stages"]["browser"].get("artifacts", {}), **artifact}})
                current["overallStatus"] = "excel_ready"
            else:
                source_hash = str(handoff.get("sourceSha256") or "")
                if not source_hash or not secrets.compare_digest(source_hash, digest):
                    raise ValueError("粘贴 JSON 与 Runner 导出的原始 JSON 不一致")
                handoff.update({"pastedSha256": digest, "pastedPath": str(path), "pasteVerified": True, "pastedAt": now_iso()})
                current["mergedJsonPath"] = str(path)
                current["stages"]["excel"].update({"status": "ready", "message": "JSON 交接校验通过，可生成 Excel", "stats": artifact})

        updated = STORE.update(batch_id, apply)
        canonical_source_saved = source == "browser" and updated.get("jsonHandoff", {}).get("sourceSha256") == digest
        if updated.get("overallStatus") == "cancelled" and source == "browser":
            with STORE.db:
                STORE.db.execute("UPDATE bridge_sessions SET status='cancelled' WHERE batch_id=?", (batch_id,))
            STORE.complete_stop_commands(batch_id)
            event_message = "已保存停止后的 Runner 合并 JSON（仅供审计）"
        elif source == "browser" and not canonical_source_saved:
            event_message = f"已保存{terminal_batch_status(updated) or '终态'}批次的迟到 Runner 合并 JSON（仅供审计）"
        else:
            event_message = "Runner 合并 JSON 已保存" if source == "browser" else "人工粘贴 JSON 校验通过"
        STORE.event(batch_id, event_message, "success", {"sha256": digest, **artifact})
        return {"batch": updated, "artifact": artifact}


def copy_merged_json(batch_id: str) -> dict[str, Any]:
    batch = STORE.get(batch_id)
    handoff = batch.get("jsonHandoff", {})
    source_path = Path(handoff.get("sourcePath") or "")
    if not source_path.is_file():
        raise ValueError("Runner 合并 JSON 尚未就绪")
    text_value = source_path.read_text(encoding="utf-8")
    digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    source_digest = str(handoff.get("sourceSha256") or "")
    if not source_digest or not secrets.compare_digest(source_digest, digest):
        raise ValueError("Runner 原始 JSON 指纹已变化，拒绝复制")
    STORE.update(batch_id, lambda current: current.setdefault("jsonHandoff", {}).update({"copiedAt": now_iso()}))
    STORE.event(batch_id, "已在控制台复制合并 JSON", "info", {"sha256": digest})
    return {"text": text_value, "sha256": digest, "bytes": len(text_value.encode("utf-8"))}


def browser_artifact(batch_path: Path, batch_id: str) -> dict[str, Any]:
    batch_json = parse_json_file(batch_path)
    if not isinstance(batch_json, dict):
        raise ValueError("合并 JSON 顶层必须是对象")
    results = batch_json.get("results")
    if not isinstance(results, list):
        raise ValueError("合并 JSON 缺少 results 数组")
    qualified = [row for row in results if row.get("qualified") is True and (row.get("strictDecision") in (None, "pass"))]
    return {"mergedJson": str(batch_path), "batchName": batch_json.get("batchName", ""), "resultCount": len(results), "qualifiedCount": len(qualified), "runnerVersion": batch_json.get("runnerVersion", ""), "collectorVersion": batch_json.get("collectorVersion", "")}


def direct_import_success(replay_dir: Path) -> dict[str, Any]:
    data_path = replay_dir / "final_candidates_data.json"
    summary_path = replay_dir / "run_summary.json"
    if not data_path.exists() or not summary_path.exists():
        raise ValueError("直接导入数据集未生成")
    rows = parse_json_file(data_path)
    summary = parse_json_file(summary_path)
    if not isinstance(rows, list) or not rows:
        raise ValueError("直接导入没有浏览器通过项")
    if not isinstance(summary, dict):
        raise ValueError("直接导入运行摘要无效")
    if summary.get("directImport") is not True or summary.get("importMode") != "browser-qualified":
        raise ValueError("控制台直接导入摘要必须明确为 browser-qualified")
    workbook_report = replay_dir / "workbook_build_report.json"
    report = parse_json_file(workbook_report) if workbook_report.exists() else {}
    if (
        report.get("candidateProfileVersion") != "runner-unaccepted-workbook-v1.0.0"
        or report.get("candidateStatus") != "runner_pass_unaccepted"
        or report.get("acceptance") != "not_run_by_user_mode"
    ):
        raise ValueError("Runner 通过候选工作簿缺少未验收标记")
    final_data_digest = str(report.get("finalDataSha256") or "").strip().lower()
    run_summary_digest = str(report.get("runSummarySha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", final_data_digest) or not re.fullmatch(r"[0-9a-f]{64}", run_summary_digest):
        raise ValueError("构建报告缺少有效的直接导入数据指纹")
    if not secrets.compare_digest(hashlib.sha256(data_path.read_bytes()).hexdigest(), final_data_digest):
        raise ValueError("直接导入候选数据与构建报告不一致")
    if not secrets.compare_digest(hashlib.sha256(summary_path.read_bytes()).hexdigest(), run_summary_digest):
        raise ValueError("直接导入运行摘要与构建报告不一致")
    workbook = str(report.get("finalXlsx") or "").strip()
    workbook_digest = str(report.get("finalXlsxSha256") or "").strip().lower()
    if not workbook:
        raise ValueError("构建报告缺少 finalXlsx 路径")
    workbook_path = Path(workbook)
    if not workbook_path.is_absolute():
        raise ValueError("构建报告 finalXlsx 必须是绝对路径")
    workbook_path = workbook_path.resolve()
    replay_root = replay_dir.resolve()
    if workbook_path.parent != replay_root:
        raise ValueError("Excel 必须位于当前直接导入回放目录")
    if not re.fullmatch(r"runner_candidates_unaccepted_[A-Za-z0-9][A-Za-z0-9_-]*\.xlsx", workbook_path.name):
        raise ValueError("Excel 文件名缺少未验收标记")
    if not workbook_path.is_file():
        raise ValueError("没有找到生成的 Excel")
    if not re.fullmatch(r"[0-9a-f]{64}", workbook_digest):
        raise ValueError("构建报告缺少有效的 Excel SHA-256")
    actual_workbook_digest = hashlib.sha256(workbook_path.read_bytes()).hexdigest()
    if not secrets.compare_digest(actual_workbook_digest, workbook_digest):
        raise ValueError("Excel 文件指纹与构建报告不一致")
    media_count = 0
    with zipfile.ZipFile(workbook_path) as archive:
        media_count = len([name for name in archive.namelist() if name.startswith("xl/media/")])
    if media_count != len(rows):
        raise ValueError(f"Excel 主图嵌入数量与导入行数不一致: {media_count}/{len(rows)}")
    return {"replayDir": str(replay_dir), "dataPath": str(data_path), "workbookPath": str(workbook_path), "rowCount": len(rows), "embeddedImageCount": media_count, "directImport": True, "acceptance": "not_run_by_user_mode"}


def update_browser(batch_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    batch = STORE.get(batch_id)
    if batch.get("archived"):
        raise ValueError("批次已删除，请先恢复后再操作")
    if terminal_batch_status(batch) or batch.get("overallStatus") == "stopping":
        raise ValueError("批次已停止，不能更新浏览器阶段")
    status = str(payload.get("status") or "").strip()
    if status not in ALLOWED_BROWSER_STATUSES:
        raise ValueError(f"浏览器状态必须是: {', '.join(sorted(ALLOWED_BROWSER_STATUSES))}")
    merged_path = str(payload.get("mergedJsonPath") or "").strip()
    artifact = None
    if merged_path:
        path = valid_file(merged_path, (".json",))
        artifact = browser_artifact(path, batch_id)

    def apply(batch: dict[str, Any]) -> None:
        if terminal_batch_status(batch) or batch.get("overallStatus") == "stopping":
            raise ValueError("批次已停止，不能更新浏览器阶段")
        stage = batch["stages"]["browser"]
        stage["status"] = status
        stage["message"] = str(payload.get("message") or default_browser_message(status))
        stage["stats"] = {**stage.get("stats", {}), **(artifact or {}), **(payload.get("stats") or {})}
        if artifact:
            stage["artifacts"] = {**stage.get("artifacts", {}), **artifact}
            batch["mergedJsonPath"] = artifact["mergedJson"]
        if status == "completed":
            batch["overallStatus"] = "excel_ready"
        elif status in {"paused", "needs_attention"}:
            batch["overallStatus"] = "needs_attention"
        elif status == "running":
            batch["overallStatus"] = "running"
    updated = STORE.update(batch_id, apply)
    STORE.event(batch_id, f"浏览器阶段更新为 {status}", "warning" if status in {"paused", "needs_attention"} else "info", artifact)
    return updated


def default_browser_message(status: str) -> str:
    return {"waiting": "等待 Chrome / Runner 采集", "running": "浏览器正在采集", "paused": "浏览器阶段已暂停，等待人工恢复", "completed": "已收到合并 JSON，可生成 Excel", "needs_attention": "需要人工检查 Chrome、登录或站点存储"}[status]


def bridge_event(batch_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    token = str(payload.get("token") or "")
    with STORE.lock:
        event_type = str(payload.get("eventType") or "telemetry")
        pending_request = STORE._active_archive_request_locked(batch_id)
        allow_archive_request = ""
        if pending_request:
            allow_archive_request = str(pending_request["request_id"])
        STORE.validate_bridge_runner_identity(
            batch_id,
            token,
            payload,
            allow_archive_request=allow_archive_request,
        )
        if allow_archive_request and event_type not in {"done", "completed"}:
            raise ValueError("批次正在删除收尾，仅接受 Runner 完成停止事件")
        current = STORE.get(batch_id)
        if terminal_batch_status(current):
            return {"ok": True, "ignored": True, "serverTime": now_iso()}
        asin = str(payload.get("asin") or "")
        event_payload = {key: value for key, value in payload.items() if key not in {"token", "batchId", "stats"}}
        if asin and not allow_archive_request:
            STORE.record_asin_event(batch_id, asin, payload.get("rowIndex"), event_type, payload.get("gate"), payload.get("decision"), event_payload)
        message = str(payload.get("message") or event_type)
        level = "warning" if event_type in {"paused", "needs_attention", "captcha", "login_required", "storage_full"} else ("success" if event_type in {"row_committed", "done"} else "info")
        STORE.event(batch_id, message, level, event_payload, allow_archive_request=allow_archive_request)
        if event_type in {"done", "completed"}:
            def apply_done(batch: dict[str, Any]) -> None:
                if terminal_batch_status(batch):
                    return
                if batch.get("overallStatus") == "stopping":
                    batch["overallStatus"] = "cancelled"
                    batch.pop("cancelCommandId", None)
                    batch.pop("cancelRetryCount", None)
                    batch["stages"]["browser"].update({"status": "cancelled", "message": "Runner 已完成当前行并停止"})
                    return
                verified_json = bool(batch.get("jsonHandoff", {}).get("sourceSha256"))
                batch["stages"]["browser"].update({
                    "status": "completed" if verified_json else "running",
                    "message": "Runner 已完成，合并 JSON 已校验" if verified_json else "Runner 已完成，等待校验合并 JSON",
                })
                batch["overallStatus"] = "excel_ready" if verified_json else "running"

            updated = STORE.update(batch_id, apply_done, allow_archive_request=allow_archive_request)
            if updated.get("overallStatus") == "cancelled":
                with STORE.db:
                    STORE.db.execute("UPDATE bridge_sessions SET status='cancelled' WHERE batch_id=?", (batch_id,))
                STORE.complete_stop_commands(batch_id, allow_archive_request=allow_archive_request)
                if allow_archive_request:
                    STORE.reconcile_archive_requests()
        elif event_type in {"paused", "needs_attention", "captcha", "login_required", "storage_full"}:
            def apply_attention(batch: dict[str, Any]) -> None:
                if terminal_batch_status(batch) or batch.get("overallStatus") == "stopping":
                    return
                batch["stages"]["browser"].update({"status": "needs_attention", "message": message})
                batch["overallStatus"] = "needs_attention"
            STORE.update(batch_id, apply_attention, allow_archive_request=allow_archive_request)
        else:
            def apply_telemetry(batch: dict[str, Any]) -> None:
                if terminal_batch_status(batch) or batch.get("overallStatus") == "stopping":
                    return
                batch["stages"]["browser"].update({"status": "running", "message": message, "stats": {**batch["stages"]["browser"].get("stats", {}), **event_payload}})
            STORE.update(batch_id, apply_telemetry, allow_archive_request=allow_archive_request)
        return {"ok": True, "serverTime": now_iso()}


class Handler(BaseHTTPRequestHandler):
    server_version = "AmazonSelectionConsole/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def send_json(self, payload: Any, status: int = 200) -> None:
        raw = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def send_file(self, path: Path, content_type: str | None = None, download: bool = False) -> None:
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        self.end_headers()
        self.wfile.write(data)

    def read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_REQUEST_BYTES:
            raise ValueError("请求体过大")
        raw = self.rfile.read(length)
        if not raw:
            return {}
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return payload

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/browser-bridge.user.js":
            self.send_file(CONSOLE_ROOT / "browser_bridge_v2.user.js", "text/javascript; charset=utf-8")
            return
        if parsed.path == "/browser-bridge-v1.user.js":
            self.send_file(CONSOLE_ROOT / "browser_bridge_v1.user.js", "text/javascript; charset=utf-8")
            return
        if parsed.path == "/seller-sprite-bridge.user.js":
            self.send_file(CONSOLE_ROOT / "sellersprite_browser_bridge_v1.user.js", "text/javascript; charset=utf-8")
            return
        if parsed.path.startswith("/static/"):
            requested = (STATIC_DIR / unquote(parsed.path.removeprefix("/static/"))).resolve()
            if not safe_child(STATIC_DIR, requested):
                self.send_error(HTTPStatus.FORBIDDEN)
                return
            content_type = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8"}.get(requested.suffix, "application/octet-stream")
            self.send_file(requested, content_type)
            return
        try:
            if parsed.path == "/api/overview":
                check, preflight_meta = preflight_snapshot()
                pool = STORE.category_pool_overview()
                repository = STORE.category_repository_overview()
                batch_counts = STORE.batch_counts()
                self.send_json({"projectRoot": str(PROJECT_ROOT), "consoleRoot": str(CONSOLE_ROOT), "preflight": check, "preflightMeta": preflight_meta, "batches": STORE.list(), "batchCounts": batch_counts, "archivedBatchCount": batch_counts["archived"], "archiveRequests": STORE.list_archive_requests(), "categoryPool": pool["items"], "categoryPoolCounts": pool["counts"], "categoryRepository": {"enabled": ENABLE_CATEGORY_REPOSITORY, "version": CATEGORY_REPOSITORY_VERSION, "marketplace": CATEGORY_MARKETPLACE, "scope": CATEGORY_SCREENING_SCOPE, "counts": repository["counts"]}, "features": {"categoryRepository": {"enabled": ENABLE_CATEGORY_REPOSITORY, "version": CATEGORY_REPOSITORY_VERSION}}, "threads": STORE.list_threads(), "dispatches": STORE.list_dispatches(30), "approvedPair": {"bridge": APPROVED_BROWSER_BRIDGE_VERSION, "collector": APPROVED_COLLECTOR_VERSION, "runner": APPROVED_RUNNER_VERSION}, "sellerSpriteApi": check.get("sellerSpriteApi", {}), "candidateSources": {"default": DEFAULT_CANDIDATE_SOURCE_MODE, "browserExport": True, "officialApiCredentialPresent": SELLERSPRITE_CREDENTIAL.is_file()}, "sellerSpriteBridge": {"version": SELLERSPRITE_BRIDGE_VERSION, "enabled": ENABLE_SELLERSPRITE_BRIDGE, "scriptUrl": "/seller-sprite-bridge.user.js"}, "threadControl": {"version": CONTROL_PLANE_VERSION, "enabled": ENABLE_THREAD_CONTROL_PLANE}})
                return
            if parsed.path == "/api/bridge/pairing":
                self.send_json({"pairingToken": BROWSER_PAIRING_TOKEN, "protocol": "browser-bridge-v2", "scriptUrl": "/browser-bridge.user.js"})
                return
            if parsed.path == "/api/sellersprite/pairing":
                self.send_json({"pairingToken": BROWSER_PAIRING_TOKEN, "protocol": SELLERSPRITE_BRIDGE_VERSION, "scriptUrl": "/seller-sprite-bridge.user.js", "enabled": ENABLE_SELLERSPRITE_BRIDGE})
                return
            if parsed.path == "/api/batches":
                archived = parse_qs(parsed.query).get("archived", [""])[0].lower() in {"1", "true", "yes"}
                self.send_json({"batches": STORE.list_archived() if archived else STORE.list(), "counts": STORE.batch_counts(), "archived": archived})
                return
            if parsed.path == "/api/category-pool":
                self.send_json(STORE.category_pool_overview())
                return
            if parsed.path == "/api/category-repository":
                search = parse_qs(parsed.query).get("q", [""])[0]
                self.send_json(STORE.category_repository_overview(search))
                return
            if parsed.path == "/api/threads":
                self.send_json({"threads": STORE.list_threads()})
                return
            if parsed.path == "/api/dispatches":
                self.send_json({"dispatches": STORE.list_dispatches()})
                return
            match = re.fullmatch(r"/api/batches/([a-f0-9]{12})", parsed.path)
            if match:
                self.send_json(STORE.get(match.group(1)))
                return
            archive_request_match = re.fullmatch(r"/api/batches/([a-f0-9]{12})/archive-request", parsed.path)
            if archive_request_match:
                STORE.reconcile_archive_requests()
                batch = STORE.get(archive_request_match.group(1))
                self.send_json({"batch": batch, "request": batch.get("archiveRequest")})
                return
            bridge_info_match = re.fullmatch(r"/api/batches/([a-f0-9]{12})/bridge", parsed.path)
            if bridge_info_match:
                batch = STORE.get(bridge_info_match.group(1))
                self.send_json({"batchId": batch["id"], "protocol": batch.get("bridgeProtocol", "browser-bridge-v1"), "token": batch.get("bridgeToken", ""), "registerUrl": "/bridge/register", "heartbeatUrl": "/bridge/heartbeat", "commandPollUrl": "/bridge/commands/poll", "approvedPair": {"bridge": APPROVED_BROWSER_BRIDGE_VERSION, "collector": APPROVED_COLLECTOR_VERSION, "runner": APPROVED_RUNNER_VERSION}})
                return
            events_match = re.fullmatch(r"/api/batches/([a-f0-9]{12})/events", parsed.path)
            if events_match:
                batch_id = events_match.group(1)
                STORE.get(batch_id)
                query = parse_qs(parsed.query)
                self.send_json({"events": STORE.list_events(batch_id, int(query.get("after", ["0"])[0]), int(query.get("limit", ["200"])[0]))})
                return
            stream_match = re.fullmatch(r"/api/batches/([a-f0-9]{12})/stream", parsed.path)
            if stream_match:
                batch_id = stream_match.group(1)
                STORE.get(batch_id)
                last_id = int(parse_qs(parsed.query).get("after", ["0"])[0])
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                deadline = time.time() + 25
                while time.time() < deadline:
                    events = STORE.list_events(batch_id, last_id, 100)
                    if events:
                        for event in events:
                            last_id = event["id"]
                            self.wfile.write(f"id: {last_id}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8"))
                        self.wfile.flush()
                    else:
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
                    time.sleep(1)
                return
            artifact_match = re.fullmatch(r"/api/batches/([a-f0-9]{12})/artifact", parsed.path)
            if artifact_match:
                batch = STORE.get(artifact_match.group(1))
                key = parse_qs(parsed.query).get("key", [""])[0]
                path = artifact_path(batch, key)
                self.send_file(path, download=True)
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except KeyError:
            self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:  # noqa: BLE001
            self.send_json({"error": str(exc)}, 400)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            upload_match = re.fullmatch(r"/api/batches/([a-f0-9]{12})/candidate-export", parsed.path)
            if upload_match:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_REQUEST_BYTES:
                    raise ValueError("上传文件大小无效或超过限制")
                raw = self.rfile.read(length)
                self.send_json(store_browser_export(upload_match.group(1), parse_qs(parsed.query), self.headers, raw), 201)
                return
            payload = self.read_body()
            if parsed.path == "/bridge/control/poll":
                self.send_json({"commands": STORE.poll_global_commands(
                    str(payload.get("pairingToken") or ""),
                    str(payload.get("protocol") or ""),
                    str(payload.get("bridgeVersion") or ""),
                    str(payload.get("scriptVersion") or ""),
                ), "serverTime": now_iso()})
                return
            if parsed.path == "/bridge/control/ack":
                STORE.acknowledge_global_command(str(payload.get("pairingToken") or ""), str(payload.get("batchId") or ""), str(payload.get("commandId") or ""), str(payload.get("status") or ""), str(payload.get("message") or ""))
                self.send_json({"ok": True})
                return
            if parsed.path == "/bridge/sellersprite/poll":
                self.send_json({"commands": STORE.poll_sellersprite_commands(str(payload.get("pairingToken") or "")), "serverTime": now_iso(), "bridgeVersion": SELLERSPRITE_BRIDGE_VERSION})
                return
            if parsed.path == "/bridge/sellersprite/ack":
                STORE.acknowledge_sellersprite_command(str(payload.get("pairingToken") or ""), str(payload.get("batchId") or ""), str(payload.get("commandId") or ""), str(payload.get("status") or ""), str(payload.get("message") or ""))
                self.send_json({"ok": True})
                return
            if parsed.path == "/bridge/sellersprite/export":
                self.send_json(store_sellersprite_export(payload), 201)
                return
            if parsed.path == "/bridge/register":
                if str(payload.get("scriptVersion") or "") != APPROVED_BROWSER_BRIDGE_SCRIPT_VERSION:
                    raise ValueError(
                        f"Browser Bridge 脚本必须为 {APPROVED_BROWSER_BRIDGE_SCRIPT_VERSION}"
                    )
                batch_id = str(payload.get("batchId") or "")
                result = STORE.register_bridge(
                    batch_id,
                    str(payload.get("token") or ""),
                    str(payload.get("protocol") or ""),
                    str(payload.get("bridgeVersion") or ""),
                    str(payload.get("collectorVersion") or ""),
                    str(payload.get("runnerVersion") or ""),
                    str(payload.get("batchName") or ""),
                    str(payload.get("queueHash") or ""),
                    str(payload.get("commandId") or ""),
                    str(payload.get("executionMode") or ""),
                    str(payload.get("scriptVersion") or ""),
                )
                self.send_json(result)
                return
            if parsed.path == "/bridge/heartbeat":
                batch_id = str(payload.get("batchId") or "")
                self.send_json(STORE.heartbeat(batch_id, str(payload.get("token") or ""), payload))
                return
            if parsed.path == "/bridge/event":
                batch_id = str(payload.get("batchId") or "")
                self.send_json(bridge_event(batch_id, payload))
                return
            if parsed.path == "/bridge/artifact":
                batch_id = str(payload.get("batchId") or "")
                STORE.bridge_batch(batch_id, str(payload.get("token") or ""))
                self.send_json(STORE.register_artifact(batch_id, str(payload.get("key") or "artifact"), str(payload.get("path") or ""), str(payload.get("kind") or "browser")))
                return
            if parsed.path == "/bridge/merged-json":
                batch_id = str(payload.get("batchId") or "")
                merged = normalize_merged_payload(payload.get("mergedJson"))
                validate_merged_bridge_execution(merged, payload)
                STORE.validate_bridge_runner_identity(batch_id, str(payload.get("token") or ""), {**payload, "batchName": merged.get("batchName"), "queueHash": merged.get("queueHash")})
                self.send_json(store_merged_json(batch_id, merged, "browser"), 201)
                return
            if parsed.path == "/bridge/commands/poll":
                batch_id = str(payload.get("batchId") or "")
                self.send_json({"commands": STORE.poll_commands(batch_id, str(payload.get("token") or ""))})
                return
            if parsed.path == "/bridge/commands/ack":
                batch_id = str(payload.get("batchId") or "")
                STORE.acknowledge_command(batch_id, str(payload.get("token") or ""), str(payload.get("commandId") or ""), str(payload.get("status") or "acknowledged"), str(payload.get("message") or ""))
                self.send_json({"ok": True})
                return
            if parsed.path == "/api/batches":
                created = STORE.create(payload)
                self.send_json(auto_prepare_browser_export_batch(created), 201)
                return
            if parsed.path == "/api/batches/archive":
                self.send_json(STORE.archive_batches(payload.get("batchIds")))
                return
            if parsed.path == "/api/batches/archive-request":
                idempotency_key = str(self.headers.get("Idempotency-Key") or payload.get("idempotencyKey") or "")
                result = STORE.request_archive_batches(payload.get("batchIds"), idempotency_key=idempotency_key)
                self.send_json(result, HTTPStatus.ACCEPTED if result.get("pendingCount") else HTTPStatus.OK)
                return
            if parsed.path == "/api/category-pool/import":
                self.send_json(
                    STORE.import_category_pool(
                        str(payload.get("categories") or ""),
                        payload.get("selectedKeys"),
                        payload.get("overrideScreenedKeys"),
                    ),
                    201,
                )
                return
            if parsed.path == "/api/category-pool/preview":
                self.send_json(STORE.preview_category_pool_import(str(payload.get("categories") or "")))
                return
            if parsed.path == "/api/preflight":
                self.send_json(refresh_preflight_cache_sync())
                return
            thread_match = re.fullmatch(r"/api/threads/([0-9a-f-]{36})/snapshot", parsed.path)
            if thread_match:
                self.send_json(STORE.update_thread_snapshot(thread_match.group(1), payload))
                return
            dispatch_match = re.fullmatch(r"/api/dispatches/([a-f0-9]{32})/status", parsed.path)
            if dispatch_match:
                self.send_json(STORE.update_dispatch_status(dispatch_match.group(1), str(payload.get("status") or "")))
                return
            match = re.fullmatch(r"/api/batches/([a-f0-9]{12})/([^/]+)", parsed.path)
            if not match:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            batch_id, action = match.groups()
            batch_snapshot = STORE.get(batch_id)
            if batch_snapshot.get("archived") and action not in {"archive", "restore"}:
                raise ValueError("批次已删除，请先恢复后再操作")
            if action == "archive":
                if batch_snapshot.get("archived"):
                    # Keep the legacy single-batch endpoint idempotent for archived rows.
                    self.send_json(batch_snapshot)
                    return
                archive_key = str(self.headers.get("Idempotency-Key") or payload.get("idempotencyKey") or "")
                archive_request = batch_snapshot.get("archiveRequest") or {}
                if str(archive_request.get("status") or "") in ARCHIVE_REQUEST_ACTIVE_STATUSES:
                    # A legacy caller may retry while graceful deletion is still
                    # draining; reuse that durable request instead of reporting
                    # a misleading synchronous archive conflict.
                    result = STORE.request_archive_batches([batch_id], idempotency_key=archive_key)
                    self.send_json(result, HTTPStatus.ACCEPTED if result.get("pendingCount") else HTTPStatus.OK)
                elif batch_snapshot.get("archiveEligible") is True:
                    self.send_json(STORE.archive_completed_batch(batch_id))
                else:
                    result = STORE.request_archive_batches([batch_id], idempotency_key=archive_key)
                    self.send_json(result, HTTPStatus.ACCEPTED if result.get("pendingCount") else HTTPStatus.OK)
            elif action == "restore":
                self.send_json(STORE.restore_batch(batch_id))
            elif action == "dispatch":
                result = STORE.prepare_dispatch(batch_id, str(payload.get("stage") or ""), str(payload.get("note") or ""))
                self.send_json(result, 201)
            elif action == "candidates":
                start_candidates(batch_id)
                self.send_json(STORE.get(batch_id), 202)
            elif action == "approve-candidates":
                self.send_json(approve_candidate_queue(batch_id, payload))
            elif action == "retry":
                stage = str(payload.get("stage") or "")
                if stage == "candidates":
                    start_candidates(batch_id)
                elif stage == "browser":
                    STORE.enqueue_command(batch_id, "resume", {"fromCheckpoint": True})
                elif stage == "excel":
                    start_excel(batch_id, payload)
                else:
                    raise ValueError("stage 必须是 candidates、browser 或 excel")
                self.send_json(STORE.get(batch_id), 202)
            elif action == "intervention":
                kind = str(payload.get("kind") or "manual")
                message = str(payload.get("message") or "需要人工处理")
                self.send_json(STORE.add_intervention(batch_id, kind, message, payload.get("payload")), 202)
            elif action == "browser":
                command = str(payload.get("command") or "").strip()
                allowed_commands = {"start", "pause", "resume", "export"}
                if command and command not in allowed_commands:
                    raise ValueError(f"不支持的浏览器命令: {command}")
                command_payload = payload.get("commandPayload") or {}
                if command == "start":
                    command_payload = runner_command_payload(STORE.get(batch_id))
                    reset_browser_for_start(batch_id, command_payload)
                command_result = STORE.enqueue_command(batch_id, command, command_payload) if command else None
                updated = update_browser(batch_id, payload) if payload.get("status") else STORE.get(batch_id)
                self.send_json({"batch": updated, "command": command_result} if command_result else updated, 202 if command_result else 200)
            elif action == "copy-json":
                self.send_json(copy_merged_json(batch_id))
            elif action == "paste-json":
                self.send_json(store_merged_json(batch_id, payload.get("mergedJson"), "paste"), 201)
            elif action == "excel":
                start_excel(batch_id, payload)
                self.send_json(STORE.get(batch_id), 202)
            elif action == "stop":
                self.send_json(STORE.cancel(batch_id))
            elif action == "event":
                message = str(payload.get("message") or "").strip()
                if not message:
                    raise ValueError("事件消息不能为空")
                STORE.event(batch_id, message, str(payload.get("level") or "info"))
                self.send_json(STORE.get(batch_id))
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except KeyError:
            self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:  # noqa: BLE001
            self.send_json({"error": str(exc)}, 400)


def artifact_path(batch: dict[str, Any], key: str) -> Path:
    stage_artifacts = batch["stages"]["candidates"].get("artifacts", {})
    candidates = {"queue": stage_artifacts.get("queuePath"), "queueJson": stage_artifacts.get("queueJsonPath"), "analysisWorkbook": stage_artifacts.get("analysisWorkbookPath"), "sourceManifest": stage_artifacts.get("sourceManifestPath"), "candidateSummary": stage_artifacts.get("summaryPath"), "mergedJson": batch.get("mergedJsonPath") or batch.get("jsonHandoff", {}).get("sourcePath"), "workbook": batch["stages"]["excel"].get("artifacts", {}).get("workbookPath"), "replayData": batch["stages"]["excel"].get("artifacts", {}).get("dataPath"), "log": stage_artifacts.get("stdout")}
    value = candidates.get(key)
    if not value:
        raise ValueError("该产物尚未生成")
    path = Path(value).resolve()
    if not safe_child(PROJECT_ROOT, path) and not safe_child(WORKSPACE_ROOT, path):
        raise ValueError("产物路径不在允许目录")
    return path


def start_candidates(batch_id: str) -> None:
    with STORE.lock:
        STORE._assert_batch_not_archived_locked(batch_id)
        _start_candidates_locked(batch_id)


def _start_candidates_locked(batch_id: str) -> None:
    batch = STORE.get(batch_id)
    if batch.get("overallStatus") in {"completed", "cancelled", "stopping"}:
        raise ValueError("批次已停止，不能重新生成候选队列")
    check = preflight()
    if not check.get("ok"):
        STORE.update(batch_id, lambda b: set_stage(b, "candidates", "needs_attention", "正式预检未通过，已停止生成队列", {"preflight": check}))
        raise ValueError("正式预检未通过")
    queue_name = slug(f"{batch['name']}_{batch['id']}")
    if batch.get("categoryPool"):
        if batch.get("candidateSourceMode") == "browser_export":
            tasks = browser_export_tasks(batch)
            if not tasks or any(not item["uploaded"] for item in tasks):
                prepare_browser_export_tasks(batch_id)
                return
            run_dir = Path(batch["runDir"])
            config_path = run_dir / "console_browser_export_request.json"
            atomic_json_write(config_path, {
                "categories": batch.get("categories", ""),
                "filters": batch.get("queryFilters", {}),
                "exports": batch.get("browserExports", []),
            })
            argv = [
                str(PYTHON_EXE), str(BROWSER_EXPORT_PIPELINE_SCRIPT),
                "--config", str(config_path),
                "--run-dir", batch["runDir"],
                "--project-root", str(PROJECT_ROOT),
                "--queue-name", queue_name,
                "--queue-size", str(batch["queueSize"]),
                "--run-date", batch["runDate"],
            ]
            STORE.launch(
                batch_id,
                "candidates",
                argv,
                "sellersprite_browser_exports",
                lambda run_path: seller_sprite_candidate_success(batch_id, run_path),
                completion_status="needs_attention",
                completion_message="候选分析表已生成，请确认 Runner ASIN 队列",
            )
            return
        if not SELLERSPRITE_CREDENTIAL.is_file():
            raise ValueError("SellerSprite API DPAPI 凭据尚未部署")
        run_dir = Path(batch["runDir"])
        config_path = run_dir / "console_candidate_request.json"
        atomic_json_write(config_path, {"categories": batch.get("categories", ""), "filters": batch.get("queryFilters", {})})
        argv = [
            str(PYTHON_EXE), str(SELLERSPRITE_PIPELINE_SCRIPT),
            "--config", str(config_path),
            "--run-dir", batch["runDir"],
            "--project-root", str(PROJECT_ROOT),
            "--credential", str(SELLERSPRITE_CREDENTIAL),
            "--queue-name", queue_name,
            "--queue-size", str(batch["queueSize"]),
            "--run-date", batch["runDate"],
        ]
        STORE.launch(
            batch_id,
            "candidates",
            argv,
            "sellersprite_api_candidates",
            lambda run_path: seller_sprite_candidate_success(batch_id, run_path),
            completion_status="needs_attention",
            completion_message="候选分析表已生成，请确认 Runner ASIN 队列",
        )
        return
    argv = [str(NODE_EXE), str(PREPARE_SCRIPT), "--input", batch["sourceXlsx"], "--run-dir", batch["runDir"], "--queue-name", queue_name, "--query-url", batch["sourceUrl"], "--source-page", batch["sourcePage"], "--queue-size", str(batch["queueSize"]), "--part-size", str(batch["partSize"]), "--run-date", batch["runDate"], "--python", str(PYTHON_EXE)]
    STORE.launch(batch_id, "candidates", argv, "candidate_queue", lambda run_dir: candidate_success(run_dir))


def verify_excel_input_contract(batch_id: str, expected: dict[str, str]) -> dict[str, Any]:
    with STORE.lock:
        batch = STORE.get(batch_id)
        if batch.get("stages", {}).get("excel", {}).get("status") != "running":
            raise ValueError("Excel 构建状态已变化，拒绝完成旧任务")
        handoff = batch.get("jsonHandoff", {})
        for digest_key in ("sourceSha256", "pastedSha256"):
            actual_digest = str(handoff.get(digest_key) or "")
            expected_digest = str(expected.get(digest_key) or "")
            if not actual_digest or not secrets.compare_digest(actual_digest, expected_digest):
                raise ValueError("Excel 构建期间 JSON 交接指纹已变化")
        for path_key, digest_key in (("sourcePath", "sourceSha256"), ("pastedPath", "pastedSha256")):
            current_path = Path(handoff.get(path_key) or "").resolve()
            expected_path = Path(expected.get(path_key) or "").resolve()
            if current_path != expected_path or not current_path.is_file():
                raise ValueError("Excel 构建期间 JSON 交接路径已变化")
            current_digest = hashlib.sha256(current_path.read_bytes()).hexdigest()
            if not secrets.compare_digest(current_digest, str(expected[digest_key])):
                raise ValueError("Excel 构建期间 JSON 文件指纹已变化")
        return batch


def start_excel(batch_id: str, payload: dict[str, Any]) -> None:
    with STORE.lock:
        STORE._assert_batch_not_archived_locked(batch_id)
        batch = STORE.get(batch_id)
        if terminal_batch_status(batch) or batch.get("overallStatus") == "stopping":
            raise ValueError("批次已结束或正在停止，不能生成 Excel")
        if batch.get("stages", {}).get("excel", {}).get("status") == "running":
            raise ValueError("该批次已有 Excel 任务正在运行")
        handoff = batch.get("jsonHandoff", {})
        if not handoff.get("pasteVerified"):
            raise ValueError("请先复制并手动粘贴同一份 Runner 合并 JSON")
        override_keys = ("batchJsonPath", "candidatesJsonPath", "titleOverridesPath", "imagesDir")
        if any(str(payload.get(key) or "").strip() for key in override_keys):
            raise ValueError("Excel 生成只允许使用当前批次已校验的固定产物")
        source_digest = str(handoff.get("sourceSha256") or "")
        pasted_digest = str(handoff.get("pastedSha256") or "")
        if not source_digest or not pasted_digest or not secrets.compare_digest(source_digest, pasted_digest):
            raise ValueError("JSON 交接指纹状态无效，请重新复制并校验")
        source_path = valid_file(handoff.get("sourcePath"), (".json",))
        source_current_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if not secrets.compare_digest(source_digest, source_current_digest):
            raise ValueError("Runner 原始 JSON 文件指纹发生变化，拒绝生成 Excel")
        merged = valid_file(handoff.get("pastedPath"), (".json",))
        current_digest = hashlib.sha256(merged.read_bytes()).hexdigest()
        if not secrets.compare_digest(pasted_digest, current_digest):
            raise ValueError("已校验 JSON 文件指纹发生变化，拒绝生成 Excel")
        run_dir = Path(batch["runDir"]).resolve()
        try:
            merged.relative_to(run_dir)
        except ValueError as exc:
            raise ValueError("已校验 JSON 不属于当前批次目录") from exc
        candidates_value = batch.get("candidateJsonPath")
        if not candidates_value:
            candidates_value = batch["stages"]["candidates"].get("artifacts", {}).get("queueJsonPath")
        candidates = valid_file(candidates_value, (".json",))
        titles = valid_file(batch.get("titleOverridesPath"), (".json",))
        images_dir = Path(batch.get("imagesDir") or "").expanduser().resolve()
        if not images_dir.is_dir():
            raise ValueError("主图目录不存在")
        for label, path in (("候选 JSON", candidates), ("中文标题 JSON", titles), ("主图目录", images_dir)):
            try:
                path.relative_to(run_dir)
            except ValueError as exc:
                raise ValueError(f"{label}不属于当前批次目录") from exc
        replay_dir = run_dir / "direct_import" / "replay"
        run_id = f"{batch['runId']}_direct_import"
        input_contract = {
            "sourceSha256": source_digest,
            "pastedSha256": pasted_digest,
            "sourcePath": str(source_path),
            "pastedPath": str(merged),
        }
        argv = [str(NODE_EXE), str(DIRECT_IMPORT_SCRIPT), str(merged), str(candidates), str(titles), str(images_dir), str(replay_dir), run_id, batch["runDate"], "--mode", "browser-qualified"]
        STORE.launch(
            batch_id,
            "excel",
            argv,
            "direct_import",
            lambda run_dir: start_build_workbook(batch_id, replay_dir, input_contract),
        )
        STORE.update(batch_id, lambda current: (
            current.update({"mergedJsonPath": str(merged), "candidateJsonPath": str(candidates), "titleOverridesPath": str(titles), "imagesDir": str(images_dir)}),
            current["stages"]["excel"].setdefault("artifacts", {}).update({"replayDir": str(replay_dir), "inputContract": input_contract}),
        ))


def start_build_workbook(batch_id: str, replay_dir: Path, input_contract: dict[str, str]) -> dict[str, Any]:
    verify_excel_input_contract(batch_id, input_contract)
    build_log = replay_dir.parent / "console_workbook_build.log"
    replay_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([str(NODE_EXE), str(BUILD_SCRIPT), str(replay_dir)], cwd=str(PROJECT_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900, creationflags=SUBPROCESS_CREATION_FLAGS)
    build_log.write_text((result.stdout or "") + "\n" + (result.stderr or ""), encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"Excel 构建失败，退出码 {result.returncode}: {result.stderr[-1200:]}")
    result_data = direct_import_success(replay_dir)
    verify_excel_input_contract(batch_id, input_contract)
    result_data["inputContract"] = input_contract
    result_data["buildLog"] = str(build_log)
    return result_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Amazon selection workflow console")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args()
    # Resume durable cancellation/archive intents before accepting browser
    # traffic. The same reconciler also runs on overview/list refreshes.
    STORE.reconcile_archive_requests()
    try:
        server = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        raise SystemExit(f"无法启动控制台，端口 {args.port} 已被占用: {exc}") from exc
    print(f"Amazon selection console: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
