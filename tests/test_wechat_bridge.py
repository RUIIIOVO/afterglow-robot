from __future__ import annotations

import io
import json
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from src.cli.commands import handle_serve
from src.runtime.chat_service import ChatReplyResult
from src.runtime.errors import OpenClawWriteBackError, VectorStoreNotBuiltError
from src.wechat_bridge.adapter import OpenClawAdapter
from src.wechat_bridge.models import BridgeProcessResult
from src.wechat_bridge.server import WechatBridgeService


class _FakeVectorStore:
    def __init__(self, chroma_dir: Path, model_name: str) -> None:
        self.chroma_dir = chroma_dir
        self.model_name = model_name

    def query(self, query_text: str, top_k: int) -> list[dict]:
        raise VectorStoreNotBuiltError(str(self.chroma_dir))


class WechatBridgeTests(unittest.TestCase):
    def _write_config(self, workdir: Path) -> Path:
        content = (
            "wechat:\n"
            '  export_dir: "unused"\n'
            '  account_wxid: "wxid_owner"\n'
            '  target_wxid: "wxid_target"\n'
            "\n"
            "output:\n"
            f'  base_dir: "{(workdir / "output").as_posix()}"\n'
            "\n"
            "dataset:\n"
            "  min_text_length: 4\n"
            "  fewshot_limit: 10\n"
            "\n"
            "embedding:\n"
            '  model_name: "BAAI/bge-small-zh-v1.5"\n'
            f'  chroma_dir: "{(workdir / "models" / "chroma_db").as_posix()}"\n'
            "\n"
            "retrieval:\n"
            "  top_k: 5\n"
            "\n"
            "llm:\n"
            '  endpoint: "http://localhost:11434"\n'
            '  model: "qwen2.5:7b"\n'
            "  temperature: 0.7\n"
            "  timeout_seconds: 30\n"
            "\n"
            "conversation:\n"
            "  history_limit: 10\n"
            "  fewshot_limit: 20\n"
        )
        config_path = workdir / "config.yaml"
        config_path.write_text(content, encoding="utf-8")
        return config_path

    def test_adapter_maps_openclaw_payload(self) -> None:
        adapter = OpenClawAdapter()
        payload = {
            "session_id": "conv_001",
            "sender": {"id": "wxid_sender"},
            "message": {"type": "text", "content": "你好呀"},
            "timestamp": 1710001234,
        }
        event = adapter.parse_event(payload)
        self.assertEqual(event.conversation_id, "conv_001")
        self.assertEqual(event.sender_id, "wxid_sender")
        self.assertEqual(event.text, "你好呀")
        self.assertEqual(event.message_type, "text")

    def test_bridge_calls_reply_chain_on_text_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            config = self._write_config(workdir)
            from src.common.config import load_config

            service = WechatBridgeService(config=load_config(config))
            payload = {
                "conversation_id": "conv_01",
                "sender_id": "wxid_u",
                "message_type": "text",
                "text": "晚上好",
                "timestamp": 1710001111,
            }
            with patch(
                "src.wechat_bridge.server.generate_chat_reply",
                return_value=ChatReplyResult(reply_text="你好", prompt="p", rag_hits=[]),
            ) as mocked:
                result = service.process_payload(payload)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.payload.get("status"), "ok")
            self.assertEqual(result.payload.get("reply_text"), "你好")
            mocked.assert_called_once()

    def test_bridge_rejects_non_text_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            config = self._write_config(workdir)
            from src.common.config import load_config

            service = WechatBridgeService(config=load_config(config))
            payload = {
                "conversation_id": "conv_02",
                "sender_id": "wxid_u",
                "message_type": "image",
                "text": "[图片]",
                "timestamp": 1710001112,
            }
            result = service.process_payload(payload)
            self.assertEqual(result.status_code, 400)
            self.assertEqual(result.payload["error"]["code"], "NON_TEXT_EVENT")

    def test_bridge_missing_artifacts_returns_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            config = self._write_config(workdir)
            from src.common.config import load_config

            service = WechatBridgeService(config=load_config(config))
            payload = {
                "conversation_id": "conv_03",
                "sender_id": "wxid_u",
                "message_type": "text",
                "text": "在吗",
                "timestamp": 1710001113,
            }
            result = service.process_payload(payload)
            self.assertEqual(result.status_code, 503)
            self.assertEqual(result.payload["error"]["code"], "INGEST_ARTIFACT_MISSING")

    def test_bridge_vectorstore_not_built_returns_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            config_path = self._write_config(workdir)
            output_dir = workdir / "output"
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "persona_prompt.txt").write_text("你是助手", encoding="utf-8")
            (output_dir / "fewshot.json").write_text('[{"context":"hi","response":"ok"}]', encoding="utf-8")

            from src.common.config import load_config

            service = WechatBridgeService(config=load_config(config_path))
            payload = {
                "conversation_id": "conv_04",
                "sender_id": "wxid_u",
                "message_type": "text",
                "text": "测一下",
                "timestamp": 1710001114,
            }
            with patch("src.runtime.chat_service.ChromaVectorStore", _FakeVectorStore):
                result = service.process_payload(payload)
            self.assertEqual(result.status_code, 503)
            self.assertEqual(result.payload["error"]["code"], "VECTORSTORE_NOT_BUILT")

    def test_bridge_returns_reply_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            config = self._write_config(workdir)
            from src.common.config import load_config

            service = WechatBridgeService(config=load_config(config))
            payload = {
                "conversation_id": "conv_05",
                "sender_id": "wxid_u",
                "message_type": "text",
                "text": "今天天气如何",
                "timestamp": 1710001115,
            }
            with patch(
                "src.wechat_bridge.server.generate_chat_reply",
                return_value=ChatReplyResult(reply_text="晴天", prompt="p", rag_hits=[]),
            ):
                result = service.process_payload(payload)
            self.assertEqual(result.payload["conversation_id"], "conv_05")
            self.assertEqual(result.payload["reply_text"], "晴天")

    def test_bridge_distinguishes_writeback_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            config = self._write_config(workdir)
            from src.common.config import load_config

            service = WechatBridgeService(config=load_config(config))
            payload = {
                "conversation_id": "conv_06",
                "sender_id": "wxid_u",
                "message_type": "text",
                "text": "hi",
                "timestamp": 1710001116,
                "reply_url": "http://127.0.0.1:9999/callback",
            }
            with patch(
                "src.wechat_bridge.server.generate_chat_reply",
                return_value=ChatReplyResult(reply_text="ok", prompt="p", rag_hits=[]),
            ):
                with patch(
                    "src.wechat_bridge.adapter.OpenClawAdapter.push_reply",
                    side_effect=OpenClawWriteBackError("网络失败", context={"reply_url": "x"}),
                ):
                    result = service.process_payload(payload)
            self.assertEqual(result.status_code, 502)
            self.assertEqual(result.payload["error"]["code"], "OPENCLAW_WRITEBACK_FAILED")

    def test_cli_serve_once_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            config = self._write_config(workdir)
            event_file = workdir / "event.json"
            event_file.write_text(
                json.dumps(
                    {
                        "conversation_id": "conv_07",
                        "sender_id": "wxid_u",
                        "message_type": "text",
                        "text": "once",
                        "timestamp": 1710001117,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            args = Namespace(
                config=str(config),
                host="127.0.0.1",
                port=8787,
                once_file=str(event_file),
            )
            fake_result = BridgeProcessResult(
                status_code=200,
                payload={"conversation_id": "conv_07", "status": "ok", "reply_text": "once-reply"},
            )
            with patch("src.cli.commands.WechatBridgeService.process_payload", return_value=fake_result):
                with io.StringIO() as stdout, redirect_stdout(stdout):
                    code = handle_serve(args)
                    output = stdout.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("once-reply", output)


if __name__ == "__main__":
    unittest.main()

