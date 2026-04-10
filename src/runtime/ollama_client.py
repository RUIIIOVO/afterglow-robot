from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from src.common.config import LLMConfig
from src.runtime.errors import OllamaNotRunningError


class OllamaClient:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self.endpoint = config.endpoint.rstrip("/")

    def check_health(self) -> None:
        url = f"{self.endpoint}/api/tags"
        request = urllib.request.Request(url=url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds):
                return
        except urllib.error.URLError as error:
            raise OllamaNotRunningError(self.endpoint, details=str(error)) from error

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": self.config.temperature},
        }
        response = self._post_json(f"{self.endpoint}/api/generate", payload)
        text = str(response.get("response", "")).strip()
        if not text:
            return "（模型未返回文本）"
        return text

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url=url,
            method="POST",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                status = response.status
                text = response.read().decode("utf-8")
                if status >= 400:
                    raise OllamaNotRunningError(self.endpoint, details=text)
                return json.loads(text)
        except urllib.error.URLError as error:
            raise OllamaNotRunningError(self.endpoint, details=str(error)) from error

