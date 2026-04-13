from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_BRIDGE_URL = "http://127.0.0.1:8787/openclaw/event"
DEFAULT_TIMEOUT_MS = 120000


SCHEMA_INSERT = """const afterglowSchema = z.object({
  enabled: z.boolean().optional(),
  bridgeUrl: z.string().default("http://127.0.0.1:8787/openclaw/event"),
  timeoutMs: z.number().int().positive().default(120000),
});

"""


SCHEMA_REPLACE_FROM = """export const WeixinConfigSchema = weixinAccountSchema.extend({
  accounts: z.record(z.string(), weixinAccountSchema).optional(),
  /** ISO 8601; bumped on each successful login to refresh gateway config from disk. */
  channelConfigUpdatedAt: z.string().optional(),
});
"""


SCHEMA_REPLACE_TO = """export const WeixinConfigSchema = weixinAccountSchema.extend({
  accounts: z.record(z.string(), weixinAccountSchema).optional(),
  afterglow: afterglowSchema.optional(),
  /** ISO 8601; bumped on each successful login to refresh gateway config from disk. */
  channelConfigUpdatedAt: z.string().optional(),
});
"""


HELPER_INSERT = """type AfterglowBridgeConfig = {
  enabled: boolean;
  bridgeUrl: string;
  timeoutMs: number;
};

function pickFirstNonEmptyText(...values: unknown[]): string {
  for (const value of values) {
    if (value == null) {
      continue;
    }
    const text = String(value).trim();
    if (text) {
      return text;
    }
  }
  return "";
}

function resolveAfterglowBridgeConfig(
  config: import("openclaw/plugin-sdk/core").OpenClawConfig,
): AfterglowBridgeConfig | null {
  const channels = (config as { channels?: Record<string, unknown> }).channels;
  const section = (channels?.["openclaw-weixin"] as { afterglow?: Record<string, unknown> } | undefined)?.afterglow;
  if (!section || section.enabled !== true) {
    return null;
  }

  const bridgeUrl =
    typeof section.bridgeUrl === "string" && section.bridgeUrl.trim()
      ? section.bridgeUrl.trim()
      : "http://127.0.0.1:8787/openclaw/event";
  const timeoutMs =
    typeof section.timeoutMs === "number" && Number.isFinite(section.timeoutMs) && section.timeoutMs > 0
      ? section.timeoutMs
      : 120000;

  return {
    enabled: true,
    bridgeUrl,
    timeoutMs,
  };
}

async function requestAfterglowReply(params: {
  config: AfterglowBridgeConfig;
  accountId: string;
  message: WeixinMessage;
  text: string;
}): Promise<string> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), params.config.timeoutMs);

  try {
    const conversationId = pickFirstNonEmptyText(
      params.message.session_id,
      params.message.from_user_id,
    );
    const sessionId = pickFirstNonEmptyText(params.message.session_id);
    const senderId = pickFirstNonEmptyText(params.message.from_user_id);
    const response = await fetch(params.config.bridgeUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        conversation_id: conversationId,
        session_id: sessionId,
        sender_id: senderId,
        message_type: "text",
        text: params.text,
        timestamp: params.message.create_time_ms ?? Date.now(),
        event_id: String(params.message.message_id ?? ""),
        account_id: params.accountId,
        channel: "openclaw-weixin",
      }),
      signal: controller.signal,
    });

    const payload = await response.json() as Record<string, unknown>;
    const replyText = typeof payload.reply_text === "string"
      ? payload.reply_text.trim()
      : typeof payload.reply === "string"
        ? payload.reply.trim()
        : "";
    if (!response.ok) {
      const errorMessage =
        typeof payload.error === "object" && payload.error && typeof (payload.error as { message?: unknown }).message === "string"
          ? String((payload.error as { message?: unknown }).message)
          : JSON.stringify(payload);
      throw new Error(`afterglow bridge failed: ${response.status} ${errorMessage}`);
    }
    if (!replyText) {
      throw new Error("afterglow bridge returned empty reply");
    }
    return replyText;
  } finally {
    clearTimeout(timeout);
  }
}

"""


