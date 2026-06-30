"""MySQL 连接配置的 CRUD 持久化 + 密码加密。

存储文件：data/mysql_connections.yaml

格式：
  connections:
    - name: DEFAULT
      host: 127.0.0.1
      port: 3306
      user: root
      password: gAAAAA...   # Fernet 加密后的密文
      database: mydb
    - name: BI
      ...
"""
from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import yaml
from cryptography.fernet import Fernet, InvalidToken

# 存储文件路径（独立于 .env，便于 UI 编辑）
CONFIG_PATH = Path("data/mysql_connections.yaml")
SECRET_KEY_PATH = Path("data/.secret_key")


def _get_or_create_fernet() -> Fernet:
    """从 .env SECRET_KEY 读密钥；没设就生成并保存到 data/.secret_key。"""
    env_key = os.environ.get("SECRET_KEY", "").strip()
    if env_key:
        # SECRET_KEY 必须以 "base64:" 开头或为原始 base64 字符串
        if env_key.startswith("base64:"):
            key = env_key[len("base64:"):].encode("utf-8")
        else:
            key = env_key.encode("utf-8")
        try:
            return Fernet(key)
        except (ValueError, TypeError) as e:
            raise RuntimeError(
                f"SECRET_KEY 无效（需 base64 字符串或 base64:xxx）：{e}"
            ) from e
    # 没设 → 用持久化文件
    SECRET_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SECRET_KEY_PATH.exists():
        key = SECRET_KEY_PATH.read_bytes()
    else:
        key = Fernet.generate_key()
        SECRET_KEY_PATH.write_bytes(key)
    return Fernet(key)


def encrypt_password(plain: str) -> str:
    """明文 → 密文（base64 字符串）。"""
    if not plain:
        return ""
    f = _get_or_create_fernet()
    return f.encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_password(cipher: str) -> str:
    """密文 → 明文。失败时返回空（容错）。"""
    if not cipher:
        return ""
    try:
        f = _get_or_create_fernet()
        return f.decrypt(cipher.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


# --------------------- CRUD ---------------------


def _load() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {"connections": []}
    try:
        data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
        if "connections" not in data:
            data["connections"] = []
        return data
    except yaml.YAMLError:
        return {"connections": []}


def _save(data: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    # password 字段已经是密文，直接 dump
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )


def list_connections_with_secret() -> list[dict[str, Any]]:
    """列出所有连接（密码是密文）。用于内部存储/审计。"""
    return _load().get("connections", [])


def list_connections_masked() -> list[dict[str, Any]]:
    """列出所有连接（密码掩码为 ******）。用于 UI 展示。"""
    out = []
    for c in _load().get("connections", []):
        item = dict(c)
        if item.get("password"):
            item["password"] = "******"  # 永远不返回明文到前端
        item.setdefault("source", "yaml")
        out.append(item)
    return out


def get_connection(name: str) -> dict[str, Any] | None:
    for c in _load().get("connections", []):
        if c.get("name") == name:
            return c
    return None


def upsert_connection(
    name: str,
    host: str,
    user: str,
    password: str,
    database: str,
    port: int = 3306,
) -> None:
    """新增或更新连接。如果 password 是 "******" 则保留原密码。"""
    data = _load()
    conns = data["connections"]
    cipher = ""  # 默认空
    if password and password != "******":
        cipher = encrypt_password(password)
    else:
        # 保留原密码
        existing = next((c for c in conns if c.get("name") == name), None)
        if existing:
            cipher = existing.get("password", "")

    new_entry = {
        "name": name,
        "host": host,
        "port": int(port) if port else 3306,
        "user": user,
        "password": cipher,
        "database": database,
    }
    replaced = False
    for i, c in enumerate(conns):
        if c.get("name") == name:
            conns[i] = new_entry
            replaced = True
            break
    if not replaced:
        conns.append(new_entry)
    _save(data)


def delete_connection(name: str) -> bool:
    data = _load()
    conns = data["connections"]
    new_list = [c for c in conns if c.get("name") != name]
    if len(new_list) == len(conns):
        return False
    data["connections"] = new_list
    _save(data)
    return True


def test_connection(name: str) -> dict[str, Any]:
    """尝试实际连接数据库，验证配置是否正确。"""
    from sqlalchemy import create_engine, text
    cfg = get_connection(name)
    if not cfg:
        return {"ok": False, "error": f"连接 {name!r} 不存在"}
    plain = decrypt_password(cfg.get("password", ""))
    user = cfg.get("user", "")
    pwd = plain
    user_enc = quote(user)
    pwd_enc = quote(pwd)
    url = f"mysql+pymysql://{user_enc}:{pwd_enc}@{cfg['host']}:{cfg['port']}/{cfg['database']}"
    try:
        engine = create_engine(url, future=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1")).fetchone()
        engine.dispose()
        return {"ok": True, "host": cfg["host"], "database": cfg["database"]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def quote(s: str) -> str:
    from urllib.parse import quote as _quote
    return _quote(s, safe="")


# 让 loader 优先读 yaml 配置，再 fallback 环境变量
def get_connection_for_loader(name: str | None) -> dict[str, Any]:
    """loader 用的接口：先查 yaml，没有再读 env。返回明文密码。"""
    yaml_name = name or "DEFAULT"
    cfg = get_connection(yaml_name)
    if cfg:
        return {
            "host": cfg["host"],
            "port": cfg.get("port", 3306),
            "user": cfg["user"],
            "password": decrypt_password(cfg.get("password", "")),
            "database": cfg["database"],
        }
    # fallback 环境变量
    from app.loaders.mysql import _resolve_connection
    return _resolve_connection(name)