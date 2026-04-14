from __future__ import annotations

import math


class HashEmbeddingFunction:
    provider = "hash"

    def __init__(self, model_name: str, dim: int = 256) -> None:
        self.model_name = model_name
        self.dim = dim

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in input]

    def name(self) -> str:
        return f"{self.provider}-{self.model_name}"

    def embed_documents(self, input: list[str]) -> list[list[float]]:
        return self.__call__(input)

    def embed_query(self, input: list[str]) -> list[list[float]]:
        return self.__call__(input)

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
