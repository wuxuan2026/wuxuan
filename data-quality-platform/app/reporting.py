"""报告汇总：把 RunSummary + 评分打包成可序列化的字典。"""
from __future__ import annotations

from dataclasses import asdict

from app.engine.runner import RunSummary
from app.scoring import summarize


def build_report(summary: RunSummary) -> dict:
    """生成报告 dict，供模板渲染和后续持久化使用。"""
    s = summarize(summary.results)
    return {
        "dataset": summary.dataset,
        "started_at": summary.started_at.isoformat(timespec="seconds"),
        "finished_at": summary.finished_at.isoformat(timespec="seconds"),
        "duration_ms": summary.duration_ms,
        **s,
        "results": [asdict(r) for r in summary.results],
    }