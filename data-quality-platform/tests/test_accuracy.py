"""准确性维度规则：sum_check / statistical。"""
from __future__ import annotations

import pandas as pd

from app.detectors.accuracy import SumCheckRule, StatisticalRule
from app.engine.base import ExecutionContext


def _ctx(df: pd.DataFrame) -> ExecutionContext:
    return ExecutionContext(df=df)


# ----------------------- SumCheckRule -----------------------

def test_sum_check_all_match():
    df = pd.DataFrame({
        "a": ["10", "20", "30"],
        "b": ["5", "5", "0"],
        "tot": ["15", "25", "30"],
    })
    r = SumCheckRule(id="r", dimension="accuracy", columns=["a", "b"], params={"target": "tot", "tol": 0}).evaluate(_ctx(df))
    assert r.passed is True
    assert r.failed == 0
    assert r.total == 3


def test_sum_check_some_mismatch():
    df = pd.DataFrame({
        "a": ["10", "20", "30"],
        "b": ["5", "5", "0"],
        "tot": ["15", "26", "30"],  # 第二行 sum=25, tot=26
    })
    r = SumCheckRule(id="r", dimension="accuracy", columns=["a", "b"], params={"target": "tot", "tol": 0}).evaluate(_ctx(df))
    assert r.passed is False
    assert r.failed == 1
    assert r.failure_rate > 0


def test_sum_check_with_tolerance():
    df = pd.DataFrame({
        "a": ["10.005", "20"],
        "b": ["5.000", "5"],
        "tot": ["15", "25"],
    })
    r = SumCheckRule(id="r", dimension="accuracy", columns=["a", "b"], params={"target": "tot", "tol": 0.01}).evaluate(_ctx(df))
    assert r.passed is True


def test_sum_check_skips_partial_missing():
    df = pd.DataFrame({
        "a": ["10", "", "30"],
        "b": ["5", "5", "0"],
        "tot": ["15", "5", "30"],
    })
    r = SumCheckRule(id="r", dimension="accuracy", columns=["a", "b"], params={"target": "tot", "allow_partial": True}).evaluate(_ctx(df))
    # 第二行 a 缺失 → 跳过；其它行 OK
    assert r.passed is True
    assert r.total == 2


def test_sum_check_strict_partial():
    df = pd.DataFrame({
        "a": ["10", ""],
        "b": ["5", "5"],
        "tot": ["15", "5"],
    })
    r = SumCheckRule(id="r", dimension="accuracy", columns=["a", "b"], params={"target": "tot", "allow_partial": False}).evaluate(_ctx(df))
    # 严格模式：第二行 a 缺失 → 失败
    assert r.failed >= 1


def test_sum_check_missing_target_column():
    df = pd.DataFrame({"a": ["1"], "b": ["2"]})
    r = SumCheckRule(id="r", dimension="accuracy", columns=["a", "b"], params={"target": "nope"}).evaluate(_ctx(df))
    assert r.passed is True
    assert "不存在" in r.message


# ----------------------- StatisticalRule -----------------------

def test_statistical_range_only():
    df = pd.DataFrame({"x": ["1", "2", "3", "1000"]})
    r = StatisticalRule(id="r", dimension="accuracy", columns=["x"], params={"max": 100}).evaluate(_ctx(df))
    assert r.failed == 1
    assert r.passed is False


def test_statistical_min_max():
    df = pd.DataFrame({"x": ["-5", "10", "20", "30"]})
    r = StatisticalRule(id="r", dimension="accuracy", columns=["x"], params={"min": 0, "max": 100}).evaluate(_ctx(df))
    assert r.failed == 1
    assert r.passed is False


def test_statistical_sigma_outlier():
    # 制造一个明显的离群点
    df = pd.DataFrame({"x": ["10", "11", "9", "10", "11", "9", "10", "1000"]})
    r = StatisticalRule(id="r", dimension="accuracy", columns=["x"], params={"k": 2}).evaluate(_ctx(df))
    assert r.failed >= 1
    assert r.passed is False


def test_statistical_no_params_raises():
    df = pd.DataFrame({"x": ["1"]})
    r = StatisticalRule(id="r", dimension="accuracy", columns=["x"], params={}).evaluate(_ctx(df))
    assert r.passed is True
    assert "至少需要" in r.message


def test_statistical_missing_column():
    df = pd.DataFrame({"x": ["1"]})
    r = StatisticalRule(id="r", dimension="accuracy", columns=["nope"], params={"min": 0}).evaluate(_ctx(df))
    assert r.passed is True
    assert "不存在" in r.message


# ----------------------- 注册表 -----------------------

def test_accuracy_rules_registered():
    from app.engine import REGISTRY
    assert "sum_check" in REGISTRY
    assert "statistical" in REGISTRY
    assert REGISTRY["sum_check"] is SumCheckRule
    assert REGISTRY["statistical"] is StatisticalRule