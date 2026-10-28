from __future__ import annotations

import platform
import re
import subprocess
import sys
from dataclasses import dataclass


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


def validate_bootstrap_lock(lock: dict) -> None:
    for key in ("toolchain", "cpu_baseline", "host_requirements"):
        if key not in lock:
            raise ValueError(f"bootstrap lock missing section: {key}")
    for key in ("xcode", "sdk", "clang", "host_machine"):
        if key not in lock["toolchain"]:
            raise ValueError(f"bootstrap lock toolchain missing: {key}")
    for key in ("cflag", "deployment_target"):
        if key not in lock["cpu_baseline"]:
            raise ValueError(f"bootstrap lock cpu_baseline missing: {key}")
    if "linux_toolchain" not in lock:
        raise ValueError("bootstrap lock missing section: linux_toolchain")
    for key in ("gcc", "clang", "musl", "host_machine"):
        if key not in lock["linux_toolchain"]:
            raise ValueError(f"bootstrap lock linux_toolchain missing: {key}")
    if "linux_baseline" not in lock:
        raise ValueError("bootstrap lock missing section: linux_baseline")
    for key in ("cflag", "deployment_target"):
        if key not in lock["linux_baseline"]:
            raise ValueError(f"bootstrap lock linux_baseline missing: {key}")


def _run(argv: list[str]) -> str:
    completed = subprocess.run(argv, capture_output=True, text=True, timeout=60, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"{' '.join(argv)} failed: {completed.stderr.strip()}")
    return (completed.stdout or "") + (completed.stderr or "")


def xcode_version() -> str:
    output = _run(["xcodebuild", "-version"])
    match = re.search(r"Xcode\s+(\S+)", output)
    if not match:
        raise RuntimeError(f"could not parse xcodebuild output: {output!r}")
    return match.group(1)


def sdk_path() -> str:
    return _run(["xcrun", "--show-sdk-path"]).strip()


def sdk_version() -> str:
    return _run(["xcrun", "--show-sdk-version"]).strip()


def clang_version() -> str:
    output = _run(["clang", "--version"])
    match = re.search(r"Apple clang version\s+(\S+)", output)
    if not match:
        raise RuntimeError(f"could not parse clang output: {output!r}")
    return match.group(1)


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


def check_locked_toolchain(lock: dict, identity: ToolchainIdentity) -> list[DoctorFinding]:
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


def check_locked_baseline(lock: dict) -> list[DoctorFinding]:
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
    output = _run(["clang", "--version"])
    match = re.search(r"clang version\s+(\S+)", output)
    if not match:
        raise RuntimeError(f"could not parse clang output: {output!r}")
    return match.group(1)


def musl_version() -> str:
    completed = subprocess.run(
        ["ldd", "--version"], capture_output=True, text=True, timeout=60, check=False
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    match = re.search(r"Version\s+(\S+)", output)
    if not match:
        raise RuntimeError(f"could not parse musl ldd output: {output!r}")
    return match.group(1)


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
    lock: dict, identity: LinuxToolchainIdentity
) -> list[DoctorFinding]:
    toolchain = lock["linux_toolchain"]
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


def check_linux_baseline(lock: dict) -> list[DoctorFinding]:
    baseline = lock["linux_baseline"]
    return [
        DoctorFinding(
            "cpu-baseline",
            baseline["cflag"] == "-march=x86-64-v2",
            f"locked {baseline['cflag']}",
        ),
        DoctorFinding(
            "deployment-target",
            baseline["deployment_target"] == "1.2.6",
            f"locked {baseline['deployment_target']}",
        ),
    ]
