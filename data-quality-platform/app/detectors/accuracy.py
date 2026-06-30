"""准确性规则：业务计算、统计异常、量级合理性。

与一致性 (consistency) 的差别：一致性检查字段间的逻辑关系（不变量），
准确性检查数值是否与业务事实相符（求和、统计分布等）。
"""
from __future__ import annotations

import pandas as pd

from app.engine.base import ExecutionContext, Rule, RuleResult
from app.engine.registry import register


def _to_numeric(s: pd.Series) -> pd.Series:
    """把列转成数值，无法解析的变为 NaN。空字符串/None 视作 NaN。"""
    s = s.astype(str).str.strip()
    s = s.replace({"": pd.NA, "None": pd.NA, "null": pd.NA, "nan": pd.NA})
    return pd.to_numeric(s, errors="coerce")


@register("sum_check")
class SumCheckRule(Rule):
    """检查一组数值列求和是否等于目标列。

    YAML 用法：
      columns: [paid_amount, refund_amount]
      params:
        target: order_amount
        tol: 0.01        # 浮点容忍误差，默认 0
        allow_partial: true  # 任一列缺失即跳过该行，默认 True
    """

    def evaluate(self, ctx: ExecutionContext) -> RuleResult:
        if len(self.columns) < 1:
            return self._make_result(0, 0, "未指定 columns")
        target = self.params.get("target")
        if not target or target not in ctx.df.columns:
            return self._make_result(0, 0, f"params.target {target!r} 不存在")
        tol = float(self.params.get("tol", 0))
        allow_partial = bool(self.params.get("allow_partial", True))

        src_cols = [c for c in self.columns if c in ctx.df.columns]
        if not src_cols:
            return self._make_result(0, 0, "columns 中的列都不存在")

        # 转数值
        src = ctx.df[src_cols].apply(_to_numeric)
        tgt = _to_numeric(ctx.df[target])

        # 是否完整行（所有相关列都非空）
        complete_mask = tgt.notna() & src.notna().all(axis=1)
        if not allow_partial:
            # 不允许缺失：那缺失行也视为失败
            missing_mask = (~complete_mask) & (tgt.notna() | src.notna().any(axis=1))
            failed_idx = missing_mask.copy()
        else:
            failed_idx = pd.Series(False, index=ctx.df.index)

        # 计算 |sum - target| > tol 的行
        sums = src.sum(axis=1, skipna=True)
        diff = (sums - tgt).abs()
        bad_calc = complete_mask & (diff > tol)
        failed_idx = failed_idx | bad_calc
        failed = int(failed_idx.sum())
        total = int(complete_mask.sum()) if allow_partial else len(ctx.df)
        msg = (
            f"{'+'.join(src_cols)} 之和应等于 {target}（容差 {tol}），"
            f"共 {failed}/{total} 条不满足"
        )
        samples, _meta = self._sample(ctx, failed_idx) if failed else ([], {"id_columns": [], "check_columns": []})
        return self._make_result(
            total=total,
            failed=failed,
            message=msg,
            sample_failures=samples,
            sample_meta=_meta,
        )


@register("statistical")
class StatisticalRule(Rule):
    """统计异常检测：用均值 ± k * 标准差判断是否合理。

    YAML 用法：
      column: order_amount
      params:
        min: 0            # 下界（绝对值）
        max: 100000       # 上界
        k: 3              # 均值 ± k*std 之外视为异��
    其中 min/max 与 k 至少给一个。
    """

    def evaluate(self, ctx: ExecutionContext) -> RuleResult:
        if not self.columns:
            return self._make_result(0, 0, "未指定列")
        col = self.columns[0]
        if col not in ctx.df.columns:
            return self._make_result(0, 0, f"列 {col!r} 不存在")

        min_v = self.params.get("min")
        max_v = self.params.get("max")
        k = self.params.get("k")
        if min_v is None and max_v is None and k is None:
            return self._make_result(0, 0, "params 至少需要 min/max/k 之一")

        s = _to_numeric(ctx.df[col])
        non_null = s.dropna()
        total = len(s)
        if total == 0:
            return self._make_result(0, 0, "列全为空")

        bad = pd.Series(False, index=s.index)
        bounds_msgs = []
        if min_v is not None or max_v is not None:
            lo = -float("inf") if min_v is None else float(min_v)
            hi = float("inf") if max_v is None else float(max_v)
            out_of_range = (s < lo) | (s > hi)
            bad = bad | out_of_range.fillna(False)
            bounds_msgs.append(f"范围 [{lo}, {hi}]")
        if k is not None and len(non_null) >= 2:
            mu = non_null.mean()
            sigma = non_null.std(ddof=0)
            if sigma and sigma > 0:
                kk = float(k)
                lower = mu - kk * sigma
                upper = mu + kk * sigma
                anomaly = (s < lower) | (s > upper)
                bad = bad | anomaly.fillna(False)
                bounds_msgs.append(f"均值±{kk}σ=[{lower:.2f}, {upper:.2f}]")

        failed = int(bad.sum())
        msg = f"列 {col} 有 {failed}/{total} 条异常（违反 {'/'.join(bounds_msgs) or '无约束'}）"
        samples, _meta = self._sample(ctx, bad) if failed else ([], {"id_columns": [], "check_columns": []})
        return self._make_result(
            total=total,
            failed=failed,
            message=msg,
            sample_failures=samples,
            sample_meta=_meta,
        )