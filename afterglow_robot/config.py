from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

"""配置加载与路径解析。"""


@dataclass(slots=True)
class WechatConfig:
    """微信导出源配置。"""

    export_dir: Path
    account_wxid: str | None = None
    target_wxid: str | None = None


@dataclass(slots=True)
class OutputConfig:
    """离线产物输出配置。"""

    base_dir: Path


@dataclass(slots=True)
class DatasetConfig:
    """数据集筛选参数。"""

    min_text_length: int = 4
    fewshot_limit: int = 300


@dataclass(slots=True)
class EmbeddingConfig:
    """向量化相关配置。"""

    model_name: str = "BAAI/bge-small-zh-v1.5"
    chroma_dir: Path = Path("models/chroma_db")


@dataclass(slots=True)
class RetrievalConfig:
    """运行时检索配置。"""

    chroma_dir: Path = Path("models/chroma_db")
    top_k: int = 5


@dataclass(slots=True)
class LlmConfig:
    """本地 LLM 调用配置。"""

    endpoint: str = "http://localhost:11434"
    model: str = "qwen2.5:7b"
    temperature: float = 0.7
    timeout_seconds: int = 120


@dataclass(slots=True)
class ConversationConfig:
    """回复生成时的上下文配置。"""

    history_limit: int = 10
    fewshot_limit: int = 20


@dataclass(slots=True)
class AppConfig:
    """项目一级配置聚合对象。"""

    wechat: WechatConfig
    output: OutputConfig
    dataset: DatasetConfig
    embedding: EmbeddingConfig
    retrieval: RetrievalConfig
    llm: LlmConfig
    conversation: ConversationConfig


def _resolve_path(value: str | Path, base_dir: Path) -> Path:
    """将相对路径统一解析到配置文件所在目录。"""

    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return (base_dir / candidate).resolve()


def load_app_config(config_path: str | Path) -> AppConfig:
    """从 YAML 配置文件加载项目运行配置。"""

    path = Path(config_path).resolve()
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    base_dir = path.parent
    wechat_raw = raw.get("wechat", {})
    output_raw = raw.get("output", {})
    dataset_raw = raw.get("dataset", {})
    embedding_raw = raw.get("embedding", {})
    retrieval_raw = raw.get("retrieval", {})
    llm_raw = raw.get("llm", {})
    conversation_raw = raw.get("conversation", {})

    wechat = WechatConfig(
        export_dir=_resolve_path(wechat_raw["export_dir"], base_dir),
        account_wxid=wechat_raw.get("account_wxid"),
        target_wxid=wechat_raw.get("target_wxid"),
    )
    output = OutputConfig(
        base_dir=_resolve_path(output_raw.get("base_dir", "data/outputs"), base_dir),
    )
    dataset = DatasetConfig(
        min_text_length=int(dataset_raw.get("min_text_length", 4)),
        fewshot_limit=int(dataset_raw.get("fewshot_limit", 300)),
    )
    embedding = EmbeddingConfig(
        model_name=str(embedding_raw.get("model_name", "BAAI/bge-small-zh-v1.5")),
        chroma_dir=_resolve_path(embedding_raw.get("chroma_dir", "models/chroma_db"), base_dir),
    )
    retrieval_chroma_dir = retrieval_raw.get("chroma_dir", embedding.chroma_dir)
    retrieval = RetrievalConfig(
        chroma_dir=_resolve_path(retrieval_chroma_dir, base_dir),
        top_k=int(retrieval_raw.get("top_k", 5)),
    )
    llm = LlmConfig(
        endpoint=str(llm_raw.get("endpoint", "http://localhost:11434")),
        model=str(llm_raw.get("model", "qwen2.5:7b")),
        temperature=float(llm_raw.get("temperature", 0.7)),
        timeout_seconds=int(llm_raw.get("timeout_seconds", 120)),
    )
    conversation = ConversationConfig(
        history_limit=int(conversation_raw.get("history_limit", 10)),
        fewshot_limit=int(conversation_raw.get("fewshot_limit", 20)),
    )
    return AppConfig(
        wechat=wechat,
        output=output,
        dataset=dataset,
        embedding=embedding,
        retrieval=retrieval,
        llm=llm,
        conversation=conversation,
    )


def require_value(value: Any, field_name: str) -> Any:
    """校验必须配置，避免 CLI 在缺参时静默继续执行。"""

    if value is None or value == "":
        raise ValueError(f"缺少必要配置：{field_name}")
    return value
