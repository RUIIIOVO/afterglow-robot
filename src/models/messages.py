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
    display_text: str
    normalized_text: str
    text_length: int
    turn_index: int
    prev_message_id: str
    next_message_id: str
    source_parser: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DialogTurn:
    turn_id: str
    conversation_id: str
    context_message_id: str
    response_message_id: str
    context: str
    response: str
    normalized_context: str
    normalized_response: str
    timestamp: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FewshotSample:
    context: str
    response: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FewshotCandidate:
    turn_id: str
    context_message_id: str
    response_message_id: str
    context: str
    response: str
    normalized_context: str
    normalized_response: str
    score: float
    reasons: list[str]
    timestamp: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RagRecord:
    id: str
    turn_id: str
    context: str
    text: str
    timestamp: int
    target_wxid: str
    source_message_id: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class VoiceUtterance:
    utterance_id: str
    source_message_id: str
    conversation_id: str
    timestamp: int
    text: str
    display_text: str
    normalized_text: str
    text_length: int
    ending_punctuation: str
    tone_words: list[str]
    emojis: list[str]
    has_question: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PersonaProfile:
    target_wxid: str
    message_count: int
    avg_response_length: float
    response_length_label: str
    preferred_terms: list[str]
    sentence_endings: list[str]
    tone_words: list[str]
    emojis: list[str]
    question_ratio: float
    style_tendency: str

    def to_dict(self) -> dict:
        return asdict(self)
