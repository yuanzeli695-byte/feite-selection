from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "normalize_mcp_shadow_raw.py"
SPEC = importlib.util.spec_from_file_location("normalize_mcp_shadow_raw_test", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load normalizer")
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)


class NormalizeShadowTests(unittest.TestCase):
    def test_latest_uses_newest_nonnegative_point(self) -> None:
        self.assertEqual(MOD.latest([{"timePoint": 2, "value": -1}, {"timePoint": 1, "value": 5}, {"timePoint": 3, "value": 7}]), 7)
        self.assertIsNone(MOD.latest([{"timePoint": 1, "value": -1}]))

    def test_inner_response_fails_closed(self) -> None:
        self.assertEqual(MOD.inner_response({"result": {"isError": True}})["code"], "TRANSPORT_ERROR")


if __name__ == "__main__":
    unittest.main()
