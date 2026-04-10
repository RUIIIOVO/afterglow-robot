from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from src.common.config import AppConfig
from src.runtime.chat_service import generate_chat_reply
from src.runtime.errors import AfterglowError, ReplyGenerationError
from src.wechat_bridge.adapter import OpenClawAdapter
from src.wechat_bridge.models import BridgeProcessResult


def setup_bridge_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("afterglow.wechat_bridge")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger


class WechatBridgeService:
    def __init__(
        self,
        config: AppConfig,
        adapter: OpenClawAdapter | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config
        self.adapter = adapter or OpenClawAdapter()
        self.logger = logger or setup_bridge_logger(Path("logs/wechat_bridge.log").resolve())

    def process_payload(self, payload: object) -> BridgeProcessResult:
        conversation_id = "unknown"
        try:
            event = self.adapter.parse_event(payload)
            conversation_id = event.conversation_id
            reply = generate_chat_reply(config=self.config, message=event.text, history=[])
            response_payload = self.adapter.build_success_payload(event=event, reply_text=reply.reply_text)
            if event.reply_url:
                self.adapter.push_reply(
                    reply_url=event.reply_url,
                    payload=response_payload,
                    timeout_seconds=self.config.llm.timeout_seconds,
                )
            self.logger.info(
                "bridge_ok conversation_id=%s sender_id=%s text_len=%s",
                event.conversation_id,
                event.sender_id,
                len(event.text),
            )
            return BridgeProcessResult(status_code=200, payload=response_payload)
        except AfterglowError as error:
            self.logger.error(
                "bridge_error code=%s message=%s context=%s",
                error.code,
                error.user_message,
                error.context,
            )
            return BridgeProcessResult(
                status_code=self._status_from_error_code(error.code),
                payload=self.adapter.build_error_payload(
                    conversation_id=conversation_id,
                    error_code=error.code,
                    error_message=error.user_message,
                ),
            )
        except Exception as error:  # noqa: BLE001
            wrapped = ReplyGenerationError(
                details="未预期异常",
                context={"error": str(error)},
            )
            self.logger.exception("bridge_unexpected_error error=%s", str(error))
            return BridgeProcessResult(
                status_code=500,
                payload=self.adapter.build_error_payload(
                    conversation_id=conversation_id,
                    error_code=wrapped.code,
                    error_message=wrapped.user_message,
                ),
            )

    @staticmethod
    def _status_from_error_code(code: str) -> int:
        if code in {"OPENCLAW_REQUEST_INVALID", "NON_TEXT_EVENT"}:
            return 400
        if code == "OPENCLAW_WRITEBACK_FAILED":
            return 502
        if code in {"OLLAMA_UNAVAILABLE", "VECTORSTORE_NOT_BUILT", "INGEST_ARTIFACT_MISSING"}:
            return 503
        return 500


class WechatBridgeRequestHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, service: WechatBridgeService, **kwargs) -> None:
        self._service = service
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            self._send_json(404, {"status": "error", "message": "not_found"})
            return
        self._send_json(200, {"status": "ok"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/openclaw/event":
            self._send_json(404, {"status": "error", "message": "not_found"})
            return
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        raw_body = self.rfile.read(content_length).decode("utf-8")
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            result = self._service.process_payload("invalid_json")
            self._send_json(400, result.payload)
            return
        result = self._service.process_payload(payload)
        self._send_json(result.status_code, result.payload)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        self._service.logger.info("http " + format, *args)

    def _send_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_bridge_server(
    host: str,
    port: int,
    service: WechatBridgeService,
) -> None:
    handler_factory: Callable[..., BaseHTTPRequestHandler] = lambda *args, **kwargs: WechatBridgeRequestHandler(
        *args,
        service=service,
        **kwargs,
    )
    httpd = ThreadingHTTPServer((host, port), handler_factory)
    service.logger.info("bridge_server_start host=%s port=%s", host, port)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        service.logger.info("bridge_server_stop")

