from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

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

    @property
    def workspace_dir(self) -> Path:
        if self.config_dir.name.lower() == "config":
            return self.config_dir.parent
        return self.config_dir

    def resolve_path(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return (self.workspace_dir / path).resolve()


def _require(raw: dict[str, Any], path: str) -> Any:
    current: Any = raw
    keys = path.split(".")
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            raise ConfigValidationError(path, context={"missing_key": path})
        current = current[key]
    return current


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def load_config(config_path: str | Path) -> AppConfig:
    path = Path(config_path)
    if not path.exists():
        raise ConfigFileNotFoundError(str(path))
    with path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}
    try:
        config = AppConfig(
            wechat=WechatConfig(
                export_dir=str(_require(raw, "wechat.export_dir")).strip(),
                account_wxid=_optional_text(raw.get("wechat", {}).get("account_wxid")),
                target_wxid=str(_require(raw, "wechat.target_wxid")).strip(),
            ),
            output=OutputConfig(
                base_dir=str(_require(raw, "output.base_dir")).strip(),
            ),
            dataset=DatasetConfig(
                min_text_length=int(_require(raw, "dataset.min_text_length")),
                fewshot_limit=int(_require(raw, "dataset.fewshot_limit")),
            ),
            embedding=EmbeddingConfig(
                model_name=str(_require(raw, "embedding.model_name")).strip(),
                chroma_dir=str(_require(raw, "embedding.chroma_dir")).strip(),
            ),
            retrieval=RetrievalConfig(
                top_k=int(_require(raw, "retrieval.top_k")),
            ),
            llm=LLMConfig(
                endpoint=str(_require(raw, "llm.endpoint")).strip(),
                model=str(_require(raw, "llm.model")).strip(),
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
    if config.wechat.export_dir == "":
        raise ConfigValidationError(
            "wechat.export_dir 不能为空",
            context={"field": "wechat.export_dir", "hint": "填写 WeChatDataAnalysis 导出目录或导出 ZIP 路径。"},
        )
    if config.wechat.target_wxid.strip() == "":
        raise ConfigValidationError(
            "wechat.target_wxid 不能为空",
            context={"field": "wechat.target_wxid", "hint": "可填写联系人 wxid，或使用 self 提取号主本人消息。"},
        )
    if config.output.base_dir == "":
        raise ConfigValidationError("output.base_dir 不能为空", context={"field": "output.base_dir"})
    if config.embedding.model_name == "":
        raise ConfigValidationError("embedding.model_name 不能为空", context={"field": "embedding.model_name"})
    if config.embedding.chroma_dir == "":
        raise ConfigValidationError("embedding.chroma_dir 不能为空", context={"field": "embedding.chroma_dir"})
    if config.dataset.min_text_length <= 0:
        raise ConfigValidationError("dataset.min_text_length 必须大于 0")
    if config.dataset.fewshot_limit <= 0:
        raise ConfigValidationError("dataset.fewshot_limit 必须大于 0")
    if config.retrieval.top_k <= 0:
        raise ConfigValidationError("retrieval.top_k 必须大于 0")
    if config.llm.endpoint == "":
        raise ConfigValidationError("llm.endpoint 不能为空", context={"field": "llm.endpoint"})
    parsed_endpoint = urlparse(config.llm.endpoint)
    if parsed_endpoint.scheme not in {"http", "https"} or not parsed_endpoint.netloc:
        raise ConfigValidationError(
            "llm.endpoint 必须是 http/https URL",
            context={"field": "llm.endpoint", "value": config.llm.endpoint},
        )
    if config.llm.model == "":
        raise ConfigValidationError("llm.model 不能为空", context={"field": "llm.model"})
    if not 0 <= config.llm.temperature <= 2:
        raise ConfigValidationError("llm.temperature 必须在 0 到 2 之间")
    if config.llm.timeout_seconds <= 0:
        raise ConfigValidationError("llm.timeout_seconds 必须大于 0")
    if config.conversation.history_limit <= 0:
        raise ConfigValidationError("conversation.history_limit 必须大于 0")
    if config.conversation.fewshot_limit <= 0:
        raise ConfigValidationError("conversation.fewshot_limit 必须大于 0")
