"""规则集与注册表完整性校验：保证 orders_rules.yaml 不会被人改残。

注：删除 demo 数据后，orders 规则集精简为单文件可用版本（12 条规则，6 维度）。
删除的规则：foreign_key（需要关联表）、arrival（需要关联表）。
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.fixture(scope="module")
def orders_yaml() -> dict:
    p = Path("data/rulesets/orders_rules.yaml")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


# 单文件版规则集：去掉需关联表的 foreign_key 和 arrival，保留 12 条
EXPECTED_RULE_IDS = {f"ord_{i:03d}" for i in range(1, 13)}  # ord_001..ord_012


def test_orders_yaml_exists():
    p = Path("data/rulesets/orders_rules.yaml")
    assert p.exists()


def test_orders_yaml_has_expected_rules(orders_yaml):
    assert len(orders_yaml["rules"]) == len(EXPECTED_RULE_IDS), (
        f"orders_rules.yaml 应有 {len(EXPECTED_RULE_IDS)} 条规则，实际 {len(orders_yaml['rules'])} 条"
    )


def test_orders_yaml_ids_are_unique_and_sequential(orders_yaml):
    ids = [r["id"] for r in orders_yaml["rules"]]
    assert len(ids) == len(set(ids)), "rule id 必须唯一"
    assert set(ids) == EXPECTED_RULE_IDS, f"id 集合不匹配：缺/多 {set(ids) ^ EXPECTED_RULE_IDS}"


def test_orders_yaml_covers_6_dimensions(orders_yaml):
    dims = {r["dimension"] for r in orders_yaml["rules"]}
    assert dims == {"completeness", "uniqueness", "conformity", "accuracy", "consistency", "timeliness"}


def test_orders_yaml_no_relations_required(orders_yaml):
    """单文件规则集不应包含需要关联表的规则。"""
    types_used = {r["type"] for r in orders_yaml["rules"]}
    assert "foreign_key" not in types_used, "单文件规则集不应使用 foreign_key（需关联表）"
    assert "arrival" not in types_used, "单文件规则集不应使用 arrival（需关联表）"


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
    from app.main import app  # noqa: F401
    from app.engine import REGISTRY
    needed = {r["type"] for r in orders_yaml["rules"]}
    missing = needed - set(REGISTRY)
    assert not missing, f"REGISTRY 缺规则类型: {missing}（main.py 没 import 对应 detector）"


def test_yaml_loader_can_load_orders_yaml():
    """load_ruleset 必须能正确实例化所有规则。"""
    from app.main import app  # noqa: F401
    from app.engine import load_ruleset
    p = Path("data/rulesets/orders_rules.yaml")
    ds, desc, rules = load_ruleset(p)
    assert ds == "orders"
    assert len(rules) == len(EXPECTED_RULE_IDS)


def test_check_service_runs_all_rules():
    """端到端：上传一份 orders 数据 + orders 规则集，必须真正执行所有规则。"""
    import io
    from app.main import app  # noqa: F401
    from app.services.check_service import CheckService

    # 用一个最小 CSV 测试上传路径（不再依赖 demo 数据）
    csv = (
        "order_id,customer_id,order_date,order_amount,discount,paid_amount,refund_amount,order_status,customer_email\n"
        "O000001,C00001,2026-06-29,100.0,10.0,90.0,0.0,paid,a@b.com\n"
        "O000002,C00002,2026-06-29,200.0,20.0,180.0,0.0,paid,a@b.com\n"
    )
    # 写到临时文件
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(csv)
        tmp = f.name
    try:
        svc = CheckService()
        r = svc.run_for_uploaded(
            dataset="orders",
            csv_path=Path(tmp),
            ruleset_path=Path("data/rulesets/orders_rules.yaml"),
        )
        assert len(r["results"]) == len(EXPECTED_RULE_IDS), (
            f"期望 {len(EXPECTED_RULE_IDS)} 条结果，实际 {len(r['results'])} 条"
        )
        rule_ids = {x["rule_id"] for x in r["results"]}
        assert rule_ids == EXPECTED_RULE_IDS
    finally:
        Path(tmp).unlink()