BRIDGE_BLOCK = """  const rawContextToken = full.context_token;
  if (rawContextToken) {
    setContextToken(deps.accountId, full.from_user_id ?? "", rawContextToken);
  }

  const afterglowBridge = resolveAfterglowBridgeConfig(deps.config);
  if (afterglowBridge && textBody) {
    logger.info(
      `[afterglow] direct route enabled accountId=${deps.accountId} bridgeUrl=${afterglowBridge.bridgeUrl}`,
    );
    try {
      const replyText = await requestAfterglowReply({
        config: afterglowBridge,
        accountId: deps.accountId,
        message: full,
        text: textBody,
      });
      await sendMessageWeixin({
        to: full.from_user_id ?? "",
        text: replyText,
        opts: {
          baseUrl: deps.baseUrl,
          token: deps.token,
          contextToken: rawContextToken,
        },
      });
      logger.info(`[afterglow] direct reply sent to=${full.from_user_id ?? ""}`);
      return;
    } catch (err) {
      logger.error(`[afterglow] direct route failed err=${String(err)}`);
      await sendWeixinErrorNotice({
        to: full.from_user_id ?? "",
        contextToken: rawContextToken,
        message: `⚠️ afterglow-robot 本地桥接失败：${String(err)}`,
        baseUrl: deps.baseUrl,
        token: deps.token,
        errLog: deps.errLog,
      });
      return;
    }
  }

"""


BRIDGE_INSERT_AFTER = """  if (debug) {
    debugTrace.push(
      "── 鉴权 & 路由 ──",
      `│ auth: cmdAuthorized=${String(commandAuthorized)} senderAllowed=${String(senderAllowedForCommands)}`,
    );
  }

"""


def patch_schema(schema_path: Path) -> bool:
    content = schema_path.read_text(encoding="utf-8")
    changed = False

    malformed_block = """const weixinAccountSchema = z.object({
  name: z.string().optional(),
  enabled: z.boolean().optional(),
  baseUrl: z.string().default(DEFAULT_BASE_URL),
  cdnBaseUrl: z.string().default(CDN_BASE_URL),
  routeTag: z.number().optional(),
const afterglowSchema = z.object({
  enabled: z.boolean().optional(),
  bridgeUrl: z.string().default("http://127.0.0.1:8787/openclaw/event"),
  timeoutMs: z.number().int().positive().default(120000),
});

});
"""
    fixed_block = """const weixinAccountSchema = z.object({
  name: z.string().optional(),
  enabled: z.boolean().optional(),
  baseUrl: z.string().default(DEFAULT_BASE_URL),
  cdnBaseUrl: z.string().default(CDN_BASE_URL),
  routeTag: z.number().optional(),
});

const afterglowSchema = z.object({
  enabled: z.boolean().optional(),
  bridgeUrl: z.string().default("http://127.0.0.1:8787/openclaw/event"),
  timeoutMs: z.number().int().positive().default(120000),
});
"""
    if malformed_block in content:
        content = content.replace(malformed_block, fixed_block)
        changed = True

    if "const afterglowSchema" not in content:
        end_marker = '});\n\n/** Top-level weixin config schema (token is stored in credentials file, not config). */\n'
        end = content.find(end_marker)
        if end == -1:
            raise RuntimeError(f"无法定位 schema 插入点：{schema_path}")
        insert_pos = end
        content = content[:insert_pos] + SCHEMA_INSERT + content[insert_pos:]
        changed = True

    if "afterglow: afterglowSchema.optional()" not in content:
        if SCHEMA_REPLACE_FROM not in content:
            raise RuntimeError(f"无法定位 schema 替换块：{schema_path}")
        content = content.replace(SCHEMA_REPLACE_FROM, SCHEMA_REPLACE_TO)
        changed = True

    if changed:
        schema_path.write_text(content, encoding="utf-8")
    return changed


