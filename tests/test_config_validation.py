from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.common.config import load_config
from src.runtime.errors import ConfigValidationError


class ConfigValidationTests(unittest.TestCase):
    def _write_config(self, workdir: Path, overrides: dict[str, str] | None = None) -> Path:
        values = {
            "wechat.export_dir": "tests/fixtures/wechat_data_analysis_export",
            "wechat.account_wxid": "",
            "wechat.target_wxid": "self",
            "output.base_dir": "data/processed",
            "dataset.min_text_length": "4",
            "dataset.fewshot_limit": "10",
            "embedding.model_name": "BAAI/bge-small-zh-v1.5",
            "embedding.chroma_dir": "models/chroma_db",
            "retrieval.top_k": "5",
            "llm.endpoint": "http://localhost:11434",
            "llm.model": "qwen2.5:7b",
            "llm.temperature": "0.7",
            "llm.timeout_seconds": "30",
            "conversation.history_limit": "10",
            "conversation.fewshot_limit": "20",
        }
        values.update(overrides or {})
        account_line = ""
        if values["wechat.account_wxid"] != "":
            account_line = f'  account_wxid: "{values["wechat.account_wxid"]}"\n'
        content = (
            "wechat:\n"
            f'  export_dir: "{values["wechat.export_dir"]}"\n'
            f"{account_line}"
            f'  target_wxid: "{values["wechat.target_wxid"]}"\n'
            "\n"
            "output:\n"
            f'  base_dir: "{values["output.base_dir"]}"\n'
            "\n"
            "dataset:\n"
            f'  min_text_length: {values["dataset.min_text_length"]}\n'
            f'  fewshot_limit: {values["dataset.fewshot_limit"]}\n'
            "\n"
            "embedding:\n"
            f'  model_name: "{values["embedding.model_name"]}"\n'
            f'  chroma_dir: "{values["embedding.chroma_dir"]}"\n'
            "\n"
            "retrieval:\n"
            f'  top_k: {values["retrieval.top_k"]}\n'
            "\n"
            "llm:\n"
            f'  endpoint: "{values["llm.endpoint"]}"\n'
            f'  model: "{values["llm.model"]}"\n'
            f'  temperature: {values["llm.temperature"]}\n'
            f'  timeout_seconds: {values["llm.timeout_seconds"]}\n'
            "\n"
            "conversation:\n"
            f'  history_limit: {values["conversation.history_limit"]}\n'
            f'  fewshot_limit: {values["conversation.fewshot_limit"]}\n'
        )
        config_path = workdir / "config.yaml"
        config_path.write_text(content, encoding="utf-8")
        return config_path

    def test_rejects_invalid_llm_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = self._write_config(Path(tmp), overrides={"llm.endpoint": "localhost:11434"})
            with self.assertRaises(ConfigValidationError) as ctx:
                load_config(config_path)
        self.assertIn("llm.endpoint 必须是 http/https URL", str(ctx.exception))

    def test_rejects_blank_export_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = self._write_config(Path(tmp), overrides={"wechat.export_dir": "   "})
            with self.assertRaises(ConfigValidationError) as ctx:
                load_config(config_path)
        self.assertIn("wechat.export_dir 不能为空", str(ctx.exception))

    def test_normalizes_blank_account_to_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = self._write_config(Path(tmp))
            config = load_config(config_path)
        self.assertIsNone(config.wechat.account_wxid)


if __name__ == "__main__":
    unittest.main()
