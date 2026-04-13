from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.models.messages import Contact, RawMessage


@dataclass(frozen=True)
class _ExportSource:
    path: Path
    source_type: str
    account: str
    zip_prefix: str = ""


class WeChatDataAnalysisV1Parser:
    """
    WeChatDataAnalysis 导出 ZIP 或解压目录结构：
    manifest.json
    conversations/<conversation>/meta.json
    conversations/<conversation>/messages.json 或 messages.txt
    """

    name = "wechat_data_analysis_v1"

    def can_parse(self, export_dir: Path) -> bool:
        return bool(self._discover_sources(export_dir))

    def list_accounts(self, export_dir: Path) -> list[str]:
        return sorted({source.account for source in self._discover_sources(export_dir) if source.account != "hidden"})

    def load_contacts(self, export_dir: Path, account_wxid: str) -> list[Contact]:
        contacts: dict[str, Contact] = {}
        contacts[account_wxid] = Contact(wxid=account_wxid, display_name=account_wxid)
        for source in self._sources_for_account(export_dir, account_wxid):
            for conversation in self._load_conversations(source):
                conv = conversation.get("conversation") or {}
                if isinstance(conv, dict):
                    username = _pick_text(conv.get("username"), conv.get("conversationUsername"))
                    display_name = _pick_text(conv.get("displayName"), username)
                    if username:
                        contacts.setdefault(username, Contact(wxid=username, display_name=display_name or username))

                for message in _as_list(conversation.get("messages")):
                    if not isinstance(message, dict):
                        continue
                    sender = _pick_text(message.get("senderUsername"), message.get("fromUsername"))
                    if sender and sender not in contacts:
                        display_name = _pick_text(message.get("senderDisplayName"), sender)
                        contacts[sender] = Contact(wxid=sender, display_name=display_name or sender)
        return list(contacts.values())

    def load_messages(self, export_dir: Path, account_wxid: str) -> list[RawMessage]:
        messages: list[RawMessage] = []
        for source in self._sources_for_account(export_dir, account_wxid):
            for conversation in self._load_conversations(source):
                conv = conversation.get("conversation") or {}
                conv_username = ""
                if isinstance(conv, dict):
                    conv_username = _pick_text(conv.get("username"), conv.get("conversationUsername"))
                for index, row in enumerate(_as_list(conversation.get("messages")), start=1):
                    if not isinstance(row, dict):
                        continue
                    conversation_id = _pick_text(row.get("conversationUsername"), conv_username, f"conv-{account_wxid}")
                    is_sent = bool(row.get("isSent"))
                    message_type = _normalize_message_type(row)
                    sender = _pick_text(row.get("senderUsername"), row.get("fromUsername"))
                    if is_sent:
                        sender = account_wxid
                    elif message_type == "text" and not sender and conversation_id and not conversation_id.endswith("@chatroom"):
                        sender = conversation_id
                    text = _pick_text(row.get("content"), row.get("text"), row.get("message"))
                    message_id = _pick_text(row.get("id"), row.get("messageId"), row.get("localId"))
                    if not message_id:
                        message_id = f"{source.path.name}:{conversation_id}:{index}"
                    messages.append(
                        RawMessage(
                            message_id=message_id,
                            timestamp=_normalize_timestamp(row.get("createTime") or row.get("timestamp") or row.get("time")),
                            sender_wxid=sender,
                            conversation_id=conversation_id,
                            message_type=message_type,
                            text=text,
                            is_system=message_type == "system",
                        )
                    )
        messages.sort(key=lambda item: item.timestamp)
        return messages

    def _sources_for_account(self, export_dir: Path, account_wxid: str) -> list[_ExportSource]:
        return [source for source in self._discover_sources(export_dir) if source.account == account_wxid]

    def _discover_sources(self, export_dir: Path) -> list[_ExportSource]:
        candidates: list[_ExportSource] = []
        seen: set[Path] = set()

        if export_dir.is_file() and export_dir.suffix.lower() == ".zip":
            source = self._source_from_zip(export_dir)
            return [source] if source else []

        if not export_dir.is_dir():
            return []

        root_source = self._source_from_directory(export_dir)
        if root_source:
            candidates.append(root_source)
            seen.add(export_dir.resolve())

        for manifest in export_dir.rglob("manifest.json"):
            root = manifest.parent
            resolved = root.resolve()
            if resolved in seen:
                continue
            source = self._source_from_directory(root)
            if source:
                candidates.append(source)
                seen.add(resolved)

        for archive in export_dir.rglob("*.zip"):
            source = self._source_from_zip(archive)
            if source:
                candidates.append(source)

        return sorted(candidates, key=lambda item: str(item.path))

    def _source_from_directory(self, root: Path) -> _ExportSource | None:
        manifest_path = root / "manifest.json"
        conversations_dir = root / "conversations"
        if not manifest_path.is_file() or not conversations_dir.is_dir():
            return None
        account = _read_manifest_account(manifest_path)
        if not account or account == "hidden":
            return None
        if not any(conversations_dir.glob("*/messages.json")) and not any(conversations_dir.glob("*/messages.txt")):
            return None
        return _ExportSource(path=root, source_type="directory", account=account)

    def _source_from_zip(self, archive: Path) -> _ExportSource | None:
        try:
            with zipfile.ZipFile(archive) as zf:
                prefix = _discover_zip_prefix(zf)
                if prefix is None:
                    return None
                account = _read_zip_manifest_account(zf, prefix)
        except (OSError, zipfile.BadZipFile, json.JSONDecodeError):
            return None
        if not account or account == "hidden":
            return None
        return _ExportSource(path=archive, source_type="zip", account=account, zip_prefix=prefix)

    def _load_conversations(self, source: _ExportSource) -> list[dict[str, Any]]:
        if source.source_type == "zip":
            return self._load_zip_conversations(source)
        return self._load_directory_conversations(source)

    def _load_directory_conversations(self, source: _ExportSource) -> list[dict[str, Any]]:
        conversations: list[dict[str, Any]] = []
        for conversation_dir in sorted((source.path / "conversations").iterdir()):
            if not conversation_dir.is_dir():
                continue
            json_path = conversation_dir / "messages.json"
            if json_path.is_file():
                conversations.append(json.loads(json_path.read_text(encoding="utf-8")))
                continue
            txt_path = conversation_dir / "messages.txt"
            meta_path = conversation_dir / "meta.json"
            if txt_path.is_file():
                meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
                conversations.append(_parse_txt_conversation(txt_path.read_text(encoding="utf-8"), meta, source.account))
        return conversations

    def _load_zip_conversations(self, source: _ExportSource) -> list[dict[str, Any]]:
        conversations: list[dict[str, Any]] = []
        with zipfile.ZipFile(source.path) as zf:
            names = set(zf.namelist())
            prefix = source.zip_prefix
            for name in sorted(names):
                if not name.startswith(f"{prefix}conversations/") or not name.endswith("/messages.json"):
                    continue
                with zf.open(name) as file:
                    conversations.append(json.loads(file.read().decode("utf-8")))
            json_dirs = {
                name.rsplit("/", 1)[0]
                for name in names
                if name.startswith(f"{prefix}conversations/") and name.endswith("/messages.json")
            }
            for name in sorted(names):
                if not name.startswith(f"{prefix}conversations/") or not name.endswith("/messages.txt"):
                    continue
                conv_dir = name.rsplit("/", 1)[0]
                if conv_dir in json_dirs:
                    continue
                meta_name = f"{conv_dir}/meta.json"
                meta = {}
                if meta_name in names:
                    with zf.open(meta_name) as file:
                        meta = json.loads(file.read().decode("utf-8"))
                with zf.open(name) as file:
                    conversations.append(_parse_txt_conversation(file.read().decode("utf-8"), meta, source.account))
        return conversations


