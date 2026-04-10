from __future__ import annotations

from dataclasses import asdict, dataclass

"""离线文本管线的核心数据模型。"""


@dataclass(slots=True)
class NormalizedMessage:
    """规范化后的单条消息。"""

    account_wxid: str
    target_wxid: str
    target_name: str
    message_id: str
    timestamp: int
    sender_role: str
    message_type: str
    text: str
    local_type: int
    source_db: str
    source_table: str

    def to_dict(self) -> dict[str, object]:
        """转换为可直接落盘的字典结构。"""

        return asdict(self)


@dataclass(slots=True)
class FewShotSample:
    """Few-shot 提示样本。"""

    context: str
    response: str
    timestamp: int
    source_message_id: str

    def to_dict(self) -> dict[str, object]:
        """转换为可直接落盘的字典结构。"""

        return asdict(self)


@dataclass(slots=True)
class RagRecord:
    """写入向量库前的 RAG 语料记录。"""

    record_id: str
    text: str
    context: str
    embedding_text: str
    timestamp: int
    source_message_id: str
    account_wxid: str
    target_wxid: str
    target_name: str

    def to_dict(self) -> dict[str, object]:
        """转换为可直接落盘的字典结构。"""

        return asdict(self)
