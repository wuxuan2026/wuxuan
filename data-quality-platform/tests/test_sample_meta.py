"""失败样本元信息：标识列与检测列的自动识别 + YAML 显式声明。"""
from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pandas as pd

from app.detectors.completeness import NotNullRule
from app.engine.base import ExecutionContext


def _ctx(df: pd.DataFrame) -> ExecutionContext:
    return ExecutionContext(df=df)


def test_identifier_columns_heuristic():
    """含 id 且唯一比例高的列自动识别为标识列。"""
    df = pd.DataFrame({
        "order_id": ["O001", "O002", "O003", "O004"],
        "amount": ["100", "200", "", "400"],
        "note": ["a", "b", "c", "d"],
    })
    rule = NotNullRule(id="r", dimension="completeness", columns=["amount"])
    samples, meta = rule._sample(_ctx(df), df["amount"] == "")
    assert "order_id" in meta["id_columns"]
    assert "amount" in meta["check_columns"]
    assert samples[0]["order_id"] == "O003"


def test_identifier_columns_param_override():
    """YAML 里 params.identifier 覆盖启发式。"""
    df = pd.DataFrame({
        "order_id": ["O001", "O002"],
        "customer_id": ["C001", "C002"],
        "amount": ["100", ""],
    })
    rule = NotNullRule(
        id="r", dimension="completeness", columns=["amount"],
        params={"identifier": "customer_id"},
    )
    samples, meta = rule._sample(_ctx(df), df["amount"] == "")
    assert meta["id_columns"] == ["customer_id"]
    assert samples[0]["customer_id"] == "C002"
    assert "order_id" not in samples[0]


def test_sample_includes_both_identifier_and_check_columns():
    """样本 dict 应同时包含标识列和检测列。"""
    df = pd.DataFrame({
        "order_id": ["O001", "O002"],
        "order_amount": ["100", "abc"],
    })
    rule = NotNullRule(
        id="r", dimension="completeness", columns=["order_amount"],
        params={"identifier": "order_id"},
    )
    bad = df["order_amount"] == "abc"
    samples, meta = rule._sample(_ctx(df), bad)
    assert "order_id" in samples[0]
    assert "order_amount" in samples[0]


def test_identifier_fallback_to_first_column():
    """如果没有 id 列且没显式声明，回退到第 1 个列。"""
    df = pd.DataFrame({
        "first_col": ["X1", "X2"],
        "value": ["100", ""],
    })
    rule = NotNullRule(id="r", dimension="completeness", columns=["value"])
    samples, meta = rule._sample(_ctx(df), df["value"] == "")
    # 启发式没有 id 候选 → 选用 first_col
    assert meta["id_columns"] == ["first_col"]


def test_report_failure_detail_table_header():
    """报告页「失败数据明细」应该有「唯一值」和「检测字段」列分组。"""
    import tempfile
    from app.services.check_service import CheckService
    from app.main import app as fastapi_app
    from fastapi.testclient import TestClient

    csv = (
        "order_id,order_amount,order_date,customer_id,customer_email,order_status,discount,paid_amount,refund_amount\n"
        "O001,100,2026-06-29,C001,a@b.com,paid,0,100,0\n"
        "O002,abc,not-a-date,C002,a@b.com,paid,0,100,0\n"
        "O003,200,2026-06-29,C003,not-an-email,paid,0,100,0\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(csv)
        tmp = f.name
    try:
        svc = CheckService()
        r = svc.run_for_uploaded(
            dataset="orders",
            csv_path=Path(tmp),
            ruleset_path=Path("data/rulesets/orders_rules.yaml"),
        )
        c = TestClient(fastapi_app)
        resp = c.get(f"/report/{r['id']}")
        text = resp.content.decode("utf-8")
        assert "失败数据明细" in text
        # 表头或表格项里出现「唯一值」或「标识」分组
        assert "标识列" in text or "唯一值" in text or "检测列" in text or "检测字段" in text
    finally:
        Path(tmp).unlink()


def test_meta_passes_through_runner():
    """runner 应当把 meta 透传到 RuleResult 上。"""
    df = pd.DataFrame({"order_id": ["O001", "O002"], "amount": ["100", ""]})
    from app.detectors.completeness import NotNullRule
    rule = NotNullRule(
        id="r", dimension="completeness", columns=["amount"],
        params={"identifier": "order_id"},
    )
    res = rule.evaluate(_ctx(df))
    assert hasattr(res, "sample_failures")
    # 透传 meta 应该作为 RuleResult 字段
    assert getattr(res, "sample_meta", None) is not None, (
        "RuleResult 应当带 sample_meta"
    )
    assert res.sample_meta["id_columns"] == ["order_id"]
    assert res.sample_meta["check_columns"] == ["amount"]


def test_evaluation_via_yaml_ruleset():
    """完整规则加载 → 检测 → 标识/检测列都能识别。"""
    from app.main import app as _app  # noqa: F401
    from app.engine import load_ruleset, ExecutionContext, RuleRunner
    p = Path("data/rulesets/orders_rules.yaml")
    _, _, rules = load_ruleset(p)
    # 故意制造问题：日期格式错、邮箱格式错、status 越界
    df = pd.DataFrame({
        "order_id": ["O001", "O002"],
        "customer_id": ["C001", "C002"],
        "order_date": ["2026-06-29", "bad-date"],
        "order_amount": ["100", "200"],
        "discount": ["0", "0"],
        "paid_amount": ["100", "200"],
        "refund_amount": ["0", "0"],
        "order_status": ["paid", "BAD"],
        "customer_email": ["a@b.com", "not-an-email"],
    })
    ctx = ExecutionContext(df=df)
    summary = RuleRunner().run(rules, ctx)
    failed = [r for r in summary.results if r.failed > 0]
    assert len(failed) > 0
    for r in failed:
        assert r.sample_meta["id_columns"], f"{r.rule_id} 缺标识列"
        assert r.sample_meta["check_columns"], f"{r.rule_id} 缺检测列"