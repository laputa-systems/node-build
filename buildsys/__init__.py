from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import NamedTuple

_WHEEL_INPUT = "laputa-buildlib"


class _WheelPin(NamedTuple):
    url: str
    sha256: str
    size: int


def _wheel_pin(raw: object) -> _WheelPin:
    if not isinstance(raw, dict):
        raise TypeError("invalid sources.lock.json")
    entries: object = raw.get("inputs")
    if not isinstance(entries, list):
        raise TypeError("invalid sources.lock.json inputs")
    for item in entries:
        if not isinstance(item, dict):
            raise TypeError("invalid sources.lock.json input")
        if item.get("name") != _WHEEL_INPUT:
            continue
        url: object = item.get("url")
        sha256: object = item.get("sha256")
        size: object = item.get("size")
        if (
            not isinstance(url, str)
            or "/" not in url
            or not url.rsplit("/", 1)[1]
            or not isinstance(sha256, str)
            or len(sha256) != 64
            or any(c not in "0123456789abcdef" for c in sha256)
            or type(size) is not int
            or size < 0
        ):
            raise ValueError("invalid laputa-buildlib pin in sources.lock.json")
        return _WheelPin(url, sha256, size)
    raise ValueError("missing laputa-buildlib pin in sources.lock.json")


def _verified(data: bytes, entry: _WheelPin) -> bool:
    return len(data) == entry.size and hashlib.sha256(data).hexdigest() == entry.sha256


def _pinned_wheel(root: Path) -> Path:
    raw: object = json.loads((root / "sources.lock.json").read_text(encoding="utf-8"))
    entry = _wheel_pin(raw)
    wheel = root / "build" / "cache" / entry.url.rsplit("/", 1)[1]
    if wheel.is_file() and _verified(wheel.read_bytes(), entry):
        return wheel
    with urllib.request.urlopen(entry.url) as response:
        data = response.read()
    if not _verified(data, entry):
        raise RuntimeError(f"{entry.url}: bytes do not match the pin in sources.lock.json")
    wheel.parent.mkdir(parents=True, exist_ok=True)
    scratch = wheel.with_name(wheel.name + ".part")
    scratch.write_bytes(data)
    os.replace(scratch, wheel)
    return wheel


def _ensure_buildlib() -> None:
    if importlib.util.find_spec("buildlib") is None:
        sys.path.insert(0, str(_pinned_wheel(Path(__file__).resolve().parent.parent)))


_ensure_buildlib()
