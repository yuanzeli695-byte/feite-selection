from __future__ import annotations

import base64
from contextlib import ExitStack
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlencode, urlsplit

from automation_console import server
from automation_console import sellersprite_browser_export_pipeline as browser_export_pipeline
from automation_console import sellersprite_api_pipeline as sellersprite_pipeline


def delivered_start_command(store: server.SQLiteWorkflowStore, batch_id: str, batch_name: str) -> str:
    command = store.enqueue_command(batch_id, "start", {"batchName": batch_name})
    with store.db:
        store.db.execute(
            "UPDATE commands SET status='delivered',delivered_at=? WHERE id=?",
            (server.now_iso(), command["id"]),
        )
    return command["id"]


def register_test_bridge(
    store: server.SQLiteWorkflowStore,
    batch: dict,
    batch_name: str,
    queue_hash: str,
    *,
    execution_mode: str = "generated_for_command",
):
    command_id = delivered_start_command(store, batch["id"], batch_name)
    return store.register_bridge(
        batch["id"], batch["bridgeToken"], "browser-bridge-v2", "2.1.3",
        "0.4.6.4", "0.3.8.13", batch_name, queue_hash, command_id, execution_mode,
    )


def bridge_attempt(store: server.SQLiteWorkflowStore, batch_id: str) -> dict[str, str]:
    row = store.db.execute(
        "SELECT command_id,execution_mode FROM bridge_sessions WHERE batch_id=?",
        (batch_id,),
    ).fetchone()
    return {"commandId": row["command_id"], "executionMode": row["execution_mode"]}


def complete_test_batch(store: server.SQLiteWorkflowStore, batch_id: str) -> dict:
    completed_at = server.now_iso()

    def apply(batch: dict) -> None:
        for stage in batch["stages"].values():
            stage.update({"status": "completed", "completedAt": completed_at})
        batch["overallStatus"] = "completed"

    return store.update(batch_id, apply)


