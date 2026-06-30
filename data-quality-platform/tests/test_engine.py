"""规则引擎和检测器单测。"""
from __future__ import annotations

import pandas as pd
import pytest

from app.engine import ExecutionContext, RuleRunner, load_ruleset
from app.engine.registry import REGISTRY, register
from app.detectors import completeness  # noqa: F401  触发 @register
from app.detectors import conformity  # noqa: F401
from app.detectors import consistency  # noqa: F401
from app.detectors import timeliness  # noqa: F401
from app.detectors import accuracy  # noqa: F401


@pytest.fixture
def sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "order_id": ["O1", "O2", "O3", "O2", "O5", ""],
        "email": ["a@b.com", "bad", "c@d.com", "", "e@f.com", "g@h.com"],
        "status": ["paid", "shipped", "unknown", "paid", "paid", "paid"],
        "amount": [10, 20, 30, 40, -1, 999999],
    })


@pytest.fixture
def ctx(sample_df) -> ExecutionContext:
    return ExecutionContext(df=sample_df)


def test_registry_has_core_types():
    for t in ("not_null", "no_duplicates", "range", "regex", "enum", "type"):
        assert t in REGISTRY


def test_not_null_finds_blanks(ctx):
    rule = REGISTRY["not_null"](
        id="t1", dimension="completeness", column="order_id", severity="major"
    )
    r = rule.evaluate(ctx)
    assert r.total == 6
    assert r.failed == 1  # 最后一行空字符串
    assert not r.passed


def test_no_duplicates_detects_dup(ctx):
    rule = REGISTRY["no_duplicates"](
        id="t2", dimension="completeness", columns=["order_id"], severity="major"
    )
    r = rule.evaluate(ctx)
    # "O2" 出现两次 → 2 行计入失败
    assert r.failed == 2


def test_range_out_of_bounds(ctx):
    rule = REGISTRY["range"](
        id="t3",
        dimension="completeness",
        column="amount",
        params={"min": 0, "max": 1000},
    )
    r = rule.evaluate(ctx)
    assert r.failed == 2  # -1, 999999
    assert r.passed is False


def test_regex_invalid_emails(ctx):
    rule = REGISTRY["regex"](
        id="t4",
        dimension="conformity",
        column="email",
        params={"pattern": r"^[^@\s]+@[^@\s]+\.[^@\s]+$"},
    )
    r = rule.evaluate(ctx)
    assert r.failed == 1  # "bad"
    assert r.passed is False


def test_enum_unknown_value(ctx):
    rule = REGISTRY["enum"](
        id="t5",
        dimension="conformity",
        column="status",
        params={"values": ["paid", "shipped", "delivered"]},
    )
    r = rule.evaluate(ctx)
    assert r.failed == 1  # "unknown"


def test_type_date_ok(ctx):
    df = pd.DataFrame({"d": ["2025-01-01", "2025-12-31", "not-a-date", ""]})
    c = ExecutionContext(df=df)
    rule = REGISTRY["type"](
        id="t6", dimension="conformity", column="d", params={"dtype": "date"}
    )
    r = rule.evaluate(c)
    # 空值不计入类型失败 → 只有 "not-a-date" 失败
    assert r.failed == 1
    assert r.passed is False


def test_runner_returns_summary(ctx):
    rules = [
        REGISTRY["not_null"](id="r1", dimension="completeness", column="order_id"),
        REGISTRY["enum"](
            id="r2", dimension="conformity", column="status",
            params={"values": ["paid"]},
        ),
    ]
    summary = RuleRunner(dataset="t").run(rules, ctx)
    assert summary.rules_total == 2
    assert summary.rules_passed == 0
    assert len(summary.results) == 2
    assert summary.duration_ms >= 0


def test_runner_keeps_going_when_one_rule_errors(ctx):
    rules = [
        REGISTRY["not_null"](id="r1", dimension="completeness", column="order_id"),
        # 用一个会真的抛异常的场景：range 规则对非数值列做 coerce 不抛，
        # 但我们可以用一个故意写错 params 的规则来触发异常。
        # 简单办法：直接构造一个会抛的 rule 子类。
    ]

    class BoomRule:
        id = "boom"
        name = "boom"
        dimension = "conformity"
        severity = "major"

        def evaluate(self, ctx):
            raise RuntimeError("oops")

    rules.append(BoomRule())
    rules.append(
        REGISTRY["enum"](
            id="r3", dimension="conformity", column="status",
            params={"values": ["paid"]},
        )
    )
    summary = RuleRunner().run(rules, ctx)
    assert summary.rules_total == 3
    errored = [r for r in summary.results if r.error]
    assert len(errored) == 1
    assert errored[0].rule_id == "boom"


def test_load_yaml_ruleset():
    from pathlib import Path

    p = Path("data/rulesets/orders_rules.yaml")
    if not p.exists():
        pytest.skip("规则集文件不存在，跳过")
    dataset, desc, rules = load_ruleset(p)
    assert dataset == "orders"
    assert len(rules) >= 6
    for r in rules:
        assert r.id.startswith("ord_")
        assert r.dimension in {"completeness", "uniqueness", "conformity", "accuracy", "consistency", "timeliness"}
