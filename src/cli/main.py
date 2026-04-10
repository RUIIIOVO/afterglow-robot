from __future__ import annotations

import argparse

from src.cli.commands import handle_chat, handle_ingest, handle_init, handle_wechat_connect
from src.runtime.runner import run_cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="afterglow")
    parser.set_defaults(handler=None)
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="环境检查与配置初始化")
    init_parser.add_argument("--config", default="config/config.yaml")
    init_parser.add_argument("--force-check", action="store_true")
    init_parser.set_defaults(handler=handle_init)

    ingest_parser = subparsers.add_parser("ingest", help="导入聊天并构建数据产物")
    ingest_parser.add_argument("--config", default="config/config.yaml")
    ingest_parser.add_argument("--target-wxid")
    ingest_parser.add_argument("--export-dir")
    ingest_parser.set_defaults(handler=handle_ingest)

    chat_parser = subparsers.add_parser("chat", help="本地单轮回复调试")
    chat_parser.add_argument("--config", default="config/config.yaml")
    chat_parser.add_argument("--message", required=True)
    chat_parser.add_argument("--history-file")
    chat_parser.add_argument("--output")
    chat_parser.set_defaults(handler=handle_chat)

    wechat_parser = subparsers.add_parser("wechat-connect", help="OpenClaw 接入前检查与安装")
    wechat_parser.add_argument("--config", default="config/config.yaml")
    wechat_parser.add_argument("--check-only", action="store_true")
    wechat_parser.set_defaults(handler=handle_wechat_connect)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.handler:
        parser.print_help()
        return 1
    return run_cli(lambda: args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())

