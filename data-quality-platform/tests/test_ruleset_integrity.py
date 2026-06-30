"""规则集与注册表完整性校验：保证 orders_rules.yaml 不会被人改残。"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.fixture(scope="module")
def orders_yaml() -> dict:
    p = Path("data/rulesets/orders_rules.yaml")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


REQUIRED_RULE_IDS = {f"ord_{i:03d}" for i in range(1, 15)}  # ord_001..ord_014


def test_orders_yaml_exists():
    p = Path("data/rulesets/orders_rules.yaml")
    assert p.exists()


def test_orders_yaml_has_14_rules(orders_yaml):
    assert len(orders_yaml["rules"]) == 14, (
        f"orders_rules.yaml 必须有 14 条规则，实际 {len(orders_yaml['rules'])} 条"
    )


def test_orders_yaml_ids_are_unique_and_sequential(orders_yaml):
    ids = [r["id"] for r in orders_yaml["rules"]]
    assert len(ids) == len(set(ids)), "rule id 必须唯一"
    assert set(ids) == REQUIRED_RULE_IDS, f"id 集合不匹配：缺/多 {set(ids) ^ REQUIRED_RULE_IDS}"


def test_orders_yaml_covers_6_dimensions(orders_yaml):
    dims = {r["dimension"] for r in orders_yaml["rules"]}
    assert dims == {"completeness", "uniqueness", "conformity", "accuracy", "consistency", "timeliness"}


def test_orders_yaml_each_rule_has_required_fields(orders_yaml):
    defaults = (orders_yaml.get("defaults") or {})
    for r in orders_yaml["rules"]:
        assert "id" in r, r
        assert "type" in r, r
        assert "dimension" in r, r
        # severity 可来自默认值
        assert ("severity" in r) or ("severity" in defaults), r


def test_registry_contains_all_yaml_types(orders_yaml):
    """REGISTRY 必须包含 yaml 里所有用到的 type。"""
    # 确保 main.py 里的 import 被触发
    from app.main import app  # noqa: F401
    from app.engine import REGISTRY
    needed = {r["type"] for r in orders_yaml["rules"]}
    missing = needed - set(REGISTRY)
    assert not missing, f"REGISTRY 缺规则类型: {missing}（main.py 没 import 对应 detector）"


def test_yaml_loader_can_load_orders_yaml():
    """load_ruleset 必须能正确实例化 14 条规则。"""
    from app.main import app  # noqa: F401
    from app.engine import load_ruleset
    p = Path("data/rulesets/orders_rules.yaml")
    ds, desc, rules = load_ruleset(p)
    assert ds == "orders"
    assert len(rules) == 14


def test_check_service_runs_all_rules():
    """端到端：CheckService 必须真正执行所有 14 条规则（不能因为某种 bug 只跑 1 条）。"""
    from app.main import app  # noqa: F401
    from app.services.check_service import CheckService
    svc = CheckService()
    r = svc.run_for_dataset("orders")
    assert len(r["results"]) == 14, f"期望 14 条结果，实际 {len(r['results'])} 条"
    rule_ids = {x["rule_id"] for x in r["results"]}
    assert rule_ids == REQUIRED_RULE_IDS