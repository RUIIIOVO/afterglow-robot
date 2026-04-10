from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from src.runtime.errors import DependencyMissingError, OpenClawNotInstalledError


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    available: bool
    detail: str


def _which(name: str) -> str | None:
    return shutil.which(name)


def _resolve_python_command() -> str | None:
    python_cmd = _which("python")
    if python_cmd:
        return python_cmd
    py_cmd = _which("py")
    if py_cmd:
        return py_cmd
    return None


def _read_python_detail(command: str) -> str:
    cmd = [command, "--version"]
    if Path(command).name.lower() == "py.exe" or Path(command).name.lower() == "py":
        cmd = [command, "-3", "--version"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    output = (result.stdout or result.stderr).strip()
    if output:
        return f"{command} ({output})"
    return command


def _check_python_status() -> DependencyStatus:
    runtime_python = sys.executable
    runtime_ok = bool(runtime_python and Path(runtime_python).exists())
    command = _resolve_python_command()

    if command:
        try:
            detail = _read_python_detail(command)
        except Exception:  # noqa: BLE001
            detail = command
        return DependencyStatus(name="python", available=True, detail=detail)

    if runtime_ok:
        return DependencyStatus(
            name="python",
            available=True,
            detail=f"{runtime_python} ({sys.version.split()[0]})",
        )

    return DependencyStatus(name="python", available=False, detail="未找到")


def check_environment() -> list[DependencyStatus]:
    statuses = [
        _check_python_status(),
        DependencyStatus(
            name="node",
            available=_which("node") is not None,
            detail=_which("node") or "未找到",
        ),
        DependencyStatus(
            name="npx",
            available=_which("npx") is not None,
            detail=_which("npx") or "未找到",
        ),
        DependencyStatus(
            name="ollama",
            available=_which("ollama") is not None,
            detail=_which("ollama") or "未找到",
        ),
    ]
    return statuses


def require_node_and_npx() -> None:
    if _which("node") is None:
        raise DependencyMissingError("Node.js", "请先安装 Node.js。")
    if _which("npx") is None:
        raise DependencyMissingError("npx", "请先安装 npm（包含 npx）。")


def ensure_openclaw_installed() -> None:
    require_node_and_npx()
    npx_path = _which("npx")
    if npx_path is None:
        raise DependencyMissingError("npx", "请先安装 npm（包含 npx）。")
    command = [npx_path, "-y", "@tencent-weixin/openclaw-weixin-cli@latest", "help"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=90)
    except FileNotFoundError as error:
        raise DependencyMissingError("npx", "未找到可执行 npx，请检查 Node.js 安装路径。") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "命令执行失败"
        raise OpenClawNotInstalledError(detail)


def run_openclaw_install() -> None:
    require_node_and_npx()
    npx_path = _which("npx")
    if npx_path is None:
        raise DependencyMissingError("npx", "请先安装 npm（包含 npx）。")
    command = [npx_path, "-y", "@tencent-weixin/openclaw-weixin-cli@latest", "install"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    except FileNotFoundError as error:
        raise DependencyMissingError("npx", "未找到可执行 npx，请检查 Node.js 安装路径。") from error
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "命令执行失败"
        raise OpenClawNotInstalledError(detail)
