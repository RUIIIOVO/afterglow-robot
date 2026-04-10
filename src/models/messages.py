from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Contact:
    wxid: str
    display_name: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RawMessage:
    message_id: str
    timestamp: int
    sender_wxid: str
    conversation_id: str
    message_type: str
    text: str
    is_system: bool = False


@dataclass(frozen=True)
class CandidateMessage:
    message_id: str
    timestamp: int
    sender_role: str
    sender_wxid: str
    conversation_id: str
    message_type: str
    text: str
    is_system: bool = False


@dataclass(frozen=True)
class NormalizedMessage:
    message_id: str
    timestamp: int
    sender_role: str
    sender_wxid: str
    conversation_id: str
    message_type: str
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FewshotSample:
    context: str
    response: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RagRecord:
    id: str
    context: str
    text: str
    timestamp: int
    target_wxid: str
    source_message_id: str

    def to_dict(self) -> dict:
        return asdict(self)

