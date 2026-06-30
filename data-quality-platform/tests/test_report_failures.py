"""报告页失败数据展示。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.check_service import CheckService


def _decode(resp) -> str:
    return resp.content.decode("utf-8")


def test_report_page_has_failure_detail_section():
    svc = CheckService()
    r = svc.run_for_dataset("orders")
    c = TestClient(app)
    resp = c.get(f"/report/{r['id']}")
    text = _decode(resp)
    assert "失败数据明细" in text
    assert "失败样本" in text


def test_report_page_shows_sample_rows():
    svc = CheckService()
    r = svc.run_for_dataset("orders")
    c = TestClient(app)
    resp = c.get(f"/report/{r['id']}")
    text = _decode(resp)
    # 至少能看到行号
    assert "行号" in text
    # 失败规则 ord_001 的样本里有 order_id 空值
    assert "（空）" in text


def test_report_page_toggle_button_present():
    svc = CheckService()
    r = svc.run_for_dataset("orders")
    c = TestClient(app)
    resp = c.get(f"/report/{r['id']}")
    text = _decode(resp)
    assert "展开样本" in text


def test_failed_rules_have_red_border():
    """失败行有 row-fail / row-error class。"""
    svc = CheckService()
    r = svc.run_for_dataset("orders")
    assert any(x["failed"] > 0 for x in r["results"])
    c = TestClient(app)
    resp = c.get(f"/report/{r['id']}")
    text = _decode(resp)
    assert "row-fail" in text or "row-error" in text


def test_sample_table_has_columns():
    """失败样本表头包含涉及的列名。"""
    svc = CheckService()
    r = svc.run_for_dataset("orders")
    c = TestClient(app)
    resp = c.get(f"/report/{r['id']}")
    text = _decode(resp)
    # ord_001 失败样本列是 order_id
    assert "order_id" in text
    # ord_006 失败样本列是 customer_email
    assert "customer_email" in text