from __future__ import annotations

import os
from pathlib import Path


def path_inside_root(path: Path, root: Path) -> bool:
    try:
        return os.path.commonpath((str(path), str(root))) == str(root)
    except ValueError:
        return False


def resolve_image_path(
    value: str,
    image: Path,
    install: Path,
    executable: Path | None = None,
) -> Path | None:
    if value == "@loader_path":
        candidate = image.parent
    elif value.startswith("@loader_path/"):
        candidate = image.parent / value.removeprefix("@loader_path/")
    elif value == "@executable_path":
        if executable is None:
            return None
        candidate = executable.parent
    elif value.startswith("@executable_path/"):
        if executable is None:
            return None
        candidate = executable.parent / value.removeprefix("@executable_path/")
    elif value.startswith("/"):
        candidate = Path(value)
    else:
        return None
    resolved = candidate.resolve()
    return resolved if path_inside_root(resolved, install) else None


def rpath_directories(
    rpath: str,
    image: Path,
    install: Path,
    executable_images: list[Path],
) -> list[Path | None]:
    if rpath == "@loader_path" or rpath.startswith("@loader_path/"):
        return [resolve_image_path(rpath, image, install)]
    if rpath == "@executable_path" or rpath.startswith("@executable_path/"):
        return [
            resolve_image_path(rpath, image, install, executable)
            for executable in executable_images
        ]
    return []


def system_load_path(value: str) -> bool:
    if not value.startswith(("/usr/lib/", "/System/Library/")):
        return False
    normalized = os.path.normpath(value)
    return normalized == value and not normalized.endswith("/")
