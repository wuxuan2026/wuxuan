"""一致性规则：跨字段表达式、主键唯一、跨表外键。"""
from __future__ import annotations

import pandas as pd

from app.engine.base import ExecutionContext, Rule
from app.engine.registry import register


@register("cross_field")
class CrossFieldRule(Rule):
    """跨字段表达式约束。params.expr 用 pandas eval 求值，结果为 True 表示合规。

    例: discount <= order_amount   （折扣不能超过订单金额）
    """

    def evaluate(self, ctx: ExecutionContext) -> "RuleResult":
        expr = self.params.get("expr", "")
        if not expr:
            return self._make_result(0, 0, "params.expr 未指定")
        try:
            ok_mask = ctx.df.eval(expr)
        except Exception as e:
            return self._make_result(len(ctx.df), len(ctx.df), f"表达式求值失败: {e}")
        # 关键列：引用到的列（粗略地用所有数值/字符串列，方便 sample 展示）
        bad = ~ok_mask.fillna(False)
        total = len(ctx.df)
        failed = int(bad.sum())
        msg = f"跨字段表达式 {expr!r} 不满足 {failed}/{total} 条"
        samples, _meta = self._sample(ctx, bad) if failed else ([], {"id_columns": [], "check_columns": []})
        return self._make_result(
            total=total,
            failed=failed,
            message=msg,
            sample_failures=samples,
            sample_meta=_meta,
        )


@register("primary_key")
class PrimaryKeyUniqueRule(Rule):
    """强主键检查：列组合唯一，重复任一不通过。

    与 no_duplicates 等价，但语义化为"主键"。
    """

    def evaluate(self, ctx: ExecutionContext) -> "RuleResult":
        if not self.columns:
            return self._make_result(0, 0, "未指定列")
        for c in self.columns:
            if c not in ctx.df.columns:
                return self._make_result(0, 0, message=f"列 {c!r} 不存在")
        null_in_pk = pd.Series(False, index=ctx.df.index)
        for c in self.columns:
            null_in_pk = null_in_pk | self._null_mask(ctx, c)
        dup = ctx.df.duplicated(subset=self.columns, keep=False) | null_in_pk
        total = len(ctx.df)
        failed = int(dup.sum())
        msg = (
            f"主键 {self.columns} 有 {failed} 条违反唯一或非空"
            if failed
            else f"主键 {self.columns} 唯一且非空"
        )
        samples, _meta = self._sample(ctx, dup) if failed else ([], {"id_columns": [], "check_columns": []})
        return self._make_result(
            total=total,
            failed=failed,
            message=msg,
            sample_failures=samples,
            sample_meta=_meta,
        )


@register("foreign_key")
class ForeignKeyRule(Rule):
    """跨表外键：当前表的 column 必须在 ref_table.ref_column 的值集合中。

    params:
      ref_table:  引用的关联表名（已在 ctx.tables 中加载）
      ref_column: 关联表的列名
    """

    def evaluate(self, ctx: ExecutionContext) -> "RuleResult":
        if not self.columns:
            return self._make_result(0, 0, "未指定列")
        col = self.columns[0]
        if col not in ctx.df.columns:
            return self._make_result(0, 0, message=f"列 {col!r} 不存在")

        ref_table = self.params.get("ref_table")
        ref_col = self.params.get("ref_column")
        if not ref_table or not ref_col:
            return self._make_result(0, 0, "params.ref_table / ref_column 未指定")
        if ref_table not in ctx.tables:
            return self._make_result(
                total=len(ctx.df), failed=len(ctx.df),
                message=f"关联表 {ref_table!r} 未加载到 ctx.tables",
            )
        ref_df = ctx.tables[ref_table]
        if ref_col not in ref_df.columns:
            return self._make_result(
                total=len(ctx.df), failed=len(ctx.df),
                message=f"关联表缺少列 {ref_col!r}",
            )

        valid_values = set(ref_df[ref_col].astype(str))
        null_mask = self._null_mask(ctx, col)
        non_null = ctx.df[~null_mask][col].astype(str)
        bad = non_null.map(lambda v: v not in valid_values)
        failed_idx = pd.Series(False, index=ctx.df.index)
        failed_idx.loc[bad.index] = bad.values
        total = len(ctx.df)
        failed = int(failed_idx.sum())
        msg = (
            f"外键 {col}->{ref_table}.{ref_col} 有 {failed}/{total} 条不在合法集"
            if failed
            else f"外键 {col}->{ref_table}.{ref_col} 全部命中"
        )
        samples, _meta = self._sample(ctx, failed_idx) if failed else ([], {"id_columns": [], "check_columns": []})
        return self._make_result(
            total=total,
            failed=failed,
            message=msg,
            sample_failures=samples,
            sample_meta=_meta,
        )