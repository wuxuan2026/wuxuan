"""从 YAML 加载规则集。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.engine.base import Rule
from app.engine.registry import get_rule_class


def load_ruleset(path: str | Path) -> tuple[str, str, list[Rule]]:
    """加载 .yaml/.yml 规则集，返回 (dataset, description, [Rule, ...])。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"规则集文件不存在: {path}")

    with path.open("r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    dataset = raw.get("dataset", path.stem)
    description = raw.get("description", "")
    defaults = raw.get("defaults") or {}
    default_severity = defaults.get("severity", "major")

    rules: list[Rule] = []
    for item in raw.get("rules", []):
        if "type" not in item:
            raise ValueError(f"规则缺少 'type' 字段: {item}")
        cls = get_rule_class(item["type"])
        kwargs = dict(item)
        kwargs.pop("type", None)
        kwargs.setdefault("severity", default_severity)
        try:
            rules.append(cls(**kwargs))
        except TypeError as e:
            raise ValueError(f"实例化规则 {item.get('id', '?')} ({item.get('type')}) 失败: {e}") from e
    return dataset, description, rules


def dump_ruleset(dataset: str, description: str, rules: list[dict[str, Any]]) -> str:
    """把内存里的规则列表重新序列化回 YAML 字符串（编辑后写回磁盘用）。"""
    return yaml.safe_dump(
        {"dataset": dataset, "description": description, "rules": rules},
        allow_unicode=True,
        sort_keys=False,
    )
