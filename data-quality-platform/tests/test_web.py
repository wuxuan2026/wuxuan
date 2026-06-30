"""Web 端到端冒烟测试：用 TestClient 验证主要路由。"""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_index_renders():
    r = client.get("/")
    assert r.status_code == 200
    assert "数据质量监测平台" in r.text
    # 已注册规则类型
    assert "not_null" in r.text


def test_upload_page_renders():
    r = client.get("/upload")
    assert r.status_code == 200
    assert "orders" in r.text  # 规则集下拉


def test_rulesets_page_lists_yaml():
    r = client.get("/rulesets")
    assert r.status_code == 200
    assert "orders_rules" in r.text
    assert "type: not_null" in r.text


def test_run_check_then_report():
    """端到端：上传 CSV 后检测 → 跳转到报告页。"""
    import tempfile
    csv = (
        "order_id,customer_id,order_date,order_amount,discount,paid_amount,refund_amount,order_status,customer_email\n"
        "O000001,C00001,2026-06-29,100.0,10.0,90.0,0.0,paid,a@b.com\n"
        "O000002,C00002,2026-06-29,200.0,20.0,180.0,0.0,paid,a@b.com\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(csv)
        tmp = f.name
    try:
        with open(tmp, "rb") as fp:
            r = client.post(
                "/uploads",
                files={"file": ("orders.csv", fp, "text/csv")},
                data={"ruleset": "orders"},
                follow_redirects=False,
            )
        assert r.status_code in (302, 303)
        loc = r.headers.get("location", "")
        assert loc.startswith("/report/")
        r2 = client.get(loc)
        assert r2.status_code == 200
        assert "检测报告" in r2.text
        assert "完整性" in r2.text
        assert "规范性" in r2.text
        assert "一致性" in r2.text
        assert "时效性" in r2.text
    finally:
        import os
        os.unlink(tmp)


def test_report_unknown_id_redirects():
    r = client.get("/report/99999", follow_redirects=False)
    assert r.status_code == 200
    assert "找不到" in r.text or "检测" in r.text


def test_upload_csv_then_check():
    import tempfile, os

    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("order_id,order_amount,order_status,order_date,customer_id,customer_email,discount\n")
        f.write("X1,100,paid,2026-06-28,C00001,foo@bar.com,0\n")
        f.write("X2,50,paid,2026-06-28,C00001,not-an-email,5\n")
        csv_path = f.name

    try:
        with open(csv_path, "rb") as fp:
            r = client.post(
                "/uploads",
                files={"file": ("orders.csv", fp, "text/csv")},
                data={"ruleset": "orders_rules"},
                follow_redirects=False,
            )
        assert r.status_code in (302, 303)
        loc = r.headers.get("location", "")
        assert loc.startswith("/report/")
        r2 = client.get(loc)
        assert r2.status_code == 200
        assert "检测报告" in r2.text
    finally:
        os.unlink(csv_path)


def test_history_page_renders_after_run():
    client.post("/checks/run", data={"dataset": "orders"}, follow_redirects=False)
    r = client.get("/history")
    assert r.status_code == 200
    assert "历史记录" in r.text
    assert "orders" in r.text


def test_ruleset_edit_save_roundtrip():
    r = client.get("/rulesets/orders_rules/edit")
    assert r.status_code == 200
    assert "编辑规则集" in r.text
    r2 = client.post(
        "/rulesets/orders_rules/edit",
        data={"content": (Path("data/rulesets/orders_rules.yaml").read_text(encoding="utf-8"))},
        follow_redirects=False,
    )
    assert r2.status_code in (302, 303)