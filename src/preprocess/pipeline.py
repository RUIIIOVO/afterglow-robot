from __future__ import annotations

import re
from collections import Counter, defaultdict

from src.models.messages import (
    CandidateMessage,
    DialogTurn,
    FewshotCandidate,
    FewshotSample,
    NormalizedMessage,
    PersonaProfile,
    RagRecord,
    VoiceUtterance,
)
from src.runtime.errors import NoTextMessagesError

_WHITESPACE_RE = re.compile(r"\s+")
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F900-\U0001F9FF"
    "\u2600-\u26FF"
    "\u2700-\u27BF"
    "]+",
    flags=re.UNICODE,
)
_ENDING_PUNCTUATIONS = ("。", "！", "？", "!", "?", "~", "～", "…")
_TONE_WORD_CANDIDATES = (
    "哈哈",
    "嘿嘿",
    "嗯",
    "啊",
    "呀",
    "啦",
    "呢",
    "吧",
    "哦",
    "哇",
    "嘛",
    "诶",
)
_PREFERRED_TERM_CANDIDATES = (
    "你",
    "你们",
    "我",
    "我们",
    "他",
    "她",
    "宝",
    "宝宝",
    "亲",
    "老婆",
    "老公",
)
_EXPLANATORY_MARKERS = ("因为", "所以", "但是", "不过", "刚", "准备", "已经", "正在", "先", "再")


def clean_messages(
    candidates: list[CandidateMessage],
    min_text_length: int,
    source_parser: str = "",
) -> list[NormalizedMessage]:
    cleaned_rows: list[dict[str, object]] = []
    for item in candidates:
        display_text = _normalize_display_text(item.text)
        normalized_text = _normalize_text(item.text)
        if item.is_system:
            continue
        if item.message_type != "text":
            continue
        if not normalized_text:
            continue
        if len(normalized_text) < min_text_length:
            continue
        cleaned_rows.append(
            {
                "message_id": item.message_id,
                "timestamp": item.timestamp,
                "sender_role": item.sender_role,
                "sender_wxid": item.sender_wxid,
                "conversation_id": item.conversation_id,
                "message_type": "text",
                "text": normalized_text,
                "display_text": display_text,
                "normalized_text": normalized_text,
                "text_length": len(normalized_text),
                "source_parser": source_parser,
            }
        )

    rows_by_conversation: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in cleaned_rows:
        rows_by_conversation[str(row["conversation_id"])].append(row)

    normalized: list[NormalizedMessage] = []
    for conversation_rows in rows_by_conversation.values():
        conversation_rows.sort(key=lambda item: (int(item["timestamp"]), str(item["message_id"])))
        for index, row in enumerate(conversation_rows):
            prev_message_id = str(conversation_rows[index - 1]["message_id"]) if index > 0 else ""
            next_message_id = str(conversation_rows[index + 1]["message_id"]) if index + 1 < len(conversation_rows) else ""
            normalized.append(
                NormalizedMessage(
                    message_id=str(row["message_id"]),
                    timestamp=int(row["timestamp"]),
                    sender_role=str(row["sender_role"]),
                    sender_wxid=str(row["sender_wxid"]),
                    conversation_id=str(row["conversation_id"]),
                    message_type="text",
                    text=str(row["text"]),
                    display_text=str(row["display_text"]),
                    normalized_text=str(row["normalized_text"]),
                    text_length=int(row["text_length"]),
                    turn_index=index + 1,
                    prev_message_id=prev_message_id,
                    next_message_id=next_message_id,
                    source_parser=str(row["source_parser"]),
                )
            )
    normalized.sort(key=lambda item: (item.timestamp, item.message_id))
    return normalized


def ensure_non_empty(messages: list[NormalizedMessage], target_wxid: str) -> None:
    if not messages:
        raise NoTextMessagesError(target_wxid=target_wxid)


def build_dialog_turns(messages: list[NormalizedMessage]) -> list[DialogTurn]:
    turns: list[DialogTurn] = []
    for index in range(1, len(messages)):
        prev = messages[index - 1]
        curr = messages[index]
        if prev.conversation_id != curr.conversation_id:
            continue
        if curr.sender_role != "target":
            continue
        if prev.sender_role == "target":
            continue
        turns.append(
            DialogTurn(
                turn_id=f"turn-{len(turns) + 1:06d}",
                conversation_id=curr.conversation_id,
                context_message_id=prev.message_id,
                response_message_id=curr.message_id,
                context=prev.display_text,
                response=curr.display_text,
                normalized_context=prev.normalized_text,
                normalized_response=curr.normalized_text,
                timestamp=curr.timestamp,
            )
        )
    return turns


