"""中文标签：type / severity 中文展示 + 权重列。"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _run_and_get_report():
    from app.services.check_service import CheckService
    svc = CheckService()
    return svc.run_for_dataset("orders")


def _decode(resp) -> str:
    """TestClient resp.text 默认 latin-1 解码，中文会乱码。统一用 utf-8。"""
    return resp.content.decode("utf-8")


def test_rule_result_has_type_field():
    """RuleResult 必须带 type（runner 会从 rule 拷贝过来）。"""
    r = _run_and_get_report()
    for x in r["results"]:
        assert "type" in x, f"{x['rule_id']} 缺少 type"
        assert isinstance(x["type"], str)
        assert x["type"], f"{x['rule_id']} type 为空"


def test_rulesets_page_shows_chinese_type_and_severity():
    c = TestClient(app)
    resp = c.get("/rulesets")
    assert resp.status_code == 200
    text = _decode(resp)
    assert "非空检查" in text
    assert "无重复" in text or "求和校验" in text
    assert "阻断" in text or "主要" in text or "次要" in text
    assert "×3" in text or "×2" in text or "×1" in text


def test_report_page_shows_chinese_type():
    r = _run_and_get_report()
    c = TestClient(app)
    resp = c.get(f"/report/{r['id']}")
    assert resp.status_code == 200
    text = _decode(resp)
    # 报告里至少一种类型中文（orders 里有 not_null / sum_check 等）
    for label in ("非空检查", "求和校验", "正则匹配", "枚举值", "类型检查", "外键引用"):
        assert label in text, f"报告页缺少类型中文标签: {label}"
    # 严重等级：orders_rules.yaml 里只有 blocker 和 major
    assert "阻断" in text, "报告页缺少严重等级中文标签: 阻断"
    assert "主要" in text, "报告页缺少严重等级中文标签: 主要"


def test_report_page_shows_weight_column():
    r = _run_and_get_report()
    c = TestClient(app)
    resp = c.get(f"/report/{r['id']}")
    text = _decode(resp)
    assert "×3" in text
    assert "×2" in text


def test_report_page_shows_type_column_header():
    r = _run_and_get_report()
    c = TestClient(app)
    resp = c.get(f"/report/{r['id']}")
    text = _decode(resp)
    assert "类型" in text


def test_ruleset_edit_page_has_type_field():
    c = TestClient(app)
    resp = c.get("/rulesets/orders/edit")
    assert resp.status_code == 200
    text = _decode(resp)
    assert "类型" in text


def test_chinese_labels_have_full_coverage():
    """RULE_TYPE_LABELS 应覆盖所有已注册类型（防御未来漏配）。"""
    from app.config import RULE_TYPE_LABELS
    from app.engine import REGISTRY
    registered = set(REGISTRY.keys())
    labeled = set(RULE_TYPE_LABELS.keys())
    missing = registered - labeled
    assert not missing, f"未配中文标签的规则类型: {missing}"


def test_severity_labels_have_full_coverage():
    from app.config import SEVERITY_LABELS, SEVERITY_WEIGHTS
    assert set(SEVERITY_LABELS.keys()) == set(SEVERITY_WEIGHTS.keys())


def test_rule_type_persists_in_db():
    """DB 必须持久化 type，否则刷新页面就丢了。"""
    from app.database import SessionLocal, RuleResultRow
    r = _run_and_get_report()
    with SessionLocal() as s:
        rows = s.query(RuleResultRow).filter_by(run_id=r["id"]).all()
        assert len(rows) == 14
        for row in rows:
            assert row.type, f"{row.rule_id} 在 DB 里 type 为空"