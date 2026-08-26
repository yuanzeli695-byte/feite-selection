"""Phase 1 端到端 smoke test — 无 IO 依赖,证明 config + state + cache 可以联动。

跑法:
    python tests/smoke_phase1.py

不出错就算 Phase 1 通过,Phase 2 可以接入。
"""
import json
import sys
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from state_store import StateStore
from cache_store import sellersprite_cache, product_meta_cache


def load_configs():
    cfg = {}
    for name in ("rules", "exclusions", "pipeline"):
        with (ROOT / "config" / f"{name}.json").open("r", encoding="utf-8") as f:
            cfg[name] = json.load(f)
    return cfg


def check_rules_shape(rules):
    required = {
        "priceMinUsd", "priceMaxUsd", "minRating", "maxReviews",
        "launchAgeMaxDays", "variationsMax", "monthlySalesHardMax",
        "trafficNaturalMinPct", "trafficRecent4AvgMinPct",
        "trafficRecent4MinMinPct", "trafficWeeksReadMin",
        "asinMismatchPolicy", "imageEmbedRequired",
    }
    missing = required - set(rules.keys())
    assert not missing, f"rules.json missing: {missing}"
    assert rules["priceMinUsd"] < rules["priceMaxUsd"]
    assert 0 <= rules["trafficNaturalMinPct"] <= 100
    print("  ✓ rules.json shape OK")


def check_exclusions_shape(exc):
    assert "hardExclusions" in exc
    assert isinstance(exc["hardExclusions"], dict)
    assert len(exc["hardExclusions"]) >= 5, "至少 5 类硬排除"
    assert "reviewFlags" in exc
    assert isinstance(exc["reviewFlags"], dict)
    assert isinstance(exc["hardExclusions"].get("ip_character_risk"), list)
    assert len(exc["hardExclusions"]["ip_character_risk"]) >= 20, "IP 词库应 >=20 条"
    assert "categories" not in exc
    assert "ip_character_keywords" not in exc
    assert "brand_scrutiny" not in exc
    print(f"  ✓ exclusions.json OK — {len(exc['hardExclusions'])} hard exclusions, "
          f"{len(exc['hardExclusions']['ip_character_risk'])} IP keywords, "
          f"{len(exc.get('brandScrutiny', []))} brands to scrutinize")


def check_pipeline_shape(p):
    assert p["targetN"] >= 1
    assert p["maxAttemptTotal"] > p["targetN"]
    assert "candidateSources" in p and len(p["candidateSources"]) >= 1
    assert p["cache"]["sellersprite_ttl_hours"] > 0
    print("  ✓ pipeline.json shape OK")


def check_state_store():
    with tempfile.TemporaryDirectory() as tmp:
        s = StateStore(Path(tmp) / "state.jsonl")
        s.mark("B0GXGWNXBH", "candidate_taken")
        s.mark("B0GXGWNXBH", "prefilter_pass")
        s.mark("B0GXGWNXBH", "excl_pass")
        s.mark("B0GXGWNXBH", "traffic_ok")
        s.mark("B0GXGWNXBH", "hard_pass")
        s.mark("B0GXGWNXBH", "QUALIFIED")

        s.mark("B0GVZ1M77K", "candidate_taken")
        s.mark("B0GVZ1M77K", "prefilter_pass")
        s.mark("B0GVZ1M77K", "excl_pass")
        s.mark("B0GVZ1M77K", "traffic_ok")
        s.mark("B0GVZ1M77K", "hard_fail", reason="pass70=false")

        assert s.current("B0GXGWNXBH") == "QUALIFIED"
        assert s.current("B0GVZ1M77K") == "hard_fail"
        counts = s.count_by_state()
        assert counts.get("QUALIFIED") == 1
        assert counts.get("hard_fail") == 1
        print("  ✓ state_store live cycle OK (2 ASINs, full state history)")


