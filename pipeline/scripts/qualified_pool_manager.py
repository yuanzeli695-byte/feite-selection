from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class QualifiedPool:
    def __init__(self, path: str | Path, run_id: str, target: int):
        self.path = Path(path)
        self.run_id = run_id
        self.target = target
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8-sig"))
        return {
            "runId": self.run_id,
            "targetN": self.target,
            "currentCount": 0,
            "acceptedAt": "",
            "candidates": [],
        }

    def save(self) -> None:
        self.data["currentCount"] = len(self.data["candidates"])
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, candidate: dict[str, Any]) -> None:
        asin = candidate.get("asin")
        if asin and any(item.get("asin") == asin for item in self.data["candidates"]):
            return
        self.data["candidates"].append(candidate)
        self.data["acceptedAt"] = datetime.now().astimezone().isoformat(timespec="seconds")
        self.save()

    def count(self) -> int:
        return len(self.data["candidates"])

    def should_continue(self, attempts: int, max_attempts: int) -> bool:
        return self.count() < self.target and attempts < max_attempts
