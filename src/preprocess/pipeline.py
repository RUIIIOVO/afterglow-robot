from __future__ import annotations

from src.models.messages import CandidateMessage, FewshotSample, NormalizedMessage, RagRecord
from src.runtime.errors import NoTextMessagesError


def clean_messages(candidates: list[CandidateMessage], min_text_length: int) -> list[NormalizedMessage]:
    normalized: list[NormalizedMessage] = []
    for item in candidates:
        text = item.text.strip()
        if item.is_system:
            continue
        if item.message_type != "text":
            continue
        if not text:
            continue
        if len(text) < min_text_length:
            continue
        normalized.append(
            NormalizedMessage(
                message_id=item.message_id,
                timestamp=item.timestamp,
                sender_role=item.sender_role,
                sender_wxid=item.sender_wxid,
                conversation_id=item.conversation_id,
                message_type="text",
                text=text,
            )
        )
    return normalized


def ensure_non_empty(messages: list[NormalizedMessage], target_wxid: str) -> None:
    if not messages:
        raise NoTextMessagesError(target_wxid=target_wxid)


def build_fewshot(messages: list[NormalizedMessage], limit: int) -> list[FewshotSample]:
    candidates: list[FewshotSample] = []
    for index in range(1, len(messages)):
        prev = messages[index - 1]
        curr = messages[index]
        if prev.conversation_id != curr.conversation_id:
            continue
        candidates.append(FewshotSample(context=prev.text, response=curr.text))
    candidates.sort(key=lambda item: len(item.context) + len(item.response), reverse=True)
    return candidates[:limit]


def build_rag_corpus(messages: list[NormalizedMessage], resolved_target_wxid: str) -> list[RagRecord]:
    records: list[RagRecord] = []
    for index, message in enumerate(messages):
        context = ""
        if index > 0 and messages[index - 1].conversation_id == message.conversation_id:
            context = messages[index - 1].text
        records.append(
            RagRecord(
                id=f"rag-{index + 1:06d}",
                context=context,
                text=message.text,
                timestamp=message.timestamp,
                target_wxid=resolved_target_wxid,
                source_message_id=message.message_id,
            )
        )
    return records


def build_persona_prompt(target_wxid: str) -> str:
    return "\n".join(
        [
            "你是一个微信聊天助手。",
            f"目标称呼占位：{target_wxid}",
            "风格约束：保持口语化、简洁、贴近日常聊天语气。",
            "回复长度偏好：默认 1-3 句，不要过长。",
            "禁止暴露 AI 身份。",
            "禁止编造明确记忆或未经提供的事实。",
        ]
    )

