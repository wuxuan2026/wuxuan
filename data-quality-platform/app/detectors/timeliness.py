"""时效性规则：数据新鲜度、到达及时性。"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from app.engine.base import ExecutionContext, Rule
from app.engine.registry import register


@register("freshness")
class FreshnessRule(Rule):
    """数据新鲜度：column 的最新一条距 now 不得超过 max_age_days。"""

    def evaluate(self, ctx: ExecutionContext) -> "RuleResult":
        if not self.columns:
            return self._make_result(0, 0, "未指定列")
        col = self.columns[0]
        if col not in ctx.df.columns:
            return self._make_result(0, 0, message=f"列 {col!r} 不存在")
        max_age_days = self.params.get("max_age_days")
        if max_age_days is None:
            return self._make_result(0, 0, "params.max_age_days 未指定")

        parsed = pd.to_datetime(ctx.df[col], errors="coerce")
        non_null = parsed.dropna()
        if non_null.empty:
            return self._make_result(len(ctx.df), 0, "无可解析的时间值")

        latest = non_null.max()
        now = ctx.get("now")
        if isinstance(now, str):
            now = datetime.fromisoformat(now)
        now = now or datetime.now()
        age_days = (now - latest).total_seconds() / 86400.0

        passed = age_days <= float(max_age_days)
        total = 1
        failed = 0 if passed else 1
        msg = (
            f"最新 {col}={latest.date().isoformat()} 距今 {age_days:.1f} 天"
            f"（阈值 {max_age_days} 天），{'新鲜' if passed else '过期'}"
        )
        return self._make_result(
            total=total,
            failed=failed,
            message=msg,
            sample_failures=(
                [{"row": 1, col: latest.date().isoformat(), "age_days": round(age_days, 2)}]
                if not passed
                else []
            ),
        )


@register("arrival")
class ArrivalRule(Rule):
    """到达及时性：orders 表的每行应在 expected_arrival 之后到达。

    约定 orders 表的 order_id 与 arrivals 表的 order_id 一一对应。
    params:
      arrivals_table: 到达记录表名（默认 arrivals）
      expected_col:   预期到达时间列（默认 expected_arrival）
      actual_col:     实际到达时间列（默认 actual_arrival）
      tolerance_min:  允许的延迟分钟数（默认 30）
    """

    def evaluate(self, ctx: ExecutionContext) -> "RuleResult":
        arrivals_table = self.params.get("arrivals_table", "arrivals")
        expected_col = self.params.get("expected_col", "expected_arrival")
        actual_col = self.params.get("actual_col", "actual_arrival")
        tolerance_min = float(self.params.get("tolerance_min", 30))

        if arrivals_table not in ctx.tables:
            return self._make_result(0, 0, f"关联表 {arrivals_table!r} 未加载")
        a = ctx.tables[arrivals_table]
        for c in (expected_col, actual_col):
            if c not in a.columns:
                return self._make_result(0, 0, f"arrivals 缺少列 {c!r}")

        merged = ctx.df.merge(
            a[["order_id", expected_col, actual_col]],
            on="order_id",
            how="left",
        )
        exp = pd.to_datetime(merged[expected_col], errors="coerce")
        act = pd.to_datetime(merged[actual_col], errors="coerce")
        lag_min = (act - exp).dt.total_seconds() / 60.0
        # 缺失到达记录或超出容忍 = 失败
        bad = lag_min.isna() | (lag_min > tolerance_min)
        total = len(merged)
        failed = int(bad.sum())
        msg = (
            f"有 {failed}/{total} 条订单到达延迟超过 {tolerance_min} 分钟或缺失到达记录"
        )
        # sample 时回到原 orders 表上找行。merge 可能引入重复索引，用 reindex 安全对齐。
        bad_by_pos = pd.Series(bad.to_numpy(), index=merged.index)
        bad_mask = bad_by_pos.reindex(ctx.df.index, fill_value=False).astype(bool)
        samples, _meta = self._sample(ctx, bad_mask) if failed else ([], {"id_columns": [], "check_columns": []})
        return self._make_result(
            total=total,
            failed=failed,
            message=msg,
            sample_failures=samples,
            sample_meta=_meta,
        )