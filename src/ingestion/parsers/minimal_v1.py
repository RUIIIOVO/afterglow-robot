from __future__ import annotations

import json
from pathlib import Path

from src.models.messages import Contact, RawMessage


class MinimalV1Parser:
    """
    最小可测目录结构：
    <export_dir>/accounts/<account_wxid>/contacts.json
    <export_dir>/accounts/<account_wxid>/messages.jsonl
    """

    name = "minimal_v1"

    def can_parse(self, export_dir: Path) -> bool:
        accounts_dir = export_dir / "accounts"
        if not accounts_dir.is_dir():
            return False
        for child in accounts_dir.iterdir():
            if not child.is_dir():
                continue
            if (child / "contacts.json").is_file() and (child / "messages.jsonl").is_file():
                return True
        return False

    def list_accounts(self, export_dir: Path) -> list[str]:
        accounts_dir = export_dir / "accounts"
        accounts: list[str] = []
        if not accounts_dir.exists():
            return accounts
        for child in accounts_dir.iterdir():
            if not child.is_dir():
                continue
            if (child / "contacts.json").is_file() and (child / "messages.jsonl").is_file():
                accounts.append(child.name)
        return sorted(accounts)

    def load_contacts(self, export_dir: Path, account_wxid: str) -> list[Contact]:
        contacts_file = export_dir / "accounts" / account_wxid / "contacts.json"
        data = json.loads(contacts_file.read_text(encoding="utf-8"))
        contacts: list[Contact] = []
        for row in data:
            wxid = str(row.get("wxid", "")).strip()
            if not wxid:
                continue
            display_name = str(row.get("display_name") or row.get("name") or wxid)
            contacts.append(Contact(wxid=wxid, display_name=display_name))
        return contacts

    def load_messages(self, export_dir: Path, account_wxid: str) -> list[RawMessage]:
        messages_file = export_dir / "accounts" / account_wxid / "messages.jsonl"
        messages: list[RawMessage] = []
        with messages_file.open("r", encoding="utf-8") as file:
            for line_no, line in enumerate(file, start=1):
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                message_id = str(row.get("message_id") or f"msg-{line_no}")
                timestamp = int(row.get("timestamp", 0))
                sender_wxid = str(row.get("sender_wxid", "")).strip()
                conversation_id = str(row.get("conversation_id", ""))
                if not conversation_id:
                    conversation_id = f"conv-{account_wxid}"
                message_type = str(row.get("message_type", "text")).lower()
                text = str(row.get("text", ""))
                is_system = bool(row.get("is_system", False))
                messages.append(
                    RawMessage(
                        message_id=message_id,
                        timestamp=timestamp,
                        sender_wxid=sender_wxid,
                        conversation_id=conversation_id,
                        message_type=message_type,
                        text=text,
                        is_system=is_system,
                    )
                )
        return messages

