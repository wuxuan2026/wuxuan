"""历史服务：把检测结果写入 SQLite；查询历史/单次报告。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.database import CheckRun, RuleResultRow, SessionLocal


def save_report(report: dict) -> int:
    """持久化一次报告，返回 run_id。"""
    with SessionLocal() as s:
        run = CheckRun(
            dataset=report["dataset"],
            source_file=report.get("source_file", ""),
            ruleset_file=report.get("ruleset_file", ""),
            total_score=report["total_score"],
            grade=report["grade"],
            rules_total=report["rules_total"],
            rules_passed=report["rules_passed"],
            rules_failed=report["rules_failed"],
            dimension_scores=report["dimension_scores"],
            severity_summary=report["by_severity"],
            started_at=datetime.fromisoformat(report["started_at"]),
            finished_at=datetime.fromisoformat(report["finished_at"]),
            duration_ms=report["duration_ms"],
            created_at=datetime.now(),
        )
        s.add(run)
        s.flush()
        for r in report["results"]:
            s.add(RuleResultRow(
                run_id=run.id,
                rule_id=r["rule_id"],
                name=r["name"],
                dimension=r["dimension"],
                severity=r["severity"],
                passed=bool(r["passed"]),
                total=int(r["total"]),
                failed=int(r["failed"]),
                failure_rate=float(r["failure_rate"]),
                message=r.get("message", ""),
                error=r.get("error"),
                sample_failures=r.get("sample_failures", []),
            ))
        s.commit()
        return run.id


def list_runs(limit: int = 50) -> list[dict[str, Any]]:
    with SessionLocal() as s:
        runs = (
            s.query(CheckRun)
            .order_by(CheckRun.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "dataset": r.dataset,
                "source_file": r.source_file,
                "total_score": r.total_score,
                "grade": r.grade,
                "rules_total": r.rules_total,
                "rules_passed": r.rules_passed,
                "rules_failed": r.rules_failed,
                "created_at": r.created_at.isoformat(timespec="seconds"),
            }
            for r in runs
        ]


def get_run(run_id: int) -> dict[str, Any] | None:
    with SessionLocal() as s:
        r = s.get(CheckRun, run_id)
        if r is None:
            return None
        return _run_to_report(r)


def get_rule_result(run_id: int, rule_id: str) -> dict[str, Any] | None:
    with SessionLocal() as s:
        row = (
            s.query(RuleResultRow)
            .filter(RuleResultRow.run_id == run_id, RuleResultRow.rule_id == rule_id)
            .first()
        )
        if row is None:
            return None
        return {
            "rule_id": row.rule_id,
            "name": row.name,
            "dimension": row.dimension,
            "severity": row.severity,
            "passed": row.passed,
            "total": row.total,
            "failed": row.failed,
            "failure_rate": row.failure_rate,
            "message": row.message,
            "error": row.error,
            "sample_failures": row.sample_failures or [],
        }


def _run_to_report(r: CheckRun) -> dict[str, Any]:
    return {
        "id": r.id,
        "dataset": r.dataset,
        "source_file": r.source_file,
        "ruleset_file": r.ruleset_file,
        "total_score": r.total_score,
        "grade": r.grade,
        "rules_total": r.rules_total,
        "rules_passed": r.rules_passed,
        "rules_failed": r.rules_failed,
        "dimension_scores": r.dimension_scores,
        "by_severity": r.severity_summary,
        "started_at": r.started_at.isoformat(timespec="seconds"),
        "finished_at": r.finished_at.isoformat(timespec="seconds"),
        "duration_ms": r.duration_ms,
        "created_at": r.created_at.isoformat(timespec="seconds"),
        "results": [
            {
                "rule_id": rr.rule_id,
                "name": rr.name,
                "dimension": rr.dimension,
                "severity": rr.severity,
                "passed": rr.passed,
                "total": rr.total,
                "failed": rr.failed,
                "failure_rate": rr.failure_rate,
                "message": rr.message,
                "error": rr.error,
                "sample_failures": rr.sample_failures or [],
            }
            for rr in r.rule_results
        ],
    }