class ConsoleServerTests(unittest.TestCase):
    def test_query_filters_cannot_weaken_hard_bounds(self) -> None:
        accepted = server.normalize_query_filters({"minPrice": 12, "maxPrice": 40, "maxReviews": 80})
        self.assertEqual(accepted["maxReviews"], 80)
        for overrides in (
            {"minPrice": 9.8},
            {"maxPrice": 50.1},
            {"minRating": 3.9},
            {"maxReviews": 101},
            {"maxVariations": 26},
            {"availableMonth": 4},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                server.normalize_query_filters(overrides)

    def test_category_pool_parser_supports_labels_and_explicit_node_paths(self) -> None:
        rows = sellersprite_pipeline.parse_category_lines("Home Storage\nBeauty | 3760911\n3760901\nHome Storage")
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1]["nodeIdPath"], "3760911")
        self.assertEqual(rows[2]["nodeIdPath"], "3760901")

    def test_console_category_pool_extracts_one_numeric_node_from_sellersprite_links(self) -> None:
        url = "https://www.sellersprite.com/v3/product-research?market=US&nodeIdPaths=%5B%221064954%22%5D"
        direct = server.category_pool_rows(f"Office Products | {url}")
        markdown = server.category_pool_rows(f"Office Products | [{url}]({url})")
        self.assertEqual(direct[0]["nodeIdPath"], "1064954")
        self.assertEqual(markdown[0]["nodeIdPath"], "1064954")
        with self.assertRaisesRegex(ValueError, "nodeIdPath 必须是数字路径"):
            server.category_pool_rows("Office Products | not-a-node")

    def test_cancelled_browser_batch_cannot_be_revived_by_heartbeat(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Stop Runner", "categories": "Beauty | 3760911"})
                    store.update(batch["id"], lambda current: (
                        current.update({"runnerBatchName": "current-runner", "overallStatus": "running"}),
                        current["stages"]["browser"].update({"status": "running", "stats": {"status": "running"}}),
                    ))
                    register_test_bridge(store, batch, "current-runner", "1234abcd")
                    stopped = store.cancel(batch["id"])
                    self.assertEqual(stopped["overallStatus"], "stopping")
                    self.assertEqual(stopped["stages"]["browser"]["status"], "stopping")
                    session = store.db.execute("SELECT status FROM bridge_sessions WHERE batch_id=?", (batch["id"],)).fetchone()
                    self.assertEqual(session["status"], "stopping")
                    telemetry = {
                        "protocol": "browser-bridge-v2", "bridgeVersion": "2.1.3", "scriptVersion": "2.1.6",
                        "collectorVersion": "0.4.6.4", "runnerVersion": "0.3.8.13",
                        "batchName": "current-runner", "queueHash": "1234abcd", "status": "running",
                        **bridge_attempt(store, batch["id"]),
                    }
                    response = store.heartbeat(batch["id"], batch["bridgeToken"], telemetry)
                    self.assertEqual(response["commands"], [])
                    pending = store.db.execute(
                        "SELECT status FROM commands WHERE batch_id=? AND action='stop_after_current'",
                        (batch["id"],),
                    ).fetchone()
                    self.assertEqual(pending["status"], "pending")
                    commands = store.poll_global_commands(server.BROWSER_PAIRING_TOKEN, "browser-bridge-v2", "2.1.3")
                    self.assertEqual([item["action"] for item in commands], ["stop_after_current"])
                    after = store.get(batch["id"])
                    self.assertEqual(after["overallStatus"], "stopping")
                    self.assertEqual(after["stages"]["browser"]["status"], "stopping")
                    other = store.create({"name": "Next Runner", "categories": "Beauty | 3760911"})
                    store.update(other["id"], lambda current: current.update({"runnerBatchName": "next-runner"}))
                    with self.assertRaisesRegex(ValueError, "正在停止批次"):
                        register_test_bridge(store, other, "next-runner", "deadbeef")
                    telemetry["status"] = "done"
                    store.heartbeat(batch["id"], batch["bridgeToken"], telemetry)
                    after = store.get(batch["id"])
                    self.assertEqual(after["overallStatus"], "cancelled")
                    self.assertEqual(after["stages"]["browser"]["status"], "cancelled")
                    completed_command = store.db.execute("SELECT status FROM commands WHERE id=?", (stopped["cancelCommandId"],)).fetchone()
                    self.assertEqual(completed_command["status"], "completed")
                    registered = register_test_bridge(store, other, "next-runner", "deadbeef")
                    self.assertTrue(registered["ok"])
                finally:
                    store.db.close()

    def test_bridge_reload_preserves_stopping_and_terminal_batch_rejects_reconnect(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Reload During Stop", "categories": "Beauty | 3760911"})
                    store.update(batch["id"], lambda current: (
                        current.update({"runnerBatchName": "current-runner", "overallStatus": "running"}),
                        current["stages"]["browser"].update({"status": "running", "stats": {"status": "running"}}),
                    ))
                    register_test_bridge(store, batch, "current-runner", "1234abcd")
                    attempt = bridge_attempt(store, batch["id"])
                    register_args = (
                        batch["id"], batch["bridgeToken"], "browser-bridge-v2", "2.1.3",
                        "0.4.6.4", "0.3.8.13", "current-runner", "1234abcd",
                        attempt["commandId"], attempt["executionMode"],
                    )
                    store.cancel(batch["id"])
                    store.acknowledge_global_command(
                        server.BROWSER_PAIRING_TOKEN,
                        batch["id"],
                        attempt["commandId"],
                        "accepted",
                        "late Start ACK",
                    )
                    cancelled_start = store.db.execute(
                        "SELECT status FROM commands WHERE id=?",
                        (attempt["commandId"],),
                    ).fetchone()
                    self.assertEqual(cancelled_start["status"], "cancelled")
                    reconnected = store.register_bridge(*register_args)
                    self.assertTrue(reconnected["ok"])
                    stopping = store.get(batch["id"])
                    self.assertEqual(stopping["overallStatus"], "stopping")
                    self.assertEqual(stopping["stages"]["browser"]["status"], "stopping")
                    self.assertEqual(stopping["stages"]["browser"]["connection"]["status"], "stopping")
                    session = store.db.execute("SELECT status FROM bridge_sessions WHERE batch_id=?", (batch["id"],)).fetchone()
                    self.assertEqual(session["status"], "stopping")
                    store.heartbeat(batch["id"], batch["bridgeToken"], {
                        "protocol": "browser-bridge-v2", "bridgeVersion": "2.1.3", "scriptVersion": "2.1.6",
                        "collectorVersion": "0.4.6.4", "runnerVersion": "0.3.8.13",
                        "batchName": "current-runner", "queueHash": "1234abcd", "status": "done",
                        **attempt,
                    })
                    with self.assertRaisesRegex(ValueError, "批次已结束"):
                        store.register_bridge(*register_args)
                finally:
                    store.db.close()

    def test_cancel_before_bridge_registration_cancels_start_without_waiting(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Cancel Pending Start", "categories": "Beauty | 3760911"})
                    store.update(batch["id"], lambda current: (
                        current.update({"runnerBatchName": "pending-runner", "overallStatus": "browser_waiting"}),
                        current["stages"]["browser"].update({"status": "waiting"}),
                    ))
                    start = store.enqueue_command(batch["id"], "start", {"batchName": "pending-runner"})
                    stopped = store.cancel(batch["id"])
                    self.assertEqual(stopped["overallStatus"], "cancelled")
                    self.assertNotIn("cancelCommandId", stopped)
                    row = store.db.execute("SELECT status FROM commands WHERE id=?", (start["id"],)).fetchone()
                    self.assertEqual(row["status"], "cancelled")
                    self.assertEqual(store.poll_global_commands(server.BROWSER_PAIRING_TOKEN, "browser-bridge-v2", "2.1.3"), [])
                    with self.assertRaisesRegex(ValueError, "批次已结束"):
                        store.register_bridge(
                            batch["id"], batch["bridgeToken"], "browser-bridge-v2", "2.1.3",
                            "0.4.6.4", "0.3.8.13", "pending-runner", "1234abcd",
                            start["id"], "generated_for_command",
                        )
                finally:
                    store.db.close()

    def test_delivered_stop_command_is_retried_after_delivery_lease(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Retry Lost Stop", "categories": "Beauty | 3760911"})
                    store.update(batch["id"], lambda current: (
                        current.update({"runnerBatchName": "current-runner", "overallStatus": "running"}),
                        current["stages"]["browser"].update({"status": "running", "stats": {"status": "running"}}),
                    ))
                    register_test_bridge(store, batch, "current-runner", "1234abcd")
                    stopped = store.cancel(batch["id"])
                    first = store.poll_global_commands(server.BROWSER_PAIRING_TOKEN, "browser-bridge-v2", "2.1.3")
                    self.assertEqual([item["id"] for item in first], [stopped["cancelCommandId"]])
                    with store.db:
                        store.db.execute("UPDATE commands SET delivered_at='2000-01-01T00:00:00+00:00' WHERE id=?", (stopped["cancelCommandId"],))
                    retried = store.poll_global_commands(server.BROWSER_PAIRING_TOKEN, "browser-bridge-v2", "2.1.3")
                    self.assertEqual([item["id"] for item in retried], [stopped["cancelCommandId"]])
                finally:
                    store.db.close()

    def test_stale_stopping_session_keeps_lease_and_allows_explicit_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Stale Stop Recovery", "categories": "Beauty | 3760911"})
                    store.update(batch["id"], lambda current: (
                        current.update({"runnerBatchName": "current-runner", "overallStatus": "running"}),
                        current["stages"]["browser"].update({"status": "running", "stats": {"status": "running"}}),
                    ))
                    register_test_bridge(store, batch, "current-runner", "1234abcd")
                    stopped = store.cancel(batch["id"])
                    command_id = stopped["cancelCommandId"]
                    with store.db:
                        store.db.execute("UPDATE bridge_sessions SET last_heartbeat='2000-01-01T00:00:00+00:00' WHERE batch_id=?", (batch["id"],))
                    recovered = store.get(batch["id"])
                    self.assertEqual(recovered["overallStatus"], "stopping")
                    self.assertEqual(recovered["stages"]["browser"]["status"], "stopping")
                    self.assertEqual(recovered["stages"]["browser"]["connection"]["status"], "disconnected")
                    self.assertEqual(recovered["cancelCommandId"], command_id)
                    session = store.db.execute("SELECT status FROM bridge_sessions WHERE batch_id=?", (batch["id"],)).fetchone()
                    self.assertEqual(session["status"], "stopping")
                    command = store.db.execute("SELECT status FROM commands WHERE id=?", (command_id,)).fetchone()
                    self.assertEqual(command["status"], "pending")
                    retried = store.cancel(batch["id"])
                    self.assertEqual(retried["overallStatus"], "stopping")
                    self.assertNotEqual(retried["cancelCommandId"], command_id)
                    session = store.db.execute("SELECT status FROM bridge_sessions WHERE batch_id=?", (batch["id"],)).fetchone()
                    self.assertEqual(session["status"], "stopping")
                finally:
                    store.db.close()

    def test_stop_with_stale_connected_heartbeat_keeps_intent_and_lease(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Stale Connected Stop", "categories": "Beauty | 3760911"})
                    store.update(batch["id"], lambda current: (
                        current.update({"runnerBatchName": "current-runner", "overallStatus": "running"}),
                        current["stages"]["browser"].update({"status": "running", "stats": {"status": "running"}}),
                    ))
                    register_test_bridge(store, batch, "current-runner", "1234abcd")
                    with store.db:
                        store.db.execute("UPDATE bridge_sessions SET last_heartbeat='2000-01-01T00:00:00+00:00' WHERE batch_id=?", (batch["id"],))
                    stopped = store.cancel(batch["id"])
                    self.assertEqual(stopped["overallStatus"], "stopping")
                    self.assertTrue(stopped.get("cancelCommandId"))
                    session = store.db.execute("SELECT status FROM bridge_sessions WHERE batch_id=?", (batch["id"],)).fetchone()
                    self.assertEqual(session["status"], "stopping")
                    command = store.db.execute("SELECT status FROM commands WHERE id=?", (stopped["cancelCommandId"],)).fetchone()
                    self.assertEqual(command["status"], "pending")
                finally:
                    store.db.close()

    def test_unacknowledged_stop_recovers_while_heartbeat_is_still_fresh(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Unacknowledged Stop", "categories": "Beauty | 3760911"})
                    store.update(batch["id"], lambda current: (
                        current.update({"runnerBatchName": "current-runner", "overallStatus": "running"}),
                        current["stages"]["browser"].update({"status": "running", "stats": {"status": "running"}}),
                    ))
                    register_test_bridge(store, batch, "current-runner", "1234abcd")
                    stopped = store.cancel(batch["id"])
                    first_command_id = stopped["cancelCommandId"]
                    store.poll_global_commands(server.BROWSER_PAIRING_TOKEN, "browser-bridge-v2", "2.1.3")
                    store.update(batch["id"], lambda current: current.update({"cancelRequestedAt": "2000-01-01T00:00:00+00:00"}))
                    recovered = store.get(batch["id"])
                    self.assertEqual(recovered["overallStatus"], "stopping")
                    self.assertEqual(recovered["stages"]["browser"]["connection"]["status"], "stopping")
                    self.assertNotEqual(recovered["cancelCommandId"], first_command_id)
                    replacement_id = recovered["cancelCommandId"]
                    self.assertEqual(recovered["cancelRetryCount"], 1)
                    session = store.db.execute("SELECT status FROM bridge_sessions WHERE batch_id=?", (batch["id"],)).fetchone()
                    self.assertEqual(session["status"], "stopping")
                    command = store.db.execute("SELECT status FROM commands WHERE id=?", (first_command_id,)).fetchone()
                    self.assertEqual(command["status"], "failed")
                    delivered = store.poll_global_commands(server.BROWSER_PAIRING_TOKEN, "browser-bridge-v2", "2.1.3")
                    self.assertEqual([item["id"] for item in delivered], [replacement_id])
                    retried = store.cancel(batch["id"])
                    self.assertEqual(retried["overallStatus"], "stopping")
                    self.assertNotEqual(retried["cancelCommandId"], replacement_id)
                finally:
                    store.db.close()

    def test_concurrent_cancel_wins_over_an_inflight_heartbeat(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                release_heartbeat = threading.Event()
                try:
                    batch = store.create({"name": "Concurrent Stop", "categories": "Beauty | 3760911"})
                    store.update(batch["id"], lambda current: (
                        current.update({"runnerBatchName": "current-runner", "overallStatus": "running"}),
                        current["stages"]["browser"].update({"status": "running", "stats": {"status": "running"}}),
                    ))
                    register_test_bridge(store, batch, "current-runner", "1234abcd")
                    telemetry = {
                        "protocol": "browser-bridge-v2", "bridgeVersion": "2.1.3", "scriptVersion": "2.1.6",
                        "collectorVersion": "0.4.6.4", "runnerVersion": "0.3.8.13",
                        "batchName": "current-runner", "queueHash": "1234abcd", "status": "running",
                        **bridge_attempt(store, batch["id"]),
                    }
                    heartbeat_at_update = threading.Event()
                    heartbeat_errors = []
                    original_update = store.update

                    def delayed_update(batch_id, callback):
                        if threading.current_thread().name == "inflight-heartbeat":
                            heartbeat_at_update.set()
                            if not release_heartbeat.wait(2):
                                raise TimeoutError("heartbeat test release timed out")
                        return original_update(batch_id, callback)

                    def run_heartbeat() -> None:
                        try:
                            store.heartbeat(batch["id"], batch["bridgeToken"], telemetry)
                        except Exception as exc:  # noqa: BLE001
                            heartbeat_errors.append(exc)

                    with mock.patch.object(store, "update", side_effect=delayed_update):
                        thread = threading.Thread(target=run_heartbeat, name="inflight-heartbeat")
                        thread.start()
                        self.assertTrue(heartbeat_at_update.wait(2))
                        store.cancel(batch["id"])
                        release_heartbeat.set()
                        thread.join(2)

                    self.assertFalse(thread.is_alive())
                    self.assertEqual(heartbeat_errors, [])
                    after = store.get(batch["id"])
                    self.assertEqual(after["overallStatus"], "stopping")
                    self.assertEqual(after["stages"]["browser"]["status"], "stopping")
                    session = store.db.execute("SELECT status FROM bridge_sessions WHERE batch_id=?", (batch["id"],)).fetchone()
                    self.assertEqual(session["status"], "stopping")
                    telemetry["status"] = "done"
                    store.heartbeat(batch["id"], batch["bridgeToken"], telemetry)
                    after = store.get(batch["id"])
                    self.assertEqual(after["overallStatus"], "cancelled")
                    self.assertEqual(after["stages"]["browser"]["status"], "cancelled")
                finally:
                    release_heartbeat.set()
                    store.db.close()

    def test_stop_on_fully_completed_batch_restores_completed_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Already Done", "categories": "Beauty | 3760911"})
                    store.update(batch["id"], lambda current: (
                        [stage.update({"status": "completed"}) for stage in current["stages"].values()],
                        current.update({"overallStatus": "excel_ready"}),
                    ))
                    stopped = store.cancel(batch["id"])
                    self.assertEqual(stopped["overallStatus"], "completed")
                    pending = store.db.execute("SELECT COUNT(*) AS count FROM commands WHERE batch_id=?", (batch["id"],)).fetchone()["count"]
                    self.assertEqual(pending, 0)
                finally:
                    store.db.close()

    def test_failed_stop_command_preserves_intent_and_retries_with_new_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Stop Retry", "categories": "Beauty | 3760911"})
                    store.update(batch["id"], lambda current: (
                        current.update({"runnerBatchName": "current-runner", "overallStatus": "running"}),
                        current["stages"]["browser"].update({"status": "running", "stats": {"status": "running"}}),
                    ))
                    register_test_bridge(store, batch, "current-runner", "1234abcd")
                    stopped = store.cancel(batch["id"])
                    command_id = stopped["cancelCommandId"]
                    store.acknowledge_global_command(server.BROWSER_PAIRING_TOKEN, batch["id"], command_id, "failed", "Runner 控件不可用")
                    after = store.get(batch["id"])
                    self.assertEqual(after["overallStatus"], "stopping")
                    self.assertEqual(after["stages"]["browser"]["status"], "stopping")
                    self.assertNotEqual(after["cancelCommandId"], command_id)
                    second_command_id = after["cancelCommandId"]
                    self.assertEqual(after["cancelRetryCount"], 1)
                    session = store.db.execute("SELECT status FROM bridge_sessions WHERE batch_id=?", (batch["id"],)).fetchone()
                    self.assertEqual(session["status"], "stopping")
                    store.acknowledge_global_command(server.BROWSER_PAIRING_TOKEN, batch["id"], command_id, "failed", "迟到的旧回执")
                    after_late_ack = store.get(batch["id"])
                    self.assertEqual(after_late_ack["overallStatus"], "stopping")
                    self.assertEqual(after_late_ack["cancelCommandId"], second_command_id)
                    session = store.db.execute("SELECT status FROM bridge_sessions WHERE batch_id=?", (batch["id"],)).fetchone()
                    self.assertEqual(session["status"], "stopping")

                    store.acknowledge_global_command(server.BROWSER_PAIRING_TOKEN, batch["id"], second_command_id, "failed", "Runner 控件仍不可用")
                    after_second_failure = store.get(batch["id"])
                    third_command_id = after_second_failure["cancelCommandId"]
                    self.assertEqual(after_second_failure["overallStatus"], "stopping")
                    self.assertNotEqual(third_command_id, second_command_id)
                    self.assertEqual(after_second_failure["cancelRetryCount"], server.MAX_AUTOMATIC_STOP_RETRIES)

                    store.acknowledge_global_command(server.BROWSER_PAIRING_TOKEN, batch["id"], third_command_id, "failed", "Runner 控件连续失败")
                    exhausted = store.get(batch["id"])
                    self.assertEqual(exhausted["overallStatus"], "stopping")
                    self.assertEqual(exhausted["cancelCommandId"], third_command_id)
                    self.assertEqual(exhausted["cancelRetryCount"], server.MAX_AUTOMATIC_STOP_RETRIES)
                    session = store.db.execute("SELECT status FROM bridge_sessions WHERE batch_id=?", (batch["id"],)).fetchone()
                    self.assertEqual(session["status"], "stopping")
                    failed_command = store.db.execute("SELECT status FROM commands WHERE id=?", (third_command_id,)).fetchone()
                    self.assertEqual(failed_command["status"], "failed")

                    manual_retry = store.cancel(batch["id"])
                    self.assertEqual(manual_retry["overallStatus"], "stopping")
                    self.assertNotEqual(manual_retry["cancelCommandId"], third_command_id)
                finally:
                    store.db.close()

    def test_stopped_runner_json_is_audit_only_and_releases_bridge_lease(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Stopped JSON", "categories": "Beauty | 3760911"})
                    store.update(batch["id"], lambda current: (
                        current.update({"runnerBatchName": "current-runner", "overallStatus": "running"}),
                        current["stages"]["browser"].update({"status": "running", "stats": {"status": "running"}}),
                    ))
                    register_test_bridge(store, batch, "current-runner", "1234abcd")
                    store.cancel(batch["id"])
                    merged = {
                        "batchName": "current-runner", "queueHash": "1234abcd", "status": "done",
                        "runnerVersion": "0.3.8.13", "collectorVersion": "0.4.6.4", "results": [],
                    }
                    with mock.patch.object(server, "STORE", store):
                        result = server.store_merged_json(batch["id"], merged, "browser")
                    updated = result["batch"]
                    self.assertEqual(updated["overallStatus"], "cancelled")
                    self.assertEqual(updated["stages"]["browser"]["status"], "cancelled")
                    self.assertIn("cancelledSourceSha256", updated["jsonHandoff"])
                    self.assertFalse(updated["jsonHandoff"].get("sourceSha256"))
                    self.assertFalse(updated["jsonHandoff"].get("pasteVerified", False))
                    session = store.db.execute("SELECT status FROM bridge_sessions WHERE batch_id=?", (batch["id"],)).fetchone()
                    self.assertEqual(session["status"], "cancelled")
                finally:
                    store.db.close()

    def test_cancel_during_runner_json_normalization_writes_only_audit_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                release_normalize = threading.Event()
                normalize_ready = threading.Event()
                errors = []
                result = {}
                try:
                    batch = store.create({"name": "Cancel During JSON", "categories": "Beauty | 3760911"})
                    store.update(batch["id"], lambda current: (
                        current.update({"runnerBatchName": "current-runner", "overallStatus": "running"}),
                        current["stages"]["browser"].update({"status": "running", "stats": {"status": "running"}}),
                    ))
                    register_test_bridge(store, batch, "current-runner", "1234abcd")
                    merged = {
                        "batchName": "current-runner", "queueHash": "1234abcd", "status": "done",
                        "runnerVersion": "0.3.8.13", "collectorVersion": "0.4.6.4", "results": [],
                    }
                    original_normalize = server.normalize_merged_payload

                    def delayed_normalize(value):
                        normalized = original_normalize(value)
                        normalize_ready.set()
                        if not release_normalize.wait(2):
                            raise TimeoutError("normalization release timed out")
                        return normalized

                    def upload() -> None:
                        try:
                            result.update(server.store_merged_json(batch["id"], merged, "browser"))
                        except Exception as exc:  # noqa: BLE001
                            errors.append(exc)

                    with mock.patch.object(server, "STORE", store), mock.patch.object(server, "normalize_merged_payload", side_effect=delayed_normalize):
                        thread = threading.Thread(target=upload)
                        thread.start()
                        self.assertTrue(normalize_ready.wait(2))
                        store.cancel(batch["id"])
                        release_normalize.set()
                        thread.join(2)
                    self.assertFalse(thread.is_alive())
                    self.assertEqual(errors, [])
                    self.assertEqual(result["batch"]["overallStatus"], "cancelled")
                    audit_path = Path(result["artifact"]["mergedJson"])
                    self.assertIn("merged_cancelled_audit_", audit_path.name)
                    self.assertFalse((Path(batch["runDir"]) / "browser" / "merged_source.json").exists())
                finally:
                    release_normalize.set()
                    store.db.close()

    def test_api_product_normalization_uses_actual_review_and_fulfillment_fields(self) -> None:
        row = sellersprite_pipeline.normalize_product(
            {
                "asin": "B000000001",
                "reviews": 42,
                "ratings": 999,
                "sellerType": "FBA",
                "imageUrl": "https://example.com/main.jpg",
            },
            {"nodeLabelPath": "Home & Kitchen:Storage", "nodeIdPath": "1055398:3610841", "input": "Storage"},
            "https://www.sellersprite.com/v3/product-research?market=US",
        )
        self.assertEqual(row["reviews"], 42)
        self.assertEqual(row["fulfillment"], "FBA")
        self.assertEqual(row["image"], "https://example.com/main.jpg")

    def test_analysis_workbook_serializes_rejection_reason_lists(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "analysis.xlsx"
            sellersprite_pipeline.make_analysis_workbook(
                [{
                    "asin": "B000000001",
                    "categoryPath": "Home & Kitchen",
                    "brand": "Example",
                    "title": "Example product",
                    "price": 10,
                    "rating": 4.5,
                    "reviews": 10,
                    "childSales": 50,
                    "parentSales": 50,
                    "launchDate": "2026-08-01",
                    "variations": 1,
                    "amazonUrl": "https://www.amazon.com/dp/B000000001",
                    "sellerSpriteUrl": "https://www.sellersprite.com/v3/product-research?market=US",
                }],
                [{"asin": "B000000002", "title": "Rejected", "reasons": ["invalid_childSales"]}],
                Path(temp) / "images",
                output,
            )
            from openpyxl import load_workbook

            workbook = load_workbook(output, read_only=True, data_only=True)
            try:
                self.assertEqual(workbook["筛除审计"]["C2"].value, "invalid_childSales")
            finally:
                workbook.close()

    def test_running_stage_clears_stale_process_failure_artifacts(self) -> None:
        batch = {
            "stages": {
                "candidates": {
                    "status": "needs_attention",
                    "message": "previous",
                    "completedAt": "2026-08-15T00:00:00+00:00",
                    "artifacts": {"exitCode": 1, "stdout": "old.out", "stderr": "old.err", "queueCount": 4},
                },
                "browser": {"status": "waiting", "artifacts": {}},
                "excel": {"status": "idle", "artifacts": {}},
            },
            "overallStatus": "needs_attention",
        }
        server.set_stage(batch, "candidates", "running", "retrying", {"stdout": "new.out", "stderr": "new.err"})
        artifacts = batch["stages"]["candidates"]["artifacts"]
        self.assertNotIn("exitCode", artifacts)
        self.assertEqual(artifacts["stdout"], "new.out")
        self.assertEqual(artifacts["queueCount"], 4)
        self.assertNotIn("completedAt", batch["stages"]["candidates"])

    def test_store_creates_single_category_batch_without_legacy_export(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                batch = store.create({"name": "API Pool", "categories": "Beauty | 3760911"})
                self.assertEqual(len(batch["categoryPool"]), 1)
                self.assertEqual(batch["sourceXlsx"], "")
                self.assertEqual(batch["bridgeProtocol"], "browser-bridge-v2")
                self.assertEqual(batch["queryFilters"]["maxReviews"], 100)
                self.assertEqual(batch["candidateSourceMode"], "browser_export")
                self.assertEqual(batch["categoryPool"][0]["nodeIdPath"], "3760911")
                with self.assertRaisesRegex(ValueError, "每个批次只能运行一个类目"):
                    store.create({"name": "Too Many", "categories": "Home Storage\nBeauty | 3760911"})
                store.db.close()

    def test_global_category_pool_deduplicates_claims_and_completes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    imported = store.import_category_pool("Home Storage\nhome storage\nBeauty | 3760911")
                    self.assertEqual(imported["addedCount"], 2)
                    self.assertEqual(imported["duplicateCount"], 1)
                    item = next(row for row in imported["items"] if row["label"] == "Home Storage")
                    batch = store.create({
                        "name": "Pool Claim",
                        "categoryPoolItemId": item["id"],
                        "categories": "Injected One\nInjected Two",
                    })
                    self.assertEqual(batch["categories"], "Home Storage")
                    self.assertEqual(len(batch["categoryPool"]), 1)
                    assigned = next(row for row in store.list_category_pool() if row["id"] == item["id"])
                    self.assertEqual(assigned["status"], "assigned")
                    self.assertEqual(assigned["batchId"], batch["id"])
                    with self.assertRaisesRegex(ValueError, "已被其他批次领取"):
                        store.create({"name": "Duplicate Claim", "categoryPoolItemId": item["id"]})
                    complete_test_batch(store, batch["id"])
                    completed = next(row for row in store.list_category_pool() if row["id"] == item["id"])
                    self.assertEqual(completed["status"], "completed")
                finally:
                    store.db.close()

    def test_category_repository_migrates_and_backfills_completed_batches_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                with mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", False):
                    legacy_store = server.SQLiteWorkflowStore()
                    batch = legacy_store.create({"name": "Legacy Complete", "categories": "Legacy Category | 100:200"})
                    complete_test_batch(legacy_store, batch["id"])
                    self.assertEqual(legacy_store.db.execute("SELECT COUNT(*) FROM screened_category_completions").fetchone()[0], 0)
                    legacy_store.db.close()

                with mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", True):
                    first = server.SQLiteWorkflowStore()
                    tables = {row["name"] for row in first.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    self.assertTrue({"batch_archive_state", "screened_categories", "screened_category_completions", "feature_audit_events"}.issubset(tables))
                    completion = first.db.execute(
                        "SELECT marketplace,node_id_path,batch_id,registration_source FROM screened_category_completions"
                    ).fetchone()
                    self.assertEqual(dict(completion), {
                        "marketplace": "Amazon US",
                        "node_id_path": "100:200",
                        "batch_id": batch["id"],
                        "registration_source": "startup_backfill",
                    })
                    self.assertEqual(first.category_repository_overview()["items"][0]["scope"], "console_completed_runner_unaccepted")
                    first.db.close()

                    second = server.SQLiteWorkflowStore()
                    self.assertEqual(second.db.execute("SELECT COUNT(*) FROM screened_categories").fetchone()[0], 1)
                    self.assertEqual(second.db.execute("SELECT COUNT(*) FROM screened_category_completions").fetchone()[0], 1)
                    audit_count = second.db.execute(
                        "SELECT COUNT(*) FROM feature_audit_events WHERE action='screened_category_backfilled'"
                    ).fetchone()[0]
                    self.assertEqual(audit_count, 1)
                    second.db.close()

    def test_completed_batch_archive_preserves_payload_artifacts_and_history_then_restores(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", True),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    incomplete = store.create({"name": "Not Complete", "categories": "Pending | 900"})
                    self.assertTrue(store.get(incomplete["id"])["archiveEligible"])
                    archived_incomplete = store.archive_completed_batch(incomplete["id"])
                    self.assertTrue(archived_incomplete["archived"])
                    store.restore_batch(incomplete["id"])

                    batch = store.create({"name": "Archive Me", "categories": "Archive Category | 901"})
                    evidence = root / "formal" / "runs" / "archive-evidence.json"
                    evidence.parent.mkdir(parents=True)
                    evidence.write_text('{"preserve":true}\n', encoding="utf-8")
                    evidence_digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
                    with store.db:
                        store.db.execute(
                            "INSERT INTO artifacts(batch_id,artifact_key,path,sha256,kind,created_at) VALUES(?,?,?,?,?,?)",
                            (batch["id"], "evidence", str(evidence), evidence_digest, "test", server.now_iso()),
                        )
                    complete_test_batch(store, batch["id"])
                    payload_before = store.db.execute("SELECT payload FROM runs WHERE id=?", (batch["id"],)).fetchone()["payload"]
                    updated_before = json.loads(payload_before)["updatedAt"]

                    store.jobs[batch["id"]] = mock.Mock()
                    with self.assertRaisesRegex(ValueError, "仍有任务运行"):
                        store.archive_completed_batch(batch["id"])
                    store.jobs.pop(batch["id"])

                    archived = store.archive_completed_batch(batch["id"])
                    archived_again = store.archive_completed_batch(batch["id"])
                    self.assertTrue(archived["archived"])
                    self.assertEqual(archived_again["archivedAt"], archived["archivedAt"])
                    self.assertNotIn(batch["id"], {item["id"] for item in store.list()})
                    self.assertIn(batch["id"], {item["id"] for item in store.list_archived()})
                    self.assertEqual(store.db.execute("SELECT payload FROM runs WHERE id=?", (batch["id"],)).fetchone()["payload"], payload_before)
                    self.assertEqual(store.get(batch["id"])["updatedAt"], updated_before)
                    self.assertEqual(hashlib.sha256(evidence.read_bytes()).hexdigest(), evidence_digest)
                    self.assertEqual(store.db.execute("SELECT COUNT(*) FROM artifacts WHERE batch_id=?", (batch["id"],)).fetchone()[0], 1)
                    self.assertEqual(store.db.execute("SELECT COUNT(*) FROM screened_category_completions WHERE batch_id=?", (batch["id"],)).fetchone()[0], 1)
                    self.assertEqual(store.db.execute("SELECT COUNT(*) FROM feature_audit_events WHERE action='batch_archived' AND subject_id=?", (batch["id"],)).fetchone()[0], 1)

                    with self.assertRaises(sqlite3.IntegrityError):
                        with store.db:
                            store.db.execute("DELETE FROM runs WHERE id=?", (batch["id"],))
                    self.assertIsNotNone(store.db.execute("SELECT id FROM runs WHERE id=?", (batch["id"],)).fetchone())

                    restored = store.restore_batch(batch["id"])
                    restored_again = store.restore_batch(batch["id"])
                    self.assertFalse(restored["archived"])
                    self.assertFalse(restored_again["archived"])
                    self.assertIn(batch["id"], {item["id"] for item in store.list()})
                    self.assertEqual(store.db.execute("SELECT payload FROM runs WHERE id=?", (batch["id"],)).fetchone()["payload"], payload_before)
                    self.assertEqual(store.db.execute("SELECT COUNT(*) FROM feature_audit_events WHERE action='batch_restored' AND subject_id=?", (batch["id"],)).fetchone()[0], 1)

                    store.archive_completed_batch(batch["id"])
                    with mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", False):
                        self.assertIn(batch["id"], {item["id"] for item in store.list()})
                        with self.assertRaisesRegex(ValueError, "未启用"):
                            store.restore_batch(batch["id"])
                finally:
                    store.db.close()

    def test_repository_rejects_inconsistent_completion_while_recoverable_delete_allows_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", True),
            ):
                store = server.SQLiteWorkflowStore()
                batch = store.create({"name": "Inconsistent Complete", "categories": "Not Actually Done | 902"})
                store.update(batch["id"], lambda current: current.__setitem__("overallStatus", "completed"))
                self.assertFalse(server.verified_completed_workflow(store.get(batch["id"])))
                self.assertEqual(
                    store.db.execute(
                        "SELECT COUNT(*) FROM screened_category_completions WHERE batch_id=?",
                        (batch["id"],),
                    ).fetchone()[0],
                    0,
                )
                archived = store.archive_completed_batch(batch["id"])
                self.assertTrue(archived["archived"])
                store.db.close()

                reopened = server.SQLiteWorkflowStore()
                try:
                    self.assertEqual(
                        reopened.db.execute(
                            "SELECT COUNT(*) FROM screened_category_completions WHERE batch_id=?",
                            (batch["id"],),
                        ).fetchone()[0],
                        0,
                    )
                finally:
                    reopened.db.close()

    def test_archive_blocks_live_orphaned_local_process_until_confirmed_dead(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", True),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Live Orphan Archive Guard", "categories": "Orphan Archive | 906"})
                    complete_test_batch(store, batch["id"])
                    with store.db:
                        store.db.execute(
                            """INSERT INTO local_job_leases(
                                   id,batch_id,stage,attempt,pid,argv_sha256,executable,run_dir,
                                   stdout_path,stderr_path,owner_instance_id,status,started_at,last_seen_at,
                                   recovery_reason
                               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (
                                "orphan-archive", batch["id"], "candidates", 1, os.getpid(),
                                "command-hash", "python.exe", str(root / "formal"), "out.log", "err.log",
                                "previous-instance", "orphaned", server.now_iso(), server.now_iso(),
                                "service_restart_process_alive",
                            ),
                        )

                    with mock.patch.object(server, "local_pid_alive", return_value=True):
                        blocked = store.get(batch["id"])
                        self.assertFalse(blocked["archiveEligible"])
                        self.assertIn("遗留本地进程", blocked["archiveBlockedReason"])
                        with self.assertRaisesRegex(ValueError, "未执行任何删除"):
                            store.archive_completed_batch(batch["id"])
                        self.assertFalse(store.get(batch["id"])["archived"])

                    with mock.patch.object(server, "local_pid_alive", return_value=False):
                        unblocked = store.get(batch["id"])
                        self.assertTrue(unblocked["archiveEligible"])
                        archived = store.archive_completed_batch(batch["id"])
                        self.assertTrue(archived["archived"])
                        lease = store.db.execute(
                            "SELECT status,recovery_reason FROM local_job_leases WHERE id='orphan-archive'"
                        ).fetchone()
                        self.assertEqual(dict(lease), {
                            "status": "interrupted",
                            "recovery_reason": "orphan_process_missing_before_archive",
                        })
                finally:
                    store.db.close()

    def test_archive_request_cancels_running_runner_idempotently_then_archives(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", True),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Graceful Runner Delete", "categories": "Graceful | 930"})
                    store.update(batch["id"], lambda current: (
                        current.update({"runnerBatchName": "graceful-runner", "overallStatus": "running"}),
                        current["stages"]["browser"].update({"status": "running", "stats": {"status": "running"}}),
                    ))
                    register_test_bridge(store, batch, "graceful-runner", "9300abcd")

                    first = store.request_archive_batches([batch["id"]], idempotency_key="graceful-key")
                    self.assertEqual(first["schemaVersion"], "batchArchiveRequest/v1")
                    self.assertEqual(first["pendingCount"], 1)
                    request_id = first["requests"][0]["requestId"]
                    self.assertEqual(first["requests"][0]["status"], "cancelling")
                    self.assertEqual(store.get(batch["id"])["overallStatus"], "stopping")

                    duplicate = store.request_archive_batches([batch["id"]], idempotency_key="graceful-key")
                    self.assertEqual(duplicate["requests"][0]["requestId"], request_id)
                    self.assertEqual(
                        store.db.execute(
                            "SELECT COUNT(*) FROM commands WHERE batch_id=? AND action='stop_after_current'",
                            (batch["id"],),
                        ).fetchone()[0],
                        1,
                    )

                    session = store.db.execute(
                        "SELECT command_id,execution_mode FROM bridge_sessions WHERE batch_id=?",
                        (batch["id"],),
                    ).fetchone()
                    store.register_bridge(
                        batch["id"], batch["bridgeToken"], "browser-bridge-v2", "2.1.3",
                        "0.4.6.4", "0.3.8.13", "graceful-runner", "9300abcd",
                        session["command_id"], session["execution_mode"],
                    )
                    heartbeat = {
                        "protocol": "browser-bridge-v2",
                        "bridgeVersion": "2.1.3",
                        "scriptVersion": "2.1.6",
                        "collectorVersion": "0.4.6.4",
                        "runnerVersion": "0.3.8.13",
                        "batchName": "graceful-runner",
                        "queueHash": "9300abcd",
                        "status": "done",
                        **bridge_attempt(store, batch["id"]),
                    }
                    store.heartbeat(batch["id"], batch["bridgeToken"], heartbeat)
                    store.reconcile_archive_requests()
                    archived = store.get(batch["id"])
                    self.assertTrue(archived["archived"])
                    self.assertEqual(archived["overallStatus"], "cancelled")
                    self.assertEqual(archived["archiveRequest"]["requestId"], request_id)
                    self.assertEqual(archived["archiveRequest"]["status"], "archived")
                finally:
                    store.db.close()

    def test_archive_request_survives_restart_and_is_reconciled_on_first_list(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            patches = (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", True),
            )
            with ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                store = server.SQLiteWorkflowStore()
                batch = store.create({"name": "Restart Archive Request", "categories": "Restart | 931"})
                store.update(batch["id"], lambda current: (
                    current.update({"runnerBatchName": "restart-runner", "overallStatus": "running"}),
                    current["stages"]["browser"].update({"status": "running", "stats": {"status": "running"}}),
                ))
                register_test_bridge(store, batch, "restart-runner", "9310abcd")
                result = store.request_archive_batches([batch["id"]], idempotency_key="restart-key")
                self.assertEqual(result["pendingCount"], 1)
                store.db.close()

            with ExitStack() as stack:
                for patcher in patches:
                    stack.enter_context(patcher)
                restarted = server.SQLiteWorkflowStore()
                try:
                    pending = restarted.list_all()[0]
                    self.assertFalse(pending["archived"])
                    self.assertEqual(pending["archiveRequest"]["status"], "cancelling")
                    heartbeat = {
                        "protocol": "browser-bridge-v2",
                        "bridgeVersion": "2.1.3",
                        "scriptVersion": "2.1.6",
                        "collectorVersion": "0.4.6.4",
                        "runnerVersion": "0.3.8.13",
                        "batchName": "restart-runner",
                        "queueHash": "9310abcd",
                        "status": "done",
                        **bridge_attempt(restarted, batch["id"]),
                    }
                    restarted.heartbeat(batch["id"], pending["bridgeToken"], heartbeat)
                    restarted.reconcile_archive_requests()
                    self.assertTrue(restarted.get(batch["id"])["archived"])
                    row = restarted.db.execute(
                        "SELECT status FROM batch_archive_requests WHERE batch_id=?", (batch["id"],)
                    ).fetchone()
                    self.assertEqual(row["status"], "archived")
                finally:
                    restarted.db.close()

    def test_archive_request_retry_after_timeout_starts_a_fresh_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", True),
                mock.patch.object(server, "ARCHIVE_REQUEST_TIMEOUT_SECONDS", 30),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Retry Graceful Delete", "categories": "Retry | 933"})
                    store.update(batch["id"], lambda current: (
                        current.update({"runnerBatchName": "retry-runner", "overallStatus": "running"}),
                        current["stages"]["browser"].update({"status": "running", "stats": {"status": "running"}}),
                    ))
                    register_test_bridge(store, batch, "retry-runner", "9330abcd")
                    first = store.request_archive_batches([batch["id"]], idempotency_key="retry-old-key")
                    request_id = first["requests"][0]["requestId"]
                    with store.db:
                        store.db.execute(
                            "UPDATE batch_archive_requests SET requested_at=? WHERE request_id=?",
                            ("2000-01-01T00:00:00Z", request_id),
                        )
                    store.reconcile_archive_requests()
                    failed = store.get(batch["id"])["archiveRequest"]
                    self.assertEqual(failed["status"], "failed")
                    old_requested_at = failed["requestedAt"]

                    retry = store.request_archive_batches([batch["id"]], idempotency_key="retry-new-key")
                    retried = retry["requests"][0]
                    self.assertEqual(retried["requestId"], request_id)
                    self.assertIn(retried["status"], {"cancelling", "waiting"})
                    self.assertNotEqual(retried["requestedAt"], old_requested_at)
                    self.assertGreater(retried["attempt"], failed["attempt"])
                finally:
                    store.db.close()

    def test_archive_request_rejects_missing_batch_without_partial_cancellation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", True),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Atomic Missing Delete", "categories": "Atomic | 934"})
                    with self.assertRaises(KeyError):
                        store.request_archive_batches([batch["id"], "aaaaaaaaaaaa"], idempotency_key="atomic-key")
                    snapshot = store.get(batch["id"])
                    self.assertEqual(snapshot["overallStatus"], "created")
                    self.assertIsNone(snapshot["archiveRequest"])
                    self.assertEqual(
                        store.db.execute(
                            "SELECT COUNT(*) FROM batch_archive_requests WHERE batch_id=?", (batch["id"],)
                        ).fetchone()[0],
                        0,
                    )
                finally:
                    store.db.close()

    def test_archive_request_can_stop_a_console_owned_local_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", True),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Owned Local Delete", "categories": "Owned | 935"})
                    started_at = server.now_iso()
                    store.update(
                        batch["id"],
                        lambda current: current["stages"]["candidates"]["artifacts"].update({"localJobId": "owned-local-job"}),
                    )
                    with store.lock:
                        store._insert_local_job_locked(
                            "owned-local-job", batch["id"], "candidates", 1, "argv-hash", "python.exe",
                            str(root / "formal"), str(root / "stdout.log"), str(root / "stderr.log"), started_at,
                        )
                        fake_process = mock.Mock()
                        fake_process.poll.return_value = None
                        store.jobs[batch["id"]] = fake_process
                    eligible = store.get(batch["id"])
                    self.assertFalse(eligible["archiveEligible"])
                    self.assertTrue(eligible["archiveRequestEligible"])

                    result = store.request_archive_batches([batch["id"]], idempotency_key="owned-local-key")
                    self.assertEqual(result["pendingCount"], 1)
                    fake_process.terminate.assert_called_once_with()
                    self.assertEqual(
                        store.db.execute(
                            "SELECT status FROM local_job_leases WHERE id='owned-local-job'"
                        ).fetchone()["status"],
                        "interrupted",
                    )

                    with store.lock:
                        store.jobs.pop(batch["id"], None)
                        store.cancel_flags.discard(batch["id"])
                    store.reconcile_archive_requests()
                    self.assertTrue(store.get(batch["id"])["archived"])
                finally:
                    store.db.close()

    def test_unfinished_archive_retains_pool_ownership_and_hides_item_until_restore(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", True),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    imported = store.import_category_pool("Reusable Category | 903")
                    item = next(row for row in imported["items"] if row["nodeIdPath"] == "903")
                    batch = store.create({"name": "Unfinished Pool Batch", "categoryPoolItemId": item["id"]})
                    assigned = store.db.execute(
                        "SELECT status,batch_id FROM category_pool_items WHERE id=?", (item["id"],)
                    ).fetchone()
                    self.assertEqual(dict(assigned), {"status": "assigned", "batch_id": batch["id"]})

                    archived = store.archive_completed_batch(batch["id"])
                    retained = store.db.execute(
                        "SELECT status,batch_id FROM category_pool_items WHERE id=?", (item["id"],)
                    ).fetchone()
                    self.assertTrue(archived["archived"])
                    self.assertEqual(dict(retained), {"status": "assigned", "batch_id": batch["id"]})
                    self.assertNotIn(item["id"], {row["id"] for row in store.list_category_pool()})
                    self.assertEqual(store.category_pool_overview()["counts"]["total"], 0)

                    with self.assertRaisesRegex(ValueError, "已被其他批次领取"):
                        store.create({"name": "Replacement Batch", "categoryPoolItemId": item["id"]})

                    audit = json.loads(store.db.execute(
                        """SELECT details FROM feature_audit_events
                           WHERE action='batch_archived' AND subject_id=?""",
                        (batch["id"],),
                    ).fetchone()["details"])
                    self.assertEqual(audit["retainedCategoryPoolItemId"], item["id"])

                    with mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", False):
                        rollback_batch = store.get(batch["id"])
                        rollback_item = next(row for row in store.list_category_pool() if row["id"] == item["id"])
                        self.assertFalse(rollback_batch["archived"])
                        self.assertEqual(rollback_item["status"], "assigned")
                        self.assertEqual(rollback_item["batchId"], batch["id"])

                    restored = store.restore_batch(batch["id"])
                    self.assertFalse(restored["archived"])
                    rebound = store.db.execute(
                        "SELECT status,batch_id FROM category_pool_items WHERE id=?", (item["id"],)
                    ).fetchone()
                    self.assertEqual(dict(rebound), {"status": "assigned", "batch_id": batch["id"]})
                    visible = next(row for row in store.list_category_pool() if row["id"] == item["id"])
                    self.assertEqual(visible["batchId"], batch["id"])
                finally:
                    store.db.close()

    def test_archive_blocks_active_work_and_bulk_archive_is_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", True),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    safe = store.create({"name": "Safe Unfinished", "categories": "Safe | 904"})
                    active = store.create({"name": "Active Command", "categories": "Active | 905"})
                    command = store.enqueue_command(active["id"], "start", {"batchName": "active"})
                    active_snapshot = store.get(active["id"])
                    self.assertFalse(active_snapshot["archiveEligible"])
                    self.assertIn("活跃浏览器命令", active_snapshot["archiveBlockedReason"])

                    with self.assertRaisesRegex(ValueError, "未执行任何删除"):
                        store.archive_batches([safe["id"], active["id"]])
                    self.assertFalse(store.get(safe["id"])["archived"])
                    self.assertFalse(store.get(active["id"])["archived"])
                    self.assertEqual(store.db.execute("SELECT COUNT(*) FROM batch_archive_state").fetchone()[0], 0)

                    with store.db:
                        store.db.execute("UPDATE commands SET status='failed' WHERE id=?", (command["id"],))
                    store.jobs[active["id"]] = mock.Mock()
                    self.assertIn("任务运行", store.get(active["id"])["archiveBlockedReason"])
                    store.jobs.pop(active["id"])
                    with store.db:
                        store.db.execute(
                            "INSERT INTO bridge_sessions(batch_id,token_hash,status) VALUES(?,?,?)",
                            (active["id"], "test-token", "connected"),
                        )
                    self.assertIn("Browser Bridge", store.get(active["id"])["archiveBlockedReason"])
                    with store.db:
                        store.db.execute("DELETE FROM bridge_sessions WHERE batch_id=?", (active["id"],))
                        now = server.now_iso()
                        store.db.execute(
                            """INSERT INTO thread_dispatches(
                                   id,batch_id,thread_id,stage,prompt,note,status,created_at,updated_at
                               ) VALUES(?,?,?,?,?,?,?,?,?)""",
                            ("d" * 32, active["id"], "thread-test", "browser", "test", "", "prepared", now, now),
                        )
                    self.assertIn("外部任务派发", store.get(active["id"])["archiveBlockedReason"])
                    with store.db:
                        store.db.execute("UPDATE thread_dispatches SET status='acknowledged' WHERE batch_id=?", (active["id"],))
                    store.update(active["id"], lambda current: current.update({"overallStatus": "stopping"}))
                    self.assertIn("停止中", store.get(active["id"])["archiveBlockedReason"])
                    store.update(active["id"], lambda current: (
                        current.update({"overallStatus": "cancelled"}),
                        [stage.update({"status": "cancelled"}) for stage in current["stages"].values()],
                    ))

                    result = store.archive_batches([safe["id"], safe["id"], active["id"]])
                    self.assertEqual(result["requestedCount"], 2)
                    self.assertEqual(result["archivedCount"], 2)
                    self.assertEqual(set(result["batchIds"]), {safe["id"], active["id"]})
                    self.assertTrue(all(row["archived"] for row in result["batches"]))
                    self.assertEqual(
                        store.db.execute("SELECT COUNT(*) FROM feature_audit_events WHERE action='batch_archived'").fetchone()[0],
                        2,
                    )
                finally:
                    store.db.close()

    def test_concurrent_thread_snapshot_cannot_commit_partial_bulk_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", True),
            ):
                store = server.SQLiteWorkflowStore()
                release_archive = threading.Event()
                first_archive_write = threading.Event()
                snapshot_finished = threading.Event()
                archive_errors: list[Exception] = []
                snapshot_errors: list[Exception] = []
                try:
                    first = store.create({"name": "Atomic First", "categories": "Atomic First | 914"})
                    second = store.create({"name": "Atomic Second", "categories": "Atomic Second | 915"})
                    original_audit = store._audit_feature_locked
                    archive_audit_count = 0

                    def interrupt_second_archive(action, subject_type, subject_id, outcome, details=None):
                        nonlocal archive_audit_count
                        if action != "batch_archived":
                            return original_audit(action, subject_type, subject_id, outcome, details)
                        archive_audit_count += 1
                        if archive_audit_count == 1:
                            original_audit(action, subject_type, subject_id, outcome, details)
                            first_archive_write.set()
                            if not release_archive.wait(2):
                                raise TimeoutError("archive release timed out")
                            return None
                        raise RuntimeError("forced second archive failure")

                    def archive() -> None:
                        try:
                            store.archive_batches([first["id"], second["id"]])
                        except Exception as exc:  # noqa: BLE001
                            archive_errors.append(exc)

                    def update_snapshot() -> None:
                        try:
                            store.update_thread_snapshot(
                                server.THREAD_ASSIGNMENTS[0]["threadId"],
                                {"status": "idle", "summary": "concurrent snapshot"},
                            )
                        except Exception as exc:  # noqa: BLE001
                            snapshot_errors.append(exc)
                        finally:
                            snapshot_finished.set()

                    with mock.patch.object(store, "_audit_feature_locked", side_effect=interrupt_second_archive):
                        archive_thread = threading.Thread(target=archive)
                        archive_thread.start()
                        self.assertTrue(first_archive_write.wait(2))
                        snapshot_thread = threading.Thread(target=update_snapshot)
                        snapshot_thread.start()
                        self.assertFalse(snapshot_finished.wait(0.15))
                        release_archive.set()
                        archive_thread.join(2)
                        snapshot_thread.join(2)

                    self.assertFalse(archive_thread.is_alive())
                    self.assertFalse(snapshot_thread.is_alive())
                    self.assertEqual(len(archive_errors), 1)
                    self.assertIsInstance(archive_errors[0], RuntimeError)
                    self.assertEqual(snapshot_errors, [])
                    self.assertEqual(
                        store.db.execute("SELECT COUNT(*) FROM batch_archive_state WHERE archived_at IS NOT NULL").fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        store.db.execute("SELECT COUNT(*) FROM feature_audit_events WHERE action='batch_archived'").fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        store.db.execute("SELECT summary FROM thread_snapshots LIMIT 1").fetchone()["summary"],
                        "concurrent snapshot",
                    )
                finally:
                    release_archive.set()
                    store.db.close()

    def test_reenabled_repository_skips_stale_stopping_reconcile_for_archived_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "BROWSER_PAIRING_TOKEN", "pairing-test"),
                mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", True),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Archived Stale Stop", "categories": "Archived Stop | 916"})
                    store.archive_completed_batch(batch["id"])
                    with mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", False):
                        command = store.enqueue_command(batch["id"], "stop_after_current", {})
                        stale_at = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat(timespec="seconds")
                        store.update(
                            batch["id"],
                            lambda current: current.update({
                                "overallStatus": "stopping",
                                "cancelCommandId": command["id"],
                                "cancelRequestedAt": stale_at,
                                "cancelRetryCount": 0,
                            }),
                        )

                    commands = store.poll_global_commands(
                        "pairing-test",
                        protocol="browser-bridge-v2",
                        bridge_version=server.APPROVED_BROWSER_BRIDGE_VERSION,
                        script_version=server.APPROVED_BROWSER_BRIDGE_SCRIPT_VERSION,
                    )
                    self.assertEqual(commands, [])
                    self.assertTrue(store.get(batch["id"])["archived"])
                    rows = store.db.execute(
                        "SELECT id,status FROM commands WHERE batch_id=? ORDER BY created_at",
                        (batch["id"],),
                    ).fetchall()
                    self.assertEqual([(row["id"], row["status"]) for row in rows], [(command["id"], "cancelled")])
                finally:
                    store.db.close()

    def test_terminal_batches_revoke_stale_control_activity_when_archived(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", True),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    completed = store.create({"name": "Terminal Complete", "categories": "Complete | 907"})
                    complete_test_batch(store, completed["id"])
                    cancelled = store.create({"name": "Terminal Cancelled", "categories": "Cancelled | 908"})
                    store.update(cancelled["id"], lambda current: current.update({"overallStatus": "cancelled"}))
                    failed = store.create({"name": "Terminal Failed", "categories": "Failed | 909"})
                    store.update(failed["id"], lambda current: current.update({"overallStatus": "failed"}))
                    terminal_batches = [completed, cancelled, failed]
                    terminal_statuses = ["completed", "cancelled", "failed"]

                    with store.db:
                        for index, (batch, terminal_status) in enumerate(zip(terminal_batches, terminal_statuses), start=1):
                            command_id = f"{index:032x}"
                            dispatch_id = f"{index + 10:032x}"
                            at = server.now_iso()
                            store.db.execute(
                                "INSERT INTO commands(id,batch_id,action,payload,status,created_at) VALUES(?,?,?,?,?,?)",
                                (command_id, batch["id"], "start", "{}", "accepted", at),
                            )
                            store.db.execute(
                                "INSERT INTO bridge_sessions(batch_id,token_hash,status) VALUES(?,?,?)",
                                (batch["id"], f"token-{index}", "connected"),
                            )
                            store.db.execute(
                                """INSERT INTO thread_dispatches(
                                       id,batch_id,thread_id,stage,prompt,note,status,created_at,updated_at
                                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                                (dispatch_id, batch["id"], f"thread-{index}", "browser", "test", "", "prepared", at, at),
                            )
                            snapshot = store.get(batch["id"])
                            self.assertEqual(server.terminal_batch_status(snapshot), terminal_status)
                            self.assertTrue(snapshot["archiveEligible"])

                    result = store.archive_batches([batch["id"] for batch in terminal_batches])
                    self.assertEqual(result["archivedCount"], 3)
                    for batch, terminal_status in zip(terminal_batches, terminal_statuses):
                        self.assertEqual(
                            store.db.execute(
                                "SELECT status FROM commands WHERE batch_id=?", (batch["id"],)
                            ).fetchone()["status"],
                            "cancelled",
                        )
                        self.assertEqual(
                            store.db.execute(
                                "SELECT status FROM bridge_sessions WHERE batch_id=?", (batch["id"],)
                            ).fetchone()["status"],
                            terminal_status,
                        )
                        self.assertEqual(
                            store.db.execute(
                                "SELECT status FROM thread_dispatches WHERE batch_id=?", (batch["id"],)
                            ).fetchone()["status"],
                            "cancelled",
                        )
                        audit = json.loads(store.db.execute(
                            """SELECT details FROM feature_audit_events
                               WHERE action='batch_archived' AND subject_id=?""",
                            (batch["id"],),
                        ).fetchone()["details"])
                        self.assertEqual(
                            audit["revokedStaleActivity"],
                            {"commands": 1, "bridgeSessions": 1, "dispatches": 1},
                        )
                finally:
                    store.db.close()

    def test_archived_batch_rejects_late_mutations_until_restored(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", True),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Archived Boundary", "categories": "Boundary | 906"})
                    dispatch_id = "f" * 32
                    with store.db:
                        at = server.now_iso()
                        store.db.execute(
                            """INSERT INTO thread_dispatches(
                                   id,batch_id,thread_id,stage,prompt,note,status,created_at,updated_at
                               ) VALUES(?,?,?,?,?,?,?,?,?)""",
                            (dispatch_id, batch["id"], "thread-late", "candidates", "test", "", "acknowledged", at, at),
                        )
                    store.archive_completed_batch(batch["id"])
                    payload_before = store.db.execute(
                        "SELECT payload FROM runs WHERE id=?", (batch["id"],)
                    ).fetchone()["payload"]
                    event_count = store.db.execute(
                        "SELECT COUNT(*) FROM events WHERE batch_id=?", (batch["id"],)
                    ).fetchone()[0]

                    with self.assertRaisesRegex(ValueError, "已删除"):
                        store.update(batch["id"], lambda current: current.update({"overallStatus": "running"}))
                    with self.assertRaisesRegex(ValueError, "已删除"):
                        store.event(batch["id"], "late event")
                    with self.assertRaisesRegex(ValueError, "已删除"):
                        store.enqueue_command(batch["id"], "start", {})
                    with self.assertRaisesRegex(ValueError, "已删除"):
                        store.cancel(batch["id"])
                    with self.assertRaisesRegex(ValueError, "已删除"):
                        store.add_intervention(batch["id"], "late", "late intervention")
                    with self.assertRaisesRegex(ValueError, "已删除"):
                        store.prepare_dispatch(batch["id"], "candidates", "late dispatch")
                    with self.assertRaisesRegex(ValueError, "已删除"):
                        store.update_dispatch_status(dispatch_id, "sent")
                    self.assertEqual(
                        store.db.execute("SELECT status FROM thread_dispatches WHERE id=?", (dispatch_id,)).fetchone()["status"],
                        "acknowledged",
                    )
                    with self.assertRaisesRegex(ValueError, "已删除"):
                        store.enqueue_sellersprite_command(batch["id"], {"categoryInput": "Boundary | 906"})
                    with self.assertRaisesRegex(ValueError, "已删除"):
                        store.complete_stop_commands(batch["id"])
                    with self.assertRaisesRegex(ValueError, "已删除"):
                        store.record_asin_event(batch["id"], "B000000001", 1, "late", None, None, {})
                    with self.assertRaisesRegex(ValueError, "已删除"):
                        store.acknowledge_command(batch["id"], "late-token", "0" * 32, "completed")

                    bridge_token = "late-bridge-token"
                    with store.db:
                        store.db.execute(
                            """INSERT INTO bridge_sessions(
                                   batch_id,token_hash,script_version,status
                               ) VALUES(?,?,?,?)""",
                            (
                                batch["id"],
                                hashlib.sha256(bridge_token.encode()).hexdigest(),
                                server.APPROVED_BROWSER_BRIDGE_SCRIPT_VERSION,
                                "cancelled",
                            ),
                        )
                    with self.assertRaisesRegex(ValueError, "已删除"):
                        store.bridge_batch(batch["id"], bridge_token)

                    merged = {
                        "status": "done",
                        "runnerVersion": server.APPROVED_RUNNER_VERSION,
                        "collectorVersion": server.APPROVED_COLLECTOR_VERSION,
                        "results": [],
                    }
                    with mock.patch.object(server, "STORE", store):
                        with self.assertRaisesRegex(ValueError, "已删除"):
                            server.store_merged_json(batch["id"], merged, "browser")
                        with self.assertRaisesRegex(ValueError, "已删除"):
                            server.store_browser_export(
                                batch["id"], {}, {"X-File-Name": "late.csv"}, b"ASIN\nB000000001\n"
                            )
                    self.assertFalse((Path(batch["runDir"]) / "browser" / "merged_source.json").exists())
                    self.assertFalse((Path(batch["runDir"]) / "browser_exports").exists())
                    self.assertEqual(
                        store.db.execute("SELECT payload FROM runs WHERE id=?", (batch["id"],)).fetchone()["payload"],
                        payload_before,
                    )
                    self.assertEqual(
                        store.db.execute("SELECT COUNT(*) FROM commands WHERE batch_id=?", (batch["id"],)).fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        store.db.execute("SELECT COUNT(*) FROM interventions WHERE batch_id=?", (batch["id"],)).fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        store.db.execute("SELECT COUNT(*) FROM asin_events WHERE batch_id=?", (batch["id"],)).fetchone()[0],
                        0,
                    )
                    self.assertEqual(
                        store.db.execute("SELECT COUNT(*) FROM events WHERE batch_id=?", (batch["id"],)).fetchone()[0],
                        event_count,
                    )

                    with store.db:
                        at = server.now_iso()
                        store.db.execute(
                            "INSERT INTO commands(id,batch_id,action,payload,status,created_at) VALUES(?,?,?,?,?,?)",
                            ("1" * 32, batch["id"], "seller_export", "{}", "pending", at),
                        )
                        store.db.execute(
                            "INSERT INTO commands(id,batch_id,action,payload,status,created_at) VALUES(?,?,?,?,?,?)",
                            ("2" * 32, batch["id"], "start", "{}", "pending", at),
                        )
                    self.assertEqual(store.poll_sellersprite_commands(server.BROWSER_PAIRING_TOKEN), [])
                    self.assertEqual(store.poll_commands(batch["id"], "late-token"), [])
                    self.assertEqual(
                        store.poll_global_commands(
                            server.BROWSER_PAIRING_TOKEN,
                            "browser-bridge-v2",
                            server.APPROVED_BROWSER_BRIDGE_VERSION,
                            server.APPROVED_BROWSER_BRIDGE_SCRIPT_VERSION,
                        ),
                        [],
                    )
                    stale_statuses = {
                        row["action"]: row["status"]
                        for row in store.db.execute(
                            "SELECT action,status FROM commands WHERE batch_id=?", (batch["id"],)
                        ).fetchall()
                    }
                    self.assertEqual(stale_statuses, {"seller_export": "cancelled", "start": "cancelled"})

                    store.restore_batch(batch["id"])
                    updated = store.update(batch["id"], lambda current: current.update({"overallStatus": "cancelled"}))
                    self.assertEqual(updated["overallStatus"], "cancelled")
                finally:
                    store.db.close()

    def test_category_import_preview_matches_exact_nodes_and_fails_closed_on_ambiguous_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", True),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    for name, node in (("Shared Name", "111"), ("Shared Name", "222"), ("Exact Alias", "333")):
                        completed = store.create({"name": f"{name} {node}", "categories": f"{name} | {node}"})
                        complete_test_batch(store, completed["id"])
                    store.import_category_pool("Pool Item | 444")

                    raw = "\n".join((
                        "Renamed Exact Node | 333",
                        "Exact Alias",
                        "Shared Name",
                        "Shared Name | 999",
                        "Pool Item | 444",
                        "Fresh A | 555",
                        "Fresh B | 555",
                    ))
                    preview = store.preview_category_pool_import(raw)
                    statuses = [item["status"] for item in preview["items"]]
                    self.assertEqual(statuses, ["screened", "screened", "ambiguous", "ready", "in_pool", "ready", "duplicate"])
                    self.assertEqual(preview["items"][0]["matchMethod"], "node_exact")
                    self.assertEqual(preview["items"][1]["matchMethod"], "name_unique")
                    self.assertEqual({item["nodeIdPath"] for item in preview["items"][2]["matches"]}, {"111", "222"})
                    self.assertEqual(preview["items"][3]["matchMethod"], "node_unseen")
                    self.assertEqual(preview["items"][6]["duplicateOf"], preview["items"][5]["key"])
                    self.assertTrue(all(re.fullmatch(r"line:\d+:[a-f0-9]{24}", item["key"]) for item in preview["items"]))
                    self.assertEqual(preview["selectedKeys"], [preview["items"][3]["key"], preview["items"][5]["key"]])
                    self.assertEqual(
                        store.db.execute("SELECT COUNT(*) FROM feature_audit_events WHERE action='category_pool_previewed'").fetchone()[0],
                        0,
                    )
                    with self.assertRaisesRegex(ValueError, "ambiguous"):
                        store.import_category_pool(raw, [preview["items"][2]["key"]])
                    rejected = store.db.execute(
                        "SELECT details FROM feature_audit_events WHERE action='category_pool_import_failed' ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                    self.assertIsNotNone(rejected)
                    rejected_details = json.loads(rejected["details"])
                    self.assertEqual(rejected_details["selectedKeys"], [preview["items"][2]["key"]])
                    self.assertIn("ambiguous", rejected_details["error"])

                    imported = store.import_category_pool(raw)
                    self.assertEqual(imported["addedCount"], 2)
                    self.assertEqual(imported["selectedCount"], 2)
                    self.assertEqual(imported["skippedCount"], 5)
                    self.assertEqual(imported["duplicateCount"], 1)
                    self.assertEqual(imported["screenedCount"], 2)
                    self.assertEqual(imported["ambiguousCount"], 1)
                    self.assertEqual(sum(item["outcome"] == "imported" for item in imported["outcomes"]), 2)
                    self.assertEqual(sum(item["outcome"] == "skipped" for item in imported["outcomes"]), 5)

                    screened_preview = store.preview_category_pool_import("Exact Alias")
                    screened_key = screened_preview["items"][0]["key"]
                    with self.assertRaisesRegex(ValueError, "overrideScreenedKeys"):
                        store.import_category_pool("Exact Alias", [screened_key])
                    forced_screened = store.import_category_pool("Exact Alias", [screened_key], [screened_key])
                    self.assertEqual(forced_screened["addedCount"], 1)
                    self.assertEqual(forced_screened["overrideScreenedCount"], 1)
                    self.assertEqual(forced_screened["outcomes"][0]["reason"], "screened_override")

                    pool_preview = store.preview_category_pool_import("Pool Item | 444")
                    with self.assertRaisesRegex(ValueError, "in_pool"):
                        store.import_category_pool("Pool Item | 444", [pool_preview["items"][0]["key"]])

                    invalid_raw = "\n".join((
                        "Bad Path | not-a-node",
                        "Wrong Market | https://www.sellersprite.com/v3/product-research?market=UK&nodeIdPaths=%5B123%5D",
                        "Valid Alongside Errors | 777",
                    ))
                    invalid_preview = store.preview_category_pool_import(invalid_raw)
                    self.assertEqual([item["status"] for item in invalid_preview["items"]], ["invalid", "invalid", "ready"])
                    self.assertEqual([item["tone"] for item in invalid_preview["items"][:2]], ["gray", "gray"])
                    self.assertIn("Amazon US", invalid_preview["items"][1]["error"])
                    with self.assertRaisesRegex(ValueError, "invalid"):
                        store.import_category_pool(invalid_raw, [invalid_preview["items"][0]["key"]])
                    valid_only = store.import_category_pool(invalid_raw)
                    self.assertEqual(valid_only["addedCount"], 1)
                    self.assertEqual(valid_only["invalidCount"], 2)
                    self.assertEqual(valid_only["skippedCount"], 2)

                    stale_key = store.preview_category_pool_import("Before Change | 778")["items"][0]["key"]
                    with self.assertRaisesRegex(ValueError, "未知条目"):
                        store.import_category_pool("After Change | 779", [stale_key])

                    repository = store.category_repository_overview("shared name")
                    self.assertEqual(repository["counts"]["categories"], 3)
                    self.assertEqual(repository["counts"]["matched"], 2)
                    self.assertEqual({item["nodeIdPath"] for item in repository["items"]}, {"111", "222"})
                finally:
                    store.db.close()

    def test_screened_override_releases_only_completed_pool_key_and_preserves_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", True),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    raw = "Replay Category | 888"
                    first_import = store.import_category_pool(raw)
                    old_item = next(item for item in first_import["items"] if item["input"] == raw)
                    batch = store.create({"name": "Replay History", "categoryPoolItemId": old_item["id"]})
                    complete_test_batch(store, batch["id"])
                    old_before = store.db.execute(
                        "SELECT id,input,normalized_key,status,batch_id,created_at,updated_at FROM category_pool_items WHERE id=?",
                        (old_item["id"],),
                    ).fetchone()
                    self.assertEqual(old_before["status"], "completed")

                    preview = store.preview_category_pool_import(raw)
                    self.assertEqual(preview["items"][0]["status"], "screened")
                    key = preview["items"][0]["key"]
                    with self.assertRaisesRegex(ValueError, "overrideScreenedKeys"):
                        store.import_category_pool(raw, [key])
                    replayed = store.import_category_pool(raw, [key], [key])
                    self.assertEqual(replayed["addedCount"], 1)
                    self.assertEqual(replayed["skippedCount"], 0)
                    audit = store.db.execute(
                        "SELECT details FROM feature_audit_events WHERE action='category_pool_imported' ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                    audit_item = json.loads(audit["details"])["items"][0]
                    self.assertEqual(audit_item["key"], key)
                    self.assertEqual(audit_item["nodeIdPath"], "888")
                    self.assertEqual(audit_item["authorization"], "screened_override")
                    self.assertEqual(audit_item["releasedPoolItemId"], old_item["id"])
                    self.assertTrue(audit_item["createdPoolItemId"])

                    rows = store.db.execute(
                        "SELECT id,input,normalized_key,status,batch_id,created_at,updated_at FROM category_pool_items WHERE input=? ORDER BY created_at,id",
                        (raw,),
                    ).fetchall()
                    self.assertEqual(len(rows), 2)
                    old_after = next(row for row in rows if row["id"] == old_item["id"])
                    new_item = next(row for row in rows if row["id"] != old_item["id"])
                    self.assertEqual(old_after["status"], "completed")
                    self.assertEqual(old_after["batch_id"], batch["id"])
                    self.assertEqual(old_after["input"], old_before["input"])
                    self.assertEqual(old_after["created_at"], old_before["created_at"])
                    self.assertEqual(old_after["updated_at"], old_before["updated_at"])
                    self.assertNotEqual(old_after["normalized_key"], raw.casefold())
                    self.assertTrue(old_after["normalized_key"].startswith(f"completed:{old_item['id']}:"))
                    self.assertEqual(new_item["status"], "available")
                    self.assertEqual(new_item["normalized_key"], raw.casefold())
                    self.assertEqual(
                        store.db.execute("SELECT COUNT(*) FROM screened_category_completions WHERE batch_id=?", (batch["id"],)).fetchone()[0],
                        1,
                    )

                    active_preview = store.preview_category_pool_import(raw)
                    self.assertEqual(active_preview["items"][0]["status"], "in_pool")
                    with self.assertRaisesRegex(ValueError, "in_pool"):
                        store.import_category_pool(raw, [active_preview["items"][0]["key"]])
                    still_active = store.db.execute(
                        "SELECT status,normalized_key FROM category_pool_items WHERE id=?",
                        (new_item["id"],),
                    ).fetchone()
                    self.assertEqual(dict(still_active), {"status": "available", "normalized_key": raw.casefold()})
                finally:
                    store.db.close()

    def test_category_import_revalidates_stale_selection_and_serializes_same_node(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", True),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    stale_raw = "Completed During Import | 990"
                    stale_preview = store.preview_category_pool_import(stale_raw)
                    stale_key = stale_preview["items"][0]["key"]
                    self.assertEqual(stale_preview["items"][0]["status"], "ready")
                    completing_batch = store.create({"name": "Concurrent Completion", "categories": stale_raw})
                    completion_done = threading.Event()
                    stale_errors: list[Exception] = []

                    def complete_in_thread() -> None:
                        complete_test_batch(store, completing_batch["id"])
                        completion_done.set()

                    def import_after_completion() -> None:
                        if not completion_done.wait(5):
                            stale_errors.append(RuntimeError("并发完成线程超时"))
                            return
                        try:
                            store.import_category_pool(stale_raw, [stale_key])
                        except Exception as exc:  # noqa: BLE001
                            stale_errors.append(exc)

                    importer = threading.Thread(target=import_after_completion)
                    completer = threading.Thread(target=complete_in_thread)
                    importer.start()
                    completer.start()
                    importer.join(5)
                    completer.join(5)
                    self.assertFalse(importer.is_alive())
                    self.assertFalse(completer.is_alive())
                    self.assertEqual(len(stale_errors), 1)
                    self.assertIsInstance(stale_errors[0], ValueError)
                    self.assertIn("overrideScreenedKeys", str(stale_errors[0]))
                    red_preview = store.preview_category_pool_import(stale_raw)
                    self.assertEqual(red_preview["items"][0]["key"], stale_key)
                    self.assertEqual(red_preview["items"][0]["status"], "screened")
                    self.assertEqual(
                        store.db.execute(
                            "SELECT COUNT(*) FROM category_pool_items WHERE node_id_path='990' AND status IN ('available','assigned')"
                        ).fetchone()[0],
                        0,
                    )

                    concurrent_raw = ("Concurrent Alpha | 991", "Concurrent Beta | 991")
                    concurrent_keys = [
                        store.preview_category_pool_import(raw)["items"][0]["key"]
                        for raw in concurrent_raw
                    ]
                    start = threading.Barrier(3)
                    results: list[dict] = []
                    errors: list[Exception] = []
                    result_lock = threading.Lock()

                    def import_same_node(raw: str, key: str) -> None:
                        start.wait()
                        try:
                            result = store.import_category_pool(raw, [key])
                        except Exception as exc:  # noqa: BLE001
                            with result_lock:
                                errors.append(exc)
                        else:
                            with result_lock:
                                results.append(result)

                    threads = [
                        threading.Thread(target=import_same_node, args=(raw, key))
                        for raw, key in zip(concurrent_raw, concurrent_keys, strict=True)
                    ]
                    for thread in threads:
                        thread.start()
                    start.wait()
                    for thread in threads:
                        thread.join(5)
                        self.assertFalse(thread.is_alive())
                    self.assertEqual(len(results), 1)
                    self.assertEqual(results[0]["addedCount"], 1)
                    self.assertEqual(len(errors), 1)
                    self.assertIsInstance(errors[0], ValueError)
                    self.assertIn("in_pool", str(errors[0]))
                    active_rows = store.db.execute(
                        """SELECT id,label,node_id_path,status FROM category_pool_items
                           WHERE node_id_path='991' AND status IN ('available','assigned')"""
                    ).fetchall()
                    self.assertEqual(len(active_rows), 1)
                finally:
                    store.db.close()

    def test_browser_export_query_contract_rejects_weaker_filters(self) -> None:
        filters = server.normalize_query_filters({})
        valid = server.sellersprite_web_query_url("3760911", filters)
        contract = browser_export_pipeline.validate_query_contract(valid, filters)
        self.assertEqual(contract["nodeIdPaths"], ["3760911"])
        parsed = parse_qs(urlsplit(valid).query)
        self.assertEqual(parsed["symbolFlag"], ["true"])
        self.assertEqual(parsed["filterSub"], ["false"])
        self.assertEqual(parsed["order[field]"], ["amz_unit"])
        self.assertEqual(parsed["productTags"], ["[]"])
        with self.assertRaises(browser_export_pipeline.PipelineError):
            browser_export_pipeline.validate_query_contract(valid.replace("maxReviews=100", "maxReviews=101"), filters)
        with self.assertRaises(browser_export_pipeline.PipelineError):
            browser_export_pipeline.validate_query_contract(valid.replace("minAmzUnit=50", "minAmzUnit=0"), filters)
        actual_page_url = valid.replace("minAmzUnit=50", "minAmzUnit=50").replace("maxAmzUnit=300", "maxAmzUnit=300")
        self.assertEqual(browser_export_pipeline.validate_query_contract(actual_page_url, filters)["checks"]["minSales"], True)

    def test_browser_export_upload_is_staged_without_processing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Browser Export", "categories": "Beauty | 3760911"})
                    with mock.patch.object(server, "STORE", store), mock.patch.object(server, "preflight", return_value={"ok": True}):
                        server.start_candidates(batch["id"])
                        prepared = store.get(batch["id"])
                        task = prepared["stages"]["candidates"]["artifacts"]["exportTasks"][0]
                        query = parse_qs(urlencode({"categoryInput": "Beauty | 3760911", "sourcePage": "Beauty", "queryUrl": task["queryUrl"]}))
                        uploaded = server.store_browser_export(batch["id"], query, {"X-File-Name": "export.csv"}, b"ASIN\nB000000001\n")
                    self.assertEqual(uploaded["stages"]["candidates"]["artifacts"]["uploadedExportCount"], 1)
                    record = uploaded["browserExports"][0]
                    self.assertTrue(Path(record["path"]).is_file())
                    self.assertEqual(record["fileName"], "export.csv")
                finally:
                    store.db.close()

    def test_browser_export_batch_creation_queues_bridge_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "ENABLE_SELLERSPRITE_BRIDGE", True),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Auto Prepare", "categories": "Beauty | 3760911"})
                    with mock.patch.object(server, "STORE", store):
                        prepared = server.auto_prepare_browser_export_batch(batch)
                    self.assertEqual(prepared["stages"]["candidates"]["artifacts"]["sellerSpriteBridge"]["status"], "queued")
                    self.assertEqual(len(store.poll_sellersprite_commands(server.BROWSER_PAIRING_TOKEN)), 1)
                finally:
                    store.db.close()

    def test_last_bridge_export_starts_candidate_pipeline_automatically(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Auto Start", "categories": "Beauty | 3760911"})
                    with mock.patch.object(server, "STORE", store), mock.patch.object(server, "preflight", return_value={"ok": True}):
                        server.prepare_browser_export_tasks(batch["id"])
                        task = store.get(batch["id"])["stages"]["candidates"]["artifacts"]["exportTasks"][0]
                        query = parse_qs(urlencode({"categoryInput": task["categoryInput"], "sourcePage": task["label"], "queryUrl": task["queryUrl"]}))
                        server.store_browser_export(batch["id"], query, {"X-File-Name": "auto-export.csv"}, b"ASIN\nB000000001\n")
                        with mock.patch.object(server, "start_candidates") as start:
                            updated = server.maybe_start_browser_export_pipeline(batch["id"])
                    start.assert_called_once_with(batch["id"])
                    bridge = updated["stages"]["candidates"]["artifacts"]["sellerSpriteBridge"]
                    self.assertEqual(bridge["status"], "processing")
                finally:
                    store.db.close()

    def test_sellersprite_bridge_command_is_scoped_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "BROWSER_PAIRING_TOKEN", "pairing-test"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Bridge Queue", "categories": "Beauty | 3760911"})
                    with mock.patch.object(server, "STORE", store), mock.patch.object(server, "preflight", return_value={"ok": True}):
                        server.start_candidates(batch["id"])
                    commands = store.poll_sellersprite_commands("pairing-test")
                    self.assertEqual(len(commands), 1)
                    self.assertEqual(commands[0]["action"], "seller_export")
                    self.assertIsNone(store.enqueue_sellersprite_command(batch["id"], commands[0]["payload"]))
                    store.acknowledge_sellersprite_command("pairing-test", batch["id"], commands[0]["id"], "failed", "未登录")
                    self.assertEqual(store.get(batch["id"])["overallStatus"], "needs_attention")
                finally:
                    store.db.close()

    def test_cancelled_sellersprite_batch_ignores_late_export_and_failure_ack(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "BROWSER_PAIRING_TOKEN", "pairing-test"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Late Export", "categories": "Beauty | 3760911"})
                    with mock.patch.object(server, "STORE", store), mock.patch.object(server, "preflight", return_value={"ok": True}):
                        server.start_candidates(batch["id"])
                    command = store.poll_sellersprite_commands("pairing-test")[0]
                    stopped = store.cancel(batch["id"])
                    self.assertEqual(stopped["overallStatus"], "cancelled")
                    with mock.patch.object(server, "STORE", store), mock.patch.object(server, "maybe_start_browser_export_pipeline") as auto_start:
                        late = server.store_sellersprite_export({
                            "pairingToken": "pairing-test",
                            "batchId": batch["id"],
                            "batchToken": batch["bridgeToken"],
                            "commandId": command["id"],
                        })
                    auto_start.assert_not_called()
                    self.assertEqual(late["overallStatus"], "cancelled")
                    store.acknowledge_sellersprite_command("pairing-test", batch["id"], command["id"], "failed", "迟到失败")
                    after = store.get(batch["id"])
                    self.assertEqual(after["overallStatus"], "cancelled")
                    self.assertEqual(after["stages"]["candidates"]["status"], "cancelled")
                    command_row = store.db.execute("SELECT status FROM commands WHERE id=?", (command["id"],)).fetchone()
                    self.assertEqual(command_row["status"], "cancelled")
                    self.assertEqual(store.poll_sellersprite_commands("pairing-test"), [])
                finally:
                    store.db.close()

    def test_cancel_and_sellersprite_failure_ack_cannot_revive_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "BROWSER_PAIRING_TOKEN", "pairing-test"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Concurrent Seller Stop", "categories": "Beauty | 3760911"})
                    command = store.enqueue_sellersprite_command(batch["id"], {"categoryInput": "Beauty | 3760911"})
                    self.assertIsNotNone(command)
                    barrier = threading.Barrier(3)
                    errors = []

                    def acknowledge() -> None:
                        try:
                            barrier.wait()
                            store.acknowledge_sellersprite_command("pairing-test", batch["id"], command["id"], "failed", "late failure")
                        except Exception as exc:  # noqa: BLE001
                            errors.append(exc)

                    def cancel() -> None:
                        try:
                            barrier.wait()
                            store.cancel(batch["id"])
                        except Exception as exc:  # noqa: BLE001
                            errors.append(exc)

                    threads = [threading.Thread(target=acknowledge), threading.Thread(target=cancel)]
                    for thread in threads:
                        thread.start()
                    barrier.wait()
                    for thread in threads:
                        thread.join(2)
                    self.assertTrue(all(not thread.is_alive() for thread in threads))
                    self.assertEqual(errors, [])
                    self.assertEqual(store.get(batch["id"])["overallStatus"], "cancelled")
                finally:
                    store.db.close()

    def test_cancel_after_sellersprite_file_store_preserves_cancelled_bridge_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "BROWSER_PAIRING_TOKEN", "pairing-test"),
            ):
                store = server.SQLiteWorkflowStore()
                export_stored = threading.Event()
                release_callback = threading.Event()
                errors = []
                result = {}
                try:
                    batch = store.create({"name": "Cancel During Seller Upload", "categories": "Beauty | 3760911"})
                    with mock.patch.object(server, "STORE", store), mock.patch.object(server, "preflight", return_value={"ok": True}):
                        server.start_candidates(batch["id"])
                    command = store.poll_sellersprite_commands("pairing-test")[0]
                    payload = {
                        "pairingToken": "pairing-test",
                        "batchId": batch["id"],
                        "batchToken": batch["bridgeToken"],
                        "commandId": command["id"],
                        "categoryInput": command["payload"]["categoryInput"],
                        "sourcePage": command["payload"]["sourcePage"],
                        "queryUrl": command["payload"]["queryUrl"],
                        "capturedAt": server.now_iso(),
                        "fileName": "race-export.csv",
                        "contentBase64": base64.b64encode(b"ASIN\nB000000001\n").decode("ascii"),
                    }
                    original_store = server.store_browser_export

                    def store_then_wait(*args, **kwargs):
                        stored = original_store(*args, **kwargs)
                        export_stored.set()
                        if not release_callback.wait(2):
                            raise TimeoutError("SellerSprite callback release timed out")
                        return stored

                    def upload() -> None:
                        try:
                            result.update(server.store_sellersprite_export(payload))
                        except Exception as exc:  # noqa: BLE001
                            errors.append(exc)

                    with (
                        mock.patch.object(server, "STORE", store),
                        mock.patch.object(server, "store_browser_export", side_effect=store_then_wait),
                        mock.patch.object(server, "maybe_start_browser_export_pipeline") as auto_start,
                    ):
                        thread = threading.Thread(target=upload)
                        thread.start()
                        self.assertTrue(export_stored.wait(2))
                        store.cancel(batch["id"])
                        release_callback.set()
                        thread.join(2)
                    self.assertFalse(thread.is_alive())
                    self.assertEqual(errors, [])
                    auto_start.assert_not_called()
                    self.assertEqual(result["overallStatus"], "cancelled")
                    self.assertEqual(result["stages"]["candidates"]["status"], "cancelled")
                    bridge_status = result["stages"]["candidates"].get("artifacts", {}).get("sellerSpriteBridge", {}).get("status")
                    self.assertNotEqual(bridge_status, "uploaded")
                    command_row = store.db.execute("SELECT status FROM commands WHERE id=?", (command["id"],)).fetchone()
                    self.assertEqual(command_row["status"], "cancelled")
                finally:
                    release_callback.set()
                    store.db.close()

    def test_auto_prepare_failure_after_cancel_does_not_revive_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Cancelled Auto Prepare", "categories": "Beauty | 3760911"})

                    def cancel_then_fail(batch_id: str) -> None:
                        store.cancel(batch_id)
                        raise RuntimeError("late prepare failure")

                    with (
                        mock.patch.object(server, "STORE", store),
                        mock.patch.object(server, "prepare_browser_export_tasks", side_effect=cancel_then_fail),
                    ):
                        updated = server.auto_prepare_browser_export_batch(batch)
                    self.assertEqual(updated["overallStatus"], "cancelled")
                    self.assertEqual(updated["stages"]["candidates"]["status"], "cancelled")
                finally:
                    store.db.close()

    def test_sellersprite_bridge_upload_reuses_strict_staging(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "BROWSER_PAIRING_TOKEN", "pairing-test"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Bridge Upload", "categories": "Beauty | 3760911"})
                    with mock.patch.object(server, "STORE", store), mock.patch.object(server, "preflight", return_value={"ok": True}), mock.patch.object(server, "maybe_start_browser_export_pipeline", side_effect=lambda batch_id: store.get(batch_id)) as auto_start:
                        server.start_candidates(batch["id"])
                        command = store.poll_sellersprite_commands("pairing-test")[0]
                        uploaded = server.store_sellersprite_export({
                            "pairingToken": "pairing-test",
                            "batchId": batch["id"],
                            "batchToken": batch["bridgeToken"],
                            "commandId": command["id"],
                            "categoryInput": command["payload"]["categoryInput"],
                            "sourcePage": command["payload"]["sourcePage"],
                            "queryUrl": command["payload"]["queryUrl"],
                            "capturedAt": server.now_iso(),
                            "fileName": "auto-export.csv",
                            "contentBase64": base64.b64encode(b"ASIN\nB000000001\n").decode("ascii"),
                        })
                    auto_start.assert_called_once_with(batch["id"])
                    self.assertEqual(uploaded["stages"]["candidates"]["artifacts"]["uploadedExportCount"], 1)
                    self.assertEqual(uploaded["browserExports"][0]["fileName"], "auto-export.csv")
                finally:
                    store.db.close()

    def test_runner_payload_autofills_batch_operator_and_approved_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            queue = Path(temp) / "approved.txt"
            queue.write_text("B000000001\nB000000002\n", encoding="ascii")
            batch = {
                "id": "abcdef123456",
                "name": "Home Storage",
                "category": "Storage & Organization",
                "operator": "liyuanze",
                "runDate": "2026-08-05",
                "targetQualified": 12,
                "stages": {"candidates": {"status": "completed", "artifacts": {"queuePath": str(queue)}}},
            }
            payload = server.runner_command_payload(batch)
            self.assertEqual(payload["operator"], "liyuanze")
            self.assertEqual(payload["targetQualified"], 12)
            self.assertEqual(payload["queueAsins"], ["B000000001", "B000000002"])
            self.assertEqual(payload["approvedRunnerVersion"], "0.3.8.13")

    def test_approve_candidate_queue_creates_canonical_parent_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Approve Queue", "categories": "Beauty | 3760911"})
                    run_dir = root / "formal" / "runs" / "approve-queue"
                    proposal_dir = run_dir / "browser_export_attempts" / "attempt-1" / "candidate_pool"
                    proposal_dir.mkdir(parents=True)
                    proposal_path = proposal_dir / "runner_queue.txt"
                    proposal_path.write_text("B000000001\nB000000002\n", encoding="ascii")
                    queue_json_path = proposal_dir / "runner_queue.json"
                    queue_json_path.write_text('{"items": []}', encoding="utf-8")

                    def mark_ready(current: dict) -> None:
                        current["runDir"] = str(run_dir)
                        server.set_stage(current, "candidates", "needs_attention", "ready", {
                            "queuePath": str(proposal_path),
                            "queueJsonPath": str(queue_json_path),
                            "queueCount": 2,
                        })

                    store.update(batch["id"], mark_ready)
                    approved_path = run_dir / "candidate_pool" / "runner_queue_approved.txt"
                    self.assertFalse(approved_path.parent.exists())

                    with mock.patch.object(server, "STORE", store):
                        with self.assertRaisesRegex(ValueError, "Runner 队列不能为空"):
                            server.approve_candidate_queue(batch["id"], {"selectedAsins": ""})
                        updated = server.approve_candidate_queue(batch["id"], {"selectedAsins": "B000000001\nB000000002\n"})

                    self.assertEqual(approved_path.read_text(encoding="ascii"), "B000000001\nB000000002\n")
                    self.assertEqual(updated["stages"]["candidates"]["status"], "completed")
                    self.assertEqual(updated["stages"]["candidates"]["artifacts"]["queuePath"], str(approved_path))
                    stopped = store.cancel(batch["id"])
                    self.assertEqual(stopped["overallStatus"], "cancelled")
                    self.assertEqual(stopped["stages"]["candidates"]["status"], "completed")
                    with mock.patch.object(server, "STORE", store), self.assertRaisesRegex(ValueError, "批次已结束"):
                        server.approve_candidate_queue(batch["id"], {"selectedAsins": "B000000001\n"})
                    self.assertEqual(store.get(batch["id"])["overallStatus"], "cancelled")
                finally:
                    store.db.close()

    def test_merged_json_handoff_requires_exact_source_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Handoff", "categories": "Home Storage"})
                    store.update(batch["id"], lambda current: current.update({"runnerBatchName": "runner-handoff"}))
                    merged = {
                        "schemaVersion": "sellerSpriteIntegratedBatch/v0.3.0",
                        "batchName": "runner-handoff",
                        "status": "done",
                        "runnerVersion": "0.3.8.13",
                        "collectorVersion": "0.4.6.4",
                        "results": [{"targetAsin": "B000000001", "qualified": True}],
                    }
                    with mock.patch.object(server, "STORE", store):
                        source = server.store_merged_json(batch["id"], merged, "browser")
                        pasted = server.store_merged_json(batch["id"], json.dumps(merged), "paste")
                        self.assertEqual(source["artifact"]["sha256"], pasted["artifact"]["sha256"])
                        self.assertTrue(pasted["batch"]["jsonHandoff"]["pasteVerified"])
                        pasted_path = Path(pasted["batch"]["jsonHandoff"]["pastedPath"])
                        verified_bytes = pasted_path.read_bytes()
                        changed = {**merged, "results": []}
                        with self.assertRaises(ValueError):
                            server.store_merged_json(batch["id"], changed, "paste")
                        self.assertEqual(pasted_path.read_bytes(), verified_bytes)
                        self.assertTrue(store.get(batch["id"])["jsonHandoff"]["pasteVerified"])
                finally:
                    store.db.close()

    def test_excel_start_is_bound_to_the_verified_paste_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Excel Handoff", "categories": "Home Storage"})
                    store.update(batch["id"], lambda current: current.update({"runnerBatchName": "runner-excel"}))
                    merged = {
                        "batchName": "runner-excel", "status": "done",
                        "runnerVersion": "0.3.8.13", "collectorVersion": "0.4.6.4",
                        "results": [{"targetAsin": "B000000001", "qualified": True}],
                    }
                    with mock.patch.object(server, "STORE", store):
                        server.store_merged_json(batch["id"], merged, "browser")
                        with self.assertRaisesRegex(ValueError, "请先复制并手动粘贴"):
                            server.start_excel(batch["id"], {})
                        pasted = server.store_merged_json(batch["id"], json.dumps(merged), "paste")
                        with self.assertRaisesRegex(ValueError, "固定产物"):
                            server.start_excel(batch["id"], {"batchJsonPath": str(root / "other.json")})
                        run_dir = Path(pasted["batch"]["runDir"])
                        candidate_path = run_dir / "candidate.json"
                        title_path = run_dir / "titles.json"
                        images_dir = run_dir / "images"
                        candidate_path.write_text("[]", encoding="utf-8")
                        title_path.write_text("{}", encoding="utf-8")
                        images_dir.mkdir()
                        store.update(batch["id"], lambda current: current.update({
                            "candidateJsonPath": str(candidate_path),
                            "titleOverridesPath": str(title_path),
                            "imagesDir": str(images_dir),
                        }))
                        launch_lock_owned = []
                        def capture_launch(*_args, **_kwargs):
                            launch_lock_owned.append(store.lock._is_owned())
                        with mock.patch.object(store, "launch", side_effect=capture_launch) as launch:
                            server.start_excel(batch["id"], {})
                        self.assertEqual(launch_lock_owned, [True])
                        self.assertEqual(Path(launch.call_args.args[2][2]), Path(pasted["batch"]["jsonHandoff"]["pastedPath"]))
                        pinned = store.get(batch["id"])["stages"]["excel"]["artifacts"]["inputContract"]
                        self.assertEqual(pinned["sourceSha256"], pinned["pastedSha256"])
                        store.update(batch["id"], lambda current: current["stages"]["excel"].update({"status": "running"}))
                        with self.assertRaisesRegex(ValueError, "已有 Excel 任务"):
                            server.start_excel(batch["id"], {})
                        store.update(batch["id"], lambda current: current["stages"]["excel"].update({"status": "ready"}))
                        pasted_path = Path(pasted["batch"]["jsonHandoff"]["pastedPath"])
                        pasted_path.write_text("{}\n", encoding="utf-8")
                        with self.assertRaisesRegex(ValueError, "文件指纹发生变化"):
                            server.start_excel(batch["id"], {})
                    self.assertEqual(store.get(batch["id"])["stages"]["excel"]["status"], "ready")
                finally:
                    store.db.close()

    def test_excel_running_locks_runner_source_and_rechecks_handoff_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Excel Contract", "categories": "Home Storage"})
                    store.update(batch["id"], lambda current: current.update({"runnerBatchName": "runner-contract"}))
                    merged = {
                        "batchName": "runner-contract", "status": "done",
                        "runnerVersion": "0.3.8.13", "collectorVersion": "0.4.6.4",
                        "results": [{"targetAsin": "B000000001", "qualified": True}],
                    }
                    with mock.patch.object(server, "STORE", store):
                        source = server.store_merged_json(batch["id"], merged, "browser")
                        pasted = server.store_merged_json(batch["id"], json.dumps(merged), "paste")
                        contract = {
                            "sourceSha256": pasted["batch"]["jsonHandoff"]["sourceSha256"],
                            "pastedSha256": pasted["batch"]["jsonHandoff"]["pastedSha256"],
                            "sourcePath": pasted["batch"]["jsonHandoff"]["sourcePath"],
                            "pastedPath": pasted["batch"]["jsonHandoff"]["pastedPath"],
                        }
                        store.update(batch["id"], lambda current: (
                            current.update({"overallStatus": "running"}),
                            current["stages"]["excel"].update({"status": "running"}),
                        ))
                        same = server.store_merged_json(batch["id"], merged, "browser")
                        self.assertEqual(same["artifact"]["sha256"], source["artifact"]["sha256"])
                        self.assertTrue(same["batch"]["jsonHandoff"]["pasteVerified"])
                        original_source_bytes = Path(contract["sourcePath"]).read_bytes()
                        changed = {**merged, "results": []}
                        with self.assertRaisesRegex(ValueError, "拒绝替换原始结果"):
                            server.store_merged_json(batch["id"], changed, "browser")
                        self.assertEqual(Path(contract["sourcePath"]).read_bytes(), original_source_bytes)
                        self.assertTrue(store.get(batch["id"])["jsonHandoff"]["pasteVerified"])
                        server.verify_excel_input_contract(batch["id"], contract)
                        Path(contract["pastedPath"]).write_text("{}\n", encoding="utf-8")
                        with self.assertRaisesRegex(ValueError, "JSON 文件指纹已变化"):
                            server.verify_excel_input_contract(batch["id"], contract)
                finally:
                    store.db.close()

    def test_launch_job_remains_reserved_through_success_callback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                callback_started = threading.Event()
                release_callback = threading.Event()
                try:
                    (root / "formal").mkdir()
                    batch = store.create({"name": "Job Reservation", "categories": "Home Storage"})

                    def on_success(_run_dir: Path) -> dict[str, bool]:
                        callback_started.set()
                        self.assertTrue(release_callback.wait(5))
                        return {"callbackCompleted": True}

                    store.launch(
                        batch["id"], "candidates", [str(server.PYTHON_EXE), "-c", "pass"],
                        "job_reservation", on_success,
                    )
                    self.assertTrue(callback_started.wait(5))
                    self.assertIn(batch["id"], store.jobs)
                    with self.assertRaisesRegex(ValueError, "已有任务正在运行"):
                        store.launch(
                            batch["id"], "candidates", [str(server.PYTHON_EXE), "-c", "pass"],
                            "duplicate_job", lambda _run_dir: {},
                        )
                    release_callback.set()
                    deadline = server.time.time() + 5
                    while batch["id"] in store.jobs and server.time.time() < deadline:
                        server.time.sleep(0.02)
                    self.assertNotIn(batch["id"], store.jobs)
                    self.assertEqual(store.get(batch["id"])["stages"]["candidates"]["status"], "completed")
                    lease = store.db.execute(
                        "SELECT stage,status,pid,exit_code,owner_instance_id FROM local_job_leases WHERE batch_id=? ORDER BY started_at DESC LIMIT 1",
                        (batch["id"],),
                    ).fetchone()
                    self.assertEqual(lease["stage"], "candidates")
                    self.assertEqual(lease["status"], "completed")
                    self.assertIsNotNone(lease["pid"])
                    self.assertEqual(lease["exit_code"], 0)
                    self.assertEqual(lease["owner_instance_id"], server.CONSOLE_INSTANCE_ID)
                finally:
                    release_callback.set()
                    store.db.close()

    def test_restart_marks_running_local_stage_interrupted_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                first = server.SQLiteWorkflowStore()
                batch = first.create({"name": "Restart Recovery", "categories": "Recovery | 901"})
                first.update(batch["id"], lambda current: server.set_stage(
                    current,
                    "candidates",
                    "running",
                    "正在执行候选任务",
                    {"stdout": str(root / "formal" / "stdout.log"), "stderr": str(root / "formal" / "stderr.log")},
                ))
                first.db.close()

                second = server.SQLiteWorkflowStore()
                try:
                    recovered = second.get(batch["id"])
                    self.assertEqual(recovered["overallStatus"], "needs_attention")
                    self.assertEqual(recovered["stages"]["candidates"]["status"], "needs_attention")
                    recovery = recovered["stages"]["candidates"]["recovery"]
                    self.assertEqual(recovery["reason"], "service_restart_missing_lease")
                    self.assertTrue(recovery["canRetry"])
                    self.assertEqual(
                        second.db.execute(
                            "SELECT status,recovery_reason FROM local_job_leases WHERE batch_id=? AND stage=?",
                            (batch["id"], "candidates"),
                        ).fetchone()["status"],
                        "interrupted",
                    )
                    self.assertEqual(
                        second.db.execute(
                            "SELECT COUNT(*) FROM events WHERE batch_id=? AND message='服务重启，本地任务未自动接管'",
                            (batch["id"],),
                        ).fetchone()[0],
                        1,
                    )
                    second.db.close()

                    third = server.SQLiteWorkflowStore()
                    try:
                        still_recovered = third.get(batch["id"])
                        self.assertEqual(still_recovered["stages"]["candidates"]["status"], "needs_attention")
                        self.assertEqual(
                            third.db.execute(
                                "SELECT COUNT(*) FROM events WHERE batch_id=? AND message='服务重启，本地任务未自动接管'",
                                (batch["id"],),
                            ).fetchone()[0],
                            1,
                        )
                    finally:
                        third.db.close()
                except Exception:
                    second.db.close()
                    raise

    def test_restart_never_adopts_a_live_unverified_local_pid(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                first = server.SQLiteWorkflowStore()
                batch = first.create({"name": "Orphan Guard", "categories": "Orphan | 902"})
                first.update(batch["id"], lambda current: server.set_stage(
                    current, "candidates", "running", "正在执行候选任务", {"stdout": "out.log", "stderr": "err.log"}
                ))
                with first.db:
                    first.db.execute(
                        """INSERT INTO local_job_leases(
                               id,batch_id,stage,attempt,pid,argv_sha256,executable,run_dir,
                               stdout_path,stderr_path,owner_instance_id,status,started_at,last_seen_at
                           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            "live-orphan", batch["id"], "candidates", 1, os.getpid(),
                            "not-the-current-command", "python.exe", str(root / "formal"),
                            "out.log", "err.log", "previous-instance", "running",
                            server.now_iso(), server.now_iso(),
                        ),
                    )
                first.db.close()

                second = server.SQLiteWorkflowStore()
                try:
                    recovered = second.get(batch["id"])
                    self.assertEqual(recovered["overallStatus"], "needs_attention")
                    self.assertEqual(recovered["stages"]["candidates"]["recovery"]["status"], "orphaned")
                    self.assertTrue(recovered["stages"]["candidates"]["recovery"]["processAlive"])
                    lease = second.db.execute(
                        "SELECT status,pid,recovery_reason FROM local_job_leases WHERE id='live-orphan'"
                    ).fetchone()
                    self.assertEqual(dict(lease), {
                        "status": "orphaned",
                        "pid": os.getpid(),
                        "recovery_reason": "service_restart_process_alive",
                    })
                    with mock.patch.object(subprocess, "Popen") as popen:
                        with self.assertRaisesRegex(ValueError, "遗留进程"):
                            second.launch(
                                batch["id"], "candidates", [str(server.PYTHON_EXE), "-c", "pass"],
                                "retry_after_restart", lambda _run_dir: {},
                            )
                        popen.assert_not_called()
                finally:
                    second.db.close()

    def test_copy_json_rejects_a_changed_runner_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Copy Handoff", "categories": "Home Storage"})
                    store.update(batch["id"], lambda current: current.update({"runnerBatchName": "runner-copy"}))
                    merged = {
                        "batchName": "runner-copy", "status": "done",
                        "runnerVersion": "0.3.8.13", "collectorVersion": "0.4.6.4", "results": [],
                    }
                    with mock.patch.object(server, "STORE", store):
                        source = server.store_merged_json(batch["id"], merged, "browser")
                        source_path = Path(source["batch"]["jsonHandoff"]["sourcePath"])
                        source_path.write_text('{"changed":true}\n', encoding="utf-8")
                        with self.assertRaisesRegex(ValueError, "原始 JSON 指纹已变化"):
                            server.copy_merged_json(batch["id"])
                finally:
                    store.db.close()

    def test_browser_merged_json_rejects_non_done_before_writing_canonical_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Reject Early JSON", "categories": "Home Storage"})
                    store.update(batch["id"], lambda current: (
                        current.update({"runnerBatchName": "current-runner", "overallStatus": "running"}),
                        current["stages"]["browser"].update({"status": "running"}),
                    ))
                    merged = {
                        "batchName": "current-runner", "status": "running",
                        "runnerVersion": "0.3.8.13", "collectorVersion": "0.4.6.4",
                        "results": [{"targetAsin": "B000000001", "qualified": True}],
                    }
                    with mock.patch.object(server, "STORE", store), self.assertRaisesRegex(ValueError, "status=done"):
                        server.store_merged_json(batch["id"], merged, "browser")
                    unchanged = store.get(batch["id"])
                    self.assertEqual(unchanged["overallStatus"], "running")
                    self.assertFalse(unchanged.get("jsonHandoff", {}).get("sourceSha256"))
                    self.assertFalse((Path(batch["runDir"]) / "browser" / "merged_source.json").exists())
                finally:
                    store.db.close()

    def test_validate_sellersprite_url_requires_us_category_and_review_bound(self) -> None:
        valid = "https://www.sellersprite.com/v3/product-research?market=US&maxReviews=60&nodeIdPaths=%5B%22228013%22%5D"
        self.assertEqual(server.validate_sellersprite_url(valid), valid)
        with self.assertRaises(ValueError):
            server.validate_sellersprite_url(valid.replace("market=US", "market=CA"))
        with self.assertRaises(ValueError):
            server.validate_sellersprite_url(valid.replace("maxReviews=60", "maxReviews=101"))
        with self.assertRaises(ValueError):
            server.validate_sellersprite_url(valid.replace("nodeIdPaths=%5B%22228013%22%5D", "nodeIdPaths=%5B%5D"))

    def test_browser_bridge_supports_runner_deferred_json_contract(self) -> None:
        bridge = Path(__file__).with_name("browser_bridge_v2.user.js").read_text(encoding="utf-8")
        self.assertIn('const BRIDGE_VERSION = "2.1.3"', bridge)
        self.assertIn('const SCRIPT_VERSION = "2.1.6"', bridge)
        self.assertIn('const COLLECTOR_VERSION = "0.4.6.4"', bridge)
        self.assertIn('const RUNNER_VERSION = "0.3.8.13"', bridge)
        self.assertIn('const RUNNER_STORAGE_PREFIX = "ssIntegratedRunner:v0.3:"', bridge)
        self.assertIn('localStorage.getItem(runnerBatchStorageKey(queueHash))', bridge)
        self.assertIn('"#ss-v3-stop-row"', bridge)

    def test_http_browser_command_allowlist_excludes_direct_stop(self) -> None:
        source = Path(server.__file__).read_text(encoding="utf-8")
        self.assertIn('allowed_commands = {"start", "pause", "resume", "export"}', source)
        self.assertNotIn('allowed_commands = {"start", "pause", "resume", "stop_after_current", "export"}', source)

    def test_bridge_registration_requires_current_runner_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Bridge Identity", "categories": "Beauty | 3760911"})
                    store.update(batch["id"], lambda current: current.update({"runnerBatchName": "current-runner", "overallStatus": "browser_waiting"}))
                    command_id = delivered_start_command(store, batch["id"], "current-runner")
                    valid = {
                        "batch_id": batch["id"],
                        "token": batch["bridgeToken"],
                        "protocol": "browser-bridge-v2",
                        "bridge_version": "2.1.3",
                        "script_version": "2.1.6",
                        "collector_version": "0.4.6.4",
                        "runner_version": "0.3.8.13",
                        "batch_name": "current-runner",
                        "queue_hash": "1234abcd",
                        "command_id": command_id,
                        "execution_mode": "generated_for_command",
                    }
                    invalid = (
                        {"protocol": "browser-bridge-v1"},
                        {"bridge_version": "2.1.1"},
                        {"script_version": "2.1.5"},
                        {"batch_name": "old-runner"},
                        {"queue_hash": ""},
                        {"queue_hash": "not-a-runner-hash"},
                        {"command_id": "0" * 32},
                        {"execution_mode": "unknown"},
                    )
                    for override in invalid:
                        with self.subTest(override=override), self.assertRaises(ValueError):
                            store.register_bridge(**{**valid, **override})
                    self.assertIsNone(store.db.execute("SELECT batch_id FROM bridge_sessions WHERE batch_id=?", (batch["id"],)).fetchone())
                    registered = store.register_bridge(**valid)
                    self.assertTrue(registered["ok"])
                    row = store.db.execute("SELECT script_version,command_id,execution_mode,queue_hash,status FROM bridge_sessions WHERE batch_id=?", (batch["id"],)).fetchone()
                    self.assertEqual(row["script_version"], "2.1.6")
                    self.assertEqual(row["command_id"], command_id)
                    self.assertEqual(row["execution_mode"], "generated_for_command")
                    self.assertEqual(row["queue_hash"], "1234abcd")
                    self.assertEqual(row["status"], "connected")
                    with self.assertRaisesRegex(ValueError, "非本次 Start 命令"):
                        store.heartbeat(batch["id"], batch["bridgeToken"], {
                            "protocol": "browser-bridge-v2", "bridgeVersion": "2.1.3", "scriptVersion": "2.1.6",
                            "batchName": "current-runner", "queueHash": "1234abcd", "status": "running",
                            "commandId": "f" * 32, "executionMode": "generated_for_command",
                        })
                    replacement_command_id = delivered_start_command(store, batch["id"], "current-runner")
                    with self.assertRaisesRegex(ValueError, "会话与本次 Start 命令不一致"):
                        store.register_bridge(**{**valid, "command_id": replacement_command_id})
                    with store.db:
                        store.db.execute("UPDATE bridge_sessions SET script_version='2.1.5' WHERE batch_id=?", (batch["id"],))
                    with self.assertRaisesRegex(ValueError, "会话脚本已过期"):
                        store.heartbeat(batch["id"], batch["bridgeToken"], {
                            "protocol": "browser-bridge-v2", "bridgeVersion": "2.1.3", "scriptVersion": "2.1.5",
                            "batchName": "current-runner", "queueHash": "1234abcd", "status": "running",
                            **bridge_attempt(store, batch["id"]),
                        })
                finally:
                    store.db.close()

    def test_merged_json_execution_must_match_bridge_request(self) -> None:
        merged = {
            "bridgeExecution": {
                "commandId": "a" * 32,
                "mode": "adopted_existing",
                "recordedAt": "2026-08-22T03:48:00.000Z",
            },
        }
        request = {"commandId": "a" * 32, "executionMode": "adopted_existing"}
        self.assertIsNone(server.validate_merged_bridge_execution(merged, request))
        with self.assertRaisesRegex(ValueError, "执行来源"):
            server.validate_merged_bridge_execution({}, request)
        with self.assertRaisesRegex(ValueError, "执行来源与当前 Bridge 会话不一致"):
            server.validate_merged_bridge_execution(merged, {**request, "commandId": "b" * 32})

    def test_existing_session_cannot_switch_execution_mode_for_same_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Execution Mode", "categories": "Beauty | 3760911"})
                    store.update(batch["id"], lambda current: current.update({"runnerBatchName": "current-runner", "overallStatus": "browser_waiting"}))
                    register_test_bridge(store, batch, "current-runner", "1234abcd")
                    attempt = bridge_attempt(store, batch["id"])
                    with self.assertRaisesRegex(ValueError, "会话与本次 Start 命令不一致"):
                        store.register_bridge(
                            batch["id"], batch["bridgeToken"], "browser-bridge-v2", "2.1.3",
                            "0.4.6.4", "0.3.8.13", "current-runner", "1234abcd",
                            attempt["commandId"], "adopted_existing",
                        )
                finally:
                    store.db.close()

    def test_stale_bridge_data_cannot_mutate_current_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Stale Telemetry", "categories": "Beauty | 3760911"})
                    store.update(batch["id"], lambda current: current.update({"runnerBatchName": "current-runner", "overallStatus": "browser_waiting"}))
                    register_test_bridge(store, batch, "current-runner", "1234abcd")
                    baseline_events = store.db.execute("SELECT COUNT(*) AS count FROM events WHERE batch_id=?", (batch["id"],)).fetchone()["count"]
                    stale = {
                        "protocol": "browser-bridge-v2", "bridgeVersion": "2.1.3", "scriptVersion": "2.1.6",
                        "collectorVersion": "0.4.6.4", "runnerVersion": "0.3.8.13",
                        "batchName": "old-runner", "queueHash": "1234abcd", "status": "done",
                        "token": batch["bridgeToken"], "batchId": batch["id"], "eventType": "done",
                        **bridge_attempt(store, batch["id"]),
                    }
                    with self.assertRaisesRegex(ValueError, "非当前批次"):
                        store.heartbeat(batch["id"], batch["bridgeToken"], stale)
                    with mock.patch.object(server, "STORE", store), self.assertRaisesRegex(ValueError, "非当前批次"):
                        server.bridge_event(batch["id"], stale)
                    unchanged = store.get(batch["id"])
                    self.assertEqual(unchanged["stages"]["browser"]["status"], "waiting")
                    self.assertEqual(unchanged["stages"]["browser"].get("stats", {}), {})
                    self.assertEqual(unchanged["overallStatus"], "browser_waiting")
                    self.assertEqual(store.db.execute("SELECT COUNT(*) AS count FROM events WHERE batch_id=?", (batch["id"],)).fetchone()["count"], baseline_events)
                finally:
                    store.db.close()

    def test_valid_done_waits_for_verified_json_and_does_not_persist_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Verified Done", "categories": "Beauty | 3760911"})
                    store.update(batch["id"], lambda current: current.update({"runnerBatchName": "current-runner", "overallStatus": "browser_waiting"}))
                    register_test_bridge(store, batch, "current-runner", "1234abcd")
                    telemetry = {
                        "protocol": "browser-bridge-v2", "bridgeVersion": "2.1.3", "scriptVersion": "2.1.6",
                        "collectorVersion": "0.4.6.4", "runnerVersion": "0.3.8.13",
                        "batchName": "current-runner", "queueHash": "1234abcd", "status": "done",
                        "completed": 2, "qualifiedCount": 1, "token": batch["bridgeToken"],
                        "batchId": batch["id"], "stats": {"token": "must-not-persist"},
                        **bridge_attempt(store, batch["id"]),
                    }
                    store.heartbeat(batch["id"], batch["bridgeToken"], telemetry)
                    waiting = store.get(batch["id"])
                    self.assertEqual(waiting["stages"]["browser"]["status"], "running")
                    self.assertEqual(waiting["overallStatus"], "running")
                    self.assertNotIn("token", waiting["stages"]["browser"]["stats"])
                    self.assertNotIn("batchId", waiting["stages"]["browser"]["stats"])
                    self.assertNotIn("stats", waiting["stages"]["browser"]["stats"])
                    session = store.db.execute("SELECT status FROM bridge_sessions WHERE batch_id=?", (batch["id"],)).fetchone()
                    self.assertEqual(session["status"], "connected")
                    merged = {
                        "schemaVersion": "sellerSpriteIntegratedBatch/v0.3.0",
                        "batchName": "current-runner", "queueHash": "1234abcd",
                        "status": "done",
                        "runnerVersion": "0.3.8.13", "collectorVersion": "0.4.6.4",
                        "results": [{"targetAsin": "B000000001", "qualified": True}],
                    }
                    with mock.patch.object(server, "STORE", store):
                        server.store_merged_json(batch["id"], merged, "browser")
                    completed = store.get(batch["id"])
                    self.assertEqual(completed["stages"]["browser"]["status"], "completed")
                    self.assertEqual(completed["overallStatus"], "excel_ready")
                finally:
                    store.db.close()

    def test_browser_start_reset_clears_only_stale_attempt_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Reset Browser", "categories": "Beauty | 3760911"})
                    queue = root / "formal" / "runs" / "reset" / "candidate_pool" / "runner_queue_approved.txt"
                    queue.parent.mkdir(parents=True)
                    queue.write_text("B000000001\nB000000002\n", encoding="ascii")
                    def corrupt(current: dict) -> None:
                        server.set_stage(current, "candidates", "completed", "approved", {"queuePath": str(queue)})
                        current["runnerBatchName"] = "old-runner"
                        current["mergedJsonPath"] = ""
                        current["jsonHandoff"] = {"sourceSha256": "", "pasteVerified": False}
                        current["stages"]["browser"] = {"status": "needs_attention", "stats": {"completed": 379}, "artifacts": {"stale": "old"}}
                        current["stages"]["excel"] = {"status": "ready", "stats": {"qualified": 0}, "artifacts": {"workbookPath": "old.xlsx"}}
                        current["overallStatus"] = "needs_attention"
                    store.update(batch["id"], corrupt)
                    register_test_bridge(store, batch, "old-runner", "deadbeef")
                    payload = server.runner_command_payload(store.get(batch["id"]))
                    with mock.patch.object(server, "STORE", store):
                        reset = server.reset_browser_for_start(batch["id"], payload)
                    self.assertEqual(reset["stages"]["candidates"]["status"], "completed")
                    self.assertEqual(reset["stages"]["browser"]["status"], "waiting")
                    self.assertEqual(reset["stages"]["browser"]["stats"], {})
                    self.assertEqual(reset["stages"]["browser"]["artifacts"], {})
                    self.assertEqual(reset["stages"]["excel"]["status"], "idle")
                    self.assertEqual(reset["mergedJsonPath"], "")
                    self.assertFalse(reset["jsonHandoff"]["pasteVerified"])
                    self.assertEqual(reset["runnerBatchName"], payload["batchName"])
                    self.assertEqual(reset["runnerQueueSha256"], payload["queueSha256"])
                    self.assertEqual(reset["overallStatus"], "browser_waiting")
                    self.assertIsNone(store.db.execute("SELECT batch_id FROM bridge_sessions WHERE batch_id=?", (batch["id"],)).fetchone())
                finally:
                    store.db.close()

    def test_browser_start_reset_refuses_already_delivered_runner_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Delivered Browser", "categories": "Beauty | 3760911"})
                    queue = root / "formal" / "runs" / "delivered" / "candidate_pool" / "runner_queue_approved.txt"
                    queue.parent.mkdir(parents=True)
                    queue.write_text("B000000001\n", encoding="ascii")

                    def delivered(current: dict) -> None:
                        server.set_stage(current, "candidates", "completed", "approved", {"queuePath": str(queue)})
                        current["runnerBatchName"] = "delivered-runner"
                        current["stages"]["browser"]["status"] = "completed"
                        current["jsonHandoff"] = {"sourcePath": "browser/merged_source.json", "sourceSha256": "abc"}
                        current["overallStatus"] = "excel_ready"

                    store.update(batch["id"], delivered)
                    payload = server.runner_command_payload(store.get(batch["id"]))
                    with mock.patch.object(server, "STORE", store), self.assertRaisesRegex(ValueError, "不能重复启动"):
                        server.reset_browser_for_start(batch["id"], payload)
                    unchanged = store.get(batch["id"])
                    self.assertEqual(unchanged["stages"]["browser"]["status"], "completed")
                    self.assertEqual(unchanged["jsonHandoff"]["sourceSha256"], "abc")
                finally:
                    store.db.close()

    def test_recent_heartbeat_keeps_the_single_bridge_lease(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    first = store.create({"name": "Lease One", "categories": "Beauty | 3760911"})
                    second = store.create({"name": "Lease Two", "categories": "Home Storage | 3760901"})
                    store.update(first["id"], lambda current: current.update({"runnerBatchName": "runner-one"}))
                    store.update(second["id"], lambda current: current.update({"runnerBatchName": "runner-two"}))
                    register_test_bridge(store, first, "runner-one", "1111aaaa")
                    store.heartbeat(first["id"], first["bridgeToken"], {
                        "protocol": "browser-bridge-v2", "bridgeVersion": "2.1.3", "scriptVersion": "2.1.6",
                        "collectorVersion": "0.4.6.4", "runnerVersion": "0.3.8.13",
                        "batchName": "runner-one", "queueHash": "1111aaaa", "status": "running",
                        **bridge_attempt(store, first["id"]),
                    })
                    with self.assertRaisesRegex(ValueError, "已被批次"):
                        register_test_bridge(store, second, "runner-two", "2222bbbb")
                finally:
                    store.db.close()

    def test_outdated_bridge_cannot_consume_a_pending_start_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "BROWSER_PAIRING_TOKEN", "pairing-test"),
            ):
                store = server.SQLiteWorkflowStore()
                try:
                    batch = store.create({"name": "Version Gated Poll", "categories": "Beauty | 3760911"})
                    command = store.enqueue_command(batch["id"], "start", {"batchName": "current-runner"})
                    with self.assertRaisesRegex(ValueError, "协议 2.1.3 / 脚本 2.1.6"):
                        store.poll_global_commands("pairing-test", "browser-bridge-v2", "2.1.1")
                    status = store.db.execute("SELECT status FROM commands WHERE id=?", (command["id"],)).fetchone()["status"]
                    self.assertEqual(status, "pending")
                    with self.assertRaisesRegex(ValueError, "脚本 2.1.6"):
                        store.poll_global_commands("pairing-test", "browser-bridge-v2", "2.1.3", "2.1.3")
                    status = store.db.execute("SELECT status FROM commands WHERE id=?", (command["id"],)).fetchone()["status"]
                    self.assertEqual(status, "pending")
                    delivered = store.poll_global_commands("pairing-test", "browser-bridge-v2", "2.1.3", "2.1.6")
                    self.assertEqual([item["id"] for item in delivered], [command["id"]])
                finally:
                    store.db.close()

    def test_store_create_persists_a_batch_without_running_any_command(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.xlsx"
            source.write_bytes(b"xlsx")
            with mock.patch.object(server, "DATA_DIR", root / "data"), mock.patch.object(server, "DB_PATH", root / "data" / "console.db"), mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"):
                store = server.SQLiteWorkflowStore()
                batch = store.create({
                    "name": "Smoke Batch",
                    "sourceXlsx": str(source),
                    "sourceUrl": "https://www.sellersprite.com/v3/product-research?market=US&maxReviews=60&nodeIdPaths=%5B%22228013%22%5D",
                    "targetQualified": "6",
                })
                self.assertEqual(batch["overallStatus"], "created")
                row = store.db.execute("SELECT id FROM runs WHERE id=?", (batch["id"],)).fetchone()
                self.assertIsNotNone(row)
                store.db.close()

    def test_set_stage_updates_overall_state_and_completion_time(self) -> None:
        batch = {"stages": {"candidates": {"status": "idle"}, "browser": {"status": "waiting"}, "excel": {"status": "idle"}}, "overallStatus": "created"}
        server.set_stage(batch, "candidates", "completed", "队列完成", {"queueCount": 10})
        self.assertEqual(batch["overallStatus"], "browser_waiting")
        self.assertEqual(batch["stages"]["candidates"]["artifacts"]["queueCount"], 10)
        server.set_stage(batch, "browser", "completed", "采集完成", {})
        self.assertEqual(batch["overallStatus"], "excel_ready")
        server.set_stage(batch, "excel", "completed", "表格完成", {})
        self.assertEqual(batch["overallStatus"], "completed")
        self.assertIn("completedAt", batch["stages"]["excel"])

    def test_late_local_process_callback_cannot_revive_stopped_batch(self) -> None:
        for overall_status in ("completed", "cancelled", "stopping"):
            with self.subTest(overall_status=overall_status):
                batch = {
                    "overallStatus": overall_status,
                    "stages": {
                        "candidates": {"status": "cancelled", "artifacts": {}},
                        "browser": {"status": "waiting", "artifacts": {}},
                        "excel": {"status": "idle", "artifacts": {}},
                    },
                }
                server.set_stage_if_mutable(batch, "candidates", "needs_attention", "late completion", {"queueCount": 10})
                self.assertEqual(batch["overallStatus"], overall_status)
                self.assertEqual(batch["stages"]["candidates"]["status"], "cancelled")
                self.assertNotIn("queueCount", batch["stages"]["candidates"]["artifacts"])

    def test_direct_import_success_requires_rows_and_counts_embedded_media(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            replay = Path(temp) / "replay"
            replay.mkdir()
            (replay / "final_candidates_data.json").write_text('[{"asin":"B000000001"}]', encoding="utf-8")
            (replay / "run_summary.json").write_text(
                '{"directImport":true,"importMode":"browser-qualified"}', encoding="utf-8"
            )
            workbook = replay / "runner_candidates_unaccepted_smoke.xlsx"
            with zipfile.ZipFile(workbook, "w") as archive:
                archive.writestr("xl/media/image1.png", b"png")
            (replay / "workbook_build_report.json").write_text(json.dumps({
                "finalXlsx": str(workbook),
                "finalXlsxSha256": hashlib.sha256(workbook.read_bytes()).hexdigest(),
                "candidateProfileVersion": "runner-unaccepted-workbook-v1.0.0",
                "candidateStatus": "runner_pass_unaccepted",
                "acceptance": "not_run_by_user_mode",
                "finalDataSha256": hashlib.sha256((replay / "final_candidates_data.json").read_bytes()).hexdigest(),
                "runSummarySha256": hashlib.sha256((replay / "run_summary.json").read_bytes()).hexdigest(),
            }), encoding="utf-8")
            result = server.direct_import_success(replay)
            self.assertEqual(result["rowCount"], 1)
            self.assertEqual(result["embeddedImageCount"], 1)
            self.assertEqual(result["acceptance"], "not_run_by_user_mode")

            with zipfile.ZipFile(workbook, "w") as archive:
                archive.writestr("xl/media/image1.png", b"png")
                archive.writestr("xl/media/image2.png", b"png")
            report = json.loads((replay / "workbook_build_report.json").read_text(encoding="utf-8"))
            report["finalXlsxSha256"] = hashlib.sha256(workbook.read_bytes()).hexdigest()
            (replay / "workbook_build_report.json").write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "主图嵌入数量与导入行数不一致"):
                server.direct_import_success(replay)

    def test_browser_qualified_workbook_requires_explicit_unaccepted_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            replay = Path(temp) / "replay"
            replay.mkdir()
            (replay / "final_candidates_data.json").write_text('[{"asin":"B000000001"}]', encoding="utf-8")
            (replay / "run_summary.json").write_text(
                '{"directImport":true,"importMode":"browser-qualified"}', encoding="utf-8"
            )
            workbook = replay / "runner_candidates_unaccepted_smoke.xlsx"
            with zipfile.ZipFile(workbook, "w") as archive:
                archive.writestr("xl/media/image1.png", b"png")
            for invalid_summary in (
                {"directImport": True},
                {"directImport": True, "importMode": "strict-pass"},
                {"directImport": False, "importMode": "browser-qualified"},
            ):
                with self.subTest(invalid_summary=invalid_summary):
                    (replay / "run_summary.json").write_text(
                        json.dumps(invalid_summary), encoding="utf-8"
                    )
                    with self.assertRaisesRegex(ValueError, "必须明确为 browser-qualified"):
                        server.direct_import_success(replay)
            (replay / "run_summary.json").write_text(
                '{"directImport":true,"importMode":"browser-qualified"}', encoding="utf-8"
            )
            (replay / "workbook_build_report.json").write_text(
                json.dumps({"finalXlsx": str(workbook), "candidateStatus": "strict_final_accepted"}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "缺少未验收标记"):
                server.direct_import_success(replay)

            verified_profile = {
                "candidateProfileVersion": "runner-unaccepted-workbook-v1.0.0",
                "candidateStatus": "runner_pass_unaccepted",
                "acceptance": "not_run_by_user_mode",
                "finalDataSha256": hashlib.sha256((replay / "final_candidates_data.json").read_bytes()).hexdigest(),
                "runSummarySha256": hashlib.sha256((replay / "run_summary.json").read_bytes()).hexdigest(),
            }
            (replay / "workbook_build_report.json").write_text(
                json.dumps(verified_profile), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "缺少 finalXlsx"):
                server.direct_import_success(replay)

            old_name = replay / "final_candidates_smoke.xlsx"
            old_name.write_bytes(workbook.read_bytes())
            (replay / "workbook_build_report.json").write_text(json.dumps({
                **verified_profile,
                "finalXlsx": str(old_name),
                "finalXlsxSha256": hashlib.sha256(old_name.read_bytes()).hexdigest(),
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "文件名缺少未验收标记"):
                server.direct_import_success(replay)

            outside = Path(temp) / "runner_candidates_unaccepted_outside.xlsx"
            outside.write_bytes(workbook.read_bytes())
            (replay / "workbook_build_report.json").write_text(json.dumps({
                **verified_profile,
                "finalXlsx": str(outside),
                "finalXlsxSha256": hashlib.sha256(outside.read_bytes()).hexdigest(),
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "当前直接导入回放目录"):
                server.direct_import_success(replay)

            valid_report = {
                **verified_profile,
                "finalXlsx": str(workbook),
                "finalXlsxSha256": hashlib.sha256(workbook.read_bytes()).hexdigest(),
            }
            (replay / "workbook_build_report.json").write_text(
                json.dumps(valid_report), encoding="utf-8"
            )
            result = server.direct_import_success(replay)
            self.assertEqual(result["acceptance"], "not_run_by_user_mode")

            original_data = (replay / "final_candidates_data.json").read_bytes()
            (replay / "final_candidates_data.json").write_text('[{"asin":"B000000002"}]', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "候选数据与构建报告不一致"):
                server.direct_import_success(replay)
            (replay / "final_candidates_data.json").write_bytes(original_data)

            workbook.write_bytes(workbook.read_bytes() + b"tampered")
            with self.assertRaisesRegex(ValueError, "指纹与构建报告不一致"):
                server.direct_import_success(replay)

    def test_browser_qualified_builder_has_fail_closed_unaccepted_labels(self) -> None:
        source = server.BUILD_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("runner-unaccepted-workbook-v1.0.0", source)
        self.assertIn("Runner通过_未做A-F验收", source)
        self.assertIn("Runner通过，未做最终A-F验收", source)
        self.assertIn("runner_candidates_unaccepted", source)
        self.assertIn("Direct-import workbook requires an explicit supported importMode", source)
        self.assertIn("Any explicit importMode requires directImport=true", source)
        self.assertIn("RunnerCandidatesUnaccepted", source)

    def test_builder_rejects_ambiguous_direct_import_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            replay = Path(temp) / "replay"
            replay.mkdir()
            (replay / "final_candidates_data.json").write_text("[]", encoding="utf-8")
            (replay / "rejected_audit_data.json").write_text("[]", encoding="utf-8")
            invalid_summaries = (
                {"importMode": "strict-pass"},
                {"directImport": False, "importMode": "strict-pass"},
                {"directImport": "true", "importMode": "strict-pass"},
                {"directImport": 1, "importMode": "strict-pass"},
                {"directImport": True},
            )
            for invalid_summary in invalid_summaries:
                with self.subTest(invalid_summary=invalid_summary):
                    (replay / "run_summary.json").write_text(
                        json.dumps(invalid_summary), encoding="utf-8"
                    )
                    result = subprocess.run(
                        [str(server.NODE_EXE), str(server.BUILD_SCRIPT), str(replay)],
                        cwd=str(server.PROJECT_ROOT), capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=20,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertRegex(result.stderr, "directImport|importMode")

    def test_browser_qualified_builder_emits_unaccepted_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            replay = Path(temp) / "replay"
            replay.mkdir()
            image = replay / "B000000001.png"
            image.write_bytes(base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z3T8AAAAASUVORK5CYII="
            ))
            rows = [{
                "asin": "B000000001",
                "cnTitle": "简易收纳架",
                "product": {
                    "title": "Simple organizer",
                    "dimensions": "1 x 1 x 1 in",
                    "priceTrend": "稳定",
                    "priceTrendClass": "stable",
                },
                "traffic": {},
                "imagePath": str(image),
            }]
            (replay / "final_candidates_data.json").write_text(
                json.dumps(rows, ensure_ascii=False), encoding="utf-8"
            )
            (replay / "rejected_audit_data.json").write_text("[]", encoding="utf-8")
            (replay / "run_summary.json").write_text(json.dumps({
                "runId": "smoke",
                "runDate": "2026-08-22",
                "targetN": 1,
                "qualifiedCount": 1,
                "attempts": 1,
                "rejectedCount": 0,
                "completedTarget": True,
                "directImport": True,
                "importMode": "browser-qualified",
            }), encoding="utf-8")
            env = os.environ.copy()
            env["SELLERSPRITE_WORKBOOK_FORCE_EXIT_V1"] = "1"
            result = subprocess.run(
                [str(server.NODE_EXE), str(server.BUILD_SCRIPT), str(replay)],
                cwd=str(server.PROJECT_ROOT), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=120, env=env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((replay / "workbook_build_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["candidateProfileVersion"], "runner-unaccepted-workbook-v1.0.0")
            self.assertEqual(report["candidateStatus"], "runner_pass_unaccepted")
            self.assertEqual(report["acceptance"], "not_run_by_user_mode")
            self.assertEqual(
                report["finalDataSha256"], hashlib.sha256((replay / "final_candidates_data.json").read_bytes()).hexdigest()
            )
            self.assertEqual(
                report["runSummarySha256"], hashlib.sha256((replay / "run_summary.json").read_bytes()).hexdigest()
            )
            self.assertEqual(Path(report["finalXlsx"]).name, "runner_candidates_unaccepted_smoke.xlsx")
            self.assertEqual(
                report["finalXlsxSha256"], hashlib.sha256(Path(report["finalXlsx"]).read_bytes()).hexdigest()
            )
            with zipfile.ZipFile(report["finalXlsx"]) as archive:
                xml_text = "\n".join(
                    archive.read(name).decode("utf-8", errors="replace")
                    for name in archive.namelist() if name.endswith(".xml")
                )
            self.assertIn("Runner通过_未做A-F验收", xml_text)
            self.assertIn("Runner通过，未做最终A-F验收", xml_text)
            self.assertIn("Runner通过", xml_text)
            self.assertIn("未执行", xml_text)
            self.assertNotIn("实际合格", xml_text)
            self.assertNotIn("Amazon美国站最终合格候选品", xml_text)

    def test_browser_artifact_rejects_malformed_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "batch.json"
            path.write_text('{"results": "not-a-list"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                server.browser_artifact(path, "abc123abc123")

    def test_preflight_uses_configured_subprocess_window_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            preflight_script = root / "preflight.py"
            preflight_script.write_text("", encoding="utf-8")
            completed = subprocess.CompletedProcess([], 0, stdout='{"ok": true}', stderr="")
            with (
                mock.patch.object(server, "PROJECT_ROOT", root),
                mock.patch.object(server, "PREFLIGHT_SCRIPT", preflight_script),
                mock.patch.object(server, "ACTIVE_COLLECTOR_SCRIPT", root / "missing-collector.js"),
                mock.patch.object(server, "ACTIVE_RUNNER_SCRIPT", root / "missing-runner.js"),
                mock.patch.object(server.subprocess, "run", return_value=completed) as run,
            ):
                server.preflight()
            self.assertEqual(run.call_args.kwargs["creationflags"], server.SUBPROCESS_CREATION_FLAGS)
            if os.name == "nt" and server.ENABLE_WINDOWS_NO_CONSOLE:
                self.assertEqual(server.SUBPROCESS_CREATION_FLAGS, subprocess.CREATE_NO_WINDOW)

    def test_preflight_snapshot_is_non_blocking_and_single_flight(self) -> None:
        server._reset_preflight_cache_for_tests()
        entered = threading.Event()
        release = threading.Event()
        calls: list[int] = []
        payload = {"ok": True, "configuredBrowserPair": {"formalRunAuthorized": False}}

        def slow_preflight() -> dict:
            calls.append(1)
            entered.set()
            release.wait(2)
            return payload

        try:
            with mock.patch.object(server, "preflight", side_effect=slow_preflight), mock.patch.object(server, "ENABLE_PREFLIGHT_CACHE", True):
                started = server.time.monotonic()
                first, first_meta = server.preflight_snapshot()
                elapsed = server.time.monotonic() - started
                self.assertLess(elapsed, 0.5)
                self.assertFalse(first["ok"])
                self.assertIn(first_meta["status"], {"checking", "refreshing"})
                self.assertTrue(entered.wait(1))
                second, second_meta = server.preflight_snapshot()
                self.assertFalse(second["ok"])
                self.assertIn(second_meta["status"], {"checking", "refreshing"})
                self.assertEqual(len(calls), 1)
                release.set()
                deadline = server.time.monotonic() + 2
                while server.time.monotonic() < deadline:
                    with server.PREFLIGHT_CACHE_LOCK:
                        if not server.PREFLIGHT_CACHE_IN_FLIGHT:
                            break
                    server.time.sleep(0.01)
                with server.PREFLIGHT_CACHE_LOCK:
                    self.assertFalse(server.PREFLIGHT_CACHE_IN_FLIGHT)
                ready, ready_meta = server.preflight_snapshot()
                self.assertEqual(ready, payload)
                self.assertEqual(ready_meta["status"], "ready")
        finally:
            release.set()
            server._reset_preflight_cache_for_tests()

    def test_preflight_snapshot_retains_last_result_on_refresh_failure(self) -> None:
        server._reset_preflight_cache_for_tests()
        good = {"ok": True, "configuredBrowserPair": {"formalRunAuthorized": False}}
        try:
            with mock.patch.object(server, "preflight", return_value=good), mock.patch.object(server, "ENABLE_PREFLIGHT_CACHE", True):
                self.assertEqual(server.refresh_preflight_cache_sync(), good)
            with server.PREFLIGHT_CACHE_LOCK:
                server.PREFLIGHT_CACHE_CHECKED_AT = server.time.time() - server.PREFLIGHT_CACHE_TTL_SECONDS - 1
            entered = threading.Event()

            def failing_preflight() -> dict:
                entered.set()
                raise RuntimeError("模拟预检失败")

            with mock.patch.object(server, "preflight", side_effect=failing_preflight), mock.patch.object(server, "ENABLE_PREFLIGHT_CACHE", True):
                cached, meta = server.preflight_snapshot()
                self.assertEqual(cached, good)
                self.assertIn(meta["status"], {"stale", "refreshing"})
                self.assertTrue(entered.wait(1))
                deadline = server.time.monotonic() + 2
                while server.time.monotonic() < deadline:
                    with server.PREFLIGHT_CACHE_LOCK:
                        if not server.PREFLIGHT_CACHE_IN_FLIGHT:
                            break
                    server.time.sleep(0.01)
                cached, failed_meta = server.preflight_snapshot()
                self.assertEqual(cached, good)
                self.assertEqual(failed_meta["status"], "failed")
                self.assertIn("模拟预检失败", failed_meta["lastError"])
        finally:
            server._reset_preflight_cache_for_tests()

    def test_direct_import_script_supports_explicit_browser_qualified_mode(self) -> None:
        script = Path(__file__).resolve().parents[1] / "direct_import_batch_to_replay.mjs"
        source = script.read_text(encoding="utf-8")
        self.assertIn('"browser-qualified"', source)
        self.assertIn("importMode", source)

    def test_browser_qualified_mode_imports_without_offline_strict_decision(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            images = root / "images"
            replay = root / "replay"
            images.mkdir()
            (images / "B000000001.png").write_bytes(b"png")
            batch = root / "batch.json"
            candidates = root / "candidates.json"
            titles = root / "titles.json"
            batch.write_text(json.dumps({"batchName": "smoke", "results": [{"targetAsin": "B000000001", "qualified": True}]}), encoding="utf-8")
            candidates.write_text(json.dumps([{"asin": "B000000001", "title": "Simple organizer", "image": "https://example.com/image.png"}]), encoding="utf-8")
            titles.write_text(json.dumps({"B000000001": "简易收纳架"}, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run([
                str(server.NODE_EXE),
                str(Path(__file__).resolve().parents[1] / "direct_import_batch_to_replay.mjs"),
                str(batch), str(candidates), str(titles), str(images), str(replay), "smoke", "2026-08-05",
                "--mode", "browser-qualified",
            ], capture_output=True, text=True, encoding="utf-8", timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            summary = json.loads((replay / "run_summary.json").read_text(encoding="utf-8"))
            rows = json.loads((replay / "final_candidates_data.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["importMode"], "browser-qualified")
            self.assertEqual([row["asin"] for row in rows], ["B000000001"])

    def test_http_health_and_validation_error(self) -> None:
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            with urllib.request.urlopen(base + "/api/overview", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertIn("preflight", payload)
            request = urllib.request.Request(base + "/api/batches", data=b'{"name":"missing source"}', headers={"Content-Type": "application/json"}, method="POST")
            with self.assertRaises(urllib.error.HTTPError) as context:
                urllib.request.urlopen(request, timeout=5)
            self.assertEqual(context.exception.code, 400)
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_http_category_pool_import_and_listing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
            ):
                store = server.SQLiteWorkflowStore()
                httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
                thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                thread.start()
                base = f"http://127.0.0.1:{httpd.server_address[1]}"
                try:
                    request = urllib.request.Request(
                        base + "/api/category-pool/import",
                        data=json.dumps({"categories": "Beauty | 3760911"}).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with mock.patch.object(server, "STORE", store):
                        with urllib.request.urlopen(request, timeout=5) as response:
                            imported = json.loads(response.read().decode("utf-8"))
                        with urllib.request.urlopen(base + "/api/category-pool", timeout=5) as response:
                            listed = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(imported["addedCount"], 1)
                    self.assertEqual(listed["counts"]["available"], 1)
                    self.assertEqual(listed["items"][0]["nodeIdPath"], "3760911")
                finally:
                    httpd.shutdown()
                    httpd.server_close()
                    store.db.close()

    def test_repository_flag_off_keeps_legacy_preview_import_http_contract_without_new_tables(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", False),
            ):
                store = server.SQLiteWorkflowStore()
                batch = store.create({"name": "Legacy Visible Batch", "categories": "Legacy Existing | 720"})
                with store.db:
                    store.db.execute("DROP TABLE screened_category_completions")
                    store.db.execute("DROP TABLE screened_categories")
                    store.db.execute("DROP TABLE batch_archive_state")
                    store.db.execute("DROP TABLE feature_audit_events")
                httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
                thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                thread.start()
                base = f"http://127.0.0.1:{httpd.server_address[1]}"

                def post(path: str, payload: dict) -> dict:
                    request = urllib.request.Request(
                        base + path,
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(request, timeout=5) as response:
                        return json.loads(response.read().decode("utf-8"))

                try:
                    with mock.patch.object(server, "STORE", store), mock.patch.object(server, "preflight", return_value={"ok": True}):
                        legacy_raw = "Legacy HTTP A | 721\nLegacy HTTP B | 722"
                        preview = post("/api/category-pool/preview", {"categories": legacy_raw})
                        self.assertFalse(preview["enabled"])
                        self.assertEqual(preview["schemaVersion"], "categoryPoolImportPreview/legacy-v1")
                        self.assertEqual(preview["items"][0]["status"], "ready")
                        self.assertEqual(preview["items"][0]["tone"], "green")
                        self.assertTrue(preview["items"][0]["selectedByDefault"])
                        self.assertEqual(len(preview["selectedKeys"]), 2)

                        imported = post("/api/category-pool/import", {
                            "categories": legacy_raw,
                            "selectedKeys": [preview["items"][0]["key"]],
                            "overrideScreenedKeys": [],
                        })
                        self.assertEqual(imported["addedCount"], 1)
                        self.assertEqual(imported["selectedCount"], 1)
                        self.assertEqual(imported["skippedCount"], 1)

                        with urllib.request.urlopen(base + "/api/overview", timeout=5) as response:
                            overview = json.loads(response.read().decode("utf-8"))
                        self.assertFalse(overview["features"]["categoryRepository"]["enabled"])
                        self.assertEqual(overview["categoryRepository"]["counts"]["categories"], 0)
                        self.assertEqual(overview["archivedBatchCount"], 0)
                        self.assertEqual([item["id"] for item in overview["batches"]], [batch["id"]])
                        self.assertEqual(overview["categoryPoolCounts"]["available"], 1)
                        self.assertEqual(overview["categoryPool"][0]["nodeIdPath"], "721")

                        with urllib.request.urlopen(base + "/api/category-repository", timeout=5) as response:
                            repository = json.loads(response.read().decode("utf-8"))
                        self.assertFalse(repository["enabled"])
                        self.assertEqual(repository["items"], [])
                        with urllib.request.urlopen(base + "/api/batches?archived=1", timeout=5) as response:
                            archived = json.loads(response.read().decode("utf-8"))
                        self.assertEqual(archived["batches"], [])
                        remaining_tables = {
                            row["name"] for row in store.db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                        }
                        self.assertFalse({
                            "screened_category_completions",
                            "screened_categories",
                            "batch_archive_state",
                            "feature_audit_events",
                        } & remaining_tables)
                finally:
                    httpd.shutdown()
                    httpd.server_close()
                    store.db.close()

    def test_http_category_repository_preview_archive_and_restore(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", True),
            ):
                store = server.SQLiteWorkflowStore()
                batch = store.create({"name": "HTTP Complete", "categories": "HTTP Category | 818"})
                complete_test_batch(store, batch["id"])
                httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
                thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                thread.start()
                base = f"http://127.0.0.1:{httpd.server_address[1]}"

                def post(path: str, payload: dict) -> dict:
                    request = urllib.request.Request(
                        base + path,
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(request, timeout=5) as response:
                        return json.loads(response.read().decode("utf-8"))

                try:
                    with mock.patch.object(server, "STORE", store), mock.patch.object(server, "preflight", return_value={"ok": True}):
                        preview = post("/api/category-pool/preview", {"categories": "HTTP Category | 818\nFresh HTTP | 819"})
                        self.assertEqual([item["status"] for item in preview["items"]], ["screened", "ready"])
                        imported = post("/api/category-pool/import", {
                            "categories": "HTTP Category | 818\nFresh HTTP | 819",
                            "selectedKeys": [item["key"] for item in preview["items"]],
                            "overrideScreenedKeys": [preview["items"][0]["key"]],
                        })
                        self.assertEqual(imported["addedCount"], 2)
                        self.assertEqual(imported["overrideScreenedCount"], 1)
                        self.assertEqual([item["outcome"] for item in imported["outcomes"]], ["imported", "imported"])

                        with urllib.request.urlopen(base + "/api/category-repository?q=HTTP", timeout=5) as response:
                            repository = json.loads(response.read().decode("utf-8"))
                        self.assertEqual(repository["counts"]["matched"], 1)
                        self.assertEqual(repository["items"][0]["nodeIdPath"], "818")

                        archived = post(f"/api/batches/{batch['id']}/archive", {})
                        self.assertTrue(archived["archived"])
                        with urllib.request.urlopen(base + "/api/batches?archived=1", timeout=5) as response:
                            archived_list = json.loads(response.read().decode("utf-8"))
                        self.assertEqual([item["id"] for item in archived_list["batches"]], [batch["id"]])

                        with urllib.request.urlopen(base + "/api/overview", timeout=5) as response:
                            overview = json.loads(response.read().decode("utf-8"))
                        self.assertTrue(overview["features"]["categoryRepository"]["enabled"])
                        self.assertEqual(overview["features"]["categoryRepository"]["version"], server.CATEGORY_REPOSITORY_VERSION)
                        self.assertEqual(overview["archivedBatchCount"], 1)
                        self.assertEqual(overview["categoryRepository"]["counts"]["categories"], 1)
                        self.assertEqual(overview["batches"], [])

                        restored = post(f"/api/batches/{batch['id']}/restore", {})
                        self.assertFalse(restored["archived"])
                        with urllib.request.urlopen(base + "/api/batches", timeout=5) as response:
                            active_list = json.loads(response.read().decode("utf-8"))
                        self.assertEqual([item["id"] for item in active_list["batches"]], [batch["id"]])
                finally:
                    httpd.shutdown()
                    httpd.server_close()
                    store.db.close()

    def test_http_bulk_archive_accepts_unfinished_batches_and_rejects_active_set_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", True),
            ):
                store = server.SQLiteWorkflowStore()
                first = store.create({"name": "HTTP Pending One", "categories": "HTTP Pending One | 820"})
                second = store.create({"name": "HTTP Pending Two", "categories": "HTTP Pending Two | 821"})
                command = store.enqueue_command(second["id"], "start", {"batchName": "http-active"})
                httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
                thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                thread.start()
                base = f"http://127.0.0.1:{httpd.server_address[1]}"

                def post(payload: dict) -> dict:
                    request = urllib.request.Request(
                        base + "/api/batches/archive",
                        data=json.dumps(payload).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(request, timeout=5) as response:
                        return json.loads(response.read().decode("utf-8"))

                try:
                    with mock.patch.object(server, "STORE", store):
                        with self.assertRaises(urllib.error.HTTPError) as context:
                            post({"batchIds": [first["id"], second["id"]]})
                        self.assertEqual(context.exception.code, 400)
                        self.assertEqual(store.db.execute("SELECT COUNT(*) FROM batch_archive_state").fetchone()[0], 0)

                        with store.db:
                            store.db.execute("UPDATE commands SET status='failed' WHERE id=?", (command["id"],))
                        archived = post({"batchIds": [first["id"], second["id"]]})
                        self.assertEqual(archived["schemaVersion"], "batchArchiveResult/v2")
                        self.assertEqual(archived["archivedCount"], 2)
                        self.assertTrue(all(batch["archived"] for batch in archived["batches"]))
                finally:
                    httpd.shutdown()
                    httpd.server_close()
                    store.db.close()

    def test_http_archive_request_returns_202_and_exposes_durable_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "PROJECT_ROOT", root / "formal"),
                mock.patch.object(server, "ENABLE_CATEGORY_REPOSITORY", True),
            ):
                store = server.SQLiteWorkflowStore()
                batch = store.create({"name": "HTTP Graceful Delete", "categories": "HTTP Graceful | 932"})
                store.update(batch["id"], lambda current: (
                    current.update({"runnerBatchName": "http-graceful-runner", "overallStatus": "running"}),
                    current["stages"]["browser"].update({"status": "running", "stats": {"status": "running"}}),
                ))
                register_test_bridge(store, batch, "http-graceful-runner", "9320abcd")
                httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
                thread = threading.Thread(target=httpd.serve_forever, daemon=True)
                thread.start()
                base = f"http://127.0.0.1:{httpd.server_address[1]}"
                try:
                    with mock.patch.object(server, "STORE", store):
                        request = urllib.request.Request(
                            base + "/api/batches/archive-request",
                            data=json.dumps({"batchIds": [batch["id"]]}).encode("utf-8"),
                            headers={"Content-Type": "application/json", "Idempotency-Key": "http-graceful-key"},
                            method="POST",
                        )
                        with urllib.request.urlopen(request, timeout=5) as response:
                            self.assertEqual(response.status, 202)
                            result = json.loads(response.read().decode("utf-8"))
                        self.assertEqual(result["schemaVersion"], "batchArchiveRequest/v1")
                        self.assertEqual(result["pendingCount"], 1)
                        with urllib.request.urlopen(base + f"/api/batches/{batch['id']}/archive-request", timeout=5) as response:
                            status = json.loads(response.read().decode("utf-8"))
                        self.assertEqual(status["request"]["requestId"], result["requests"][0]["requestId"])
                        self.assertEqual(status["request"]["status"], "cancelling")

                        legacy_request = urllib.request.Request(
                            base + f"/api/batches/{batch['id']}/archive",
                            data=b"{}",
                            headers={"Content-Type": "application/json"},
                            method="POST",
                        )
                        with urllib.request.urlopen(legacy_request, timeout=5) as response:
                            self.assertEqual(response.status, 202)
                            legacy_pending = json.loads(response.read().decode("utf-8"))
                        self.assertEqual(
                            legacy_pending["requests"][0]["requestId"],
                            result["requests"][0]["requestId"],
                        )

                        heartbeat = {
                            "protocol": "browser-bridge-v2",
                            "bridgeVersion": "2.1.3",
                            "scriptVersion": "2.1.6",
                            "collectorVersion": "0.4.6.4",
                            "runnerVersion": "0.3.8.13",
                            "batchName": "http-graceful-runner",
                            "queueHash": "9320abcd",
                            "status": "done",
                            **bridge_attempt(store, batch["id"]),
                        }
                        store.heartbeat(batch["id"], batch["bridgeToken"], heartbeat)
                        with urllib.request.urlopen(legacy_request, timeout=5) as response:
                            self.assertEqual(response.status, 200)
                            legacy_archived = json.loads(response.read().decode("utf-8"))
                        self.assertTrue(legacy_archived["archived"])
                finally:
                    httpd.shutdown()
                    httpd.server_close()
                    store.db.close()


    def test_dispatch_gates_require_completed_upstream_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            queue = root / "runner_queue.txt"
            merged = root / "merged.json"
            batch = {
                "sourceXlsx": str(root / "source.xlsx"),
                "sourceUrl": "https://www.sellersprite.com/",
                "stages": {
                    "candidates": {"status": "idle", "artifacts": {}},
                    "browser": {"status": "waiting", "stats": {}},
                    "excel": {"status": "idle"},
                },
                "mergedJsonPath": "",
            }
            with mock.patch.object(server, "preflight", return_value={"ok": True}):
                self.assertTrue(server.dispatch_gate(batch, "candidates")["allowed"])
            self.assertFalse(server.dispatch_gate(batch, "browser")["allowed"])
            queue.write_text("B000000001\n", encoding="ascii")
            batch["stages"]["candidates"] = {
                "status": "completed",
                "artifacts": {"queuePath": str(queue), "queueCount": 1},
            }
            with mock.patch.object(server, "preflight", return_value={"configuredBrowserPair": {"technicalReady": True, "formalRunAuthorized": False}}):
                blocked = server.dispatch_gate(batch, "browser")
            self.assertFalse(blocked["allowed"])
            self.assertIn("30-ASIN", blocked["reason"])
            with mock.patch.object(server, "preflight", return_value={"configuredBrowserPair": {"technicalReady": True, "formalRunAuthorized": True}}):
                self.assertTrue(server.dispatch_gate(batch, "browser")["allowed"])
            self.assertFalse(server.dispatch_gate(batch, "excel")["allowed"])
            merged.write_text('{"results":[]}', encoding="utf-8")
            batch["mergedJsonPath"] = str(merged)
            batch["stages"]["browser"] = {"status": "completed", "stats": {"qualifiedCount": 0}}
            self.assertTrue(server.dispatch_gate(batch, "excel")["allowed"])

    def test_thread_registry_and_dispatch_are_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.xlsx"
            source.write_bytes(b"xlsx")
            with (
                mock.patch.object(server, "DATA_DIR", root / "data"),
                mock.patch.object(server, "DB_PATH", root / "data" / "console.db"),
                mock.patch.object(server, "STATE_PATH", root / "data" / "batches.json"),
                mock.patch.object(server, "preflight", return_value={"ok": True}),
            ):
                store = server.SQLiteWorkflowStore()
                batch = store.create({
                    "name": "Dispatch Smoke",
                    "sourceXlsx": str(source),
                    "sourceUrl": "https://www.sellersprite.com/v3/product-research?market=US&maxReviews=60&nodeIdPaths=%5B%22228013%22%5D",
                })
                threads = store.list_threads()
                self.assertEqual([item["stage"] for item in threads], ["candidates", "browser", "excel"])
                self.assertEqual(threads[0]["threadId"], "019fb762-cbea-7aa2-b83d-3be19117dea4")
                dispatch = store.prepare_dispatch(batch["id"], "candidates", "smoke")
                self.assertIn("runner_queue.txt", dispatch["prompt"])
                self.assertIn("A-F", dispatch["prompt"])
                updated = store.update_dispatch_status(dispatch["id"], "sent")
                self.assertEqual(updated["status"], "sent")
                self.assertEqual(store.list_threads()[0]["status"], "queued")
                store.db.close()

if __name__ == "__main__":
    unittest.main()
