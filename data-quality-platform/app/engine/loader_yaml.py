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
            rule = cls(**kwargs)
        except TypeError as e:
            raise ValueError(f"实例化规则 {item.get('id', '?')} ({item.get('type')}) 失败: {e}") from e
        # 记录 type（Rule 基类没有这个字段，但报告页和编辑页需要）
        rule.type = item["type"]
        rules.append(rule)
    return dataset, description, rules


def dump_ruleset(dataset: str, description: str, rules: list[dict[str, Any]]) -> str:
    """把内存里的规则列表重新序列化回 YAML 字符串（编辑后写回磁盘用）。"""
    return yaml.safe_dump(
        {"dataset": dataset, "description": description, "rules": rules},
        allow_unicode=True,
        sort_keys=False,
    )


def load_ruleset_raw(path: str | Path) -> dict[str, Any]:
    """只解析 YAML，不实例化规则。用于编辑预览等只读场景。"""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"规则集文件不存在: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}
    raw.setdefault("dataset", path.stem)
    raw.setdefault("description", "")
    raw.setdefault("defaults", {})
    raw.setdefault("rules", [])
    return raw


def rule_summary(item: dict[str, Any], default_severity: str = "major") -> dict[str, Any]:
    """把单条 YAML 规则整理成表格行所需的字段。"""
    columns = item.get("columns") or item.get("column")
    if isinstance(columns, str):
        columns_str = columns
    elif isinstance(columns, list):
        columns_str = ", ".join(str(c) for c in columns)
    else:
        columns_str = "—"

    params = item.get("params") or {}
    if isinstance(params, dict) and params:
        params_str = ", ".join(f"{k}={_fmt(v)}" for k, v in params.items())
    else:
        params_str = "—"

    return {
        "id": str(item.get("id", "—")),
        "name": str(item.get("name", "")) or str(item.get("id", "—")),
        "type": str(item.get("type", "—")),
        "dimension": str(item.get("dimension", "—")),
        "severity": str(item.get("severity", default_severity)),
        "columns": columns_str,
        "params": params_str,
    }


def _fmt(v: Any) -> str:
    """把 param 值渲染成短字符串（截断过长的列表/正则）。"""
    if isinstance(v, str):
        return v if len(v) <= 24 else v[:21] + "..."
    if isinstance(v, list):
        return "[" + ", ".join(str(x) for x in v[:4]) + ("]" if len(v) <= 4 else ", ...]")
    return str(v)
