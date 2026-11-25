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
        "deployment_target": "26.0",
    }


def _linux_recipe(dest_cpu: str, cflag: str) -> dict:
    return {
        "configure": [
            "--dest-os=linux",
            f"--dest-cpu={dest_cpu}",
            "--without-npm",
            "--with-intl=small-icu",
        ],
        "cflags": [cflag],
        "ldflags": ["-static-libstdc++", "-static-libgcc"],
        "optimization": "-O3",
        "deployment_target": "1.2.6",
    }


def linux_recipe() -> dict:
    return _linux_recipe("x64", "-march=x86-64-v2")


def linux_arm64_recipe() -> dict:
    return _linux_recipe("arm64", "-march=armv8-a")


def recipe_for_triple(triple: str) -> dict:
    if triple == "aarch64-apple-darwin":
        return macos_recipe()
    if triple == "x86_64-unknown-linux-musl":
        return linux_recipe()
    if triple == "aarch64-unknown-linux-musl":
        return linux_arm64_recipe()
    raise BannedFlagError(f"no recipe for target: {triple}")


def validate_recipe(recipe: dict) -> None:
    for key in ("configure", "cflags", "optimization", "deployment_target"):
        if key not in recipe:
            raise BannedFlagError(f"recipe missing required key: {key}")
    for required in REQUIRED_CONFIGURE_ARGS:
        if required not in recipe["configure"]:
            raise BannedFlagError(f"recipe missing required configure argument: {required}")
    for token in list(recipe["configure"]) + list(recipe["cflags"]) + list(recipe.get("ldflags", [])) + [recipe["optimization"]]:
        for banned in BANNED_SUBSTRINGS:
            if banned in token:
                raise BannedFlagError(f"recipe contains banned flag: {banned}")


def configure_command(source_dir: str, recipe: dict) -> list[str]:
    validate_recipe(recipe)
    return ["./configure", *recipe["configure"]]
