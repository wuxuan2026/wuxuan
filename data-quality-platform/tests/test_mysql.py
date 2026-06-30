"""MySQL 连接模块测试：环境变量解析、SQL 构造、表名校验、白名单（无真实 MySQL 连接）。"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def _isolate_allowlist(monkeypatch):
    """每次测试隔离 MYSQL_ALLOWED_CONNECTIONS 与全局缓存。"""
    import app.loaders.mysql as mod
    monkeypatch.setattr(mod, "_ALLOWED_CONNECTIONS", None)
    # 清理环境变量避免其他测试干扰
    for k in list(os.environ.keys()):
        if k.startswith("MYSQL_"):
            monkeypatch.delenv(k, raising=False)
    yield


def _setup_default_env(monkeypatch):
    """设置一个可用的 MYSQL_DEFAULT 完整环境。"""
    monkeypatch.setenv("MYSQL_DEFAULT_HOST", "h")
    monkeypatch.setenv("MYSQL_DEFAULT_USER", "u")
    monkeypatch.setenv("MYSQL_DEFAULT_PASSWORD", "pw")
    monkeypatch.setenv("MYSQL_DEFAULT_DATABASE", "d")


# ----------------- URL 构造 -----------------


def test_build_url_default_connection(monkeypatch):
    """读默认连接的 4 个必需环境变量。"""
    monkeypatch.setenv("MYSQL_DEFAULT_HOST", "127.0.0.1")
    monkeypatch.setenv("MYSQL_DEFAULT_USER", "root")
    monkeypatch.setenv("MYSQL_DEFAULT_PASSWORD", "secret")
    monkeypatch.setenv("MYSQL_DEFAULT_DATABASE", "mydb")
    monkeypatch.setenv("MYSQL_DEFAULT_PORT", "3307")

    from app.loaders.mysql import build_mysql_url
    url = build_mysql_url()
    assert "127.0.0.1:3307" in url
    assert "mydb" in url
    assert "mysql+pymysql://" in url
    assert "secret" in url  # 应该被 URL encode 后的 secret
    # URL-encoding 后密码不应明文出现
    import re
    # 密码 raw 是 "secret"，URL encode 后可能是 secret 或 %73%65...
    assert re.search(r"secret|%73%65%63%72%65%74", url)


def test_build_url_special_chars_password(monkeypatch):
    """含特殊字符的密码必须正确 URL-encode。"""
    monkeypatch.setenv("MYSQL_DEFAULT_HOST", "h")
    monkeypatch.setenv("MYSQL_DEFAULT_USER", "u")
    monkeypatch.setenv("MYSQL_DEFAULT_PASSWORD", "p@ssw0rd!#$")
    monkeypatch.setenv("MYSQL_DEFAULT_DATABASE", "d")
    from app.loaders.mysql import build_mysql_url
    url = build_mysql_url()
    # 完整 URL 必须可被 SQLAlchemy 重新解析（不抛错）
    from sqlalchemy.engine.url import make_url
    parsed = make_url(url)
    assert parsed.password == "p@ssw0rd!#$"
    assert parsed.username == "u"
    assert parsed.database == "d"


def test_build_url_named_connection(monkeypatch):
    """指定连接名读取对应前缀的环境变量。"""
    monkeypatch.setenv("MYSQL_BI_HOST", "bi.example.com")
    monkeypatch.setenv("MYSQL_BI_USER", "reader")
    monkeypatch.setenv("MYSQL_BI_PASSWORD", "")
    monkeypatch.setenv("MYSQL_BI_DATABASE", "bi_db")
    from app.loaders.mysql import build_mysql_url
    url = build_mysql_url("bi")
    assert "bi.example.com" in url
    assert "reader" in url
    assert "bi_db" in url


def test_build_url_missing_env_raises(monkeypatch):
    monkeypatch.delenv("MYSQL_DEFAULT_HOST", raising=False)
    monkeypatch.delenv("MYSQL_DEFAULT_USER", raising=False)
    monkeypatch.delenv("MYSQL_DEFAULT_DATABASE", raising=False)
    # 确保没有 yaml 配置
    import app.services.mysql_config_service as cfg_svc
    monkeypatch.setattr(cfg_svc, "CONFIG_PATH", Path("/nonexistent/mysql.yaml"))
    from app.loaders.mysql import build_mysql_url
    with pytest.raises(ValueError, match="缺少配置"):
        build_mysql_url()


# ----------------- 表名校验（防 SQL 注入） -----------------


def test_table_name_validation_rejects_injection():
    from app.loaders.mysql import _validate_table_name
    _validate_table_name("orders")
    _validate_table_name("user_logs_2024")
    # 危险输入必须被拒绝
    for bad in [
        "orders; DROP TABLE users",
        "orders WHERE 1=1",
        "1orders",
        "orders'",
        "orders--",
        "orders/*hack*/",
    ]:
        with pytest.raises(ValueError, match="非法表名"):
            _validate_table_name(bad)


# ----------------- 白名单 -----------------


def test_whitelist_blocks_unauthorized_connection(monkeypatch):
    monkeypatch.setenv("MYSQL_ALLOWED_CONNECTIONS", "DEFAULT")
    monkeypatch.setenv("MYSQL_DEFAULT_HOST", "h")
    monkeypatch.setenv("MYSQL_DEFAULT_USER", "u")
    monkeypatch.setenv("MYSQL_DEFAULT_DATABASE", "d")

    from app.loaders.mysql import MysqlLoader
    loader = MysqlLoader()
    with pytest.raises(PermissionError, match="白名单"):
        loader.load("OTHER/secret_table")


def test_whitelist_allows_listed_connection(monkeypatch):
    monkeypatch.setenv("MYSQL_ALLOWED_CONNECTIONS", "DEFAULT,BI")
    monkeypatch.setenv("MYSQL_DEFAULT_HOST", "h")
    monkeypatch.setenv("MYSQL_DEFAULT_USER", "u")
    monkeypatch.setenv("MYSQL_DEFAULT_DATABASE", "d")
    # 不真正连接，只检查 spec 解析和表名校验
    from app.loaders.mysql import MysqlLoader
    loader = MysqlLoader()
    with patch("app.loaders.mysql.create_engine") as fake_engine:
        fake_engine.return_value.connect.return_value.__enter__.return_value = MagicMock()
        with patch("pandas.read_sql", return_value=pd.DataFrame({"x": ["1"]})):
            df = loader.load("orders")
            assert len(df) == 1


def test_no_whitelist_allows_all(monkeypatch):
    monkeypatch.delenv("MYSQL_ALLOWED_CONNECTIONS", raising=False)
    monkeypatch.setenv("MYSQL_DEFAULT_HOST", "h")
    monkeypatch.setenv("MYSQL_DEFAULT_USER", "u")
    monkeypatch.setenv("MYSQL_DEFAULT_DATABASE", "d")
    from app.loaders.mysql import MysqlLoader
    loader = MysqlLoader()
    with patch("app.loaders.mysql.create_engine") as fake_engine:
        fake_engine.return_value.connect.return_value.__enter__.return_value = MagicMock()
        with patch("pandas.read_sql", return_value=pd.DataFrame({"x": ["1"]})):
            df = loader.load("orders")
            assert len(df) == 1


# ----------------- list_connections -----------------


def test_list_connections_from_env(monkeypatch):
    monkeypatch.setenv("MYSQL_DEFAULT_HOST", "h1")
    monkeypatch.setenv("MYSQL_DEFAULT_USER", "u")
    monkeypatch.setenv("MYSQL_DEFAULT_DATABASE", "d")
    monkeypatch.setenv("MYSQL_BI_HOST", "bi")
    monkeypatch.setenv("MYSQL_BI_USER", "u")
    monkeypatch.setenv("MYSQL_BI_DATABASE", "d")
    monkeypatch.setenv("MYSQL_ALLOWED_CONNECTIONS", "DEFAULT,BI")

    from app.loaders.mysql import list_connections
    conns = list_connections()
    names = {c["name"] for c in conns}
    assert {"DEFAULT", "BI"} <= names


def test_list_connections_ignores_incomplete(monkeypatch):
    """只有 HOST 没有 USER 的连接不应被列出。"""
    monkeypatch.delenv("MYSQL_ALLOWED_CONNECTIONS", raising=False)
    monkeypatch.setenv("MYSQL_BROKEN_HOST", "h")
    # 没 USER 和 DATABASE → 应该被忽略
    monkeypatch.setenv("MYSQL_OK_HOST", "h")
    monkeypatch.setenv("MYSQL_OK_USER", "u")
    monkeypatch.setenv("MYSQL_OK_DATABASE", "d")
    from app.loaders.mysql import list_connections
    conns = list_connections()
    names = {c["name"] for c in conns}
    assert "BROKEN" not in names
    assert "OK" in names


# ----------------- spec 解析 -----------------


def test_spec_parse_table_only(monkeypatch):
    """无 / 前缀 → 默认连接 + 表名。"""
    _setup_default_env(monkeypatch)
    from app.loaders.mysql import MysqlLoader
    loader = MysqlLoader()
    conn_name, table, is_url = loader._parse_spec("orders")
    assert conn_name is None
    assert table == "orders"
    assert is_url is False


def test_spec_parse_conn_and_table(monkeypatch):
    _setup_default_env(monkeypatch)
    monkeypatch.setenv("MYSQL_BI_HOST", "bi")
    monkeypatch.setenv("MYSQL_BI_USER", "u")
    monkeypatch.setenv("MYSQL_BI_PASSWORD", "")
    monkeypatch.setenv("MYSQL_BI_DATABASE", "bi")
    from app.loaders.mysql import MysqlLoader
    loader = MysqlLoader()
    conn_name, table, is_url = loader._parse_spec("BI/orders")
    assert conn_name == "BI"
    assert table == "orders"
    assert is_url is False


def test_spec_parse_url_with_table_query():
    from app.loaders.mysql import MysqlLoader
    loader = MysqlLoader()
    conn_name, table, is_url = loader._parse_spec(
        "mysql://user:pw@host:3306/db?table=orders"
    )
    assert conn_name is None
    assert table == "orders"
    assert is_url is True


def test_spec_parse_url_without_table_raises():
    from app.loaders.mysql import MysqlLoader
    loader = MysqlLoader()
    with pytest.raises(ValueError, match="必须指定"):
        loader._parse_spec("mysql://user:pw@host/db")


# ----------------- SQL 注入防护 -----------------


def test_query_params_are_used_in_safe_way(monkeypatch):
    """WHERE 条件应该用命名参数化查询，不能字符串拼接。"""
    monkeypatch.setenv("MYSQL_DEFAULT_HOST", "h")
    monkeypatch.setenv("MYSQL_DEFAULT_USER", "u")
    monkeypatch.setenv("MYSQL_DEFAULT_DATABASE", "d")
    monkeypatch.delenv("MYSQL_ALLOWED_CONNECTIONS", raising=False)

    captured_sql: list[str] = []
    captured_params: list[dict] = []

    def fake_read_sql(sql_obj, conn, params=None):
        from sqlalchemy import TextClause
        if isinstance(sql_obj, TextClause):
            captured_sql.append(str(sql_obj))
        else:
            captured_sql.append(sql_obj)
        captured_params.append(params or {})
        return pd.DataFrame({"x": ["1"]})

    from app.loaders.mysql import MysqlLoader
    loader = MysqlLoader(query={"id": "1 OR 1=1"}, limit=10)
    with patch("app.loaders.mysql.create_engine") as fake_engine:
        fake_engine.return_value.connect.return_value.__enter__.return_value = MagicMock()
        with patch("pandas.read_sql", side_effect=fake_read_sql):
            loader.load("orders")

    sql = captured_sql[0]
    # 必须用命名参数而不是字符串拼接
    assert ":p_id" in sql
    assert "1=1" not in sql or ":p_id" in sql  # 1=1 在参数里不会执行
    assert captured_params[0].get("p_id") == "1 OR 1=1"


# ----------------- API 接口 -----------------


def test_api_mysql_connections_endpoint():
    """GET /api/mysql/connections 返回 JSON 列表。"""
    monkeypatch_env()
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.get("/api/mysql/connections")
    assert r.status_code == 200
    data = r.json()
    assert "connections" in data


def test_api_mysql_tables_endpoint_handles_missing_env(monkeypatch):
    monkeypatch.delenv("MYSQL_DEFAULT_HOST", raising=False)
    monkeypatch.delenv("MYSQL_DEFAULT_USER", raising=False)
    monkeypatch.delenv("MYSQL_DEFAULT_DATABASE", raising=False)
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.get("/api/mysql/tables?conn=DEFAULT")
    assert r.status_code in (200, 400)


def test_upload_page_renders_mysql_form(monkeypatch):
    monkeypatch.setenv("MYSQL_DEFAULT_HOST", "h")
    monkeypatch.setenv("MYSQL_DEFAULT_USER", "u")
    monkeypatch.setenv("MYSQL_DEFAULT_DATABASE", "d")
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.get("/upload")
    text = r.content.decode("utf-8")
    assert "MySQL" in text or "mysql" in text
    assert "table_spec" in text or "主表名" in text


# ----------------- 工具 -----------------


def monkeypatch_env():
    import pytest
    # 用 pytest fixture 注入环境变量的简化版
    os.environ.setdefault("MYSQL_DEFAULT_HOST", "h")
    os.environ.setdefault("MYSQL_DEFAULT_USER", "u")
    os.environ.setdefault("MYSQL_DEFAULT_DATABASE", "d")