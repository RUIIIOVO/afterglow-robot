from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.runtime.errors import ConfigValidationError, DependencyMissingError, EmbeddingInitializationError
from src.vectorstore.hash_backend import HashEmbeddingFunction
from src.vectorstore.sentence_transformers_backend import SentenceTransformersEmbeddingFunction


class EmbeddingBackend(Protocol):
    provider: str
    model_name: str

    def __call__(self, input: list[str]) -> list[list[float]]:
        ...

    def name(self) -> str:
        ...

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        ...

    def embed_query(self, input: list[str]) -> list[list[float]]:
        ...


@dataclass(frozen=True)
class EmbeddingResolution:
    embedding_function: EmbeddingBackend
    requested_provider: str
    resolved_provider: str
    model_name: str
    fallback_used: bool
    fallback_reason: str

    def to_metadata(self) -> dict[str, object]:
        return {
            "requested_provider": self.requested_provider,
            "resolved_provider": self.resolved_provider,
            "model_name": self.model_name,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
        }


def resolve_embedding_backend(
    *,
    provider: str,
    model_name: str,
    allow_fallback: bool,
    fallback_provider: str,
) -> EmbeddingResolution:
    normalized_provider = provider.strip()
    normalized_fallback_provider = fallback_provider.strip()
    try:
        backend = _build_backend(normalized_provider, model_name)
        return EmbeddingResolution(
            embedding_function=backend,
            requested_provider=normalized_provider,
            resolved_provider=backend.provider,
            model_name=model_name,
            fallback_used=False,
            fallback_reason="",
        )
    except ConfigValidationError:
        raise
    except (DependencyMissingError, EmbeddingInitializationError) as error:
        if not allow_fallback or normalized_fallback_provider == normalized_provider:
            raise
        fallback_backend = _build_backend(normalized_fallback_provider, model_name)
        return EmbeddingResolution(
            embedding_function=fallback_backend,
            requested_provider=normalized_provider,
            resolved_provider=fallback_backend.provider,
            model_name=model_name,
            fallback_used=True,
            fallback_reason=str(error),
        )


def _build_backend(provider: str, model_name: str) -> EmbeddingBackend:
    if provider == "sentence_transformers":
        return SentenceTransformersEmbeddingFunction(model_name=model_name)
    if provider == "hash":
        return HashEmbeddingFunction(model_name=model_name)
    raise ConfigValidationError(
        "embedding.provider/fallback_provider 非法",
        context={"provider": provider},
    )
