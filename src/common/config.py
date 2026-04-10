from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.runtime.errors import ConfigFileNotFoundError, ConfigValidationError


@dataclass(frozen=True)
class WechatConfig:
    export_dir: str
    account_wxid: str | None
    target_wxid: str


@dataclass(frozen=True)
class OutputConfig:
    base_dir: str


@dataclass(frozen=True)
class DatasetConfig:
    min_text_length: int
    fewshot_limit: int


@dataclass(frozen=True)
class EmbeddingConfig:
    model_name: str
    chroma_dir: str


@dataclass(frozen=True)
class RetrievalConfig:
    top_k: int


@dataclass(frozen=True)
class LLMConfig:
    endpoint: str
    model: str
    temperature: float
    timeout_seconds: int


@dataclass(frozen=True)
class ConversationConfig:
    history_limit: int
    fewshot_limit: int


@dataclass(frozen=True)
class AppConfig:
    wechat: WechatConfig
    output: OutputConfig
    dataset: DatasetConfig
    embedding: EmbeddingConfig
    retrieval: RetrievalConfig
    llm: LLMConfig
    conversation: ConversationConfig
    config_path: Path

    @property
    def config_dir(self) -> Path:
        return self.config_path.parent

    def resolve_path(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return (self.config_dir / path).resolve()


def _require(raw: dict[str, Any], path: str) -> Any:
    current: Any = raw
    keys = path.split(".")
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            raise ConfigValidationError(path, context={"missing_key": path})
        current = current[key]
    return current


def load_config(config_path: str | Path) -> AppConfig:
    path = Path(config_path)
    if not path.exists():
        raise ConfigFileNotFoundError(str(path))
    with path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}
    try:
        config = AppConfig(
            wechat=WechatConfig(
                export_dir=str(_require(raw, "wechat.export_dir")),
                account_wxid=raw.get("wechat", {}).get("account_wxid"),
                target_wxid=str(_require(raw, "wechat.target_wxid")),
            ),
            output=OutputConfig(
                base_dir=str(_require(raw, "output.base_dir")),
            ),
            dataset=DatasetConfig(
                min_text_length=int(_require(raw, "dataset.min_text_length")),
                fewshot_limit=int(_require(raw, "dataset.fewshot_limit")),
            ),
            embedding=EmbeddingConfig(
                model_name=str(_require(raw, "embedding.model_name")),
                chroma_dir=str(_require(raw, "embedding.chroma_dir")),
            ),
            retrieval=RetrievalConfig(
                top_k=int(_require(raw, "retrieval.top_k")),
            ),
            llm=LLMConfig(
                endpoint=str(_require(raw, "llm.endpoint")),
                model=str(_require(raw, "llm.model")),
                temperature=float(_require(raw, "llm.temperature")),
                timeout_seconds=int(_require(raw, "llm.timeout_seconds")),
            ),
            conversation=ConversationConfig(
                history_limit=int(_require(raw, "conversation.history_limit")),
                fewshot_limit=int(_require(raw, "conversation.fewshot_limit")),
            ),
            config_path=path.resolve(),
        )
    except ValueError as error:
        raise ConfigValidationError(
            "配置字段类型错误",
            context={"error": str(error)},
        ) from error
    _validate_config(config)
    return config


def _validate_config(config: AppConfig) -> None:
    if config.wechat.target_wxid.strip() == "":
        raise ConfigValidationError("wechat.target_wxid 不能为空")
    if config.dataset.min_text_length <= 0:
        raise ConfigValidationError("dataset.min_text_length 必须大于 0")
    if config.dataset.fewshot_limit <= 0:
        raise ConfigValidationError("dataset.fewshot_limit 必须大于 0")
    if config.retrieval.top_k <= 0:
        raise ConfigValidationError("retrieval.top_k 必须大于 0")
    if config.conversation.history_limit <= 0:
        raise ConfigValidationError("conversation.history_limit 必须大于 0")
    if config.conversation.fewshot_limit <= 0:
        raise ConfigValidationError("conversation.fewshot_limit 必须大于 0")

