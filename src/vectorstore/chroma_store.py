from __future__ import annotations

from pathlib import Path
from typing import Any

from src.models.messages import RagRecord
from src.runtime.errors import (
    DependencyMissingError,
    EmbeddingProviderMismatchError,
    VectorStoreNotBuiltError,
)
from src.vectorstore.embedding_backends import EmbeddingResolution, resolve_embedding_backend


class ChromaVectorStore:
    collection_name = "afterglow_rag"
    embedding_schema_version = 1

    def __init__(
        self,
        chroma_dir: Path,
        model_name: str,
        provider: str = "sentence_transformers",
        allow_fallback: bool = True,
        fallback_provider: str = "hash",
    ) -> None:
        self.chroma_dir = chroma_dir
        self.model_name = model_name
        self.resolution = resolve_embedding_backend(
            provider=provider,
            model_name=model_name,
            allow_fallback=allow_fallback,
            fallback_provider=fallback_provider,
        )
        self._embedding = self.resolution.embedding_function
        self._client = self._create_client()

    @property
    def embedding_metadata(self) -> dict[str, object]:
        return self.resolution.to_metadata()

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
            metadata={
                "embedding_schema_version": self.embedding_schema_version,
                "embedding_requested_provider": self.resolution.requested_provider,
                "embedding_provider": self.resolution.resolved_provider,
                "embedding_model": self.model_name,
                "embedding_fallback_used": self.resolution.fallback_used,
            },
            embedding_function=self._embedding,
        )
        if not records:
            return
        ids = [item.id for item in records]
        docs = [item.text for item in records]
        metadatas = [
            {
                "turn_id": item.turn_id,
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
        metadata = getattr(collection, "metadata", {}) or {}
        schema_version = metadata.get("embedding_schema_version")
        actual_provider = str(metadata.get("embedding_provider", "")).strip()
        actual_model = str(metadata.get("embedding_model", "")).strip()
        if schema_version != self.embedding_schema_version or not actual_provider or not actual_model:
            raise EmbeddingProviderMismatchError(
                expected_provider=self.resolution.resolved_provider,
                actual_provider=actual_provider or "unknown",
                expected_model=self.model_name,
                actual_model=actual_model or "unknown",
                details="向量库缺少或不兼容 embedding metadata",
            )
        if actual_provider != self.resolution.resolved_provider or actual_model != self.model_name:
            raise EmbeddingProviderMismatchError(
                expected_provider=self.resolution.resolved_provider,
                actual_provider=actual_provider,
                expected_model=self.model_name,
                actual_model=actual_model,
            )
        result = collection.query(query_texts=[query_text], n_results=top_k)
        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        hits: list[dict] = []
        for record_id, doc, meta, distance in zip(ids, docs, metas, distances):
            hit_meta = meta if isinstance(meta, dict) else {}
            hits.append(
                {
                    "id": record_id,
                    "text": doc,
                    "context": hit_meta.get("context", ""),
                    "distance": distance,
                    "metadata": hit_meta,
                }
            )
        return hits