def build_voice_utterances(messages: list[NormalizedMessage]) -> list[VoiceUtterance]:
    return [
        VoiceUtterance(
            utterance_id=f"utt-{index + 1:06d}",
            source_message_id=message.message_id,
            conversation_id=message.conversation_id,
            timestamp=message.timestamp,
            text=message.text,
            display_text=message.display_text,
            normalized_text=message.normalized_text,
            text_length=message.text_length,
            ending_punctuation=_extract_ending_punctuation(message.display_text),
            tone_words=_extract_tone_words(message.normalized_text),
            emojis=_extract_emojis(message.display_text),
            has_question=_has_question(message.normalized_text),
        )
        for index, message in enumerate(messages)
    ]


def build_persona_profile(
    messages: list[NormalizedMessage],
    voice_utterances: list[VoiceUtterance],
    target_wxid: str,
) -> PersonaProfile:
    message_count = len(messages)
    avg_length = round(sum(item.text_length for item in messages) / message_count, 2) if message_count else 0.0
    ending_counter = Counter(item.ending_punctuation for item in voice_utterances if item.ending_punctuation)
    tone_counter = Counter(word for item in voice_utterances for word in item.tone_words)
    emoji_counter = Counter(emoji for item in voice_utterances for emoji in item.emojis)
    preferred_term_counter = Counter(
        term for message in messages for term in _extract_preferred_terms(message.normalized_text)
    )
    question_count = sum(1 for item in voice_utterances if item.has_question)
    explanatory_count = sum(1 for item in messages if _is_explanatory(item.normalized_text))
    style_tendency = "解释型" if message_count and explanatory_count / message_count >= 0.35 else "直接回应型"
    return PersonaProfile(
        target_wxid=target_wxid,
        message_count=message_count,
        avg_response_length=avg_length,
        response_length_label=_classify_length(avg_length),
        preferred_terms=_top_keys(preferred_term_counter, limit=5),
        sentence_endings=_top_keys(ending_counter, limit=3),
        tone_words=_top_keys(tone_counter, limit=5),
        emojis=_top_keys(emoji_counter, limit=5),
        question_ratio=round(question_count / message_count, 3) if message_count else 0.0,
        style_tendency=style_tendency,
    )


def build_persona_prompt(profile: PersonaProfile) -> str:
    sections = [
        "你是一个微信聊天助手。",
        f"目标称呼占位：{profile.target_wxid}",
        f"回复长度偏好：{profile.response_length_label}，平均长度约 {profile.avg_response_length:.2f} 字。",
        f"表达倾向：{profile.style_tendency}。",
    ]
    if profile.preferred_terms:
        sections.append(f"常用称呼/代词：{'、'.join(profile.preferred_terms)}。")
    if profile.sentence_endings:
        sections.append(f"句末标点偏好：{'、'.join(profile.sentence_endings)}。")
    if profile.tone_words:
        sections.append(f"高频语气词/口头禅：{'、'.join(profile.tone_words)}。")
    if profile.emojis:
        sections.append(f"常用 emoji：{' '.join(profile.emojis)}。")
    sections.extend(
        [
            f"提问句占比：{profile.question_ratio:.1%}。",
            "风格约束：保持口语化、简洁、贴近日常聊天语气。",
            "禁止暴露 AI 身份。",
            "禁止编造明确记忆或未经提供的事实。",
        ]
    )
    return "\n".join(sections)


