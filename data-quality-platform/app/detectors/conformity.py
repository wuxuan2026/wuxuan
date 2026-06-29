"""规范性规则：类型、格式正则、枚举值。"""
from __future__ import annotations

import re
from datetime import datetime

import pandas as pd

from app.engine.base import ExecutionContext, Rule
from app.engine.registry import register


@register("type")
class TypeRule(Rule):
    """检查列的数据类型是否匹配。

    params.dtype 支持: int / float / date / datetime / str
    """

    _DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d")
    _DATETIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y/%m/%d %H:%M:%S")

    def evaluate(self, ctx: ExecutionContext) -> "RuleResult":
        if not self.columns:
            return self._make_result(0, 0, "未指定列")
        col = self.columns[0]
        if col not in ctx.df.columns:
            return self._make_result(0, 0, message=f"列 {col!r} 不存在")
        dtype = str(self.params.get("dtype", "")).lower()
        if not dtype:
            return self._make_result(0, 0, "params.dtype 未指定")

        null_mask = self._null_mask(ctx, col)
        non_null = ctx.df[~null_mask][col].astype(str)
        total = len(ctx.df)
        if dtype == "str":
            failed_idx = pd.Series(False, index=ctx.df.index)
        elif dtype == "int":
            bad = pd.to_numeric(non_null, errors="coerce").isna() & non_null.str.match(r"^-?\d+$").eq(False)
            failed_idx = pd.Series(False, index=ctx.df.index)
            failed_idx.loc[bad.index] = bad.values
        elif dtype == "float":
            bad = pd.to_numeric(non_null, errors="coerce").isna()
            failed_idx = pd.Series(False, index=ctx.df.index)
            failed_idx.loc[bad.index] = bad.values
        elif dtype in {"date", "datetime"}:
            fmts = self._DATETIME_FORMATS if dtype == "datetime" else self._DATE_FORMATS
            bad = self._parse_with_formats(non_null, fmts).isna()
            failed_idx = pd.Series(False, index=ctx.df.index)
            failed_idx.loc[bad.index] = bad.values
        else:
            return self._make_result(0, 0, f"不支持的 dtype: {dtype}")

        # 缺失值不算 type 错误（归属完整性维度）
        failed_idx = failed_idx & ~null_mask
        failed = int(failed_idx.sum())
        msg = f"列 {col} 有 {failed}/{total} 条不符合 {dtype} 类型"
        return self._make_result(
            total=total,
            failed=failed,
            message=msg,
            sample_failures=self._sample(ctx, failed_idx) if failed else [],
        )

    @staticmethod
    def _parse_with_formats(series: pd.Series, formats: tuple[str, ...]) -> pd.Series:
        result = pd.Series([pd.NaT] * len(series), index=series.index)
        for fmt in formats:
            mask = result.isna()
            if not mask.any():
                break
            try:
                parsed = pd.to_datetime(series[mask], format=fmt, errors="coerce")
            except Exception:
                parsed = pd.Series([pd.NaT] * mask.sum(), index=series[mask].index)
            result.loc[mask] = parsed.values
        return result


@register("regex")
class RegexRule(Rule):
    """检查列值是否符合指定正则。params.pattern 是字符串。"""

    def evaluate(self, ctx: ExecutionContext) -> "RuleResult":
        if not self.columns:
            return self._make_result(0, 0, "未指定列")
        col = self.columns[0]
        if col not in ctx.df.columns:
            return self._make_result(0, 0, message=f"列 {col!r} 不存在")
        pattern = self.params.get("pattern", "")
        if not pattern:
            return self._make_result(0, 0, "params.pattern 未指定")
        try:
            regex = re.compile(pattern)
        except re.error as e:
            return self._make_result(0, 0, f"非法正则: {e}")

        null_mask = self._null_mask(ctx, col)
        non_null = ctx.df[~null_mask][col].astype(str)
        bad = ~non_null.map(lambda v: bool(regex.search(v)))
        failed_idx = pd.Series(False, index=ctx.df.index)
        failed_idx.loc[bad.index] = bad.values
        failed = int(failed_idx.sum())
        total = len(ctx.df)
        msg = f"列 {col} 有 {failed}/{total} 条不符合正则 {pattern!r}"
        return self._make_result(
            total=total,
            failed=failed,
            message=msg,
            sample_failures=self._sample(ctx, failed_idx) if failed else [],
        )


@register("enum")
class EnumRule(Rule):
    """检查列值是否在白名单中。params.values 是列表。"""

    def evaluate(self, ctx: ExecutionContext) -> "RuleResult":
        if not self.columns:
            return self._make_result(0, 0, "未指定列")
        col = self.columns[0]
        if col not in ctx.df.columns:
            return self._make_result(0, 0, message=f"列 {col!r} 不存在")
        values = self.params.get("values") or []
        if not isinstance(values, list) or not values:
            return self._make_result(0, 0, "params.values 未指定或为空")
        allowed = set(str(v) for v in values)

        null_mask = self._null_mask(ctx, col)
        non_null = ctx.df[~null_mask][col].astype(str)
        bad = non_null.map(lambda v: v not in allowed)
        failed_idx = pd.Series(False, index=ctx.df.index)
        failed_idx.loc[bad.index] = bad.values
        failed = int(failed_idx.sum())
        total = len(ctx.df)
        msg = f"列 {col} 有 {failed}/{total} 条不在枚举 {values} 中"
        return self._make_result(
            total=total,
            failed=failed,
            message=msg,
            sample_failures=self._sample(ctx, failed_idx) if failed else [],
        )
