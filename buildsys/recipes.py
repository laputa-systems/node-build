from __future__ import annotations


class BannedFlagError(Exception):
    pass


BANNED_SUBSTRINGS = (
    "-march=native",
    "-ffast-math",
    "--fully-static",
    "--enable-thin-lto",
)

REQUIRED_CONFIGURE_ARGS = (
    "--without-npm",
    "--with-intl=small-icu",
)


def macos_recipe() -> dict:
    return {
        "configure": [
            "--dest-os=mac",
            "--dest-cpu=arm64",
            "--without-npm",
            "--with-intl=small-icu",
        ],
        "cflags": ["-mcpu=apple-m1"],
        "optimization": "-O3",
        "deployment_target": "13.5",
    }


def validate_recipe(recipe: dict) -> None:
    for key in ("configure", "cflags", "optimization", "deployment_target"):
        if key not in recipe:
            raise BannedFlagError(f"recipe missing required key: {key}")
    for required in REQUIRED_CONFIGURE_ARGS:
        if required not in recipe["configure"]:
            raise BannedFlagError(f"recipe missing required configure argument: {required}")
    for token in list(recipe["configure"]) + list(recipe["cflags"]) + [recipe["optimization"]]:
        for banned in BANNED_SUBSTRINGS:
            if banned in token:
                raise BannedFlagError(f"recipe contains banned flag: {banned}")


def configure_command(source_dir: str, recipe: dict) -> list[str]:
    validate_recipe(recipe)
    return ["./configure", *recipe["configure"]]
