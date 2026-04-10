from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BridgeInboundEvent:
    conversation_id: str
    sender_id: str
    text: str
    timestamp: int
    message_type: str = "text"
    event_id: str = ""
    reply_url: str | None = None


@dataclass(frozen=True)
class BridgeReplyPayload:
    conversation_id: str
    status: str
    reply_text: str = ""
    error_code: str = ""
    error_message: str = ""

    def to_dict(self) -> dict:
        payload = {
            "conversation_id": self.conversation_id,
            "status": self.status,
        }
        if self.reply_text:
            payload["reply_text"] = self.reply_text
        if self.error_code:
            payload["error"] = {
                "code": self.error_code,
                "message": self.error_message,
            }
        return payload


@dataclass(frozen=True)
class BridgeProcessResult:
    status_code: int
    payload: dict

