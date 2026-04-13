from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ConversationHistoryEntry:
    role: str
    content: str
    timestamp: int
    sender_id: str = ""
    event_id: str = ""

    def to_dict(self) -> dict:
        payload = {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }
        if self.sender_id:
            payload["sender_id"] = self.sender_id
        if self.event_id:
            payload["event_id"] = self.event_id
        return payload


class ConversationHistoryStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def load_history(self, conversation_id: str, limit: int) -> list[dict[str, str]]:
        history_file = self._history_file(conversation_id)
        if not history_file.exists():
            return []

        rows: list[dict[str, str]] = []
        with history_file.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                role = str(row.get("role", "")).strip()
                content = str(row.get("content", "")).strip()
                if not role or not content:
                    continue
                rows.append({"role": role, "content": content})
        if len(rows) > limit:
            return rows[-limit:]
        return rows

    def append_entries(self, conversation_id: str, entries: list[ConversationHistoryEntry]) -> None:
        valid_entries = [entry for entry in entries if entry.content.strip()]
        if not valid_entries:
            return

        history_file = self._history_file(conversation_id)
        history_file.parent.mkdir(parents=True, exist_ok=True)
        with history_file.open("a", encoding="utf-8", newline="\n") as file:
            for entry in valid_entries:
                file.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    def _history_file(self, conversation_id: str) -> Path:
        normalized = conversation_id.strip()
        if normalized:
            digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
            file_name = f"{_safe_segment(normalized)}.{digest}.jsonl"
        else:
            file_name = "unknown.jsonl"
        return self.base_dir / file_name


def _safe_segment(value: str) -> str:
    chars: list[str] = []
    for ch in value:
        if ch.isalnum() or ch in {"-", "_", "."}:
            chars.append(ch)
        else:
            chars.append("_")
    normalized = "".join(chars).strip("._")
    return normalized[:80] or "conversation"
