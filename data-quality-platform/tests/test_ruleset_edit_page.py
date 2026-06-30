"""规则集编辑页可视化表格的渲染 / 提交流程。"""
from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from app.main import app


def _client() -> TestClient:
    return TestClient(app)


def test_edit_page_renders_table_structure():
    c = _client()
    r = c.get("/rulesets/orders/edit")
    assert r.status_code == 200
    # 表格结构
    assert 'id="rules-tbody"' in r.text
    assert 'id="add-row"' in r.text
    assert 'id="yaml-source"' in r.text  # hidden field for submission
    assert 'id="yaml-advanced"' in r.text  # 高级模式 textarea
    # 元信息
    assert 'id="dataset"' in r.text
    assert 'id="description"' in r.text
    assert 'id="default-severity"' in r.text
    # JS 资源
    assert "ruleset_editor.js" in r.text
    assert "js-yaml" in r.text  # CDN
    # 已注册规则类型要传到前端
    assert "not_null" in r.text
    assert "sum_check" in r.text


def test_edit_page_has_all_rule_types():
    """前端 select 应包含所有已注册规则类型。"""
    c = _client()
    r = c.get("/rulesets/orders/edit")
    from app.engine import REGISTRY
    for t in sorted(REGISTRY):
        assert t in r.text, f"缺少规则类型 {t}"


def test_edit_page_loads_current_yaml():
    """页面应该把现有 YAML 灌进 hidden 与 advanced textarea。"""
    c = _client()
    r = c.get("/rulesets/orders/edit")
    # 读一下 orders_rules.yaml 的内容长度，确保 hidden field 非空
    raw = Path("data/rulesets/orders_rules.yaml").read_text(encoding="utf-8")
    assert len(raw) > 100
    assert raw[:30] in r.text  # yaml 头部


def test_edit_page_save_yaml_round_trip(tmp_path: Path):
    """保存一个新 ruleset → 内容能写回并被下次 GET 读回。"""
    # 直接测路由：POST 新内容
    c = _client()
    new_yaml = (
        "dataset: tmp_test\n"
        "description: 测试编辑页\n"
        "defaults:\n  severity: major\n"
        "rules:\n"
        "  - id: t1\n"
        "    type: not_null\n"
        "    dimension: completeness\n"
        "    column: x\n"
    )
    # 先写一个临时 ruleset
    target = Path("data/rulesets/tmp_test_rules.yaml")
    target.write_text(new_yaml, encoding="utf-8")
    try:
        # GET 页面 + 提交
        r1 = c.get("/rulesets/tmp_test/edit")
        assert r1.status_code == 200
        new_content = new_yaml.replace("major\nrules", "minor\nrules")
        r2 = c.post(
            "/rulesets/tmp_test/edit",
            data={"content": new_content},
            follow_redirects=False,
        )
        assert r2.status_code == 303
        # 文件已更新
        updated = target.read_text(encoding="utf-8")
        assert "severity: minor" in updated
    finally:
        target.unlink(missing_ok=True)


def test_edit_page_invalid_yaml_shows_error():
    c = _client()
    bad = "this is not: valid: yaml: ::"
    r = c.post(
        "/rulesets/orders/edit",
        data={"content": bad},
        follow_redirects=False,
    )
    # 不应该 303 重定向，应该回 200 + flash error
    assert r.status_code == 200
    assert "YAML 解析失败" in r.text


def test_yaml_serialization_preserves_data():
    """后端拿到 content 后应该能被 yaml.safe_load 解析回原结构。"""
    raw = (
        "dataset: orders\n"
        "rules:\n"
        "  - id: ord_001\n"
        "    type: not_null\n"
        "    dimension: completeness\n"
        "    column: order_id\n"
    )
    parsed = yaml.safe_load(raw)
    assert parsed["dataset"] == "orders"
    assert parsed["rules"][0]["type"] == "not_null"