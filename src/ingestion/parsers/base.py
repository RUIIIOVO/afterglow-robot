from __future__ import annotations

from pathlib import Path
from typing import Protocol

from src.models.messages import Contact, RawMessage


class ExportParser(Protocol):
    name: str

    def can_parse(self, export_dir: Path) -> bool:
        ...

    def list_accounts(self, export_dir: Path) -> list[str]:
        ...

    def load_contacts(self, export_dir: Path, account_wxid: str) -> list[Contact]:
        ...

    def load_messages(self, export_dir: Path, account_wxid: str) -> list[RawMessage]:
        ...

