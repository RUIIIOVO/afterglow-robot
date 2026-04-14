from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AfterglowError(Exception):
    user_message: str
    code: str
    context: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.user_message


class ConfigFileNotFoundError(AfterglowError):
    def __init__(self, path: str) -> None:
        super().__init__(
            user_message=f"配置文件不存在：{path}",
            code="CONFIG_NOT_FOUND",
            context={"config_path": path},
        )


class ConfigValidationError(AfterglowError):
    def __init__(self, details: str, context: dict[str, Any] | None = None) -> None:
        super().__init__(
            user_message=f"配置缺项或格式非法：{details}",
            code="CONFIG_INVALID",
            context=context or {},
        )


class ExportDirNotFoundError(AfterglowError):
    def __init__(self, export_dir: str) -> None:
        super().__init__(
            user_message=f"导出目录不存在：{export_dir}",
            code="EXPORT_DIR_NOT_FOUND",
            context={"export_dir": export_dir},
        )


class ExportFormatError(AfterglowError):
    def __init__(self, export_dir: str, details: str) -> None:
        super().__init__(
            user_message=f"导出目录格式无法识别：{details}",
            code="EXPORT_FORMAT_UNSUPPORTED",
            context={"export_dir": export_dir, "details": details},
        )


class AccountDetectionError(AfterglowError):
    def __init__(self, details: str, context: dict[str, Any] | None = None) -> None:
        super().__init__(
            user_message=details,
            code="ACCOUNT_DETECTION_ERROR",
            context=context or {},
        )


class TargetNotFoundError(AfterglowError):
    def __init__(self, target_wxid: str, account_wxid: str) -> None:
        super().__init__(
            user_message=f"目标联系人不存在：{target_wxid}",
            code="TARGET_NOT_FOUND",
            context={"target_wxid": target_wxid, "account_wxid": account_wxid},
        )


class NoTextMessagesError(AfterglowError):
    def __init__(self, target_wxid: str) -> None:
        super().__init__(
            user_message=f"未找到可用文本消息：{target_wxid}",
            code="NO_TEXT_MESSAGES",
            context={"target_wxid": target_wxid},
        )


class VectorStoreNotBuiltError(AfterglowError):
    def __init__(self, chroma_dir: str) -> None:
        super().__init__(
            user_message="向量库未构建，请先运行 ingest。",
            code="VECTORSTORE_NOT_BUILT",
            context={"chroma_dir": chroma_dir},
        )


class EmbeddingInitializationError(AfterglowError):
    def __init__(self, provider: str, details: str, context: dict[str, Any] | None = None) -> None:
        super().__init__(
            user_message=f"Embedding 初始化失败：{provider}。{details}",
            code="EMBEDDING_INIT_FAILED",
            context={"provider": provider, **(context or {})},
        )


class EmbeddingProviderMismatchError(AfterglowError):
    def __init__(
        self,
        expected_provider: str,
        actual_provider: str,
        expected_model: str = "",
        actual_model: str = "",
        details: str = "",
    ) -> None:
        suffix = f" 当前={expected_provider}，已构建={actual_provider}"
        if expected_model or actual_model:
            suffix += f"；模型 当前={expected_model or 'unknown'}，已构建={actual_model or 'unknown'}"
        if details:
            suffix += f"；{details}"
        super().__init__(
            user_message="向量库 embedding 配置与当前运行配置不一致，请重新运行 ingest。" + suffix,
            code="EMBEDDING_PROVIDER_MISMATCH",
            context={
                "expected_provider": expected_provider,
                "actual_provider": actual_provider,
                "expected_model": expected_model,
                "actual_model": actual_model,
                "details": details,
            },
        )


class IngestArtifactsMissingError(AfterglowError):
    def __init__(self, missing_path: str) -> None:
        super().__init__(
            user_message=f"缺少 ingest 产物：{missing_path}。请先运行 ingest。",
            code="INGEST_ARTIFACT_MISSING",
            context={"missing_path": missing_path},
        )


class OllamaNotRunningError(AfterglowError):
    def __init__(self, endpoint: str, details: str | None = None) -> None:
        super().__init__(
            user_message=f"Ollama 未启动或不可访问：{endpoint}",
            code="OLLAMA_UNAVAILABLE",
            context={"endpoint": endpoint, "details": details or ""},
        )


class DependencyMissingError(AfterglowError):
    def __init__(self, dependency: str, hint: str) -> None:
        super().__init__(
            user_message=f"缺少依赖：{dependency}。{hint}",
            code="DEPENDENCY_MISSING",
            context={"dependency": dependency, "hint": hint},
        )


class OpenClawNotInstalledError(AfterglowError):
    def __init__(self, details: str) -> None:
        super().__init__(
            user_message=f"OpenClaw 未安装：{details}",
            code="OPENCLAW_NOT_INSTALLED",
            context={"details": details},
        )


class OpenClawPatchError(AfterglowError):
    def __init__(self, details: str, context: dict[str, Any] | None = None) -> None:
        super().__init__(
            user_message=f"OpenClaw 桥接配置失败：{details}",
            code="OPENCLAW_PATCH_FAILED",
            context=context or {},
        )


class OpenClawRequestFormatError(AfterglowError):
    def __init__(self, details: str, context: dict[str, Any] | None = None) -> None:
        super().__init__(
            user_message=f"OpenClaw 请求格式错误：{details}",
            code="OPENCLAW_REQUEST_INVALID",
            context=context or {},
        )


class NonTextMessageError(AfterglowError):
    def __init__(self, message_type: str) -> None:
        super().__init__(
            user_message=f"暂不支持非文本消息：{message_type}",
            code="NON_TEXT_EVENT",
            context={"message_type": message_type},
        )


class ReplyGenerationError(AfterglowError):
    def __init__(self, details: str, context: dict[str, Any] | None = None) -> None:
        super().__init__(
            user_message=f"回复生成失败：{details}",
            code="REPLY_GENERATION_FAILED",
            context=context or {},
        )


class OpenClawWriteBackError(AfterglowError):
    def __init__(self, details: str, context: dict[str, Any] | None = None) -> None:
        super().__init__(
            user_message=f"OpenClaw 回写失败：{details}",
            code="OPENCLAW_WRITEBACK_FAILED",
            context=context or {},
        )
