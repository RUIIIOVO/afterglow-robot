from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Sequence

from .models import FewShotSample, NormalizedMessage, RagRecord
from .wechat_export import ensure_directory, write_json, write_jsonl

"""规范化消息到 Few-shot / RAG 资产的构建逻辑。"""

EmbedderFactory = Callable[[str], Callable[[Sequence[str]], list[list[float]]]]
VectorWriter = Callable[[Sequence[RagRecord], Sequence[Sequence[float]], Path, str], None]


def read_normalized_messages(path: Path) -> list[NormalizedMessage]:
    """从 JSONL 读取规范化消息，并按时间重新排序。"""

    messages: list[NormalizedMessage] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            payload = json.loads(line)
            messages.append(NormalizedMessage(**payload))
    messages.sort(key=lambda item: (item.timestamp, item.message_id))
    return messages


def is_valid_dataset_text(text: str, min_text_length: int) -> bool:
    """按当前阶段的最小长度规则过滤低信息量文本。"""

    return len(text.strip()) >= min_text_length


def _find_previous_self_message(
    messages: Sequence[NormalizedMessage],
    current_index: int,
    min_text_length: int,
) -> NormalizedMessage | None:
    """回溯查找最近一条可作为上下文的用户消息。"""

    for index in range(current_index - 1, -1, -1):
        candidate = messages[index]
        if candidate.sender_role != "self":
            continue
        if not is_valid_dataset_text(candidate.text, min_text_length):
            continue
        return candidate
    return None


def build_fewshot_samples(
    messages: Sequence[NormalizedMessage],
    min_text_length: int,
    fewshot_limit: int,
) -> list[FewShotSample]:
    """从消息流中构造用于 System Prompt 的问答样本。"""

    dedup_keys: set[tuple[str, str]] = set()
    samples: list[FewShotSample] = []

    for index, message in enumerate(messages):
        if message.sender_role != "target":
            continue
        if not is_valid_dataset_text(message.text, min_text_length):
            continue

        context_message = _find_previous_self_message(messages, index, min_text_length)
        if context_message is None:
            continue

        # 用问答文本去重，避免模型被重复样本过度放大。
        dedup_key = (context_message.text, message.text)
        if dedup_key in dedup_keys:
            continue

        dedup_keys.add(dedup_key)
        samples.append(
            FewShotSample(
                context=context_message.text,
                response=message.text,
                timestamp=message.timestamp,
                source_message_id=message.message_id,
            )
        )

    if fewshot_limit > 0:
        return samples[-fewshot_limit:]
    return samples


def build_rag_records(
    messages: Sequence[NormalizedMessage],
    min_text_length: int,
) -> list[RagRecord]:
    """构造用于向量检索的语料记录。"""

    records: list[RagRecord] = []
    for index, message in enumerate(messages):
        if message.sender_role != "target":
            continue
        if not is_valid_dataset_text(message.text, min_text_length):
            continue

        context_message = _find_previous_self_message(messages, index, min_text_length)
        context = context_message.text if context_message is not None else ""
        embedding_text = (
            f"用户：{context}\n目标：{message.text}" if context else message.text
        )
        records.append(
            RagRecord(
                record_id=message.message_id,
                text=message.text,
                context=context,
                embedding_text=embedding_text,
                timestamp=message.timestamp,
                source_message_id=message.message_id,
                account_wxid=message.account_wxid,
                target_wxid=message.target_wxid,
                target_name=message.target_name,
            )
        )
    return records


def build_embedder(model_name: str) -> Callable[[Sequence[str]], list[list[float]]]:
    """初始化本地 embedding 模型。"""

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(model_name)

    def _encode(texts: Sequence[str]) -> list[list[float]]:
        """统一输出 Python 原生浮点列表，方便后续持久化。"""

        vectors = model.encode(
            list(texts),
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [list(map(float, vector)) for vector in vectors]

    return _encode


def write_chroma_collection(
    records: Sequence[RagRecord],
    embeddings: Sequence[Sequence[float]],
    chroma_dir: Path,
    collection_name: str,
) -> None:
    """将 RAG 语料写入本地 ChromaDB。"""

    from chromadb import PersistentClient

    ensure_directory(chroma_dir)
    client = PersistentClient(path=str(chroma_dir))
    collection = client.get_or_create_collection(name=collection_name)
    collection.upsert(
        ids=[record.record_id for record in records],
        documents=[record.embedding_text for record in records],
        embeddings=[list(vector) for vector in embeddings],
        metadatas=[
            {
                "timestamp": record.timestamp,
                "source_message_id": record.source_message_id,
                "account_wxid": record.account_wxid,
                "target_wxid": record.target_wxid,
                "target_name": record.target_name,
                "context": record.context,
                "text": record.text,
            }
            for record in records
        ],
    )


def build_dataset_assets(
    messages: Sequence[NormalizedMessage],
    output_dir: Path,
    chroma_dir: Path,
    model_name: str,
    min_text_length: int,
    fewshot_limit: int,
    embedder_factory: EmbedderFactory | None = None,
    vector_writer: VectorWriter | None = None,
) -> tuple[list[FewShotSample], list[RagRecord]]:
    """构建并落盘第一阶段全部文本资产。"""

    ensure_directory(output_dir)
    fewshot_samples = build_fewshot_samples(messages, min_text_length, fewshot_limit)
    rag_records = build_rag_records(messages, min_text_length)

    write_json(output_dir / "fewshot.json", [sample.to_dict() for sample in fewshot_samples])
    write_jsonl(output_dir / "rag_corpus.jsonl", [record.to_dict() for record in rag_records])

    if rag_records:
        embedder_factory = embedder_factory or build_embedder
        vector_writer = vector_writer or write_chroma_collection
        embedder = embedder_factory(model_name)
        embeddings = embedder([record.embedding_text for record in rag_records])
        collection_name = rag_records[0].target_wxid.replace("@", "_").replace("-", "_")
        vector_writer(rag_records, embeddings, chroma_dir, collection_name)
    else:
        ensure_directory(chroma_dir)

    return fewshot_samples, rag_records
