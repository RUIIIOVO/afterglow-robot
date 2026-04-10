from __future__ import annotations

from pathlib import Path

from src.ingestion.parsers.base import ExportParser
from src.models.messages import Contact


def discover_contacts(parser: ExportParser, export_dir: Path, account_wxid: str) -> list[Contact]:
    contacts = parser.load_contacts(export_dir, account_wxid)
    unique: dict[str, Contact] = {}
    for contact in contacts:
        if contact.wxid not in unique:
            unique[contact.wxid] = contact
    return list(unique.values())

