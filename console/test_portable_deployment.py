from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


class PortableDeploymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(ROOT))
        import console.server as server

        cls.server = server

    def test_defaults_are_relative_to_checkout(self) -> None:
        self.assertEqual(self.server.CONSOLE_ROOT, ROOT / "console")
        self.assertEqual(self.server.WORKSPACE_ROOT, ROOT)
        self.assertEqual(self.server.PROJECT_ROOT, ROOT / "pipeline")
        self.assertEqual(self.server.PREFLIGHT_SCRIPT, ROOT / "pipeline" / "scripts" / "preflight.py")
        self.assertEqual(self.server.DIRECT_IMPORT_SCRIPT, ROOT / "direct_import_batch_to_replay.mjs")

    def test_required_portable_entries_exist(self) -> None:
        for relative in (
            "install-client.ps1",
            "start-client.ps1",
            "stop-client.ps1",
            "verify-client.ps1",
            "direct_import_batch_to_replay.mjs",
            "pipeline/scripts/preflight.py",
            "pipeline/config/protected_script_hashes.json",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_protected_script_integrity_matches_manifest(self) -> None:
        report = self.server.protected_script_integrity()
        self.assertTrue(report["ok"], report)
        self.assertTrue(all(report["matches"].values()), report)

    def test_protected_script_integrity_fails_closed_on_tampered_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bridge = root / "browser_bridge_v2.user.js"
            collector = root / "collector.user.js"
            runner = root / "runner.user.js"
            shutil.copy2(self.server.CONSOLE_ROOT / "browser_bridge_v2.user.js", bridge)
            shutil.copy2(self.server.ACTIVE_COLLECTOR_SCRIPT, collector)
            shutil.copy2(self.server.ACTIVE_RUNNER_SCRIPT, runner)
            runner.write_bytes(runner.read_bytes() + b"\n")
            with (
                mock.patch.object(self.server, "CONSOLE_ROOT", root),
                mock.patch.object(self.server, "ACTIVE_COLLECTOR_SCRIPT", collector),
                mock.patch.object(self.server, "ACTIVE_RUNNER_SCRIPT", runner),
            ):
                report = self.server.protected_script_integrity()
        self.assertFalse(report["ok"], report)
        self.assertFalse(report["matches"]["runner"], report)
        self.assertTrue(report["matches"]["bridge"], report)
        self.assertTrue(report["matches"]["collector"], report)

    def test_server_preflight_keeps_both_strict_layers(self) -> None:
        report = self.server.preflight()
        self.assertTrue(report.get("ok"), report)
        self.assertTrue(report["configuredBrowserPair"]["ok"], report)
        self.assertEqual(report["configuredBrowserPair"]["collector"], "0.4.6.4")
        self.assertEqual(report["configuredBrowserPair"]["runner"], "0.3.8.13")
        self.assertTrue(report["configuredBrowserPair"]["scriptIntegrity"]["ok"], report)

    def test_environment_override_is_resolved_without_user_paths(self) -> None:
        env = os.environ.copy()
        env.update(
            {
                "AMAZON_CONSOLE_PROJECT_ROOT": str(ROOT / "pipeline"),
                "AMAZON_CONSOLE_PREFLIGHT_SCRIPT": str(ROOT / "pipeline" / "scripts" / "preflight.py"),
                "AMAZON_CONSOLE_PYTHON_EXE": sys.executable,
                "AMAZON_CONSOLE_NODE_EXE": "node",
                # Force both sides of the pipe to UTF-8: a checkout under a
                # non-ASCII path otherwise round-trips through the active
                # ANSI code page and the assertion compares mojibake.
                "PYTHONIOENCODING": "utf-8",
            }
        )
        result = subprocess.run(
            [sys.executable, "-c", "import console.server as s; print(s.PROJECT_ROOT); print(s.CONSOLE_ROOT)"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(ROOT / "pipeline"), result.stdout)
        self.assertIn(str(ROOT / "console"), result.stdout)


if __name__ == "__main__":
    unittest.main()
