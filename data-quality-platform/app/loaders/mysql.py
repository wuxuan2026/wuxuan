"""MySQL 数据加载器。

两种用法：

1) 单表：spec = "table_name"，从默认连接读
2) 指定连接：spec = "connection_name/table_name"
3) 完整 URL：spec = "mysql://user:pass@host:port/db?table=table_name"

连接信息从环境变量读取（MYSQL_<NAME>_HOST/USER/PASSWORD/PORT/DB）。
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

# 连接名白名单（推荐显式声明允许的连接，避免环境变量泄露给攻击者）
# 在 .env 里用 MYSQL_ALLOWED_CONNECTIONS=conn1,conn2 配置；
# 留空表示允许任意环境变量驱动的连接（开发模式）。
_ALLOWED_CONNECTIONS: set[str] | None = None


def _get_allowed_connections() -> set[str]:
    """从环境变量读白名单。None = 不限制。"""
    global _ALLOWED_CONNECTIONS
    if _ALLOWED_CONNECTIONS is not None:
        return _ALLOWED_CONNECTIONS
    raw = os.environ.get("MYSQL_ALLOWED_CONNECTIONS", "").strip()
    if not raw:
        _ALLOWED_CONNECTIONS = set()  # 空集 = 无白名单
    else:
        _ALLOWED_CONNECTIONS = {n.strip() for n in raw.split(",") if n.strip()}
    return _ALLOWED_CONNECTIONS


# 表名合法性（防 SQL 注入白名单）
_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_table_name(table: str) -> None:
    if not _TABLE_NAME_RE.match(table):
        raise ValueError(f"非法表名 {table!r}（只允许字母数字下划线）")


def _resolve_connection(conn_name: str | None) -> dict[str, Any]:
    """从环境变量读取连接参数。

    期望格式：
        MYSQL_<NAME>_HOST
        MYSQL_<NAME>_PORT (可选, 默认 3306)
        MYSQL_<NAME>_USER
        MYSQL_<NAME>_PASSWORD
        MYSQL_<NAME>_DATABASE
    """
    if conn_name is None:
        conn_name = "DEFAULT"
    prefix = f"MYSQL_{conn_name.upper()}"
    cfg = {
        "host": os.environ.get(f"{prefix}_HOST"),
        "port": int(os.environ.get(f"{prefix}_PORT", "3306")),
        "user": os.environ.get(f"{prefix}_USER"),
        "password": os.environ.get(f"{prefix}_PASSWORD", ""),
        "database": os.environ.get(f"{prefix}_DATABASE"),
    }
    missing = [k for k in ("host", "user", "database") if not cfg[k]]
    if missing:
        raise ValueError(
            f"连接 {conn_name!r} 缺少环境变量: {prefix}_{', '.join(m.upper() for m in missing)}"
        )
    return cfg


def build_mysql_url(conn_name: str | None = None) -> str:
    """构造 SQLAlchemy 用的 MySQL URL（无查询字符串）。"""
    cfg = _resolve_connection(conn_name)
    user = quote_plus(cfg["user"])
    pwd = quote_plus(cfg["password"])
    host = cfg["host"]
    port = cfg["port"]
    db = cfg["database"]
    return f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}"


def list_connections() -> list[dict[str, Any]]:
    """列出所有已配置的 MySQL 连接。

    返回 [{name, host, port, database}, ...]
    """
    allowed = _get_allowed_connections()
    names: set[str] = set(allowed)
    # 也扫描环境变量 MYSQL_<NAME>_HOST 自动发现
    for k in os.environ:
        if k.endswith("_HOST") and k.startswith("MYSQL_"):
            prefix = k[len("MYSQL_"):-len("_HOST")]
            if prefix:
                names.add(prefix)
    out: list[dict[str, Any]] = []
    for name in sorted(names):
        try:
            cfg = _resolve_connection(name)
            out.append({
                "name": name,
                "host": cfg["host"],
                "port": cfg["port"],
                "database": cfg["database"],
            })
        except ValueError:
            continue
    return out


def list_tables(conn_name: str | None = None) -> list[str]:
    """列出某连接下的所有表名（调用方应该限制权限范围）。"""
    url = build_mysql_url(conn_name)
    engine = create_engine(url, future=True)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SHOW TABLES")).fetchall()
            return [r[0] for r in rows]
    finally:
        engine.dispose()


class MysqlLoader:
    """MySQL 表加载器。

    spec 格式：
      - "table_name"                  → 默认连接 + 表
      - "connection_name/table_name"  → 指定连接 + 表
      - "mysql://..."                 → 完整 URL（含 host/db 等）
    query 参数（可选 dict）：额外 WHERE 条件 {col: value}，全部等值匹配
    limit 参数（可选 int）：最多返回行数（默认不限）
    """

    def __init__(self, query: dict[str, Any] | None = None, limit: int | None = None) -> None:
        self.query = query or {}
        self.limit = limit

    def load(self, spec: str | Path) -> pd.DataFrame:
        """读 MySQL 表到 DataFrame。"""
        spec = str(spec)
        conn_name, table, is_url = self._parse_spec(spec)

        # 白名单校验（必须在连接之前）
        allowed = _get_allowed_connections()
        # None 表示用默认连接 → 当白名单包含 DEFAULT（或 'DEFAULT' 名称）时通过
        if allowed:
            effective = conn_name or "DEFAULT"
            if effective not in allowed:
                raise PermissionError(
                    f"连接 {effective!r} 不在白名单。允许：{sorted(allowed)}"
                )

        # 现在构造 URL（如果 env 没配会抛 ValueError）
        if is_url:
            url = spec if spec.startswith("mysql+pymysql://") else spec.replace("mysql://", "mysql+pymysql://", 1)
        else:
            url = build_mysql_url(conn_name)

        _validate_table_name(table)

        engine = create_engine(url, future=True)
        try:
            return self._read(engine, table)
        finally:
            engine.dispose()

    def _parse_spec(self, spec: str) -> tuple[str | None, str, bool]:
        """解析 spec 为 (connection_name, table_name, is_url)。

        is_url=True 时 load() 用 spec 自己构造 SQLAlchemy URL；
        否则用 build_mysql_url(conn_name)。
        """
        # 完整 URL
        if spec.startswith("mysql://") or spec.startswith("mysql+pymysql://"):
            # 从 URL 提取表名（?table=xxx）
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(spec).query)
            table = qs.get("table", [""])[0]
            if not table:
                raise ValueError("URL 中必须指定 ?table=table_name")
            return None, table, True

        # connection/table 或单独 table
        if "/" in spec:
            conn_part, table = spec.split("/", 1)
        else:
            conn_part = None
            table = spec
        conn_name = conn_part if conn_part else None
        return conn_name, table, False

    def _read(self, engine: Engine, table: str) -> pd.DataFrame:
        # 构造 SQL
        sql = f"SELECT * FROM `{table}`"
        params: dict[str, Any] = {}
        if self.query:
            where_parts = []
            for k, v in self.query.items():
                _validate_table_name(k)
                ph = f":p_{k}"
                where_parts.append(f"`{k}` = {ph}")
                params[f"p_{k}"] = v
            if where_parts:
                sql += " WHERE " + " AND ".join(where_parts)
        sql += " LIMIT :lim" if self.limit else ""
        if self.limit is not None:
            params["lim"] = int(self.limit)

        log.info("MySQL 执行: %s | params=%s", sql, {k: v for k, v in params.items() if k != "password"})
        # 强制全部读为字符串（与 CSV/Excel 加载器一致，避免意外类型推断）
        with engine.connect() as conn:
            df = pd.read_sql(text(sql), conn, params=params)
        return df.astype(str)
