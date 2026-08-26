import sys, os, tempfile, time, json
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from cache_store import Cache, sellersprite_cache, product_meta_cache


def make_root():
    return tempfile.mkdtemp()


def test_write_then_read():
    root = make_root()
    c = Cache(root, "sellersprite", ttl_hours=168)
    c.write("B0GXGWNXBH", {"latestPct": 82.3, "pass70": True})
    out = c.read("B0GXGWNXBH")
    assert out["latestPct"] == 82.3
    assert out["pass70"] is True
    assert out["cachedAt"]
    assert out["cacheKind"] == "sellersprite"


def test_miss_returns_none():
    root = make_root()
    c = Cache(root, "sellersprite", ttl_hours=168)
    assert c.read("B0GXGWNXBH") is None
    assert c.hit("B0GXGWNXBH") is False
    assert c.age_hours("B0GXGWNXBH") is None


def test_ttl_expiry():
    root = make_root()
    # TTL = 1 秒 (1/3600 小时), sleep 1.5s 保证越过过期线
    c = Cache(root, "sellersprite", ttl_hours=1.0 / 3600.0)
    c.write("B0GXGWNXBH", {"x": 1})
    assert c.hit("B0GXGWNXBH"), f"just written should hit, age={c.age_hours('B0GXGWNXBH')}"
    time.sleep(1.5)
    assert not c.hit("B0GXGWNXBH"), f"after 1.5s should expire, age={c.age_hours('B0GXGWNXBH')}"
    assert c.read("B0GXGWNXBH") is None


def test_invalidate():
    root = make_root()
    c = Cache(root, "sellersprite", ttl_hours=168)
    c.write("B0GXGWNXBH", {"x": 1})
    c.invalidate("B0GXGWNXBH")
    assert c.read("B0GXGWNXBH") is None
    # 二次调用不该崩
    c.invalidate("B0GXGWNXBH")


def test_two_kinds_isolated():
    root = make_root()
    a = sellersprite_cache(root, ttl_hours=168)
    b = product_meta_cache(root, ttl_hours=24)
    a.write("B0GXGWNXBH", {"kind_a": True})
    b.write("B0GXGWNXBH", {"kind_b": True})
    assert a.read("B0GXGWNXBH")["kind_a"] is True
    assert b.read("B0GXGWNXBH")["kind_b"] is True
    assert "kind_b" not in a.read("B0GXGWNXBH")


def test_invalid_asin_raises():
    root = make_root()
    c = Cache(root, "sellersprite", ttl_hours=168)
    try:
        c.write("bad", {})
        assert False, "should have raised"
    except ValueError:
        pass


def test_corrupt_json_treated_as_miss():
    root = make_root()
    c = Cache(root, "sellersprite", ttl_hours=168)
    (c.root / "B0GXGWNXBH.json").write_text("this is not json", encoding="utf-8")
    assert c.read("B0GXGWNXBH") is None
    assert c.hit("B0GXGWNXBH") is False


def test_stats():
    root = make_root()
    c = Cache(root, "sellersprite", ttl_hours=168)
    c.write("B0GXGWNXBH", {"x": 1})
    c.write("B0GX1XKVDX", {"x": 2})
    s = c.stats()
    assert s["kind"] == "sellersprite"
    assert s["total"] == 2
    assert s["fresh"] == 2
    assert s["stale"] == 0
    assert s["ttlHours"] == 168


def test_write_preserves_payload_shape():
    root = make_root()
    c = Cache(root, "sellersprite", ttl_hours=168)
    payload = {
        "targetAsin": "B0GXGWNXBH",
        "status": "ok",
        "latestNaturalSharePct": 89.9,
        "recent4AvgNaturalSharePct": 85.88,
        "pass70": True,
    }
    c.write("B0GXGWNXBH", payload)
    out = c.read("B0GXGWNXBH")
    for k, v in payload.items():
        assert out[k] == v


if __name__ == "__main__":
    print("run via test runner")
