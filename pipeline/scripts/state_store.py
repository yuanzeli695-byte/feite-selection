from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class StateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, asin: str, state: str, prev_state: str | None = None, reason: str = "", **extra: Any) -> None:
        record = {
            "asin": asin,
            "state": state,
            "prevState": prev_state or "",
            "reason": reason,
            "at": now_iso(),
        }
        record.update({k: v for k, v in extra.items() if v is not None})
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def mark(self, asin: str, state: str, prev_state: str | None = None, reason: str = "", **extra: Any) -> None:
        self.append(asin, state, prev_state, reason, **extra)

    def mark_all(self, candidates: Iterable[Any], state: str) -> None:
        for candidate in candidates:
            if isinstance(candidate, str):
                asin = candidate
            else:
                asin = candidate.get("asin") or candidate.get("targetAsin")
            if asin:
                self.mark(str(asin), state)

    def all_entries(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        if not self.path.exists():
            return entries
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries

    def history(self, asin: str) -> list[dict[str, Any]]:
        return [entry for entry in self.all_entries() if entry.get("asin") == asin]

    def latest_by_asin(self) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for record in self.all_entries():
            if record.get("asin"):
                latest[record["asin"]] = record
        return latest

    def latest_states(self) -> dict[str, dict[str, Any]]:
        return self.latest_by_asin()

    def current(self, asin: str) -> str | None:
        record = self.latest_by_asin().get(asin)
        return record.get("state") if record else None

    def count_by_state(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self.latest_by_asin().values():
            state = record.get("state")
            if state:
                counts[state] = counts.get(state, 0) + 1
        return counts

    def asins_in_state(self, state: str) -> list[str]:
        return [asin for asin, record in self.latest_by_asin().items() if record.get("state") == state]
