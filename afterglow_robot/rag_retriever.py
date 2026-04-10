from __future__ import annotations

from pathlib import Path
from typing import Callable

"""二阶段运行时 RAG 检索。"""

ClientFactory = Callable[[str], object]


def collection_name_for_target(target_wxid: str) -> str:
    """将目标联系人 wxid 转换为 Chroma 集合名。"""

    return target_wxid.replace("@", "_").replace("-", "_")


def query_rag_records(
    chroma_dir: Path,
    target_wxid: str,
    query_text: str,
    top_k: int,
    client_factory: ClientFactory | None = None,
) -> list[dict[str, object]]:
    """按当前用户消息检索历史相关话语。"""

    if top_k <= 0 or not query_text.strip():
        return []
    if not chroma_dir.exists():
        return []

    if client_factory is None:
        from chromadb import PersistentClient

        client_factory = lambda path: PersistentClient(path=path)

    client = client_factory(str(chroma_dir))
    collection = client.get_or_create_collection(name=collection_name_for_target(target_wxid))
    result = collection.query(query_texts=[query_text], n_results=top_k)

    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0] if result.get("distances") else []

    records: list[dict[str, object]] = []
    for index, record_id in enumerate(ids):
        metadata = metadatas[index] if index < len(metadatas) else {}
        document = documents[index] if index < len(documents) else ""
        distance = distances[index] if index < len(distances) else None
        records.append(
            {
                "id": record_id,
                "document": document,
                "distance": distance,
                "text": metadata.get("text", ""),
                "context": metadata.get("context", ""),
                "timestamp": metadata.get("timestamp"),
                "target_name": metadata.get("target_name", ""),
            }
        )
    return records
