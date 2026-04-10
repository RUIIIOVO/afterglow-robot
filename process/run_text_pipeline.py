from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from afterglow_robot.config import load_app_config, require_value
from afterglow_robot.dataset_builder import build_dataset_assets
from afterglow_robot.logging_utils import setup_logging
from afterglow_robot.wechat_export import (
    discover_contacts,
    extract_chat_messages,
    resolve_account_wxid,
    write_json,
    write_jsonl,
)

"""第一阶段离线文本管线编排 CLI。"""


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数。"""

    parser = argparse.ArgumentParser(description="串联执行联系人发现、聊天提取与数据集构建。")
    parser.add_argument("--config", required=True, help="配置文件路径。")
    parser.add_argument("--verbose", action="store_true", help="输出调试日志。")
    return parser


def main(argv: list[str] | None = None) -> int:
    """按配置文件顺序执行第一阶段完整文本管线。"""

    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    config = load_app_config(args.config)
    export_dir = config.wechat.export_dir
    account_wxid = resolve_account_wxid(export_dir, config.wechat.account_wxid)
    target_wxid = require_value(config.wechat.target_wxid, "wechat.target_wxid")

    output_dir = config.output.base_dir / target_wxid
    contacts_output = config.output.base_dir / "contacts.json"
    messages_output = output_dir / "messages.normalized.jsonl"

    resolved_account, contacts = discover_contacts(export_dir, account_wxid)
    write_json(
        contacts_output,
        {
            "account_wxid": resolved_account,
            "count": len(contacts),
            "contacts": contacts,
        },
    )

    messages = extract_chat_messages(export_dir, account_wxid, target_wxid)
    write_jsonl(messages_output, [message.to_dict() for message in messages])

    fewshot_samples, rag_records = build_dataset_assets(
        messages=messages,
        output_dir=output_dir,
        chroma_dir=config.embedding.chroma_dir,
        model_name=config.embedding.model_name,
        min_text_length=config.dataset.min_text_length,
        fewshot_limit=config.dataset.fewshot_limit,
    )
    print(
        "已完成第一阶段文本管线："
        f"联系人 {len(contacts)} 个，规范化消息 {len(messages)} 条，"
        f"Few-shot {len(fewshot_samples)} 条，RAG {len(rag_records)} 条。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
