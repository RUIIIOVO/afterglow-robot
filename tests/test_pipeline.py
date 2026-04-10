from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from afterglow_robot.dataset_builder import build_fewshot_samples, build_rag_records, is_valid_dataset_text, read_normalized_messages
from afterglow_robot.wechat_export import compute_message_table_name, discover_contacts, extract_chat_messages
from process.build_dataset import main as build_dataset_main
from process.discover_contacts import main as discover_contacts_main
from process.extract_chat import main as extract_chat_main
from process.run_text_pipeline import main as run_text_pipeline_main

ACCOUNT_WXID = "wxid_owner"
TARGET_WXID = "target_user"
TARGET_TABLE = compute_message_table_name(TARGET_WXID)


def create_contact_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE Contact (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            local_type INTEGER,
            alias TEXT,
            encrypt_username TEXT,
            flag INTEGER,
            delete_flag INTEGER,
            verify_flag INTEGER,
            remark TEXT,
            remark_quan_pin TEXT,
            remark_pin_yin_initial TEXT,
            nick_name TEXT,
            pin_yin_initial TEXT,
            quan_pin TEXT,
            big_head_url TEXT,
            small_head_url TEXT,
            head_img_md5 TEXT,
            chat_room_notify INTEGER,
            is_in_chat_room INTEGER,
            description TEXT,
            extra_buffer BLOB,
            chat_room_type INTEGER
        )
        """
    )
    rows = [
        (ACCOUNT_WXID, "", "", "自己"),
        (TARGET_WXID, "target_alias", "目标备注", "目标昵称"),
        ("other_user", "", "", "其他人"),
    ]
    for username, alias, remark, nick_name in rows:
        connection.execute(
            "INSERT INTO Contact (username, alias, remark, nick_name) VALUES (?, ?, ?, ?)",
            (username, alias, remark, nick_name),
        )
    connection.commit()
    connection.close()


def create_message_db(
    path: Path,
    self_rowid: int,
    target_rowid: int,
    self_messages: list[tuple[int, int, object]],
    target_messages: list[tuple[int, int, object]],
) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE Name2ID (
            user_name TEXT,
            is_session INTEGER
        )
        """
    )

    max_rowid = max(self_rowid, target_rowid, 10)
    for index in range(1, max_rowid + 1):
        if index == self_rowid:
            username = ACCOUNT_WXID
        elif index == target_rowid:
            username = TARGET_WXID
        else:
            username = f"placeholder_{index}"
        connection.execute(
            "INSERT INTO Name2ID (user_name, is_session) VALUES (?, 1)",
            (username,),
        )

    connection.execute(
        f"""
        CREATE TABLE {TARGET_TABLE} (
            local_id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER,
            local_type INTEGER,
            sort_seq INTEGER,
            real_sender_id INTEGER,
            create_time INTEGER,
            status INTEGER,
            upload_status INTEGER,
            download_status INTEGER,
            server_seq INTEGER,
            origin_source INTEGER,
            source TEXT,
            message_content TEXT,
            compress_content TEXT,
            packed_info_data BLOB,
            WCDB_CT_message_content INTEGER DEFAULT NULL,
            WCDB_CT_source INTEGER DEFAULT NULL
        )
        """
    )

    server_id = 1000
    for timestamp, local_type, content in self_messages:
        server_id += 1
        connection.execute(
            f"""
            INSERT INTO {TARGET_TABLE} (
                server_id, local_type, sort_seq, real_sender_id, create_time, status,
                upload_status, download_status, server_seq, origin_source, source,
                message_content, compress_content, packed_info_data
            ) VALUES (?, ?, ?, ?, ?, 0, 0, 0, 0, 0, '', ?, '', X'00')
            """,
            (server_id, local_type, timestamp * 1000, self_rowid, timestamp, content),
        )

    for timestamp, local_type, content in target_messages:
        server_id += 1
        connection.execute(
            f"""
            INSERT INTO {TARGET_TABLE} (
                server_id, local_type, sort_seq, real_sender_id, create_time, status,
                upload_status, download_status, server_seq, origin_source, source,
                message_content, compress_content, packed_info_data
            ) VALUES (?, ?, ?, ?, ?, 0, 0, 0, 0, 0, '', ?, '', X'00')
            """,
            (server_id, local_type, timestamp * 1000, target_rowid, timestamp, content),
        )

    connection.commit()
    connection.close()