def patch_process_message(process_message_path: Path) -> bool:
    content = process_message_path.read_text(encoding="utf-8")
    changed = False

    if "type AfterglowBridgeConfig" not in content:
        anchor = 'const MEDIA_OUTBOUND_TEMP_DIR = path.join(resolvePreferredOpenClawTmpDir(), "weixin/media/outbound-temp");\n'
        if anchor not in content:
            raise RuntimeError(f"无法定位 helper 插入点：{process_message_path}")
        content = content.replace(anchor, anchor + "\n" + HELPER_INSERT)
        changed = True

    if "function pickFirstNonEmptyText" not in content:
        helper_anchor = """function resolveAfterglowBridgeConfig(
  config: import("openclaw/plugin-sdk/core").OpenClawConfig,
): AfterglowBridgeConfig | null {
"""
        if helper_anchor not in content:
            raise RuntimeError(f"无法定位 helper 升级插入点：{process_message_path}")
        helper_prefix = """function pickFirstNonEmptyText(...values: unknown[]): string {
  for (const value of values) {
    if (value == null) {
      continue;
    }
    const text = String(value).trim();
    if (text) {
      return text;
    }
  }
  return "";
}

"""
        content = content.replace(helper_anchor, helper_prefix + helper_anchor)
        changed = True

    if "const afterglowBridge = resolveAfterglowBridgeConfig(deps.config);" not in content:
        if BRIDGE_INSERT_AFTER not in content:
            raise RuntimeError(f"无法定位 bridge 插入点：{process_message_path}")
        content = content.replace(BRIDGE_INSERT_AFTER, BRIDGE_INSERT_AFTER + BRIDGE_BLOCK)
        changed = True

    if "const conversationId = pickFirstNonEmptyText(" not in content:
        request_anchor = "    const response = await fetch(params.config.bridgeUrl, {\n"
        request_prefix = """    const conversationId = pickFirstNonEmptyText(
      params.message.session_id,
      params.message.from_user_id,
    );
    const sessionId = pickFirstNonEmptyText(params.message.session_id);
    const senderId = pickFirstNonEmptyText(params.message.from_user_id);
"""
        if request_anchor not in content:
            raise RuntimeError(f"无法定位 request 升级插入点：{process_message_path}")
        content = content.replace(request_anchor, request_prefix + request_anchor)
        changed = True

    buggy_payload_block = """      body: JSON.stringify({
        conversation_id: params.message.session_id ?? params.message.from_user_id ?? "",
        session_id: params.message.session_id ?? "",
        sender_id: params.message.from_user_id ?? "",
        message_type: "text",
        text: params.text,
        timestamp: params.message.create_time_ms ?? Date.now(),
        event_id: String(params.message.message_id ?? ""),
        account_id: params.accountId,
        channel: "openclaw-weixin",
      }),
"""
    fixed_payload_block = """      body: JSON.stringify({
        conversation_id: conversationId,
        session_id: sessionId,
        sender_id: senderId,
        message_type: "text",
        text: params.text,
        timestamp: params.message.create_time_ms ?? Date.now(),
        event_id: String(params.message.message_id ?? ""),
        account_id: params.accountId,
        channel: "openclaw-weixin",
      }),
"""
    if buggy_payload_block in content:
        content = content.replace(buggy_payload_block, fixed_payload_block)
        changed = True

    if changed:
        process_message_path.write_text(content, encoding="utf-8")
    return changed


def patch_openclaw_config(config_path: Path, bridge_url: str, timeout_ms: int) -> bool:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    changed = False

    plugins = payload.setdefault("plugins", {})
    allow = plugins.setdefault("allow", [])
    if "openclaw-weixin" not in allow:
        allow.append("openclaw-weixin")
        changed = True

    channels = payload.setdefault("channels", {})
    weixin = channels.setdefault("openclaw-weixin", {})
    afterglow = weixin.get("afterglow")
    expected = {
        "enabled": True,
        "bridgeUrl": bridge_url,
        "timeoutMs": timeout_ms,
    }
    if afterglow != expected:
        weixin["afterglow"] = expected
        changed = True

    session_cfg = payload.setdefault("session", {})
    if session_cfg.get("dmScope") != "per-account-channel-peer":
        session_cfg["dmScope"] = "per-account-channel-peer"
        changed = True

    if changed:
        config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="补丁 OpenClaw 微信插件，让消息直连 afterglow serve。")
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE_URL, help="afterglow serve 事件入口。")
    parser.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS, help="桥接超时时间。")
    parser.add_argument("--openclaw-root", default=str(Path.home() / ".openclaw"), help="OpenClaw 根目录。")
    return parser


def main() -> int:
    args = build_parser().parse_args()

    root = Path(args.openclaw_root).expanduser().resolve()
    plugin_dir = root / "extensions" / "openclaw-weixin"
    schema_path = plugin_dir / "src" / "config" / "config-schema.ts"
    process_message_path = plugin_dir / "src" / "messaging" / "process-message.ts"
    config_path = root / "openclaw.json"

    missing = [str(path) for path in (schema_path, process_message_path, config_path) if not path.exists()]
    if missing:
        raise FileNotFoundError(f"缺少必要文件：{', '.join(missing)}")

    schema_changed = patch_schema(schema_path)
    process_changed = patch_process_message(process_message_path)
    config_changed = patch_openclaw_config(config_path, args.bridge_url, args.timeout_ms)

    print(f"schema_changed={schema_changed}")
    print(f"process_changed={process_changed}")
    print(f"config_changed={config_changed}")
    print(f"bridge_url={args.bridge_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
