from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from afterglow_robot.config import load_app_config
from afterglow_robot.logging_utils import setup_logging
from afterglow_robot.reply_generator import generate_reply
from afterglow_robot.wechat_export import write_json

"""二阶段文本回复 CLI。"""


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数。"""

    parser = argparse.ArgumentParser(description="基于 RAG + Ollama 生成单轮回复。")
    parser.add_argument("--config", required=True, help="配置文件路径。")
    parser.add_argument("--message", required=True, help="当前用户消息。")
    parser.add_argument("--history-file", help="最近对话历史 JSON 文件。")
    parser.add_argument("--output", help="调试输出 JSON 路径。")
    parser.add_argument("--verbose", action="store_true", help="输出调试日志。")
    return parser


def load_history(path: Path | None) -> list[dict[str, object]]:
    """读取可选的历史对话文件。"""

    if path is None:
        return []
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError("history-file 必须是 JSON 数组。")
    return payload


def main(argv: list[str] | None = None) -> int:
    """执行单轮回复生成。"""

    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    config = load_app_config(args.config)
    history = load_history(Path(args.history_file).resolve()) if args.history_file else []
    payload = generate_reply(config=config, user_message=args.message, history=history)

    if args.output:
        write_json(Path(args.output).resolve(), payload)

    print(payload["reply"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
