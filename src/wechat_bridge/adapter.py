from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from src.runtime.errors import NonTextMessageError, OpenClawRequestFormatError, OpenClawWriteBackError
from src.wechat_bridge.models import BridgeInboundEvent, BridgeReplyPayload


class OpenClawAdapter:
    def parse_event(self, payload: object) -> BridgeInboundEvent:
        if not isinstance(payload, dict):
            raise OpenClawRequestFormatError("请求体必须是 JSON 对象。")

        conversation_id = self._pick_text(
            payload.get("conversation_id"),
            payload.get("session_id"),
            payload.get("chat_id"),
            self._nested(payload, "conversation", "id"),
            self._nested(payload, "message", "session_id"),
            self._nested(payload, "message", "chat_id"),
        )
        sender_id = self._pick_text(
            payload.get("sender_id"),
            payload.get("from_wxid"),
            payload.get("from"),
            self._nested(payload, "sender", "id"),
            self._nested(payload, "message", "from_user_id"),
            self._nested(payload, "message", "sender_username"),
        )
        message_type = self._pick_text(
            payload.get("message_type"),
            self._nested(payload, "message", "type"),
            self._nested(payload, "message", "renderType"),
        ) or "text"
        normalized_message_type = self._normalize_message_type(message_type)
        text = self._pick_text(
            payload.get("text"),
            payload.get("content"),
            self._nested(payload, "message", "text"),
            self._nested(payload, "message", "content"),
            self._nested(payload, "message", "text_body"),
            self._nested(payload, "message", "body"),
        )
        timestamp_raw = (
            payload.get("timestamp")
            or payload.get("ts")
            or payload.get("time")
            or self._nested(payload, "message", "create_time_ms")
            or time.time()
        )
        event_id = self._pick_text(payload.get("event_id"), payload.get("id")) or ""
        reply_url = self._pick_text(
            payload.get("reply_url"),
            self._nested(payload, "reply", "url"),
            self._nested(payload, "callback", "url"),
        )

        if not conversation_id and sender_id:
            conversation_id = sender_id

        if not conversation_id:
            raise OpenClawRequestFormatError("缺少 conversation_id/session_id。", context={"payload_keys": list(payload.keys())})
        if not sender_id:
            raise OpenClawRequestFormatError("缺少 sender_id/from_wxid。", context={"payload_keys": list(payload.keys())})
        if normalized_message_type != "text":
            raise NonTextMessageError(message_type=message_type)
        if not text:
            raise OpenClawRequestFormatError("文本消息内容为空。", context={"conversation_id": conversation_id})
        try:
            timestamp = int(float(timestamp_raw))
        except (TypeError, ValueError) as error:
            raise OpenClawRequestFormatError(
                "timestamp 非法。",
                context={"timestamp": timestamp_raw},
            ) from error
        if timestamp > 10_000_000_000:
            timestamp //= 1000

        return BridgeInboundEvent(
            conversation_id=conversation_id,
            sender_id=sender_id,
            text=text,
            timestamp=timestamp,
            message_type=normalized_message_type,
            event_id=event_id,
            reply_url=reply_url,
        )

    def build_success_payload(self, event: BridgeInboundEvent, reply_text: str) -> dict:
        return BridgeReplyPayload(
            conversation_id=event.conversation_id,
            status="ok",
            reply_text=reply_text,
        ).to_dict()

    def build_error_payload(self, conversation_id: str, error_code: str, error_message: str) -> dict:
        return BridgeReplyPayload(
            conversation_id=conversation_id,
            status="error",
            error_code=error_code,
            error_message=error_message,
        ).to_dict()

    def push_reply(self, reply_url: str, payload: dict, timeout_seconds: int) -> None:
        request = urllib.request.Request(
            url=reply_url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                if response.status >= 400:
                    body = response.read().decode("utf-8")
                    raise OpenClawWriteBackError(
                        "OpenClaw 回写返回失败状态码。",
                        context={"status": response.status, "body": body, "reply_url": reply_url},
                    )
        except urllib.error.URLError as error:
            raise OpenClawWriteBackError(
                "OpenClaw 回写请求失败。",
                context={"reply_url": reply_url, "error": str(error)},
            ) from error

    @staticmethod
    def _nested(payload: dict[str, Any], key1: str, key2: str) -> object:
        obj = payload.get(key1)
        if isinstance(obj, dict):
            return obj.get(key2)
        return None

    @staticmethod
    def _pick_text(*values: object) -> str:
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return ""

    @staticmethod
    def _normalize_message_type(message_type: str) -> str:
        normalized = str(message_type or "").strip().lower()
        if normalized in {"", "1", "text"}:
            return "text"
        return normalized
