"""完整性规则：缺失值、重复记录、值域。"""
from __future__ import annotations

import pandas as pd

from app.engine.base import ExecutionContext, Rule
from app.engine.registry import register


@register("not_null")
class NotNullRule(Rule):
    """指定列不允许为空。"""

    def evaluate(self, ctx: ExecutionContext) -> "RuleResult":
        if not self.columns:
            return self._make_result(0, 0, "未指定列")
        col = self.columns[0]
        if col not in ctx.df.columns:
            return self._make_result(
                0, 0, message=f"列 {col!r} 不存在（可用列: {list(ctx.df.columns)}）"
            )
        mask = self._null_mask(ctx, col)
        total = len(ctx.df)
        failed = int(mask.sum())
        msg = f"列 {col} 有 {failed}/{total} 条缺失" if failed else f"列 {col} 无缺失"
        return self._make_result(
            total=total,
            failed=failed,
            message=msg,
            sample_failures=self._sample(ctx, mask) if failed else [],
        )


@register("no_duplicates")
class NoDuplicatesRule(Rule):
    """单列或多列联合主键不允许重复。"""

    def evaluate(self, ctx: ExecutionContext) -> "RuleResult":
        if not self.columns:
            return self._make_result(0, 0, "未指定列")
        for c in self.columns:
            if c not in ctx.df.columns:
                return self._make_result(0, 0, message=f"列 {c!r} 不存在")
        dup_mask = ctx.df.duplicated(subset=self.columns, keep=False)
        total = len(ctx.df)
        failed = int(dup_mask.sum())
        cols_str = ", ".join(self.columns)
        msg = f"主键 {cols_str} 有 {failed} 条重复" if failed else f"主键 {cols_str} 唯一"
        return self._make_result(
            total=total,
            failed=failed,
            message=msg,
            sample_failures=self._sample(ctx, dup_mask) if failed else [],
        )


@register("range")
class RangeRule(Rule):
    """数值/日期值域限制。支持 min/max（可只给一个）。"""

    def evaluate(self, ctx: ExecutionContext) -> "RuleResult":
        if not self.columns:
            return self._make_result(0, 0, "未指定列")
        col = self.columns[0]
        if col not in ctx.df.columns:
            return self._make_result(0, 0, message=f"列 {col!r} 不存在")
        min_v = self.params.get("min")
        max_v = self.params.get("max")

        # 转数字，转换失败记为失败
        series = pd.to_numeric(ctx.df[col], errors="coerce")
        null_after = series.isna() & ~self._null_mask(ctx, col)

        bad = pd.Series(False, index=ctx.df.index)
        if min_v is not None:
            bad |= series < float(min_v)
        if max_v is not None:
            bad |= series > float(max_v)
        bad = bad | null_after  # 不可解析的也算失败
        total = len(ctx.df)
        failed = int(bad.sum())
        msg = f"列 {col} 有 {failed}/{total} 条超出范围 [{min_v}, {max_v}]"
        return self._make_result(
            total=total,
            failed=failed,
            message=msg,
            sample_failures=self._sample(ctx, bad) if failed else [],
        )
