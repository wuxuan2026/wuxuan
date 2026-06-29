"""规则类型注册表：把字符串名映射到具体 Rule 子类。"""
from __future__ import annotations

from typing import Callable, Type

REGISTRY: dict[str, Type] = {}


def register(name: str) -> Callable[[Type], Type]:
    """装饰器：把 Rule 子类注册到全局表。"""

    def deco(cls: Type) -> Type:
        if name in REGISTRY:
            raise ValueError(f"规则类型 {name!r} 已被 {REGISTRY[name].__name__} 注册")
        REGISTRY[name] = cls
        cls.__registry_name__ = name  # type: ignore[attr-defined]
        return cls

    return deco


def get_rule_class(name: str) -> Type:
    if name not in REGISTRY:
        raise KeyError(f"未知规则类型 {name!r}，已注册：{sorted(REGISTRY)}")
    return REGISTRY[name]
