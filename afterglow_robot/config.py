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
class AppConfig:
    """项目一级配置聚合对象。"""

    wechat: WechatConfig
    output: OutputConfig
    dataset: DatasetConfig
    embedding: EmbeddingConfig


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
    return AppConfig(
        wechat=wechat,
        output=output,
        dataset=dataset,
        embedding=embedding,
    )


def require_value(value: Any, field_name: str) -> Any:
    """校验必须配置，避免 CLI 在缺参时静默继续执行。"""

    if value is None or value == "":
        raise ValueError(f"缺少必要配置：{field_name}")
    return value
