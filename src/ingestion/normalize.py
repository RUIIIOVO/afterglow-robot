from __future__ import annotations

from pathlib import Path

from src.ingestion.parsers.base import ExportParser
from src.models.messages import CandidateMessage, Contact
from src.runtime.errors import TargetNotFoundError


def extract_target_candidates(
    parser: ExportParser,
    export_dir: Path,
    account_wxid: str,
    target_wxid: str,
    contacts: list[Contact],
) -> tuple[list[CandidateMessage], str]:
    raw_messages = parser.load_messages(export_dir, account_wxid)
    target_is_self = target_wxid == "self"
    resolved_target_wxid = account_wxid if target_is_self else target_wxid
    if not target_is_self and target_wxid not in {contact.wxid for contact in contacts}:
        raise TargetNotFoundError(target_wxid=target_wxid, account_wxid=account_wxid)

    candidates: list[CandidateMessage] = []
    for raw in raw_messages:
        sender_role = _map_sender_role(raw.sender_wxid, account_wxid, resolved_target_wxid)
        if target_is_self:
            if sender_role != "self":
                continue
        elif sender_role != "target":
            continue
        candidates.append(
            CandidateMessage(
                message_id=raw.message_id,
                timestamp=raw.timestamp,
                sender_role=sender_role,
                sender_wxid=raw.sender_wxid,
                conversation_id=raw.conversation_id,
                message_type=raw.message_type,
                text=raw.text,
                is_system=raw.is_system,
            )
        )
    candidates.sort(key=lambda item: item.timestamp)
    return candidates, resolved_target_wxid


def _map_sender_role(sender_wxid: str, account_wxid: str, target_wxid: str) -> str:
    if sender_wxid == account_wxid:
        return "self"
    if sender_wxid == target_wxid:
        return "target"
    return ""

