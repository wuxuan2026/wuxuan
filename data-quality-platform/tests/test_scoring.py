"""评分模型 + 一致性/时效性规则的最小验证。"""
from __future__ import annotations

import pandas as pd
import pytest

from app.detectors import completeness  # noqa: F401
from app.detectors import conformity  # noqa: F401
from app.detectors import consistency  # noqa: F401
from app.detectors import timeliness  # noqa: F401
from app.engine import ExecutionContext, RuleRunner
from app.engine.base import RuleResult
from app.engine.registry import REGISTRY
from app.scoring import dimension_scores, summarize, total_score


def _r(dimension, severity, failed, total):
    return RuleResult(
        rule_id="x",
        name="x",
        dimension=dimension,
        severity=severity,
        passed=(failed == 0),
        total=total,
        failed=failed,
        failure_rate=(failed / total) if total else 0.0,
    )


def test_dimension_score_all_pass():
    rs = [_r("completeness", "major", 0, 100), _r("conformity", "minor", 0, 100)]
    d = dimension_scores(rs)
    assert d["completeness"] == 100
    assert d["conformity"] == 100
    assert total_score(d) == 100


def test_dimension_score_weighted_by_severity():
    rs = [
        _r("completeness", "blocker", 50, 100),  # pass_rate 0.5, weight 3
        _r("completeness", "minor", 0, 100),     # pass_rate 1.0, weight 1
    ]
    d = dimension_scores(rs)
    expected = (0.5 * 3 + 1.0 * 1) / 4 * 100
    assert abs(d["completeness"] - expected) < 1e-6


def test_total_score_in_0_100():
    rs = [
        _r("completeness", "major", 10, 100),
        _r("conformity", "major", 5, 100),
        _r("consistency", "blocker", 1, 100),
        _r("timeliness", "minor", 50, 100),
    ]
    s = summarize(rs)
    assert 0 <= s["total_score"] <= 100
    assert s["grade"] in {"优秀", "良好", "合格", "不合格"}


def test_foreign_key_fails_on_unknown_id():
    df = pd.DataFrame({"customer_id": ["C1", "C2", "C999"]})
    customers = pd.DataFrame({"customer_id": ["C1", "C2"]})
    ctx = ExecutionContext(df=df, tables={"customers": customers})
    rule = REGISTRY["foreign_key"](
        id="fk1", dimension="consistency", column="customer_id",
        params={"ref_table": "customers", "ref_column": "customer_id"},
    )
    r = rule.evaluate(ctx)
    assert r.failed == 1  # C999 不存在


def test_cross_field_violation():
    df = pd.DataFrame({"order_amount": [100, 100, 100], "discount": [10, 50, 200]})
    ctx = ExecutionContext(df=df)
    rule = REGISTRY["cross_field"](
        id="cf1", dimension="consistency",
        params={"expr": "discount <= order_amount"},
    )
    r = rule.evaluate(ctx)
    assert r.failed == 1  # 200 > 100


def test_freshness_passes_when_recent():
    df = pd.DataFrame({"d": ["2026-06-29"]})
    ctx = ExecutionContext(df=df, config={"now": pd.Timestamp("2026-06-29").to_pydatetime()})
    rule = REGISTRY["freshness"](
        id="f1", dimension="timeliness", column="d", params={"max_age_days": 1}
    )
    r = rule.evaluate(ctx)
    assert r.passed


def test_arrival_flags_late():
    df = pd.DataFrame({"order_id": ["O1", "O2"]})
    arr = pd.DataFrame({
        "order_id": ["O1", "O2"],
        "expected_arrival": ["2026-06-29 02:00:00", "2026-06-29 02:00:00"],
        "actual_arrival":   ["2026-06-29 02:10:00", "2026-06-29 05:00:00"],  # O2 延迟 3h
    })
    ctx = ExecutionContext(df=df, tables={"arrivals": arr})
    rule = REGISTRY["arrival"](
        id="a1", dimension="timeliness",
        params={"tolerance_min": 30},
    )
    r = rule.evaluate(ctx)
    assert r.failed == 1


def test_runner_keeps_going_on_unknown_table():
    df = pd.DataFrame({"x": [1]})
    ctx = ExecutionContext(df=df)
    rule = REGISTRY["foreign_key"](
        id="fk", dimension="consistency", column="x",
        params={"ref_table": "nonexistent", "ref_column": "x"},
    )
    summary = RuleRunner().run([rule], ctx)
    assert summary.results[0].passed is False
    assert "未加载" in summary.results[0].message
