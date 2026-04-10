from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from afterglow_robot.logging_utils import setup_logging
from afterglow_robot.wechat_export import discover_contacts, write_json

"""联系人发现 CLI。"""


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数。"""

    parser = argparse.ArgumentParser(description="发现并导出联系人列表。")
    parser.add_argument("--export-dir", required=True, help="WeChatDataAnalysis 输出目录。")
    parser.add_argument("--account-wxid", help="账号 wxid；只有一个账号目录时可省略。")
    parser.add_argument("--output", default="contacts.json", help="联系人 JSON 输出路径。")
    parser.add_argument("--verbose", action="store_true", help="输出调试日志。")
    return parser


def main(argv: list[str] | None = None) -> int:
    """读取联系人库并导出联系人清单。"""

    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    export_dir = Path(args.export_dir).resolve()
    output_path = Path(args.output).resolve()
    account_wxid, contacts = discover_contacts(export_dir, args.account_wxid)
    payload = {
        "account_wxid": account_wxid,
        "count": len(contacts),
        "contacts": contacts,
    }
    write_json(output_path, payload)
    print(f"已导出 {len(contacts)} 个联系人到：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
