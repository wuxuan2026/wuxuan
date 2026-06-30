"""规则引擎核心抽象：Rule、RuleResult、ExecutionContext。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd

Dimension = Literal["completeness", "uniqueness", "conformity", "accuracy", "consistency", "timeliness"]
Severity = Literal["blocker", "major", "minor"]


@dataclass
class RuleResult:
    """一条规则的执行结果。"""

    rule_id: str
    name: str
    dimension: str
    severity: str
    type: str = ""  # 规则类型（注册表里的 key），用于报告页中文展示
    passed: bool = False
    total: int = 0
    failed: int = 0
    failure_rate: float = 0.0
    sample_failures: list[dict] = field(default_factory=list)
    message: str = ""
    error: str | None = None

    @property
    def pass_rate(self) -> float:
        return 1 - self.failure_rate


@dataclass
class ExecutionContext:
    """单次检测的执行上下文。"""

    df: pd.DataFrame
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)


class Rule(ABC):
    """规则抽象基类。

    YAML 中声明的字段会通过 __init__ 映射；YAML 支持的字段见下面 __init__ 签名。
    """

    def __init__(
        self,
        id: str,
        dimension: Dimension,
        columns: list[str] | None = None,
        column: str | None = None,
        severity: Severity = "major",
        name: str = "",
        params: dict[str, Any] | None = None,
        **_: Any,
    ) -> None:
        self.id = id
        self.dimension = dimension
        # 同时支持 column（单数）和 columns（复数/列表）
        if column is not None:
            self.columns = [column]
        elif columns is not None:
            self.columns = list(columns)
        else:
            self.columns = []
        self.severity = severity
        self.name = name or id
        self.params = params or {}

    @abstractmethod
    def evaluate(self, ctx: ExecutionContext) -> RuleResult:
        ...

    # ---------- 工具方法（子类可直接调用） ----------

    def _make_result(
        self,
        total: int,
        failed: int,
        message: str = "",
        sample_failures: list[dict] | None = None,
    ) -> RuleResult:
        total = max(0, int(total))
        failed = max(0, min(int(failed), total))
        rate = (failed / total) if total else 0.0
        return RuleResult(
            rule_id=self.id,
            name=self.name,
            dimension=self.dimension,
            severity=self.severity,
            passed=(failed == 0),
            total=total,
            failed=failed,
            failure_rate=rate,
            sample_failures=sample_failures or [],
            message=message,
        )

    def _null_mask(self, ctx: ExecutionContext, column: str) -> pd.Series:
        """空值/缺失值掩码：空字符串、纯空白都视为缺失。"""
        s = ctx.df[column].astype(str)
        return s.str.strip().eq("") | s.str.lower().isin({"none", "null", "nan"})

    def _sample(self, ctx: ExecutionContext, mask: pd.Series, n: int | None = None) -> list[dict]:
        from app.config import SAMPLE_LIMIT

        if n is None:
            n = SAMPLE_LIMIT
        rows = ctx.df[mask].head(n)
        cols = self.columns or list(ctx.df.columns)
        out = []
        for idx, row in rows.iterrows():
            item = {"row": int(idx) + 2}  # +2：跳过 header，第一行数据 row=2
            for c in cols:
                if c in row.index:
                    val = row.get(c)
                    item[c] = "" if pd.isna(val) else str(val)
            out.append(item)
        return out
