from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path

from src.common.artifacts import resolve_artifact_paths
from src.common.config import AppConfig, load_config
from src.common.io_utils import read_json, write_json, write_jsonl
from src.ingestion.contacts import discover_contacts
from src.ingestion.discovery import resolve_account_wxid, select_parser
from src.ingestion.normalize import extract_conversation_candidates, extract_target_candidates
from src.installer.checks import (
    check_environment,
    ensure_openclaw_installed,
    run_openclaw_install,
)
from src.preprocess.pipeline import (
    build_persona_prompt,
    build_persona_profile,
    build_dialog_turns,
    build_fewshot_candidates,
    build_rag_corpus,
    build_voice_utterances,
    clean_messages,
    ensure_non_empty,
    select_fewshots,
)
from src.rag.prompt_builder import parse_history, to_pretty_json
from src.runtime.chat_service import generate_chat_reply
from src.vectorstore.chroma_store import ChromaVectorStore
from src.wechat_bridge.openclaw_integration import configure_openclaw_afterglow
from src.wechat_bridge.server import WechatBridgeService, run_bridge_server

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
    style_candidates, resolved_target_wxid = extract_target_candidates(
        parser=parser,
        export_dir=export_dir,
        account_wxid=account_wxid,
        target_wxid=config.wechat.target_wxid,
        contacts=contacts,
    )
    conversation_candidates, _ = extract_conversation_candidates(
        parser=parser,
        export_dir=export_dir,
        account_wxid=account_wxid,
        target_wxid=config.wechat.target_wxid,
        contacts=contacts,
    )
    style_messages = clean_messages(
        style_candidates,
        min_text_length=config.dataset.min_text_length,
        source_parser=parser.name,
    )
    conversation_messages = clean_messages(
        conversation_candidates,
        min_text_length=1,
        source_parser=parser.name,
    )
    ensure_non_empty(style_messages, target_wxid=config.wechat.target_wxid)
    dialog_turns = build_dialog_turns(conversation_messages)
    voice_utterances = build_voice_utterances(style_messages)
    persona_profile = build_persona_profile(
        messages=style_messages,
        voice_utterances=voice_utterances,
        target_wxid=resolved_target_wxid,
    )
    fewshot_candidates = build_fewshot_candidates(dialog_turns, persona_profile)
    fewshots = select_fewshots(fewshot_candidates, limit=config.dataset.fewshot_limit)
    rag_records = build_rag_corpus(style_messages, dialog_turns, resolved_target_wxid=resolved_target_wxid)
    persona_prompt = build_persona_prompt(persona_profile)

    output_base = config.resolve_path(config.output.base_dir)
    output_base.mkdir(parents=True, exist_ok=True)
    artifact_paths = resolve_artifact_paths(output_base)
    contacts_payload = [contact.to_dict() for contact in contacts]
    legacy_messages_payload = [message.to_dict() for message in style_messages]
    truth_messages_payload = [message.to_dict() for message in conversation_messages]
    dialog_turns_payload = [turn.to_dict() for turn in dialog_turns]
    voice_payload = [item.to_dict() for item in voice_utterances]
    fewshot_candidate_payload = [candidate.to_dict() for candidate in fewshot_candidates]
    fewshot_payload = [sample.to_dict() for sample in fewshots]
    rag_payload = [record.to_dict() for record in rag_records]

    write_json(artifact_paths.legacy_contacts, contacts_payload)
    write_json(artifact_paths.truth_contacts, contacts_payload)
    write_jsonl(artifact_paths.legacy_messages, legacy_messages_payload)
    write_jsonl(artifact_paths.truth_messages, truth_messages_payload)
    write_jsonl(artifact_paths.truth_dialog_turns, dialog_turns_payload)
    write_json(artifact_paths.truth_persona_profile, persona_profile.to_dict())
    write_jsonl(artifact_paths.voice_utterances, voice_payload)
    write_json(artifact_paths.legacy_fewshot, fewshot_payload)
    write_json(artifact_paths.retrieval_fewshot, fewshot_payload)
    write_jsonl(artifact_paths.retrieval_fewshot_candidates, fewshot_candidate_payload)
    write_jsonl(artifact_paths.legacy_rag, rag_payload)
    write_jsonl(artifact_paths.retrieval_rag, rag_payload)
    artifact_paths.legacy_persona.parent.mkdir(parents=True, exist_ok=True)
    artifact_paths.legacy_persona.write_text(persona_prompt, encoding="utf-8")
    artifact_paths.persona_prompt.parent.mkdir(parents=True, exist_ok=True)
    artifact_paths.persona_prompt.write_text(persona_prompt, encoding="utf-8")

    chroma_dir = config.resolve_path(config.embedding.chroma_dir)
    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "build_status": "pending",
        "parser": parser.name,
        "account_wxid": account_wxid,
        "target_wxid": config.wechat.target_wxid,
        "resolved_target_wxid": resolved_target_wxid,
        "embedding": {
            "requested_provider": config.embedding.provider,
            "resolved_provider": "",
            "model_name": config.embedding.model_name,
            "fallback_used": False,
            "fallback_reason": "",
            "chroma_dir": str(chroma_dir),
            "collection_name": ChromaVectorStore.collection_name,
        },
        "artifacts": {
            "contacts": {"path": _relative_to_output(artifact_paths.truth_contacts, output_base), "count": len(contacts_payload)},
            "legacy_messages": {
                "path": _relative_to_output(artifact_paths.legacy_messages, output_base),
                "count": len(legacy_messages_payload),
            },
            "messages": {"path": _relative_to_output(artifact_paths.truth_messages, output_base), "count": len(truth_messages_payload)},
            "dialog_turns": {
                "path": _relative_to_output(artifact_paths.truth_dialog_turns, output_base),
                "count": len(dialog_turns_payload),
            },
            "voice_utterances": {
                "path": _relative_to_output(artifact_paths.voice_utterances, output_base),
                "count": len(voice_payload),
            },
            "fewshot_candidates": {
                "path": _relative_to_output(artifact_paths.retrieval_fewshot_candidates, output_base),
                "count": len(fewshot_candidate_payload),
            },
            "fewshot": {"path": _relative_to_output(artifact_paths.retrieval_fewshot, output_base), "count": len(fewshot_payload)},
            "rag_corpus": {"path": _relative_to_output(artifact_paths.retrieval_rag, output_base), "count": len(rag_payload)},
            "persona_prompt": {"path": _relative_to_output(artifact_paths.persona_prompt, output_base), "count": 1},
        },
    }
    write_json(artifact_paths.manifest, manifest)

    vector_store: ChromaVectorStore | None = None
    failure_stage = "embedding_init"
    try:
        vector_store = ChromaVectorStore(
            chroma_dir=chroma_dir,
            model_name=config.embedding.model_name,
            provider=config.embedding.provider,
            allow_fallback=config.embedding.allow_fallback,
            fallback_provider=config.embedding.fallback_provider,
        )
        failure_stage = "vector_build"
        vector_store.build(rag_records)
    except Exception as error:
        manifest["build_status"] = "failed"
        if vector_store is not None:
            manifest["embedding"].update(vector_store.embedding_metadata)
        manifest["error"] = {
            "type": error.__class__.__name__,
            "message": str(error),
            "stage": failure_stage,
        }
        write_json(artifact_paths.manifest, manifest)
        raise

    manifest["build_status"] = "ready"
    manifest["embedding"].update(
        {
            **vector_store.embedding_metadata,
            "chroma_dir": str(chroma_dir),
            "collection_name": vector_store.collection_name,
        }
    )
    write_json(artifact_paths.manifest, manifest)

    print(f"ingest 完成，解析器：{parser.name}")
    print(f"账号：{account_wxid}，目标：{config.wechat.target_wxid}")
    print(f"产物目录：{output_base}")
    print(f"向量库目录：{chroma_dir}")
    if vector_store.resolution.fallback_used:
        print(
            "警告：embedding 已降级为 "
            f"{vector_store.resolution.resolved_provider}，原因：{vector_store.resolution.fallback_reason}"
        )
    return 0


