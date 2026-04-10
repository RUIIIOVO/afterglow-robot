from __future__ import annotations

import json
from typing import Any


def build_prompt(
    persona_prompt: str,
    fewshots: list[dict[str, str]],
    rag_hits: list[dict[str, Any]],
    history: list[dict[str, str]],
    user_message: str,
) -> str:
    sections: list[str] = []
    sections.append("## system_prompt")
    sections.append(persona_prompt.strip())

    sections.append("\n## few_shot")
    for index, sample in enumerate(fewshots, start=1):
        sections.append(f"[样例{index}] 上文：{sample['context']} | 回复：{sample['response']}")

    sections.append("\n## rag")
    for index, hit in enumerate(rag_hits, start=1):
        sections.append(
            f"[检索{index}] context={hit.get('context','')} text={hit.get('text','')} distance={hit.get('distance')}"
        )

    sections.append("\n## history")
    for entry in history:
        role = entry.get("role", "user")
        content = entry.get("content", "")
        sections.append(f"{role}: {content}")

    sections.append("\n## current_user_message")
    sections.append(user_message)
    sections.append("\n只输出最终回复文本。")
    return "\n".join(sections)


def parse_history(raw: object, limit: int) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    history: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, str):
            history.append({"role": "user", "content": item})
        elif isinstance(item, dict):
            role = str(item.get("role", "user"))
            content = str(item.get("content", ""))
            history.append({"role": role, "content": content})
    if len(history) > limit:
        return history[-limit:]
    return history


def parse_fewshots(raw: object, limit: int) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    fewshots: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        context = str(item.get("context", "")).strip()
        response = str(item.get("response", "")).strip()
        if not context or not response:
            continue
        fewshots.append({"context": context, "response": response})
    if len(fewshots) > limit:
        return fewshots[:limit]
    return fewshots


def dump_debug_payload(
    prompt: str,
    rag_hits: list[dict[str, Any]],
    response: str,
) -> dict[str, Any]:
    return {"prompt": prompt, "rag_hits": rag_hits, "response": response}


def to_pretty_json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)

