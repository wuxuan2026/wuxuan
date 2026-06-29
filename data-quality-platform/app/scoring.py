"""质量评分模型：单规则通过率 → 维度分（severity 加权）→ 总分（四维度加权）。"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from app.config import DIMENSION_WEIGHTS, SEVERITY_WEIGHTS, grade_of
from app.engine.base import RuleResult


def dimension_scores(results: Iterable[RuleResult]) -> dict[str, float]:
    """计算每个维度的 0-100 分。"""
    by_dim: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for r in results:
        if r.error:
            # 出错的规则按 0 通过率计入
            pass_rate = 0.0
        else:
            pass_rate = r.pass_rate
        weight = SEVERITY_WEIGHTS.get(r.severity, 2)
        by_dim[r.dimension].append((pass_rate, weight))

    out: dict[str, float] = {}
    for dim, lst in by_dim.items():
        total_w = sum(w for _, w in lst)
        if total_w == 0:
            out[dim] = 100.0
        else:
            out[dim] = sum(p * w for p, w in lst) / total_w * 100
    return out


def total_score(dim_scores: dict[str, float]) -> float:
    """按维度权重聚合 0-100 总分。

    无规则的维度按 100 分计入（避免"没配规则"被误判为失败）。
    """
    if not dim_scores:
        return 0.0
    num = sum(dim_scores.get(d, 100.0) * w for d, w in DIMENSION_WEIGHTS.items())
    den = sum(DIMENSION_WEIGHTS.values())
    return num / den if den else 0.0


def summarize(results: list[RuleResult]) -> dict:
    """把评分结果聚合成一个 dict，方便模板和持久化使用。"""
    ds = dimension_scores(results)
    ts = total_score(ds)
    return {
        "total_score": round(ts, 2),
        "grade": grade_of(ts),
        "dimension_scores": {k: round(v, 2) for k, v in ds.items()},
        "rules_total": len(results),
        "rules_passed": sum(1 for r in results if r.passed),
        "rules_failed": sum(1 for r in results if not r.passed),
        "by_severity": {
            sev: {
                "total": sum(1 for r in results if r.severity == sev),
                "failed": sum(1 for r in results if r.severity == sev and not r.passed),
            }
            for sev in ("blocker", "major", "minor")
        },
    }