def handle_chat(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    history: object = []
    if args.history_file:
        history = parse_history(
            read_json(Path(args.history_file)),
            limit=config.conversation.history_limit,
        )
    result = generate_chat_reply(config=config, message=str(args.message or ""), history=history)
    print(result.reply_text)

    if args.output:
        payload = {
            "prompt": result.prompt,
            "rag_hits": result.rag_hits,
            "response": result.reply_text,
        }
        Path(args.output).write_text(to_pretty_json(payload), encoding="utf-8")
    return 0


def handle_wechat_connect(args: argparse.Namespace) -> int:
    load_config(args.config)
    bridge_url = str(getattr(args, "bridge_url", "http://127.0.0.1:8787/openclaw/event"))
    timeout_ms = int(getattr(args, "bridge_timeout_ms", 120000))
    openclaw_root = getattr(args, "openclaw_root", None)
    skip_bridge_patch = bool(getattr(args, "skip_bridge_patch", False))
    print(f"OpenClaw 安装命令：{OPENCLAW_INSTALL_CMD}")
    if args.check_only:
        ensure_openclaw_installed()
        print("OpenClaw 检测通过。")
        if not skip_bridge_patch:
            print(f"桥接目标地址：{bridge_url}")
        print("下一步：在微信侧按 OpenClaw 指引扫码接入。")
        return 0

    print("开始执行 OpenClaw 安装命令（将触发扫码流程）...")
    run_openclaw_install()
    print("OpenClaw 安装命令执行完成。")
    if not skip_bridge_patch:
        result = configure_openclaw_afterglow(
            bridge_url=bridge_url,
            timeout_ms=timeout_ms,
            openclaw_root=openclaw_root,
            strict=False,
        )
        if result.applied:
            print(
                "桥接补丁已完成："
                f"schema={result.schema_changed}, process={result.process_changed}, config={result.config_changed}"
            )
        else:
            print("桥接补丁暂未执行：未检测到可补丁的 openclaw-weixin 安装目录。")
            print(f"请在扫码安装完成后重试：python -m src.cli.main wechat-connect --config {args.config}")
    print("下一步：在微信侧按 OpenClaw 指引扫码接入。")
    return 0


def handle_serve(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    service = WechatBridgeService(config=config)
    if args.once_file:
        payload = read_json(Path(args.once_file))
        result = service.process_payload(payload)
        print(json.dumps(result.payload, ensure_ascii=False, indent=2))
        return 0 if result.status_code < 400 else 1

    host = str(args.host)
    port = int(args.port)
    print(f"微信桥接服务已启动：http://{host}:{port}")
    print("健康检查：GET /health")
    print("事件入口：POST /openclaw/event")
    run_bridge_server(host=host, port=port, service=service)
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


def _relative_to_output(path: Path, output_base: Path) -> str:
    try:
        return str(path.relative_to(output_base)).replace("\\", "/")
    except ValueError:
        return str(path)
