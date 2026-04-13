from __future__ import annotations

from pathlib import Path

from src.ingestion.parsers.base import ExportParser
from src.ingestion.parsers.minimal_v1 import MinimalV1Parser
from src.ingestion.parsers.wechat_data_analysis_v1 import WeChatDataAnalysisV1Parser
from src.runtime.errors import (
    AccountDetectionError,
    ExportDirNotFoundError,
    ExportFormatError,
)


_PARSERS: list[ExportParser] = [
    MinimalV1Parser(),
    WeChatDataAnalysisV1Parser(),
]


def select_parser(export_dir: Path) -> ExportParser:
    if not export_dir.exists():
        raise ExportDirNotFoundError(str(export_dir))
    for parser in _PARSERS:
        if parser.can_parse(export_dir):
            return parser
    supported = ", ".join(parser.name for parser in _PARSERS)
    raise ExportFormatError(
        str(export_dir),
        f"未匹配到已支持的导出结构。当前支持：{supported}",
    )


def resolve_account_wxid(
    parser: ExportParser,
    export_dir: Path,
    configured_account_wxid: str | None,
) -> str:
    accounts = parser.list_accounts(export_dir)
    if not accounts:
        raise AccountDetectionError(
            "单账号无法识别：导出目录中没有可用账号。",
            context={"accounts": accounts},
        )
    if configured_account_wxid:
        if configured_account_wxid not in accounts:
            raise AccountDetectionError(
                f"配置的 account_wxid 不存在：{configured_account_wxid}",
                context={"available_accounts": accounts},
            )
        return configured_account_wxid
    if len(accounts) == 1:
        return accounts[0]
    raise AccountDetectionError(
        "多账号但未指定 account_wxid，请在配置中填写 wechat.account_wxid。",
        context={"available_accounts": accounts},
    )
