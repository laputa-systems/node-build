from __future__ import annotations

import datetime
import os
import re
import sys


def resolve_release_tag(raw: str) -> str:
    cleaned = raw.strip()
    if not cleaned:
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
    if not re.fullmatch(r"\d{8}", cleaned):
        raise ValueError(f"release tag must be YYYYMMDD, got {raw!r}")
    return cleaned


def main(argv: list[str]) -> int:
    try:
        tag = resolve_release_tag(argv[1] if len(argv) > 1 else "")
    except (IndexError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"release_tag={tag}\n")
    print(f"release_tag={tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
