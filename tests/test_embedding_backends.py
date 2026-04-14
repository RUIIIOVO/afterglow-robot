from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from src.runtime.errors import DependencyMissingError, EmbeddingProviderMismatchError, EmbeddingInitializationError
from src.vectorstore.chroma_store import ChromaVectorStore
from src.vectorstore.embedding_backends import resolve_embedding_backend


class _FakeCollection:
    def __init__(self, metadata: dict[str, object]) -> None:
        self.metadata = metadata

    def query(self, query_texts: list[str], n_results: int) -> dict[str, list[list[object]]]:
        return {
            "ids": [["rag-1"]],
            "documents": [["命中文本"]],
            "metadatas": [[{"context": "命中上文", "turn_id": "turn-1"}]],
            "distances": [[0.1]],
        }


class _FakeClient:
    def __init__(self, metadata: dict[str, object]) -> None:
        self.metadata = metadata

    def get_collection(self, name: str, embedding_function) -> _FakeCollection:
        return _FakeCollection(self.metadata)


class EmbeddingBackendTests(unittest.TestCase):
    def test_sentence_transformers_missing_dependency_falls_back_to_hash(self) -> None:
        with patch(
            "src.vectorstore.embedding_backends.SentenceTransformersEmbeddingFunction",
            side_effect=DependencyMissingError("sentence-transformers", "缺失"),
        ):
            resolution = resolve_embedding_backend(
                provider="sentence_transformers",
                model_name="BAAI/bge-small-zh-v1.5",
                allow_fallback=True,
                fallback_provider="hash",
            )
        self.assertTrue(resolution.fallback_used)
        self.assertEqual(resolution.resolved_provider, "hash")

    def test_sentence_transformers_missing_dependency_without_fallback_raises(self) -> None:
        with patch(
            "src.vectorstore.embedding_backends.SentenceTransformersEmbeddingFunction",
            side_effect=DependencyMissingError("sentence-transformers", "缺失"),
        ):
            with self.assertRaises(DependencyMissingError):
                resolve_embedding_backend(
                    provider="sentence_transformers",
                    model_name="BAAI/bge-small-zh-v1.5",
                    allow_fallback=False,
                    fallback_provider="hash",
                )

    def test_sentence_transformers_model_error_can_fall_back(self) -> None:
        with patch(
            "src.vectorstore.embedding_backends.SentenceTransformersEmbeddingFunction",
            side_effect=EmbeddingInitializationError("sentence_transformers", "模型加载失败"),
        ):
            resolution = resolve_embedding_backend(
                provider="sentence_transformers",
                model_name="bad-model",
                allow_fallback=True,
                fallback_provider="hash",
            )
        self.assertEqual(resolution.resolved_provider, "hash")
        self.assertTrue(resolution.fallback_used)

    def test_query_detects_embedding_provider_mismatch(self) -> None:
        with patch.object(
            ChromaVectorStore,
            "_create_client",
            return_value=_FakeClient(metadata={"embedding_provider": "sentence_transformers"}),
        ):
            store = ChromaVectorStore(
                chroma_dir=Path("unused"),
                model_name="BAAI/bge-small-zh-v1.5",
                provider="hash",
                allow_fallback=False,
                fallback_provider="hash",
            )
        with self.assertRaises(EmbeddingProviderMismatchError):
            store.query("测试", top_k=1)


if __name__ == "__main__":
    unittest.main()
