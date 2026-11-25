from __future__ import annotations

import platform
import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from buildlib import locks

from buildsys.targets import Target


@dataclass(frozen=True)
class ToolchainIdentity:
    xcode_version: str
    sdk_version: str
    sdk_path: str
    clang_version: str
    host_machine: str
    host_system: str
    build_python: str


@dataclass(frozen=True)
class LinuxToolchainIdentity:
    gcc_version: str
    clang_version: str
    musl_version: str
    kernel_release: str
    host_machine: str
    host_system: str
    build_python: str


@dataclass(frozen=True)
class DoctorFinding:
    name: str
    ok: bool
    detail: str


def load_bootstrap_lock(path: Path) -> Mapping[str, Any]:
    try:
        lock = locks.load_bootstrap(path)
    except locks.LockError as error:
        raise ValueError(str(error)) from error
    validate_bootstrap_lock(lock)
    return lock


LINUX_ARCHES = ("aarch64", "x86_64")

LINUX_TOOLCHAIN_FIELDS = ("gcc", "clang", "musl", "host_machine")
LINUX_BASELINE_FIELDS = ("cflag", "deployment_target")


def validate_bootstrap_lock(lock: Mapping[str, Any]) -> None:
    required_fields = {
        "toolchain": ("xcode", "sdk", "clang", "host_machine"),
        "cpu_baseline": ("cflag", "deployment_target"),
        "host_requirements": (),
    }
    for section, fields in required_fields.items():
        if section not in lock:
            raise ValueError(f"bootstrap lock missing section: {section}")
        values: object = lock[section]
        if not isinstance(values, Mapping):
            raise TypeError(f"bootstrap lock section must be an object: {section}")
        for key in fields:
            if key not in values:
                raise ValueError(f"bootstrap lock {section} missing: {key}")
            value: object = values[key]
            if not isinstance(value, str) or not value:
                raise ValueError(f"bootstrap lock {section} {key} must be a nonempty string")
    for section, fields in (
        ("linux_toolchain", LINUX_TOOLCHAIN_FIELDS),
        ("linux_baseline", LINUX_BASELINE_FIELDS),
    ):
        if section not in lock:
            raise ValueError(f"bootstrap lock missing section: {section}")
        values = lock[section]
        if not isinstance(values, Mapping):
            raise TypeError(f"bootstrap lock section must be an object: {section}")
        for arch in LINUX_ARCHES:
            if arch not in values:
                raise ValueError(f"bootstrap lock {section} missing: {arch}")
            per_arch: object = values[arch]
            if not isinstance(per_arch, Mapping):
                raise TypeError(f"bootstrap lock section must be an object: {section}.{arch}")
            for key in fields:
                if key not in per_arch:
                    raise ValueError(f"bootstrap lock {section} {arch} missing: {key}")
                value = per_arch[key]
                if not isinstance(value, str) or not value:
                    raise ValueError(
                        f"bootstrap lock {section} {arch} {key} must be a nonempty string"
                    )


def _run(argv: list[str]) -> str:
    completed = subprocess.run(argv, capture_output=True, text=True, timeout=60, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"{' '.join(argv)} failed: {completed.stderr.strip()}")
    return (completed.stdout or "") + (completed.stderr or "")


def _matched_version(output: str, pattern: str, tool: str) -> str:
    match = re.search(pattern, output)
    if match is None:
        raise RuntimeError(f"could not parse {tool} output: {output!r}")
    start, end = match.span(1)
    return output[start:end]


def xcode_version() -> str:
    return _matched_version(_run(["xcodebuild", "-version"]), r"Xcode\s+(\S+)", "xcodebuild")


def sdk_path() -> str:
    return _run(["xcrun", "--show-sdk-path"]).strip()


def sdk_version() -> str:
    return _run(["xcrun", "--show-sdk-version"]).strip()


def clang_version() -> str:
    return _matched_version(_run(["clang", "--version"]), r"Apple clang version\s+(\S+)", "clang")


def current_identity() -> ToolchainIdentity:
    return ToolchainIdentity(
        xcode_version=xcode_version(),
        sdk_version=sdk_version(),
        sdk_path=sdk_path(),
        clang_version=clang_version(),
        host_machine=platform.machine(),
        host_system=platform.system(),
        build_python=".".join(str(part) for part in sys.version_info[:3]),
    )


