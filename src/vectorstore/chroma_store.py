from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from src.models.messages import RagRecord
from src.runtime.errors import DependencyMissingError, VectorStoreNotBuiltError


class HashEmbeddingFunction:
    def __init__(self, model_name: str, dim: int = 256) -> None:
        self.model_name = model_name
        self.dim = dim

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in input]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        content = text.strip()
        if not content:
            return vector
        for index, char in enumerate(content):
            bucket = (ord(char) + index * 131) % self.dim
            vector[bucket] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm > 0:
            vector = [value / norm for value in vector]
        return vector


class ChromaVectorStore:
    collection_name = "afterglow_rag"

    def __init__(self, chroma_dir: Path, model_name: str) -> None:
        self.chroma_dir = chroma_dir
        self.model_name = model_name
        self._embedding = HashEmbeddingFunction(model_name=model_name)
        self._client = self._create_client()

    def _create_client(self) -> Any:
        try:
            import chromadb
        except ImportError as error:
            raise DependencyMissingError(
                "chromadb",
                "请先安装 Python 依赖：pip install chromadb",
            ) from error
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        return chromadb.PersistentClient(path=str(self.chroma_dir))

    def build(self, records: list[RagRecord]) -> None:
        try:
            self._client.delete_collection(self.collection_name)
        except Exception:  # noqa: BLE001
            pass
        collection = self._client.create_collection(
            name=self.collection_name,
            metadata={"embedding_model": self.model_name},
            embedding_function=self._embedding,
        )
        if not records:
            return
        ids = [item.id for item in records]
        docs = [item.text for item in records]
        metadatas = [
            {
                "context": item.context,
                "timestamp": item.timestamp,
                "target_wxid": item.target_wxid,
                "source_message_id": item.source_message_id,
            }
            for item in records
        ]
        collection.add(ids=ids, documents=docs, metadatas=metadatas)

    def query(self, query_text: str, top_k: int) -> list[dict]:
        try:
            collection = self._client.get_collection(
                name=self.collection_name,
                embedding_function=self._embedding,
            )
        except Exception as error:  # noqa: BLE001
            raise VectorStoreNotBuiltError(str(self.chroma_dir)) from error
        result = collection.query(query_texts=[query_text], n_results=top_k)
        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        hits: list[dict] = []
        for record_id, doc, meta, distance in zip(ids, docs, metas, distances):
            hits.append(
                {
                    "id": record_id,
                    "text": doc,
                    "context": meta.get("context", "") if isinstance(meta, dict) else "",
                    "distance": distance,
                    "metadata": meta,
                }
            )
        return hits

