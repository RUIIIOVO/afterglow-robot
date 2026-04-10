from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from afterglow_robot.config import AppConfig, load_app_config, require_value
from afterglow_robot.logging_utils import setup_logging
from afterglow_robot.wechat_export import extract_chat_messages, resolve_account_wxid, write_jsonl

"""聊天提取 CLI。"""


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数。"""

    parser = argparse.ArgumentParser(description="提取指定联系人聊天记录。")
    parser.add_argument("--config", help="配置文件路径。")
    parser.add_argument("--export-dir", help="WeChatDataAnalysis 输出目录。")
    parser.add_argument("--account-wxid", help="账号 wxid。")
    parser.add_argument("--target-wxid", help="目标联系人 wxid。")
    parser.add_argument("--output", help="规范化消息 JSONL 输出路径。")
    parser.add_argument("--verbose", action="store_true", help="输出调试日志。")
    return parser


def _resolve_parameters(args: argparse.Namespace) -> tuple[Path, str, str, Path]:
    """按显式参数优先、配置兜底的顺序解析运行参数。"""

    config: AppConfig | None = load_app_config(args.config) if args.config else None

    export_dir = Path(args.export_dir).resolve() if args.export_dir else config.wechat.export_dir
    account_wxid = args.account_wxid or (config.wechat.account_wxid if config else None)
    target_wxid = args.target_wxid or (config.wechat.target_wxid if config else None)

    export_dir = Path(export_dir).resolve()
    account_wxid = resolve_account_wxid(export_dir, account_wxid)
    target_wxid = require_value(target_wxid, "wechat.target_wxid")

    if args.output:
        output_path = Path(args.output).resolve()
    else:
        base_dir = config.output.base_dir if config else Path("data/outputs").resolve()
        output_path = base_dir / target_wxid / "messages.normalized.jsonl"
    return export_dir, account_wxid, target_wxid, output_path.resolve()


def main(argv: list[str] | None = None) -> int:
    """提取目标联系人文本消息并输出为规范化 JSONL。"""

    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    export_dir, account_wxid, target_wxid, output_path = _resolve_parameters(args)
    messages = extract_chat_messages(export_dir, account_wxid, target_wxid)
    write_jsonl(output_path, [message.to_dict() for message in messages])
    print(f"已导出 {len(messages)} 条规范化消息到：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
