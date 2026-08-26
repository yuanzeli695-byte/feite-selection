import sys, tempfile, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from state_store import StateStore


def make_store():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl")
    tmp.close()
    return StateStore(tmp.name), tmp.name


def test_mark_and_current():
    s, _ = make_store()
    s.mark("B01", "candidate_taken")
    s.mark("B01", "prefilter_pass")
    assert s.current("B01") == "prefilter_pass"
    assert s.current("B99") is None


def test_history_order():
    s, _ = make_store()
    s.mark("B01", "candidate_taken")
    s.mark("B01", "prefilter_pass")
    s.mark("B01", "excl_pass")
    h = s.history("B01")
    assert [e["state"] for e in h] == ["candidate_taken", "prefilter_pass", "excl_pass"]


def test_mark_all():
    s, _ = make_store()
    s.mark_all(["B01", "B02", "B03"], "candidate_taken")
    latest = s.latest_by_asin()
    assert set(latest.keys()) == {"B01", "B02", "B03"}
    assert all(e["state"] == "candidate_taken" for e in latest.values())


def test_count_by_state_uses_latest():
    s, _ = make_store()
    s.mark("B01", "candidate_taken")
    s.mark("B01", "prefilter_pass")
    s.mark("B02", "candidate_taken")
    s.mark("B02", "prefilter_fail", reason="price out of range")
    c = s.count_by_state()
    assert c == {"prefilter_pass": 1, "prefilter_fail": 1}


def test_asins_in_state():
    s, _ = make_store()
    s.mark("B01", "hard_pass")
    s.mark("B02", "hard_fail", reason="pass70=false")
    s.mark("B03", "hard_pass")
    assert set(s.asins_in_state("hard_pass")) == {"B01", "B03"}


def test_reason_and_meta_preserved():
    s, _ = make_store()
    s.mark("B01", "hard_fail", reason="recent4Min=32%", meta={"weeksRead": 6, "latestPct": 78})
    h = s.history("B01")
    assert h[0]["reason"] == "recent4Min=32%"
    assert h[0]["meta"]["weeksRead"] == 6


def test_persistence_across_instances():
    s1, path = make_store()
    s1.mark("B01", "candidate_taken")
    s2 = StateStore(path)
    assert s2.current("B01") == "candidate_taken"


def test_empty_file_no_crash():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl")
    tmp.close()
    s = StateStore(tmp.name)
    assert s.all_entries() == []
    assert s.count_by_state() == {}


def test_corrupt_lines_ignored():
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl", mode="w", encoding="utf-8")
    tmp.write('{"asin":"B01","state":"candidate_taken","at":"2026-07-10T09:00:00+08:00"}\n')
    tmp.write("this is not json\n")
    tmp.write('{"asin":"B02","state":"prefilter_pass","at":"2026-07-10T09:01:00+08:00"}\n')
    tmp.close()
    s = StateStore(tmp.name)
    assert len(s.all_entries()) == 2


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
