from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from src.ingestion.contacts import discover_contacts
from src.ingestion.discovery import resolve_account_wxid, select_parser
from src.ingestion.normalize import extract_target_candidates
from src.preprocess.pipeline import clean_messages


class WeChatDataAnalysisParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[1]
        self.export_dir = self.repo_root / "tests" / "fixtures" / "wechat_data_analysis_export"

    def test_selects_wechat_data_analysis_parser_for_directory_export(self) -> None:
        parser = select_parser(self.export_dir)
        self.assertEqual(parser.name, "wechat_data_analysis_v1")

        account = resolve_account_wxid(parser, self.export_dir, configured_account_wxid=None)
        self.assertEqual(account, "wxid_owner_real")

        contacts = discover_contacts(parser, self.export_dir, account)
        wxids = {item.wxid for item in contacts}
        self.assertIn("wxid_owner_real", wxids)
        self.assertIn("wxid_target_real", wxids)

    def test_extracts_target_and_self_messages_from_json_export(self) -> None:
        parser = select_parser(self.export_dir)
        contacts = discover_contacts(parser, self.export_dir, "wxid_owner_real")

        target_candidates, _ = extract_target_candidates(
            parser=parser,
            export_dir=self.export_dir,
            account_wxid="wxid_owner_real",
            target_wxid="wxid_target_real",
            contacts=contacts,
        )
        self.assertEqual([item.message_id for item in target_candidates], ["json-1"])

        self_candidates, _ = extract_target_candidates(
            parser=parser,
            export_dir=self.export_dir,
            account_wxid="wxid_owner_real",
            target_wxid="self",
            contacts=contacts,
        )
        cleaned = clean_messages(self_candidates, min_text_length=2)
        self.assertEqual([item.message_id for item in cleaned], ["json-2"])

    def test_parses_txt_export_from_zip_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "wechat_chat_export_txt.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("manifest.json", '{"schemaVersion":1,"account":"wxid_txt_owner"}')
                zf.writestr(
                    "conversations/001-Bob/meta.json",
                    '{"conversation":{"username":"wxid_txt_target","displayName":"Bob","isGroup":false}}',
                )
                zf.writestr(
                    "conversations/001-Bob/messages.txt",
                    "\n".join(
                        [
                            "[2025-01-01 10:00:00] Bob: 你好呀",
                            "[2025-01-01 10:00:03] 我: 我在",
                            "[2025-01-01 10:00:05] [系统] 你已添加了 Bob，现在可以开始聊天了",
                        ]
                    ),
                )

            parser = select_parser(archive)
            self.assertEqual(parser.name, "wechat_data_analysis_v1")
            self.assertEqual(parser.list_accounts(archive), ["wxid_txt_owner"])

            contacts = discover_contacts(parser, archive, "wxid_txt_owner")
            self.assertIn("wxid_txt_target", {item.wxid for item in contacts})

            messages = parser.load_messages(archive, "wxid_txt_owner")
            self.assertEqual([item.sender_wxid for item in messages], ["wxid_txt_target", "wxid_txt_owner", ""])
            self.assertEqual([item.message_type for item in messages], ["text", "text", "system"])

            target_candidates, _ = extract_target_candidates(
                parser=parser,
                export_dir=archive,
                account_wxid="wxid_txt_owner",
                target_wxid="wxid_txt_target",
                contacts=contacts,
            )
            self.assertEqual([item.message_id for item in target_candidates], ["txt:1"])

    def test_parses_zip_with_wrapped_root_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "wechat_chat_export_wrapped.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("wrapped/manifest.json", '{"schemaVersion":1,"account":"wxid_wrapped_owner"}')
                zf.writestr(
                    "wrapped/conversations/001-Carol/meta.json",
                    '{"conversation":{"username":"wxid_wrapped_target","displayName":"Carol","isGroup":false}}',
                )
                zf.writestr(
                    "wrapped/conversations/001-Carol/messages.json",
                    (
                        '{"schemaVersion":1,"account":"wxid_wrapped_owner",'
                        '"conversation":{"username":"wxid_wrapped_target","displayName":"Carol","isGroup":false},'
                        '"messages":[{"id":"wrapped-1","createTime":1710003000,"renderType":"text","isSent":false,'
                        '"senderUsername":"wxid_wrapped_target","conversationUsername":"wxid_wrapped_target","content":"hello"}]}'
                    ),
                )

            parser = select_parser(archive)
            self.assertEqual(parser.name, "wechat_data_analysis_v1")
            self.assertEqual(parser.list_accounts(archive), ["wxid_wrapped_owner"])
            messages = parser.load_messages(archive, "wxid_wrapped_owner")
            self.assertEqual([item.message_id for item in messages], ["wrapped-1"])

    def test_parses_wrapped_zip_with_txt_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "wechat_chat_export_wrapped_txt.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("wrapped/manifest.json", '{"schemaVersion":1,"account":"wxid_wrapped_txt_owner"}')
                zf.writestr(
                    "wrapped/conversations/001-Dora/meta.json",
                    '{"conversation":{"username":"wxid_wrapped_txt_target","displayName":"Dora","isGroup":false}}',
                )
                zf.writestr(
                    "wrapped/conversations/001-Dora/messages.txt",
                    "\n".join(
                        [
                            "[2025-01-01 11:00:00] Dora: hello",
                            "[2025-01-01 11:00:03] 我: hi",
                        ]
                    ),
                )

            parser = select_parser(archive)
            self.assertEqual(parser.name, "wechat_data_analysis_v1")
            contacts = discover_contacts(parser, archive, "wxid_wrapped_txt_owner")
            target_candidates, _ = extract_target_candidates(
                parser=parser,
                export_dir=archive,
                account_wxid="wxid_wrapped_txt_owner",
                target_wxid="wxid_wrapped_txt_target",
                contacts=contacts,
            )
            self.assertEqual([item.message_id for item in target_candidates], ["txt:1"])


if __name__ == "__main__":
    unittest.main()