def check_locked_toolchain(lock: Mapping[str, Any], identity: ToolchainIdentity) -> list[DoctorFinding]:
    toolchain = lock["toolchain"]
    findings = [
        DoctorFinding(
            "xcode",
            identity.xcode_version == toolchain["xcode"],
            f"host {identity.xcode_version} vs locked {toolchain['xcode']}",
        ),
        DoctorFinding(
            "sdk",
            identity.sdk_version == toolchain["sdk"],
            f"host {identity.sdk_version} vs locked {toolchain['sdk']}",
        ),
        DoctorFinding(
            "clang",
            identity.clang_version == toolchain["clang"],
            f"host {identity.clang_version} vs locked {toolchain['clang']}",
        ),
        DoctorFinding(
            "machine",
            identity.host_machine == toolchain["host_machine"],
            f"host {identity.host_machine} vs locked {toolchain['host_machine']}",
        ),
        DoctorFinding(
            "system",
            identity.host_system == "Darwin",
            f"host {identity.host_system}",
        ),
    ]
    return findings


def check_locked_baseline(lock: Mapping[str, Any]) -> list[DoctorFinding]:
    baseline = lock["cpu_baseline"]
    findings = [
        DoctorFinding(
            "cpu-baseline",
            baseline["cflag"] == "-mcpu=apple-m1",
            f"locked {baseline['cflag']}",
        ),
        DoctorFinding(
            "deployment-target",
            baseline["deployment_target"] == "26.0",
            f"locked {baseline['deployment_target']}",
        ),
    ]
    return findings


def gcc_version() -> str:
    output = _run(["gcc", "-dumpversion"])
    return output.strip().split()[0]


def linux_clang_version() -> str:
    return _matched_version(_run(["clang", "--version"]), r"clang version\s+(\S+)", "clang")


def musl_version() -> str:
    completed = subprocess.run(
        ["ldd", "--version"], capture_output=True, text=True, timeout=60, check=False
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    return _matched_version(output, r"Version\s+(\S+)", "musl ldd")


def linux_current_identity() -> LinuxToolchainIdentity:
    return LinuxToolchainIdentity(
        gcc_version=gcc_version(),
        clang_version=linux_clang_version(),
        musl_version=musl_version(),
        kernel_release=platform.release(),
        host_machine=platform.machine(),
        host_system=platform.system(),
        build_python=".".join(str(part) for part in sys.version_info[:3]),
    )


def check_linux_toolchain(
    lock: Mapping[str, Any], identity: LinuxToolchainIdentity, machine: str
) -> list[DoctorFinding]:
    toolchain = lock["linux_toolchain"][machine]
    return [
        DoctorFinding(
            "gcc",
            identity.gcc_version == toolchain["gcc"],
            f"host {identity.gcc_version} vs locked {toolchain['gcc']}",
        ),
        DoctorFinding(
            "clang",
            identity.clang_version == toolchain["clang"],
            f"host {identity.clang_version} vs locked {toolchain['clang']}",
        ),
        DoctorFinding(
            "musl",
            identity.musl_version == toolchain["musl"],
            f"host {identity.musl_version} vs locked {toolchain['musl']}",
        ),
        DoctorFinding(
            "machine",
            identity.host_machine == toolchain["host_machine"],
            f"host {identity.host_machine} vs locked {toolchain['host_machine']}",
        ),
        DoctorFinding(
            "system",
            identity.host_system == "Linux",
            f"host {identity.host_system}",
        ),
    ]


def check_linux_baseline(lock: Mapping[str, Any], target: Target) -> list[DoctorFinding]:
    baseline = lock["linux_baseline"][target.machine]
    return [
        DoctorFinding(
            "cpu-baseline",
            baseline["cflag"] == target.cpu_baseline_cflag,
            f"locked {baseline['cflag']}",
        ),
        DoctorFinding(
            "deployment-target",
            baseline["deployment_target"] == target.deployment_target,
            f"locked {baseline['deployment_target']}",
        ),
    ]
