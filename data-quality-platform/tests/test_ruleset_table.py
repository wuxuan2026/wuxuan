"""规则集原始解析与表格行格式化（load_ruleset_raw / rule_summary）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.engine import load_ruleset_raw, rule_summary


def test_load_ruleset_raw_returns_dict():
    p = Path("data/rulesets/orders_rules.yaml")
    raw = load_ruleset_raw(p)
    assert raw["dataset"] == "orders"
    assert isinstance(raw["rules"], list)
    assert len(raw["rules"]) >= 6
    # 必需字段
    for r in raw["rules"]:
        assert "type" in r


def test_load_ruleset_raw_supports_minimal_yaml(tmp_path: Path):
    p = tmp_path / "x.yaml"
    p.write_text("dataset: x\nrules:\n  - {id: r1, type: not_null, column: a}\n", encoding="utf-8")
    raw = load_ruleset_raw(p)
    assert raw["dataset"] == "x"
    assert raw["description"] == ""  # 默认值
    assert raw["defaults"] == {}
    assert len(raw["rules"]) == 1


def test_load_ruleset_raw_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_ruleset_raw(tmp_path / "nope.yaml")


def test_rule_summary_columns_single():
    row = rule_summary({"id": "r1", "type": "not_null", "column": "order_id"})
    assert row["columns"] == "order_id"
    assert row["severity"] == "major"  # 默认


def test_rule_summary_columns_list():
    row = rule_summary(
        {"id": "r1", "type": "no_duplicates", "columns": ["a", "b", "c"]},
        default_severity="major",
    )
    assert row["columns"] == "a, b, c"


def test_rule_summary_params_truncated():
    long_pat = "a" * 100
    row = rule_summary(
        {"id": "r1", "type": "regex", "params": {"pattern": long_pat}},
    )
    assert row["params"].startswith("pattern=")
    assert "..." in row["params"]
    assert len(row["params"]) < 50


def test_rule_summary_params_list():
    row = rule_summary(
        {"id": "r1", "type": "enum", "params": {"values": ["a", "b", "c", "d", "e"]}},
    )
    assert row["params"].startswith("values=[")
    assert "..." in row["params"]


def test_rule_summary_no_params():
    row = rule_summary({"id": "r1", "type": "not_null"})
    assert row["params"] == "—"


def test_rule_summary_severity_default():
    row = rule_summary({"id": "r1", "type": "not_null"}, default_severity="blocker")
    assert row["severity"] == "blocker"


def test_rule_summary_severity_explicit():
    row = rule_summary(
        {"id": "r1", "type": "not_null", "severity": "minor"},
        default_severity="major",
    )
    assert row["severity"] == "minor"


def test_rulesets_route_renders_table():
    """验证 /rulesets 页面包含表格行（不依赖 YAML 渲染）。"""
    from fastapi.testclient import TestClient
    from app.main import app

    c = TestClient(app)
    r = c.get("/rulesets")
    assert r.status_code == 200
    # 关键列标题
    assert "类型" in r.text
    assert "维度" in r.text
    assert "严重" in r.text
    assert "列" in r.text
    assert "参数" in r.text
    # 实际规则 type 应被展示
    assert "not_null" in r.text
    assert "cross_field" in r.text
    # 徽章数量（每条规则有 type/dimension/severity 三个 badge）
    assert "条规则" in r.text