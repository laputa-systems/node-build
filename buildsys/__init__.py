"""Controller internals for node-build.

Shared operations come from the pinned ``laputa-buildlib`` wheel: lock reading,
verified downloads, hashing, release assets, and ELF/Mach-O inspection. Run the
controller through ``sh bootstrap/buildlib-run --`` or ``uv run --frozen`` so the
wheel is importable; neither path needs the distribution's Python.
"""

from __future__ import annotations

import importlib.util

if importlib.util.find_spec("buildlib") is None:
    raise ModuleNotFoundError(
        "buildlib is unavailable: run controllers through 'sh bootstrap/buildlib-run --' "
        "or 'uv run --frozen', which provide the pinned laputa-buildlib wheel"
    )
