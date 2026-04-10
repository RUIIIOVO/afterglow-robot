from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from afterglow_robot.config import load_app_config
from afterglow_robot.dataset_builder import build_dataset_assets, read_normalized_messages
from afterglow_robot.logging_utils import setup_logging

"""数据集构建 CLI。"""


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数。"""

    parser = argparse.ArgumentParser(description="从规范化消息构建 Few-shot 与 RAG 数据。")
    parser.add_argument("--config", help="配置文件路径。")
    parser.add_argument("--input", help="规范化消息 JSONL 路径。")
    parser.add_argument("--output-dir", help="fewshot.json 与 rag_corpus.jsonl 输出目录。")
    parser.add_argument("--chroma-dir", help="ChromaDB 目录。")
    parser.add_argument("--model-name", help="embedding 模型名称。")
    parser.add_argument("--min-text-length", type=int, help="最小文本长度。")
    parser.add_argument("--fewshot-limit", type=int, help="Few-shot 样本上限。")
    parser.add_argument("--verbose", action="store_true", help="输出调试日志。")
    return parser


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path, str, int, int]:
    """解析输入、输出与向量库相关路径。"""

    config = load_app_config(args.config) if args.config else None

    if args.input:
        input_path = Path(args.input).resolve()
    else:
        if not config or not config.wechat.target_wxid:
            raise ValueError("未提供 --input，且配置文件中缺少 wechat.target_wxid。")
        input_path = (config.output.base_dir / config.wechat.target_wxid / "messages.normalized.jsonl").resolve()

    if args.output_dir:
        output_dir = Path(args.output_dir).resolve()
    else:
        if not config or not config.wechat.target_wxid:
            raise ValueError("未提供 --output-dir，且配置文件中缺少 wechat.target_wxid。")
        output_dir = (config.output.base_dir / config.wechat.target_wxid).resolve()

    chroma_dir = Path(args.chroma_dir).resolve() if args.chroma_dir else config.embedding.chroma_dir
    model_name = args.model_name or (config.embedding.model_name if config else "BAAI/bge-small-zh-v1.5")
    min_text_length = args.min_text_length or (config.dataset.min_text_length if config else 4)
    fewshot_limit = args.fewshot_limit or (config.dataset.fewshot_limit if config else 300)

    return input_path, output_dir, Path(chroma_dir).resolve(), model_name, min_text_length, fewshot_limit


def main(argv: list[str] | None = None) -> int:
    """读取规范化消息并构建 Few-shot / RAG / Chroma 资产。"""

    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    input_path, output_dir, chroma_dir, model_name, min_text_length, fewshot_limit = _resolve_paths(args)
    messages = read_normalized_messages(input_path)
    fewshot_samples, rag_records = build_dataset_assets(
        messages=messages,
        output_dir=output_dir,
        chroma_dir=chroma_dir,
        model_name=model_name,
        min_text_length=min_text_length,
        fewshot_limit=fewshot_limit,
    )
    print(
        f"已生成 Few-shot 样本 {len(fewshot_samples)} 条、RAG 语料 {len(rag_records)} 条，输出目录：{output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