def create_fixture_export_tree(base_dir: Path) -> tuple[Path, Path]:
    export_dir = base_dir / "output"
    account_dir = export_dir / "databases" / ACCOUNT_WXID
    account_dir.mkdir(parents=True, exist_ok=True)

    create_contact_db(account_dir / "contact.db")
    create_message_db(
        account_dir / "message_0.db",
        self_rowid=1,
        target_rowid=2,
        self_messages=[
            (100, 1, "你好，最近怎么样"),
            (102, 1, "我们周末见吧"),
            (104, 1, "嗯"),
            (106, 34, b"voice-bytes"),
        ],
        target_messages=[
            (101, 1, "最近挺好的"),
            (103, 1, "可以啊，周末见"),
            (105, 1, "好"),
        ],
    )
    create_message_db(
        account_dir / "message_1.db",
        self_rowid=3,
        target_rowid=7,
        self_messages=[
            (200, 1, "上次那份方案我已经改完了"),
            (202, 1, "你看看还有没有问题"),
        ],
        target_messages=[
            (201, 1, "我晚上看一下"),
            (203, 1, "看过了，没问题"),
            (204, 1, b"binary-content"),
        ],
    )

    config_path = base_dir / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "wechat:",
                f"  export_dir: \"{export_dir.as_posix()}\"",
                f"  account_wxid: \"{ACCOUNT_WXID}\"",
                f"  target_wxid: \"{TARGET_WXID}\"",
                "output:",
                f"  base_dir: \"{(base_dir / 'artifacts').as_posix()}\"",
                "dataset:",
                "  min_text_length: 4",
                "  fewshot_limit: 10",
                "embedding:",
                "  model_name: \"fake-model\"",
                f"  chroma_dir: \"{(base_dir / 'models' / 'chroma_db').as_posix()}\"",
            ]
        ),
        encoding="utf-8",
    )
    return export_dir, config_path


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.export_dir, self.config_path = create_fixture_export_tree(self.base_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_message_table_name_uses_md5(self) -> None:
        expected = f"Msg_{hashlib.md5(TARGET_WXID.encode('utf-8')).hexdigest()}"
        self.assertEqual(compute_message_table_name(TARGET_WXID), expected)

    def test_discover_contacts_reads_contact_db(self) -> None:
        account_wxid, contacts = discover_contacts(self.export_dir, None)
        self.assertEqual(account_wxid, ACCOUNT_WXID)
        usernames = {item["username"] for item in contacts}
        self.assertIn(TARGET_WXID, usernames)

    def test_extract_chat_messages_merges_and_resolves_sender_roles(self) -> None:
        messages = extract_chat_messages(self.export_dir, ACCOUNT_WXID, TARGET_WXID)
        self.assertEqual([message.timestamp for message in messages], [100, 101, 102, 103, 104, 105, 200, 201, 202, 203])
        self.assertEqual(messages[0].sender_role, "self")
        self.assertEqual(messages[1].sender_role, "target")
        self.assertEqual(messages[7].sender_role, "target")
        self.assertEqual(messages[7].text, "我晚上看一下")
        self.assertTrue(all(message.message_type == "text" for message in messages))

    def test_dataset_builder_filters_short_texts_and_builds_pairs(self) -> None:
        messages = extract_chat_messages(self.export_dir, ACCOUNT_WXID, TARGET_WXID)
        fewshot = build_fewshot_samples(messages, min_text_length=4, fewshot_limit=10)
        rag_records = build_rag_records(messages, min_text_length=4)

        self.assertEqual(
            [(sample.context, sample.response) for sample in fewshot],
            [
                ("你好，最近怎么样", "最近挺好的"),
                ("我们周末见吧", "可以啊，周末见"),
                ("上次那份方案我已经改完了", "我晚上看一下"),
                ("你看看还有没有问题", "看过了，没问题"),
            ],
        )
        self.assertTrue(all(record.text != "好" for record in rag_records))
        self.assertTrue(all(record.source_message_id for record in rag_records))
        self.assertTrue(is_valid_dataset_text("四个字啊", 4))
        self.assertFalse(is_valid_dataset_text("好", 4))

    def test_cli_pipeline_generates_expected_outputs(self) -> None:
        contacts_output = self.base_dir / "contacts.json"
        discover_contacts_main(
            [
                "--export-dir",
                str(self.export_dir),
                "--output",
                str(contacts_output),
            ]
        )
        self.assertTrue(contacts_output.exists())

        extract_chat_main(["--config", str(self.config_path)])
        normalized_path = self.base_dir / "artifacts" / TARGET_WXID / "messages.normalized.jsonl"
        self.assertTrue(normalized_path.exists())

        def fake_embedder_factory(model_name: str):
            self.assertEqual(model_name, "fake-model")

            def _encode(texts: list[str]) -> list[list[float]]:
                return [[float(index), float(len(text))] for index, text in enumerate(texts, start=1)]

            return _encode

        def fake_vector_writer(records, embeddings, chroma_dir, collection_name):
            chroma_dir.mkdir(parents=True, exist_ok=True)
            marker = chroma_dir / f"{collection_name}.json"
            marker.write_text(
                json.dumps(
                    {
                        "count": len(records),
                        "embedding_count": len(embeddings),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

        with mock.patch("afterglow_robot.dataset_builder.build_embedder", fake_embedder_factory), mock.patch(
            "afterglow_robot.dataset_builder.write_chroma_collection",
            fake_vector_writer,
        ):
            build_dataset_main(["--config", str(self.config_path)])

        fewshot_path = self.base_dir / "artifacts" / TARGET_WXID / "fewshot.json"
        rag_corpus_path = self.base_dir / "artifacts" / TARGET_WXID / "rag_corpus.jsonl"
        chroma_dir = self.base_dir / "models" / "chroma_db"
        chroma_marker = chroma_dir / f"{TARGET_WXID}.json"

        self.assertTrue(fewshot_path.exists())
        self.assertTrue(rag_corpus_path.exists())
        self.assertTrue(chroma_marker.exists())

        messages = read_normalized_messages(normalized_path)
        self.assertTrue(messages)
        with fewshot_path.open("r", encoding="utf-8") as handle:
            fewshot_payload = json.load(handle)
        self.assertTrue(all("response" in item for item in fewshot_payload))

    def test_run_text_pipeline_generates_all_artifacts(self) -> None:
        def fake_embedder_factory(model_name: str):
            self.assertEqual(model_name, "fake-model")

            def _encode(texts: list[str]) -> list[list[float]]:
                return [[float(index), float(len(text))] for index, text in enumerate(texts, start=1)]

            return _encode

        def fake_vector_writer(records, embeddings, chroma_dir, collection_name):
            chroma_dir.mkdir(parents=True, exist_ok=True)
            marker = chroma_dir / f"{collection_name}.json"
            marker.write_text(
                json.dumps(
                    {
                        "count": len(records),
                        "embedding_count": len(embeddings),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

        with mock.patch("afterglow_robot.dataset_builder.build_embedder", fake_embedder_factory), mock.patch(
            "afterglow_robot.dataset_builder.write_chroma_collection",
            fake_vector_writer,
        ):
            run_text_pipeline_main(["--config", str(self.config_path)])

        self.assertTrue((self.base_dir / "artifacts" / "contacts.json").exists())
        self.assertTrue((self.base_dir / "artifacts" / TARGET_WXID / "messages.normalized.jsonl").exists())
        self.assertTrue((self.base_dir / "artifacts" / TARGET_WXID / "fewshot.json").exists())
        self.assertTrue((self.base_dir / "artifacts" / TARGET_WXID / "rag_corpus.jsonl").exists())
        self.assertTrue((self.base_dir / "models" / "chroma_db" / f"{TARGET_WXID}.json").exists())
