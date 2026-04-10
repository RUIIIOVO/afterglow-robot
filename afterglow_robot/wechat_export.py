from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from pathlib import Path

from .models import NormalizedMessage

"""微信导出目录访问与聊天提取。"""

LOGGER = logging.getLogger(__name__)


def compute_message_table_name(wxid: str) -> str:
    """按 WeChatDataAnalysis 的规则计算消息分表名。"""

    digest = hashlib.md5(wxid.encode("utf-8")).hexdigest()
    return f"Msg_{digest}"


def ensure_directory(path: Path) -> None:
    """确保目标目录存在。"""

    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: object) -> None:
    """将结构化数据写入 JSON 文件。"""

    ensure_directory(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    """将多行记录写入 JSONL 文件。"""

    ensure_directory(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def resolve_account_wxid(export_dir: Path, account_wxid: str | None = None) -> str:
    """解析导出目录中的账号 wxid。"""

    databases_dir = export_dir / "databases"
    if not databases_dir.exists():
        raise FileNotFoundError(f"未找到数据库目录：{databases_dir}")

    account_dirs = sorted(
        item.name for item in databases_dir.iterdir() if item.is_dir()
    )
    if account_wxid:
        if account_wxid not in account_dirs:
            raise ValueError(f"未找到账号目录：{account_wxid}")
        return account_wxid
    if len(account_dirs) == 1:
        return account_dirs[0]
    raise ValueError("检测到多个账号目录，请显式传入 account_wxid。")


def account_database_dir(export_dir: Path, account_wxid: str) -> Path:
    """返回指定账号的数据库目录。"""

    path = export_dir / "databases" / account_wxid
    if not path.exists():
        raise FileNotFoundError(f"未找到账号数据库目录：{path}")
    return path


def discover_contacts(export_dir: Path, account_wxid: str | None = None) -> tuple[str, list[dict[str, object]]]:
    """读取联系人库，输出供 CLI 直接展示的联系人列表。"""

    resolved_account = resolve_account_wxid(export_dir, account_wxid)
    contact_db = account_database_dir(export_dir, resolved_account) / "contact.db"
    if not contact_db.exists():
        raise FileNotFoundError(f"未找到联系人数据库：{contact_db}")

    query = """
        SELECT username, alias, remark, nick_name
        FROM Contact
        WHERE username IS NOT NULL AND username != ''
        ORDER BY COALESCE(NULLIF(remark, ''), NULLIF(nick_name, ''), NULLIF(alias, ''), username)
    """
    connection = sqlite3.connect(contact_db)
    try:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query).fetchall()
    finally:
        connection.close()

    contacts: list[dict[str, object]] = []
    for row in rows:
        remark = (row["remark"] or "").strip()
        nickname = (row["nick_name"] or "").strip()
        alias = (row["alias"] or "").strip()
        username = row["username"]
        display_name = remark or nickname or alias or username
        contacts.append(
            {
                "account_wxid": resolved_account,
                "username": username,
                "alias": alias,
                "remark": remark,
                "nick_name": nickname,
                "display_name": display_name,
            }
        )
    return resolved_account, contacts


def _lookup_name2id(connection: sqlite3.Connection, username: str) -> int | None:
    """从当前消息库的 Name2ID 表中定位用户行号。"""

    row = connection.execute(
        "SELECT rowid FROM Name2ID WHERE user_name = ? LIMIT 1",
        (username,),
    ).fetchone()
    if row is None:
        return None
    return int(row[0])


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    """检查当前数据库是否包含指定分表。"""

    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def _clean_text(raw_text: str) -> str:
    """做最小必要的文本清洗，保持原始表达风格。"""

    return raw_text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _resolve_target_name(contacts: list[dict[str, object]], target_wxid: str) -> str:
    """优先用备注名，其次昵称/别名，作为展示名称。"""

    for contact in contacts:
        if contact["username"] == target_wxid:
            return str(contact["display_name"])
    return target_wxid


def extract_chat_messages(
    export_dir: Path,
    account_wxid: str,
    target_wxid: str,
) -> list[NormalizedMessage]:
    """按账号与目标联系人提取规范化文本消息。"""

    _, contacts = discover_contacts(export_dir, account_wxid)
    target_name = _resolve_target_name(contacts, target_wxid)
    account_dir = account_database_dir(export_dir, account_wxid)
    table_name = compute_message_table_name(target_wxid)
    messages: list[NormalizedMessage] = []

    for message_db in sorted(account_dir.glob("message_*.db")):
        connection = sqlite3.connect(message_db)
        try:
            connection.row_factory = sqlite3.Row
            if not _table_exists(connection, table_name):
                LOGGER.debug("数据库 %s 不包含表 %s，跳过。", message_db.name, table_name)
                continue

            self_sender_id = _lookup_name2id(connection, account_wxid)
            target_sender_id = _lookup_name2id(connection, target_wxid)
            if target_sender_id is None:
                LOGGER.debug("数据库 %s 中未找到目标联系人 %s。", message_db.name, target_wxid)
                continue

            query = f"""
                SELECT local_id, create_time, real_sender_id, local_type, message_content
                FROM {table_name}
                ORDER BY create_time ASC, local_id ASC
            """
            rows = connection.execute(query).fetchall()
            for row in rows:
                sender_id = int(row["real_sender_id"])
                # 发送方映射依赖各个 message_*.db 自己的 Name2ID，
                # 不能跨库复用固定 rowid。
                if self_sender_id is not None and sender_id == self_sender_id:
                    sender_role = "self"
                elif sender_id == target_sender_id:
                    sender_role = "target"
                elif sender_id == 1 and self_sender_id is None:
                    sender_role = "self"
                else:
                    sender_role = "other"

                if sender_role == "other":
                    continue
                # 第一阶段只接直接可读的文本消息，其他类型后续再扩展。
                if row["local_type"] != 1:
                    continue

                message_content = row["message_content"]
                if not isinstance(message_content, str):
                    continue

                text = _clean_text(message_content)
                if not text:
                    continue

                messages.append(
                    NormalizedMessage(
                        account_wxid=account_wxid,
                        target_wxid=target_wxid,
                        target_name=target_name,
                        message_id=f"{message_db.stem}:{table_name}:{row['local_id']}",
                        timestamp=int(row["create_time"]),
                        sender_role=sender_role,
                        message_type="text",
                        text=text,
                        local_type=int(row["local_type"]),
                        source_db=message_db.name,
                        source_table=table_name,
                    )
                )
        finally:
            connection.close()

    messages.sort(key=lambda item: (item.timestamp, item.message_id))
    return messages