def _read_manifest_account(manifest_path: Path) -> str:
    return _pick_text(json.loads(manifest_path.read_text(encoding="utf-8")).get("account"))


def _read_zip_manifest_account(zf: zipfile.ZipFile, prefix: str) -> str:
    with zf.open(f"{prefix}manifest.json") as file:
        return _pick_text(json.loads(file.read().decode("utf-8")).get("account"))


def _discover_zip_prefix(zf: zipfile.ZipFile) -> str | None:
    names = [name for name in zf.namelist() if name and not name.endswith("/")]
    if not names:
        return None

    candidate_prefixes = {""}
    for name in names:
        if not name.endswith("manifest.json"):
            continue
        prefix = name[: -len("manifest.json")]
        candidate_prefixes.add(prefix)

    for prefix in sorted(candidate_prefixes, key=len):
        manifest_name = f"{prefix}manifest.json"
        if manifest_name not in names:
            continue
        if any(
            name.startswith(f"{prefix}conversations/") and name.endswith(("/messages.json", "/messages.txt"))
            for name in names
        ):
            return prefix
    return None


def _normalize_message_type(row: dict[str, Any]) -> str:
    render_type = _pick_text(row.get("renderType"), row.get("messageType"), row.get("type")).lower()
    if render_type == "1":
        return "text"
    if render_type in {"", "text"}:
        return "text"
    if render_type == "system":
        return "system"
    return render_type


def _normalize_timestamp(value: object) -> int:
    try:
        timestamp = int(float(value or 0))
    except (TypeError, ValueError):
        return 0
    if timestamp > 10_000_000_000:
        return timestamp // 1000
    return timestamp


def _parse_txt_conversation(text: str, meta: dict[str, Any], account: str) -> dict[str, Any]:
    conversation = meta.get("conversation") if isinstance(meta.get("conversation"), dict) else meta
    if not isinstance(conversation, dict):
        conversation = {}
    conversation_username = _pick_text(conversation.get("username"))
    conversation_is_group = bool(conversation.get("isGroup", False))
    messages: list[dict[str, Any]] = []
    for index, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        system_match = re.match(r"^\[(?P<time>.+?)\]\s+\[系统\]\s*(?P<content>.*)$", line)
        if system_match:
            messages.append(
                {
                    "id": f"txt:{index}",
                    "createTime": 0,
                    "renderType": "system",
                    "isSent": False,
                    "senderUsername": "",
                    "conversationUsername": conversation_username,
                    "content": system_match.group("content"),
                }
            )
            continue
        match = re.match(r"^\[(?P<time>.+?)\]\s+(?P<sender>.+?):\s*(?P<content>.*)$", line)
        if not match:
            continue
        sender_label = match.group("sender").strip()
        sender = _extract_wxid(sender_label) or sender_label
        is_sent = sender in {"我", "me", account}
        sender_username = account if is_sent else sender
        if not is_sent and not _extract_wxid(sender_label) and conversation_username and not conversation_is_group:
            sender_username = conversation_username
        messages.append(
            {
                "id": f"txt:{index}",
                "createTime": 0,
                "renderType": "text",
                "isSent": is_sent,
                "senderUsername": sender_username,
                "senderDisplayName": sender_label,
                "conversationUsername": conversation_username,
                "content": match.group("content"),
            }
        )
    return {
        "schemaVersion": meta.get("schemaVersion", 1) if isinstance(meta, dict) else 1,
        "account": account,
        "conversation": conversation,
        "messages": messages,
    }


def _extract_wxid(sender: str) -> str:
    match = re.search(r"\((?P<wxid>[^()]+)\)\s*$", sender.strip())
    return match.group("wxid").strip() if match else ""


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _pick_text(*values: object) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""
