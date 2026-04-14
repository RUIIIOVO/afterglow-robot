from __future__ import annotations

from src.runtime.errors import DependencyMissingError, EmbeddingInitializationError


class SentenceTransformersEmbeddingFunction:
    provider = "sentence_transformers"

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise DependencyMissingError(
                "sentence-transformers",
                "请安装可选依赖：pip install \"afterglow-robot[embeddings]\" 或 pip install sentence-transformers",
            ) from error

        try:
            self._model = SentenceTransformer(model_name)
        except Exception as error:  # noqa: BLE001
            raise EmbeddingInitializationError(
                provider=self.provider,
                details="模型加载失败",
                context={"model_name": model_name, "error": str(error)},
            ) from error

    def __call__(self, input: list[str]) -> list[list[float]]:
        return self.embed_documents(input)

    def name(self) -> str:
        return f"{self.provider}-{self.model_name}"

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        if not input:
            return []
        embeddings = self._model.encode(
            input,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def embed_query(self, input: list[str]) -> list[list[float]]:
        return self.embed_documents(input)