def build_fewshot_candidates(
    turns: list[DialogTurn],
    profile: PersonaProfile,
) -> list[FewshotCandidate]:
    signature_counter = Counter(
        f"{turn.normalized_context}=>{turn.normalized_response}"
        for turn in turns
    )
    candidates: list[FewshotCandidate] = []
    total_turns = max(len(turns), 1)
    for index, turn in enumerate(turns):
        reasons: list[str] = []
        completeness_score = min(len(turn.normalized_context), 24) / 24 + min(len(turn.normalized_response), 24) / 24
        if len(turn.normalized_context) >= 4 and len(turn.normalized_response) >= 4:
            completeness_score += 0.5
            reasons.append("上下文完整")

        style_score = 0.0
        if any(word in turn.normalized_response for word in profile.tone_words):
            style_score += 0.8
            reasons.append("命中高频语气词")
        if any(emoji in turn.response for emoji in profile.emojis):
            style_score += 0.8
            reasons.append("命中高频 emoji")
        if any(turn.response.endswith(punctuation) for punctuation in profile.sentence_endings):
            style_score += 0.4
            reasons.append("符合句末标点偏好")

        signature = f"{turn.normalized_context}=>{turn.normalized_response}"
        duplicate_penalty = max(signature_counter[signature] - 1, 0) * 1.2
        if duplicate_penalty > 0:
            reasons.append("重复样本降权")

        recency_score = ((index + 1) / total_turns) * 0.6
        reasons.append("轻度近期加权")

        score = round(completeness_score + style_score + recency_score - duplicate_penalty, 4)
        candidates.append(
            FewshotCandidate(
                turn_id=turn.turn_id,
                context_message_id=turn.context_message_id,
                response_message_id=turn.response_message_id,
                context=turn.context,
                response=turn.response,
                normalized_context=turn.normalized_context,
                normalized_response=turn.normalized_response,
                score=score,
                reasons=reasons,
                timestamp=turn.timestamp,
            )
        )
    candidates.sort(key=lambda item: (-item.score, -item.timestamp, item.turn_id))
    return candidates


def select_fewshots(candidates: list[FewshotCandidate], limit: int) -> list[FewshotSample]:
    selected: list[FewshotSample] = []
    seen_pair_signatures: set[str] = set()
    seen_responses: set[str] = set()
    deferred: list[FewshotCandidate] = []

    for candidate in candidates:
        pair_signature = f"{candidate.normalized_context}=>{candidate.normalized_response}"
        if pair_signature in seen_pair_signatures:
            continue
        if candidate.normalized_response in seen_responses:
            deferred.append(candidate)
            continue
        selected.append(FewshotSample(context=candidate.context, response=candidate.response))
        seen_pair_signatures.add(pair_signature)
        seen_responses.add(candidate.normalized_response)
        if len(selected) >= limit:
            return selected

    for candidate in deferred:
        pair_signature = f"{candidate.normalized_context}=>{candidate.normalized_response}"
        if pair_signature in seen_pair_signatures:
            continue
        selected.append(FewshotSample(context=candidate.context, response=candidate.response))
        seen_pair_signatures.add(pair_signature)
        if len(selected) >= limit:
            break
    return selected


def build_rag_corpus(
    messages: list[NormalizedMessage],
    dialog_turns: list[DialogTurn],
    resolved_target_wxid: str,
) -> list[RagRecord]:
    records: list[RagRecord] = []
    turns_by_response_message_id = {
        turn.response_message_id: turn
        for turn in dialog_turns
    }
    for index, message in enumerate(messages):
        turn = turns_by_response_message_id.get(message.message_id)
        context = turn.context if turn else ""
        records.append(
            RagRecord(
                id=f"rag-{index + 1:06d}",
                turn_id=turn.turn_id if turn else "",
                context=context,
                text=message.display_text,
                timestamp=message.timestamp,
                target_wxid=resolved_target_wxid,
                source_message_id=message.message_id,
            )
        )
    return records


def _normalize_display_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", str(text).replace("\u3000", " ").strip())


def _normalize_text(text: str) -> str:
    return _normalize_display_text(text)


def _extract_ending_punctuation(text: str) -> str:
    normalized = text.strip()
    for punctuation in _ENDING_PUNCTUATIONS:
        if normalized.endswith(punctuation):
            return punctuation
    return ""


def _extract_tone_words(text: str) -> list[str]:
    return [word for word in _TONE_WORD_CANDIDATES if word in text]


def _extract_preferred_terms(text: str) -> list[str]:
    return [term for term in _PREFERRED_TERM_CANDIDATES if term in text]


def _extract_emojis(text: str) -> list[str]:
    matches = _EMOJI_RE.findall(text)
    emojis: list[str] = []
    for chunk in matches:
        emojis.extend(list(chunk))
    return emojis


def _has_question(text: str) -> bool:
    normalized = text.strip()
    return normalized.endswith(("?", "？")) or "吗" in normalized


def _classify_length(avg_length: float) -> str:
    if avg_length < 8:
        return "偏短句，默认 1 句"
    if avg_length < 18:
        return "中短句，默认 1-2 句"
    return "可用 1-3 句，必要时补充解释"


def _is_explanatory(text: str) -> bool:
    return any(marker in text for marker in _EXPLANATORY_MARKERS) or "，" in text or "," in text


def _top_keys(counter: Counter[str], limit: int) -> list[str]:
    return [item for item, _count in counter.most_common(limit)]
