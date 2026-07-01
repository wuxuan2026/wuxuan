"""MySQL 数据源「查看库表」页面 + 表预览。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """让 mysql_config_service 用临时文件。"""
    import app.services.mysql_config_service as svc
    monkeypatch.setattr(svc, "CONFIG_PATH", tmp_path / "mysql.yaml")
    monkeypatch.setattr(svc, "SECRET_KEY_PATH", tmp_path / ".key")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    return svc


def _setup_conn(svc, name="BI", host="h", user="u", password="p", database="d"):
    svc.upsert_connection(name=name, host=host, user=user, password=password, database=database)


# ----------------- 路由 -----------------


def test_tables_page_lists_tables(isolated_config, monkeypatch):
    _setup_conn(isolated_config)
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    # mock list_tables：函数在路由里被延迟 import，patch 路径要在 module 路径
    fake_module = MagicMock()
    fake_module.list_tables.return_value = [
        {"name": "orders", "comment": "订单表", "engine": "InnoDB"},
        {"name": "customers", "comment": "客户维度", "engine": "InnoDB"},
        {"name": "arrivals", "comment": "", "engine": "InnoDB"},
    ]
    with patch.dict("sys.modules", {"app.loaders.mysql": fake_module}):
        r = c.get("/mysql/connections/BI/tables")
    assert r.status_code == 200
    text = r.content.decode("utf-8")
    assert "orders" in text
    assert "customers" in text
    assert "arrivals" in text
    # 注释名也必须展示
    assert "订单表" in text
    assert "客户维度" in text
    assert "共" in text and "3" in text  # 共 3 张表


def test_tables_page_unknown_connection(isolated_config):
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.get("/mysql/connections/NOSUCH/tables", follow_redirects=False)
    assert r.status_code == 303
    assert "error=not_found" in r.headers["location"]


def test_tables_page_shows_error_when_unreachable(isolated_config):
    _setup_conn(isolated_config)
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    fake_module = MagicMock()
    fake_module.list_tables.side_effect = Exception("timeout")
    with patch.dict("sys.modules", {"app.loaders.mysql": fake_module}):
        r = c.get("/mysql/connections/BI/tables")
    assert r.status_code == 200
    text = r.content.decode("utf-8")
    assert "无法读取表列表" in text
    assert "timeout" in text


def test_tables_page_empty_database(isolated_config):
    _setup_conn(isolated_config)
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    fake_module = MagicMock()
    fake_module.list_tables.return_value = []
    with patch.dict("sys.modules", {"app.loaders.mysql": fake_module}):
        r = c.get("/mysql/connections/BI/tables")
    text = r.content.decode("utf-8")
    assert "没有表" in text


# ----------------- 表预览 -----------------


def test_table_preview_shows_rows(isolated_config):
    _setup_conn(isolated_config)
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    df = pd.DataFrame({"order_id": ["A1", "A2"], "amount": ["100", "200"], "status": ["paid", "pending"]})
    fake_loader = MagicMock()
    fake_loader.return_value.load.return_value = df
    with patch.dict("sys.modules", {"app.loaders.mysql": MagicMock(MysqlLoader=fake_loader)}):
        r = c.get("/mysql/connections/BI/tables/orders")
    assert r.status_code == 200
    text = r.content.decode("utf-8")
    assert "A1" in text
    assert "100" in text
    assert "paid" in text
    assert "order_id" in text
    assert "amount" in text


def test_table_preview_rejects_invalid_name(isolated_config):
    _setup_conn(isolated_config)
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.get("/mysql/connections/BI/tables/users;--DROP", follow_redirects=False)
    # 非法表名 → 重定向回表列表（带 bad_table）
    assert r.status_code == 303


def test_table_preview_unknown_table_load_failure(isolated_config):
    """表名合法但读不到（权限不足等）。"""
    _setup_conn(isolated_config)
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    fake_loader = MagicMock()
    fake_loader.return_value.load.side_effect = Exception("Access denied")
    with patch.dict("sys.modules", {"app.loaders.mysql": MagicMock(MysqlLoader=fake_loader)}):
        r = c.get("/mysql/connections/BI/tables/orders")
    assert r.status_code == 200
    text = r.content.decode("utf-8")
    assert "无法读取表数据" in text


def test_table_preview_unknown_connection(isolated_config):
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.get("/mysql/connections/MISSING/tables/orders", follow_redirects=False)
    assert r.status_code == 303
    assert "error=not_found" in r.headers["location"]


def test_table_preview_link_to_upload(isolated_config):
    """预览页有「用此表检测」跳转到 /upload 的链接。"""
    _setup_conn(isolated_config)
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    df = pd.DataFrame({"id": ["1"]})
    fake_loader = MagicMock()
    fake_loader.return_value.load.return_value = df
    with patch.dict("sys.modules", {"app.loaders.mysql": MagicMock(MysqlLoader=fake_loader)}):
        r = c.get("/mysql/connections/BI/tables/orders")
    text = r.content.decode("utf-8")
    assert "用此表检测" in text
    assert "/upload" in text