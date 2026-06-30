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
    sample_meta: dict = field(default_factory=dict)  # {id_columns, check_columns}，标识/检测列分组
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
        sample_meta: dict | None = None,
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
            sample_meta=sample_meta or {},
            message=message,
        )

    def _null_mask(self, ctx: ExecutionContext, column: str) -> pd.Series:
        """空值/缺失值掩码：空字符串、纯空白都视为缺失。"""
        s = ctx.df[column].astype(str)
        return s.str.strip().eq("") | s.str.lower().isin({"none", "null", "nan"})

    def _sample(self, ctx: ExecutionContext, mask: pd.Series, n: int | None = None) -> tuple[list[dict], dict]:
        """收集失败样本：(samples, meta)。

        meta 字段：
          - id_columns: 标识列（用于定位记录）
          - check_columns: 检测列（规则涉及）
        """
        from app.config import SAMPLE_LIMIT

        if n is None:
            n = SAMPLE_LIMIT
        rows = ctx.df[mask].head(n)

        check_cols = list(self.columns) if self.columns else []
        id_cols = self._pick_identifier_columns(ctx)

        seen: set[str] = set()
        ordered: list[str] = []
        for c in id_cols + check_cols:
            if c not in seen and c in ctx.df.columns:
                seen.add(c)
                ordered.append(c)

        out = []
        for idx, row in rows.iterrows():
            item: dict[str, Any] = {"row": int(idx) + 2}
            for c in ordered:
                if c in row.index:
                    val = row.get(c)
                    item[c] = "" if pd.isna(val) else str(val)
            out.append(item)
        meta = {"id_columns": id_cols, "check_columns": check_cols}
        return out, meta

    def _pick_identifier_columns(self, ctx: ExecutionContext) -> list[str]:
        """根据 YAML params 或列名启发式，找 1-3 个标识列。"""
        # 1) YAML 显式
        declared = self.params.get("identifier") or self.params.get("identifiers")
        if declared:
            if isinstance(declared, str):
                return [declared] if declared in ctx.df.columns else []
            if isinstance(declared, list):
                return [c for c in declared if c in ctx.df.columns]

        # 2) 启发式：列名含 id 且唯一比例高
        candidates: list[tuple[str, float]] = []
        n = max(1, len(ctx.df))
        for col in ctx.df.columns:
            low = col.lower()
            if "id" not in low:
                continue
            s = ctx.df[col].astype(str)
            unique_ratio = s.nunique(dropna=True) / n
            if unique_ratio >= 0.5:
                candidates.append((col, unique_ratio))
        candidates.sort(key=lambda x: -x[1])
        if candidates:
            return [candidates[0][0]]

        # 3) 数据集第 1 个列
        first = ctx.df.columns[0] if len(ctx.df.columns) else None
        return [first] if first else []


# 让 _pick_identifier_columns 在样本很少（uniqueness=1.0）时不报错的常量
_ = pd.DataFrame()  # noqa: F401  (保持 pd 在 base.py 已 import，供子类使用)