def check_cache_store():
    with tempfile.TemporaryDirectory() as tmp:
        ssc = sellersprite_cache(tmp, ttl_hours=168)
        pmc = product_meta_cache(tmp, ttl_hours=24)

        # 灌入一条真实形状的记录(和 v0.2.0 batch runner schema 对齐)
        ssc.write("B0GXGWNXBH", {
            "targetAsin": "B0GXGWNXBH", "actualAsin": "B0GXH1LB6G",
            "status": "ok", "asinMismatch": True,
            "latestNaturalSharePct": 100.0,
            "recent4AvgNaturalSharePct": 100.0,
            "recent4MinNaturalSharePct": 100.0,
            "weeksRead": 8, "pass70": True,
        })
        pmc.write("B0GXGWNXBH", {
            "title": "Oneida Kitchen And Dining, Vintage Americana Chip 'n Dip Tray",
            "brand": "Oneida", "price": 15.00, "rating": 4.7, "reviews": 21,
        })
        assert ssc.hit("B0GXGWNXBH")
        assert pmc.hit("B0GXGWNXBH")
        got = ssc.read("B0GXGWNXBH")
        assert got["pass70"] is True
        assert got["latestNaturalSharePct"] == 100.0
        assert ssc.stats()["fresh"] == 1
        assert pmc.stats()["fresh"] == 1
        print("  ✓ cache_store two-kind isolation OK")
        print(f"    ss cache stats: {ssc.stats()}")
        print(f"    pm cache stats: {pmc.stats()}")


def check_state_and_cache_integration():
    """模拟 pipeline 一小段:候选 3 个 ASIN → 缓存命中 1 个 → 剩下 2 个进 traffic_queued。"""
    with tempfile.TemporaryDirectory() as tmp:
        state = StateStore(Path(tmp) / "state.jsonl")
        ssc = sellersprite_cache(tmp, ttl_hours=168)

        # 预置缓存 —— B01 已经跑过
        ssc.write("BAAAAAAAAA", {
            "targetAsin": "BAAAAAAAAA", "status": "ok",
            "latestNaturalSharePct": 82.6, "recent4AvgNaturalSharePct": 80.08,
            "recent4MinNaturalSharePct": 72.46, "weeksRead": 6, "pass70": True,
        })

        candidates = ["BAAAAAAAAA", "BBBBBBBBBB", "BCCCCCCCCC"]
        state.mark_all(candidates, "candidate_taken")
        state.mark_all(candidates, "prefilter_pass")
        state.mark_all(candidates, "excl_pass")

        needs_traffic = []
        for a in candidates:
            if ssc.hit(a):
                cached = ssc.read(a)
                state.mark(a, "traffic_ok", reason="cache hit", meta={"cached": True})
            else:
                needs_traffic.append(a)
                state.mark(a, "traffic_queued")

        assert needs_traffic == ["BBBBBBBBBB", "BCCCCCCCCC"]
        assert state.current("BAAAAAAAAA") == "traffic_ok"
        assert state.current("BBBBBBBBBB") == "traffic_queued"
        assert state.count_by_state() == {"traffic_ok": 1, "traffic_queued": 2}
        print("  ✓ integration: cache 命中的 ASIN 跳过 traffic_queued")


def main():
    print("Phase 1 smoke test 开始...\n")
    print("[1/5] loading config/*.json")
    cfg = load_configs()
    check_rules_shape(cfg["rules"])
    check_exclusions_shape(cfg["exclusions"])
    check_pipeline_shape(cfg["pipeline"])

    print("\n[2/5] state_store cycle")
    check_state_store()

    print("\n[3/5] cache_store")
    check_cache_store()

    print("\n[4/5] state + cache integration")
    check_state_and_cache_integration()

    print("\n[5/5] all Phase 1 modules pass")
    print("\n✅ Phase 1 ready. Phase 2 can import scripts.state_store / scripts.cache_store and load config/*.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
