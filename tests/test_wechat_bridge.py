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
from src.wechat_bridge.history_store import ConversationHistoryEntry
from src.wechat_bridge.history_store import ConversationHistoryStore
from src.wechat_bridge.models import BridgeProcessResult
from src.wechat_bridge.openclaw_integration import configure_openclaw_afterglow
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

    def test_adapter_falls_back_to_sender_id_when_session_id_is_empty(self) -> None:
        adapter = OpenClawAdapter()
        payload = {
            "conversation_id": "",
            "session_id": "",
            "sender_id": "wxid_sender",
            "message_type": "text",
            "text": "你好呀",
            "timestamp": 1710001234,
        }
        event = adapter.parse_event(payload)
        self.assertEqual(event.conversation_id, "wxid_sender")
        self.assertEqual(event.sender_id, "wxid_sender")

    def test_adapter_supports_nested_message_payload(self) -> None:
        adapter = OpenClawAdapter()
        payload = {
            "message": {
                "session_id": "conv_nested",
                "from_user_id": "wxid_nested",
                "renderType": "text",
                "text_body": "来自嵌套结构",
                "create_time_ms": 1710002233000,
            }
        }
        event = adapter.parse_event(payload)
        self.assertEqual(event.conversation_id, "conv_nested")
        self.assertEqual(event.sender_id, "wxid_nested")
        self.assertEqual(event.text, "来自嵌套结构")
        self.assertEqual(event.timestamp, 1710002233)

    def test_adapter_treats_numeric_render_type_as_text(self) -> None:
        adapter = OpenClawAdapter()
        payload = {
            "message": {
                "session_id": "conv_numeric",
                "from_user_id": "wxid_numeric",
                "renderType": "1",
                "content": "数值类型文本",
                "create_time_ms": 1710002234000,
            }
        }
        event = adapter.parse_event(payload)
        self.assertEqual(event.message_type, "text")
        self.assertEqual(event.text, "数值类型文本")

    def test_adapter_treats_integer_render_type_as_text(self) -> None:
        adapter = OpenClawAdapter()
        payload = {
            "message": {
                "session_id": "conv_numeric_int",
                "from_user_id": "wxid_numeric_int",
                "renderType": 1,
                "content": "整型文本事件",
                "create_time_ms": 1710002235000,
            }
        }
        event = adapter.parse_event(payload)
        self.assertEqual(event.message_type, "text")
        self.assertEqual(event.text, "整型文本事件")

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

    def test_bridge_persists_history_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            config = self._write_config(workdir)
            from src.common.config import load_config

            history_store = ConversationHistoryStore(workdir / "history")
            service = WechatBridgeService(config=load_config(config), history_store=history_store)
            payload = {
                "conversation_id": "conv_history",
                "sender_id": "wxid_u",
                "message_type": "text",
                "text": "第一句",
                "timestamp": 1710002111,
                "event_id": "evt-1",
            }
            with patch(
                "src.wechat_bridge.server.generate_chat_reply",
                return_value=ChatReplyResult(reply_text="第一句回复", prompt="p", rag_hits=[]),
            ):
                result = service.process_payload(payload)
            self.assertEqual(result.status_code, 200)
            history = history_store.load_history("conv_history", limit=10)
            self.assertEqual(
                history,
                [
                    {"role": "user", "content": "第一句"},
                    {"role": "assistant", "content": "第一句回复"},
                ],
            )

    def test_bridge_uses_persisted_history_on_next_turn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            config = self._write_config(workdir)
            from src.common.config import load_config

            history_store = ConversationHistoryStore(workdir / "history")
            service = WechatBridgeService(config=load_config(config), history_store=history_store)
            history_store.append_entries(
                "conv_history_2",
                [
                    ConversationHistoryEntry(role="user", content="上一句", timestamp=1710002201, sender_id="wxid_u"),
                    ConversationHistoryEntry(role="assistant", content="上一句回复", timestamp=1710002202, sender_id="afterglow"),
                ],
            )
            history_file = next((workdir / "history").glob("conv_history_2.*.jsonl"))
            with history_file.open("a", encoding="utf-8", newline="\n") as file:
                file.write("{bad json}\n")

            payload = {
                "conversation_id": "conv_history_2",
                "sender_id": "wxid_u",
                "message_type": "text",
                "text": "下一句",
                "timestamp": 1710002203,
                "event_id": "evt-2",
            }

            def _fake_generate_chat_reply(*, config, message, history):
                self.assertEqual(message, "下一句")
                self.assertEqual(
                    history,
                    [
                        {"role": "user", "content": "上一句"},
                        {"role": "assistant", "content": "上一句回复"},
                    ],
                )
                return ChatReplyResult(reply_text="下一句回复", prompt="p", rag_hits=[])

            with patch("src.wechat_bridge.server.generate_chat_reply", side_effect=_fake_generate_chat_reply):
                result = service.process_payload(payload)

            self.assertEqual(result.status_code, 200)
            self.assertEqual(
                history_store.load_history("conv_history_2", limit=10),
                [
                    {"role": "user", "content": "上一句"},
                    {"role": "assistant", "content": "上一句回复"},
                    {"role": "user", "content": "下一句"},
                    {"role": "assistant", "content": "下一句回复"},
                ],
            )

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

    def test_configure_openclaw_afterglow_patches_supported_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            schema_path = root / "extensions" / "openclaw-weixin" / "src" / "config" / "config-schema.ts"
            process_path = root / "extensions" / "openclaw-weixin" / "src" / "messaging" / "process-message.ts"
            config_path = root / "openclaw.json"
            schema_path.parent.mkdir(parents=True, exist_ok=True)
            process_path.parent.mkdir(parents=True, exist_ok=True)

            schema_path.write_text(
                "\n".join(
                    [
                        "const weixinAccountSchema = z.object({",
                        "  name: z.string().optional(),",
                        "  enabled: z.boolean().optional(),",
                        "  baseUrl: z.string().default(DEFAULT_BASE_URL),",
                        "  cdnBaseUrl: z.string().default(CDN_BASE_URL),",
                        "  routeTag: z.number().optional(),",
                        "});",
                        "",
                        "/** Top-level weixin config schema (token is stored in credentials file, not config). */",
                        "export const WeixinConfigSchema = weixinAccountSchema.extend({",
                        "  accounts: z.record(z.string(), weixinAccountSchema).optional(),",
                        "  /** ISO 8601; bumped on each successful login to refresh gateway config from disk. */",
                        "  channelConfigUpdatedAt: z.string().optional(),",
                        "});",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            process_path.write_text(
                "\n".join(
                    [
                        'const MEDIA_OUTBOUND_TEMP_DIR = path.join(resolvePreferredOpenClawTmpDir(), "weixin/media/outbound-temp");',
                        "",
                        "function demo() {",
                        "  if (debug) {",
                        '    debugTrace.push(',
                        '      "── 鉴权 & 路由 ──",',
                        '      `│ auth: cmdAuthorized=${String(commandAuthorized)} senderAllowed=${String(senderAllowedForCommands)}`,',
                        "    );",
                        "  }",
                        "",
                        "    const response = await fetch(params.config.bridgeUrl, {",
                        '      body: JSON.stringify({',
                        '        conversation_id: params.message.session_id ?? params.message.from_user_id ?? "",',
                        '        session_id: params.message.session_id ?? "",',
                        '        sender_id: params.message.from_user_id ?? "",',
                        '        message_type: "text",',
                        '        text: params.text,',
                        '        timestamp: params.message.create_time_ms ?? Date.now(),',
                        '        event_id: String(params.message.message_id ?? ""),',
                        '        account_id: params.accountId,',
                        '        channel: "openclaw-weixin",',
                        "      }),",
                        "    });",
                        "  }",
                        "}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            config_path.write_text('{"plugins":{"allow":[]},"channels":{},"session":{}}', encoding="utf-8")

            result = configure_openclaw_afterglow(
                bridge_url="http://127.0.0.1:8787/openclaw/event",
                timeout_ms=90000,
                openclaw_root=root,
                strict=True,
            )
            self.assertTrue(result.applied)
            self.assertTrue(result.changed)
            self.assertIn("afterglow", schema_path.read_text(encoding="utf-8"))
            self.assertIn("resolveAfterglowBridgeConfig", process_path.read_text(encoding="utf-8"))
            self.assertIn('"bridgeUrl": "http://127.0.0.1:8787/openclaw/event"', config_path.read_text(encoding="utf-8"))

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
