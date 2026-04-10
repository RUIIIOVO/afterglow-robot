from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from afterglow_robot.config import load_app_config
from afterglow_robot.llm_client import OllamaClient
from afterglow_robot.rag_retriever import collection_name_for_target, query_rag_records
from afterglow_robot.reply_generator import (
    build_system_prompt,
    build_user_prompt,
    generate_reply,
    load_fewshot_samples,
    normalize_history,
)
from agent.generate_reply import main as generate_reply_main


class FakeHttpResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


class FakeCollection:
    def query(self, query_texts, n_results):
        return {
            "ids": [["msg-1"]],
            "documents": [["用户：你到哪了\n目标：马上到"]],
            "metadatas": [[{"text": "马上到", "context": "你到哪了", "target_name": "老爸", "timestamp": 123}]],
            "distances": [[0.12]],
        }


class FakeClient:
    def get_or_create_collection(self, name):
        self.name = name
        return FakeCollection()


class Stage2ReplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.output_dir = self.base_dir / "artifacts" / "target_user"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.base_dir / "models" / "chroma_db").mkdir(parents=True, exist_ok=True)
        with (self.output_dir / "fewshot.json").open("w", encoding="utf-8") as handle:
            json.dump(
                [
                    {"context": "你到哪了", "response": "马上到"},
                    {"context": "今晚回来吃饭吗", "response": "回去吃"},
                ],
                handle,
                ensure_ascii=False,
            )

        self.config_path = self.base_dir / "config.yaml"
        self.config_path.write_text(
            "\n".join(
                [
                    "wechat:",
                    f"  export_dir: \"{(self.base_dir / 'output').as_posix()}\"",
                    "  account_wxid: \"wxid_owner\"",
                    "  target_wxid: \"target_user\"",
                    "output:",
                    f"  base_dir: \"{(self.base_dir / 'artifacts').as_posix()}\"",
                    "dataset:",
                    "  min_text_length: 4",
                    "  fewshot_limit: 10",
                    "embedding:",
                    "  model_name: \"fake-embedding\"",
                    f"  chroma_dir: \"{(self.base_dir / 'models' / 'chroma_db').as_posix()}\"",
                    "retrieval:",
                    f"  chroma_dir: \"{(self.base_dir / 'models' / 'chroma_db').as_posix()}\"",
                    "  top_k: 3",
                    "llm:",
                    "  endpoint: \"http://localhost:11434\"",
                    "  model: \"qwen2.5:7b\"",
                    "  temperature: 0.3",
                    "  timeout_seconds: 30",
                    "conversation:",
                    "  history_limit: 4",
                    "  fewshot_limit: 2",
                ]
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_collection_name_for_target(self) -> None:
        self.assertEqual(collection_name_for_target("wxid_xxx@chatroom"), "wxid_xxx_chatroom")

    def test_query_rag_records_uses_collection_and_normalizes_result(self) -> None:
        records = query_rag_records(
            chroma_dir=self.base_dir / "models" / "chroma_db",
            target_wxid="target_user",
            query_text="你到哪了",
            top_k=3,
            client_factory=lambda _: FakeClient(),
        )
        self.assertEqual(records[0]["text"], "马上到")
        self.assertEqual(records[0]["context"], "你到哪了")

    def test_ollama_client_parses_response(self) -> None:
        captured = {}

        def fake_urlopen(req, timeout):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeHttpResponse({"response": "好的，知道了"})

        client = OllamaClient(
            endpoint="http://localhost:11434",
            model="qwen2.5:7b",
            temperature=0.2,
            timeout_seconds=15,
            urlopen=fake_urlopen,
        )
        result = client.generate("系统提示", "用户提示")
        self.assertEqual(result.response, "好的，知道了")
        self.assertEqual(captured["url"], "http://localhost:11434/api/generate")
        self.assertEqual(captured["body"]["model"], "qwen2.5:7b")
        self.assertEqual(captured["body"]["system"], "系统提示")
        self.assertEqual(captured["body"]["prompt"], "用户提示")
        self.assertEqual(captured["timeout"], 15)

    def test_prompt_builders_and_history_normalization(self) -> None:
        system_prompt = build_system_prompt("老爸", [{"context": "你到哪了", "response": "马上到"}])
        user_prompt = build_user_prompt(
            "晚上回来吗",
            [{"context": "你到哪了", "text": "马上到"}],
            [{"role": "user", "text": "你到哪了"}, {"role": "assistant", "text": "马上到"}],
        )
        history = normalize_history(
            [
                {"role": "user", "text": "a"},
                {"role": "assistant", "text": "b"},
                {"role": "system", "text": "ignored"},
            ],
            10,
        )
        self.assertIn("老爸", system_prompt)
        self.assertIn("历史风格样本", system_prompt)
        self.assertIn("当前用户消息：晚上回来吗", user_prompt)
        self.assertEqual(history, [{"role": "user", "text": "a"}, {"role": "assistant", "text": "b"}])

    def test_generate_reply_assembles_rag_and_llm(self) -> None:
        config = load_app_config(self.config_path)

        def fake_rag_query_fn(**kwargs):
            self.assertEqual(kwargs["target_wxid"], "target_user")
            return [{"context": "你到哪了", "text": "马上到"}]

        class FakeLlmClient:
            def __init__(self, endpoint, model, temperature, timeout_seconds):
                self.endpoint = endpoint
                self.model = model
                self.temperature = temperature
                self.timeout_seconds = timeout_seconds

            def generate(self, system_prompt, user_prompt):
                self.system_prompt = system_prompt
                self.user_prompt = user_prompt
                return type("Result", (), {"response": "回去吃"})()

        payload = generate_reply(
            config=config,
            user_message="今晚回来吃饭吗",
            history=[{"role": "user", "text": "你到哪了"}, {"role": "assistant", "text": "马上到"}],
            rag_query_fn=fake_rag_query_fn,
            llm_client_factory=FakeLlmClient,
        )
        self.assertEqual(payload["reply"], "回去吃")
        self.assertEqual(payload["rag_records"][0]["text"], "马上到")
        self.assertIn("历史风格样本", payload["system_prompt"])
        self.assertIn("当前用户消息：今晚回来吃饭吗", payload["user_prompt"])

    def test_generate_reply_cli_outputs_reply_and_json(self) -> None:
        history_path = self.base_dir / "history.json"
        output_path = self.base_dir / "reply.json"
        history_path.write_text(
            json.dumps([{"role": "user", "text": "你到哪了"}], ensure_ascii=False),
            encoding="utf-8",
        )

        with mock.patch("agent.generate_reply.generate_reply", return_value={"reply": "马上到", "rag_records": []}):
            with mock.patch("builtins.print") as fake_print:
                generate_reply_main(
                    [
                        "--config",
                        str(self.config_path),
                        "--message",
                        "你到哪了",
                        "--history-file",
                        str(history_path),
                        "--output",
                        str(output_path),
                    ]
                )
        self.assertTrue(output_path.exists())
        self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["reply"], "马上到")
        fake_print.assert_called_with("马上到")

    def test_load_fewshot_samples_applies_limit(self) -> None:
        samples = load_fewshot_samples(self.output_dir / "fewshot.json", 1)
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0]["response"], "回去吃")
