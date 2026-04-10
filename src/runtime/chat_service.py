from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.common.config import AppConfig
from src.common.io_utils import read_json
from src.rag.prompt_builder import build_prompt, parse_fewshots, parse_history
from src.runtime.errors import ConfigValidationError, IngestArtifactsMissingError
from src.runtime.ollama_client import OllamaClient
from src.vectorstore.chroma_store import ChromaVectorStore


@dataclass(frozen=True)
class ChatReplyResult:
    reply_text: str
    prompt: str
    rag_hits: list[dict[str, Any]]


def generate_chat_reply(
    config: AppConfig,
    message: str,
    history: object | None = None,
) -> ChatReplyResult:
    text = message.strip()
    if not text:
        raise ConfigValidationError("--message 不能为空")

    output_base = config.resolve_path(config.output.base_dir)
    persona_prompt = _read_required_text(output_base / "persona_prompt.txt")
    fewshots_raw = read_json(_read_required_path(output_base / "fewshot.json"))
    fewshots = parse_fewshots(fewshots_raw, limit=config.conversation.fewshot_limit)
    history_rows = parse_history(history or [], limit=config.conversation.history_limit)

    chroma_dir = config.resolve_path(config.embedding.chroma_dir)
    vector_store = ChromaVectorStore(chroma_dir=chroma_dir, model_name=config.embedding.model_name)
    rag_hits = vector_store.query(text, top_k=config.retrieval.top_k)
    prompt = build_prompt(
        persona_prompt=persona_prompt,
        fewshots=fewshots,
        rag_hits=rag_hits,
        history=history_rows,
        user_message=text,
    )
    ollama = OllamaClient(config.llm)
    ollama.check_health()
    reply_text = ollama.generate(prompt)
    return ChatReplyResult(reply_text=reply_text, prompt=prompt, rag_hits=rag_hits)


def _read_required_path(path: Path) -> Path:
    if not path.exists():
        raise IngestArtifactsMissingError(str(path))
    return path


def _read_required_text(path: Path) -> str:
    content = _read_required_path(path).read_text(encoding="utf-8").strip()
    if not content:
        raise IngestArtifactsMissingError(str(path))
    return content

