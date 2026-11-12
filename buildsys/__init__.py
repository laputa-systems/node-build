from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import urllib.request
from pathlib import Path

_WHEEL_INPUT = "laputa-buildlib"


def _verified(data: bytes, entry: dict) -> bool:
    return len(data) == entry["size"] and hashlib.sha256(data).hexdigest() == entry["sha256"]


def _pinned_wheel(root: Path) -> Path:
    lock = json.loads((root / "sources.lock.json").read_text(encoding="utf-8"))
    entry = next(item for item in lock["inputs"] if item["name"] == _WHEEL_INPUT)
    wheel = root / "build" / "cache" / entry["url"].rsplit("/", 1)[1]
    if wheel.is_file() and _verified(wheel.read_bytes(), entry):
        return wheel
    with urllib.request.urlopen(entry["url"]) as response:
        data = response.read()
    if not _verified(data, entry):
        raise RuntimeError(f"{entry['url']}: bytes do not match the pin in sources.lock.json")
    wheel.parent.mkdir(parents=True, exist_ok=True)
    scratch = wheel.with_name(wheel.name + ".part")
    scratch.write_bytes(data)
    os.replace(scratch, wheel)
    return wheel


def _ensure_buildlib() -> None:
    if importlib.util.find_spec("buildlib") is None:
        sys.path.insert(0, str(_pinned_wheel(Path(__file__).resolve().parent.parent)))


_ensure_buildlib()
