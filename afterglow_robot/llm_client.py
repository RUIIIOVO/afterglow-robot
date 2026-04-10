from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable
from urllib import request

"""本地 Ollama 客户端。"""


@dataclass(slots=True)
class OllamaGenerateResult:
    """Ollama 生成结果。"""

    response: str
    raw_response: dict[str, object]


class OllamaClient:
    """对 Ollama `/api/generate` 的最小封装。"""

    def __init__(
        self,
        endpoint: str,
        model: str,
        temperature: float = 0.7,
        timeout_seconds: int = 120,
        urlopen: Callable[..., object] | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self.urlopen = urlopen or request.urlopen

    def generate(self, system_prompt: str, user_prompt: str) -> OllamaGenerateResult:
        """调用 Ollama 生成单轮回复。"""

        payload = {
            "model": self.model,
            "system": system_prompt,
            "prompt": user_prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url=f"{self.endpoint}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.urlopen(req, timeout=self.timeout_seconds) as response:
            raw_payload = json.loads(response.read().decode("utf-8"))
        return OllamaGenerateResult(
            response=str(raw_payload.get("response", "")).strip(),
            raw_response=raw_payload,
        )
