from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass

from src.runtime.errors import DependencyMissingError, OpenClawNotInstalledError


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    available: bool
    detail: str


def _which(name: str) -> str | None:
    return shutil.which(name)


def check_environment() -> list[DependencyStatus]:
    statuses = [
        DependencyStatus(
            name="python",
            available=True,
            detail=sys.version.split()[0],
        ),
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
    command = ["npx", "-y", "@tencent-weixin/openclaw-weixin-cli@latest", "--version"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=90)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "命令执行失败"
        raise OpenClawNotInstalledError(detail)


def run_openclaw_install() -> None:
    require_node_and_npx()
    command = ["npx", "-y", "@tencent-weixin/openclaw-weixin-cli@latest", "install"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "命令执行失败"
        raise OpenClawNotInstalledError(detail)

