from __future__ import annotations

import argparse
import shutil
from dataclasses import replace
from pathlib import Path

from src.common.config import AppConfig, load_config
from src.common.io_utils import read_json, write_json, write_jsonl
from src.ingestion.contacts import discover_contacts
from src.ingestion.discovery import resolve_account_wxid, select_parser
from src.ingestion.normalize import extract_target_candidates
from src.installer.checks import (
    check_environment,
    ensure_openclaw_installed,
    run_openclaw_install,
)
from src.preprocess.pipeline import (
    build_fewshot,
    build_persona_prompt,
    build_rag_corpus,
    clean_messages,
    ensure_non_empty,
)
from src.rag.prompt_builder import build_prompt, dump_debug_payload, parse_fewshots, parse_history, to_pretty_json
from src.runtime.errors import ConfigValidationError, IngestArtifactsMissingError
from src.runtime.ollama_client import OllamaClient
from src.vectorstore.chroma_store import ChromaVectorStore

OPENCLAW_INSTALL_CMD = "npx -y @tencent-weixin/openclaw-weixin-cli@latest install"


def handle_init(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    ensure_config_template(config_path)
    config = load_config(config_path)
    statuses = check_environment()
    print("环境检查结果：")
    missing: list[str] = []
    for status in statuses:
        marker = "OK" if status.available else "MISSING"
        print(f"- {status.name}: {marker} ({status.detail})")
        if not status.available and status.name != "python":
            missing.append(status.name)
    print(f"配置文件：{config.config_path}")
    if missing:
        print("可执行安装脚本：")
        print("- powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1")
        print("- powershell -ExecutionPolicy Bypass -File scripts/install_ollama.ps1")
        print("- powershell -ExecutionPolicy Bypass -File scripts/install_openclaw.ps1")
        return 1
    return 0


def handle_ingest(args: argparse.Namespace) -> int:
    config = _load_with_overrides(args)
    export_dir = config.resolve_path(config.wechat.export_dir)
    parser = select_parser(export_dir)
    account_wxid = resolve_account_wxid(parser, export_dir, config.wechat.account_wxid)
    contacts = discover_contacts(parser, export_dir, account_wxid)
    candidates, resolved_target_wxid = extract_target_candidates(
        parser=parser,
        export_dir=export_dir,
        account_wxid=account_wxid,
        target_wxid=config.wechat.target_wxid,
        contacts=contacts,
    )
    messages = clean_messages(candidates, min_text_length=config.dataset.min_text_length)
    ensure_non_empty(messages, target_wxid=config.wechat.target_wxid)
    fewshots = build_fewshot(messages, limit=config.dataset.fewshot_limit)
    rag_records = build_rag_corpus(messages, resolved_target_wxid=resolved_target_wxid)
    persona_prompt = build_persona_prompt(config.wechat.target_wxid)

    output_base = config.resolve_path(config.output.base_dir)
    output_base.mkdir(parents=True, exist_ok=True)
    write_json(output_base / "contacts.json", [contact.to_dict() for contact in contacts])
    write_jsonl(output_base / "messages.normalized.jsonl", [message.to_dict() for message in messages])
    write_json(output_base / "fewshot.json", [sample.to_dict() for sample in fewshots])
    write_jsonl(output_base / "rag_corpus.jsonl", [record.to_dict() for record in rag_records])
    (output_base / "persona_prompt.txt").write_text(persona_prompt, encoding="utf-8")

    chroma_dir = config.resolve_path(config.embedding.chroma_dir)
    vector_store = ChromaVectorStore(chroma_dir=chroma_dir, model_name=config.embedding.model_name)
    vector_store.build(rag_records)

    print(f"ingest 完成，解析器：{parser.name}")
    print(f"账号：{account_wxid}，目标：{config.wechat.target_wxid}")
    print(f"产物目录：{output_base}")
    print(f"向量库目录：{chroma_dir}")
    return 0


def handle_chat(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    output_base = config.resolve_path(config.output.base_dir)
    message = (args.message or "").strip()
    if not message:
        raise ConfigValidationError("--message 不能为空")

    persona_file = output_base / "persona_prompt.txt"
    fewshot_file = output_base / "fewshot.json"
    if not persona_file.exists():
        raise IngestArtifactsMissingError(str(persona_file))
    if not fewshot_file.exists():
        raise IngestArtifactsMissingError(str(fewshot_file))
    persona_prompt = persona_file.read_text(encoding="utf-8")
    fewshots = parse_fewshots(read_json(fewshot_file), limit=config.conversation.fewshot_limit)

    history: list[dict[str, str]] = []
    if args.history_file:
        history = parse_history(
            read_json(Path(args.history_file)),
            limit=config.conversation.history_limit,
        )

    chroma_dir = config.resolve_path(config.embedding.chroma_dir)
    vector_store = ChromaVectorStore(chroma_dir=chroma_dir, model_name=config.embedding.model_name)
    rag_hits = vector_store.query(message, top_k=config.retrieval.top_k)
    prompt = build_prompt(
        persona_prompt=persona_prompt,
        fewshots=fewshots,
        rag_hits=rag_hits,
        history=history,
        user_message=message,
    )
    ollama = OllamaClient(config.llm)
    ollama.check_health()
    response = ollama.generate(prompt)
    print(response)

    if args.output:
        payload = dump_debug_payload(prompt=prompt, rag_hits=rag_hits, response=response)
        Path(args.output).write_text(to_pretty_json(payload), encoding="utf-8")
    return 0


def handle_wechat_connect(args: argparse.Namespace) -> int:
    load_config(args.config)
    print(f"OpenClaw 安装命令：{OPENCLAW_INSTALL_CMD}")
    try:
        ensure_openclaw_installed()
        print("OpenClaw 检测通过。")
    except Exception:
        if args.check_only:
            raise
        print("开始执行 OpenClaw 安装命令...")
        run_openclaw_install()
        print("OpenClaw 安装完成。")
    print("下一步：在微信侧按 OpenClaw 指引扫码接入。")
    return 0


def ensure_config_template(config_path: Path) -> None:
    if config_path.exists():
        return
    root = Path(__file__).resolve().parents[2]
    example = root / "config" / "config.example.yaml"
    if not example.exists():
        return
    config_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(example, config_path)
    print(f"已生成配置模板：{config_path}")


def _load_with_overrides(args: argparse.Namespace) -> AppConfig:
    config = load_config(args.config)
    wechat = config.wechat
    if args.target_wxid:
        wechat = replace(wechat, target_wxid=args.target_wxid)
    if args.export_dir:
        wechat = replace(wechat, export_dir=args.export_dir)
    return replace(config, wechat=wechat)
