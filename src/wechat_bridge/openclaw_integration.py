from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scripts.patch_openclaw_weixin_for_afterglow import (
    DEFAULT_BRIDGE_URL,
    DEFAULT_TIMEOUT_MS,
    patch_openclaw_config,
    patch_process_message,
    patch_schema,
)
from src.runtime.errors import OpenClawPatchError


@dataclass(frozen=True)
class OpenClawPatchResult:
    openclaw_root: Path
    bridge_url: str
    timeout_ms: int
    schema_changed: bool = False
    process_changed: bool = False
    config_changed: bool = False
    missing_paths: tuple[str, ...] = ()

    @property
    def applied(self) -> bool:
        return not self.missing_paths

    @property
    def changed(self) -> bool:
        return self.schema_changed or self.process_changed or self.config_changed


def configure_openclaw_afterglow(
    *,
    bridge_url: str = DEFAULT_BRIDGE_URL,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    openclaw_root: str | Path | None = None,
    strict: bool = False,
) -> OpenClawPatchResult:
    root = Path(openclaw_root or (Path.home() / ".openclaw")).expanduser().resolve()
    plugin_dir = root / "extensions" / "openclaw-weixin"
    schema_path = plugin_dir / "src" / "config" / "config-schema.ts"
    process_message_path = plugin_dir / "src" / "messaging" / "process-message.ts"
    config_path = root / "openclaw.json"

    missing = tuple(str(path) for path in (schema_path, process_message_path, config_path) if not path.exists())
    if missing:
        if strict:
            raise OpenClawPatchError(
                "未检测到可补丁的 openclaw-weixin 安装目录。",
                context={"openclaw_root": str(root), "missing_paths": list(missing)},
            )
        return OpenClawPatchResult(
            openclaw_root=root,
            bridge_url=bridge_url,
            timeout_ms=timeout_ms,
            missing_paths=missing,
        )

    try:
        schema_changed = patch_schema(schema_path)
        process_changed = patch_process_message(process_message_path)
        config_changed = patch_openclaw_config(config_path, bridge_url, timeout_ms)
    except Exception as error:  # noqa: BLE001
        raise OpenClawPatchError(
            str(error),
            context={"openclaw_root": str(root), "bridge_url": bridge_url},
        ) from error

    return OpenClawPatchResult(
        openclaw_root=root,
        bridge_url=bridge_url,
        timeout_ms=timeout_ms,
        schema_changed=schema_changed,
        process_changed=process_changed,
        config_changed=config_changed,
    )
