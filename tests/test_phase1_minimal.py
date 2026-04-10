from __future__ import annotations

import io
import json
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from src.cli.commands import handle_chat, handle_ingest, handle_wechat_connect
from src.ingestion.contacts import discover_contacts
from src.ingestion.discovery import resolve_account_wxid, select_parser
from src.ingestion.normalize import extract_target_candidates
from src.preprocess.pipeline import clean_messages
from src.runtime.errors import AccountDetectionError, DependencyMissingError
from src.runtime.runner import run_cli
from src.runtime.chat_service import ChatReplyResult


class _FakeVectorStore:
    def __init__(self, chroma_dir: Path, model_name: str) -> None:
        self.chroma_dir = chroma_dir
        self.model_name = model_name

    def build(self, records: list) -> None:
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        (self.chroma_dir / "_built.txt").write_text(str(len(records)), encoding="utf-8")

    def query(self, query_text: str, top_k: int) -> list[dict]:
        return [{"id": "rag-1", "text": "检索文本", "context": "上文", "distance": 0.1}]


class Phase1MinimalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.single_export_dir = self.repo_root / "tests" / "fixtures" / "single_account"
        self.multi_export_dir = self.repo_root / "tests" / "fixtures" / "multi_account"

    def _write_config(
        self,
        workdir: Path,
        export_dir: Path,
        target_wxid: str = "wxid_target",
        account_wxid: str | None = None,
    ) -> Path:
        account_line = f'  account_wxid: "{account_wxid}"\n' if account_wxid is not None else ""
        content = (
            "wechat:\n"
            f'  export_dir: "{export_dir.as_posix()}"\n'
            f"{account_line}"
            f'  target_wxid: "{target_wxid}"\n'
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

    def test_single_account_auto_detect(self) -> None:
        parser = select_parser(self.single_export_dir)
        account = resolve_account_wxid(parser, self.single_export_dir, configured_account_wxid=None)
        self.assertEqual(account, "wxid_owner")

    def test_multi_account_requires_explicit_account(self) -> None:
        parser = select_parser(self.multi_export_dir)
        with self.assertRaises(AccountDetectionError):
            resolve_account_wxid(parser, self.multi_export_dir, configured_account_wxid=None)

    def test_target_and_self_filter_logic(self) -> None:
        parser = select_parser(self.single_export_dir)
        contacts = discover_contacts(parser, self.single_export_dir, "wxid_owner")

        target_candidates, _ = extract_target_candidates(
            parser=parser,
            export_dir=self.single_export_dir,
            account_wxid="wxid_owner",
            target_wxid="wxid_target",
            contacts=contacts,
        )
        self.assertTrue(all(item.sender_role == "target" for item in target_candidates))

        self_candidates, _ = extract_target_candidates(
            parser=parser,
            export_dir=self.single_export_dir,
            account_wxid="wxid_owner",
            target_wxid="self",
            contacts=contacts,
        )
        self.assertTrue(all(item.sender_role == "self" for item in self_candidates))

    def test_filters_non_text_empty_and_short_messages(self) -> None:
        parser = select_parser(self.single_export_dir)
        contacts = discover_contacts(parser, self.single_export_dir, "wxid_owner")
        candidates, _ = extract_target_candidates(
            parser=parser,
            export_dir=self.single_export_dir,
            account_wxid="wxid_owner",
            target_wxid="wxid_target",
            contacts=contacts,
        )
        cleaned = clean_messages(candidates, min_text_length=4)
        message_ids = [item.message_id for item in cleaned]
        self.assertEqual(message_ids, ["m2", "m7", "m9"])

    def test_ingest_generates_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            config_path = self._write_config(
                workdir=workdir,
                export_dir=self.single_export_dir,
                target_wxid="wxid_target",
            )
            args = Namespace(config=str(config_path), target_wxid=None, export_dir=None)
            with patch("src.cli.commands.ChromaVectorStore", _FakeVectorStore):
                code = handle_ingest(args)
            self.assertEqual(code, 0)

            output_dir = workdir / "output"
            fewshot_path = output_dir / "fewshot.json"
            rag_path = output_dir / "rag_corpus.jsonl"
            persona_path = output_dir / "persona_prompt.txt"
            self.assertTrue(fewshot_path.exists())
            self.assertTrue(rag_path.exists())
            self.assertTrue(persona_path.exists())

            fewshots = json.loads(fewshot_path.read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(fewshots), 1)
            self.assertIn("context", fewshots[0])
            self.assertIn("response", fewshots[0])

            rag_lines = [
                json.loads(line)
                for line in rag_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(len(rag_lines), 3)
            for row in rag_lines:
                self.assertEqual(set(row.keys()), {"id", "context", "text", "timestamp", "target_wxid", "source_message_id"})

            persona = persona_path.read_text(encoding="utf-8")
            self.assertIn("禁止暴露 AI 身份", persona)

    def test_chat_command_outputs_reply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            config_path = self._write_config(workdir=workdir, export_dir=self.single_export_dir, target_wxid="wxid_target")
            args = Namespace(
                config=str(config_path),
                message="晚上吃什么",
                history_file=None,
                output=None,
            )
            fake_reply = ChatReplyResult(reply_text="测试回复", prompt="p", rag_hits=[])
            with patch("src.cli.commands.generate_chat_reply", return_value=fake_reply):
                with io.StringIO() as stdout, redirect_stdout(stdout):
                    code = handle_chat(args)
                    output = stdout.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("测试回复", output)

    def test_missing_config_returns_clear_error(self) -> None:
        args = Namespace(config="missing-config.yaml", target_wxid=None, export_dir=None)
        with io.StringIO() as stdout, redirect_stdout(stdout):
            code = run_cli(lambda: handle_ingest(args))
            output = stdout.getvalue()
        self.assertEqual(code, 1)
        self.assertIn("配置文件不存在", output)

    def test_missing_dependency_returns_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp)
            config_path = self._write_config(workdir=workdir, export_dir=self.single_export_dir)
            args = Namespace(config=str(config_path), check_only=True)
            with patch(
                "src.cli.commands.ensure_openclaw_installed",
                side_effect=DependencyMissingError("Node.js", "请先安装 Node.js。"),
            ):
                with io.StringIO() as stdout, redirect_stdout(stdout):
                    code = run_cli(lambda: handle_wechat_connect(args))
                    output = stdout.getvalue()
            self.assertEqual(code, 1)
            self.assertIn("缺少依赖：Node.js", output)


if __name__ == "__main__":
    unittest.main()
