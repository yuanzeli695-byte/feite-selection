from __future__ import annotations

import importlib.util
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "download_candidate_images.py"
SPEC = importlib.util.spec_from_file_location("download_candidate_images_under_test", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"Cannot load module from {SCRIPT_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def image_bytes(color: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), color).save(buffer, format="JPEG")
    return buffer.getvalue()


class DownloadCandidateImagesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.rows = [
            {"asin": "B0AAAA0001", "image": "https://example.com/one.jpg"},
            {"asin": "B0AAAA0002", "image": "https://example.com/two.jpg"},
        ]

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def _response(data: bytes) -> io.BytesIO:
        return io.BytesIO(data)

    def _download(self, output: Path, cache: Path, *, workers: int = 2) -> list[dict[str, object]]:
        return MODULE.download_rows(
            self.rows,
            output_dir=output,
            cache_dir=cache,
            cache_ttl_seconds=3600,
            timeout=5,
            retries=0,
            workers=workers,
        )

    def test_parallel_download_populates_and_reuses_url_keyed_cache(self) -> None:
        cache = self.root / "cache"
        first_output = self.root / "first"
        responses = [self._response(image_bytes((255, 0, 0))), self._response(image_bytes((0, 0, 255)))]
        with mock.patch.object(MODULE.urllib.request, "urlopen", side_effect=responses) as urlopen:
            first = self._download(first_output, cache)
        self.assertEqual(urlopen.call_count, 2)
        self.assertTrue(all(row["status"] == "ok" and row["cacheHit"] is False for row in first))

        second_output = self.root / "second"
        with mock.patch.object(MODULE.urllib.request, "urlopen", side_effect=AssertionError("network used")):
            second = self._download(second_output, cache)
        self.assertTrue(all(row["status"] == "ok" and row["cacheHit"] is True for row in second))
        for row in self.rows:
            asin = str(row["asin"])
            self.assertEqual(
                MODULE.file_sha256(first_output / f"{asin}.png"),
                MODULE.file_sha256(second_output / f"{asin}.png"),
            )

    def test_expired_cache_is_revalidated_from_network(self) -> None:
        cache = self.root / "cache"
        first_output = self.root / "first"
        responses = [self._response(image_bytes((1, 2, 3))), self._response(image_bytes((4, 5, 6)))]
        with mock.patch.object(MODULE.urllib.request, "urlopen", side_effect=responses):
            self._download(first_output, cache, workers=1)
        for path in cache.glob("*.png"):
            os.utime(path, (1, 1))

        second_output = self.root / "second"
        responses = [self._response(image_bytes((7, 8, 9))), self._response(image_bytes((10, 11, 12)))]
        with mock.patch.object(MODULE.urllib.request, "urlopen", side_effect=responses) as urlopen:
            second = self._download(second_output, cache, workers=1)
        self.assertEqual(urlopen.call_count, 2)
        self.assertTrue(all(row["cacheHit"] is False for row in second))

    def test_changed_url_does_not_reuse_same_asin_cache(self) -> None:
        cache = self.root / "cache"
        with mock.patch.object(
            MODULE.urllib.request,
            "urlopen",
            return_value=self._response(image_bytes((1, 1, 1))),
        ):
            MODULE.download_rows(
                [self.rows[0]],
                output_dir=self.root / "first",
                cache_dir=cache,
                cache_ttl_seconds=3600,
                timeout=5,
                retries=0,
                workers=1,
            )
        changed = dict(self.rows[0], image="https://example.com/replaced.jpg")
        with mock.patch.object(
            MODULE.urllib.request,
            "urlopen",
            return_value=self._response(image_bytes((2, 2, 2))),
        ) as urlopen:
            result = MODULE.download_rows(
                [changed],
                output_dir=self.root / "second",
                cache_dir=cache,
                cache_ttl_seconds=3600,
                timeout=5,
                retries=0,
                workers=1,
            )
        self.assertEqual(urlopen.call_count, 1)
        self.assertFalse(result[0]["cacheHit"])
        self.assertEqual(len(list(cache.glob("*.png"))), 2)

    def test_corrupt_cache_is_redownloaded(self) -> None:
        cache = self.root / "cache"
        cache.mkdir()
        row = self.rows[0]
        cached_path = MODULE.cache_path_for(cache, str(row["asin"]), str(row["image"]))
        cached_path.write_bytes(b"not a png")
        with mock.patch.object(
            MODULE.urllib.request,
            "urlopen",
            return_value=self._response(image_bytes((3, 3, 3))),
        ) as urlopen:
            result = MODULE.download_rows(
                [row],
                output_dir=self.root / "output",
                cache_dir=cache,
                cache_ttl_seconds=3600,
                timeout=5,
                retries=0,
                workers=1,
            )
        self.assertEqual(urlopen.call_count, 1)
        self.assertFalse(result[0]["cacheHit"])
        self.assertTrue(MODULE.valid_png(cached_path))


if __name__ == "__main__":
    unittest.main()
