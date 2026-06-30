"""批量执行规则的 Runner。"""
from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from app.engine.base import ExecutionContext, Rule, RuleResult

log = logging.getLogger(__name__)


@dataclass
class RunSummary:
    started_at: datetime
    finished_at: datetime
    dataset: str
    rules_total: int
    rules_passed: int
    results: list[RuleResult] = field(default_factory=list)

    @property
    def duration_ms(self) -> int:
        return int((self.finished_at - self.started_at).total_seconds() * 1000)


class RuleRunner:
    def __init__(self, dataset: str = "default") -> None:
        self.dataset = dataset

    def run(self, rules: Iterable[Rule], ctx: ExecutionContext) -> RunSummary:
        started = datetime.now()
        results: list[RuleResult] = []
        rules_list = list(rules)
        passed = 0
        for rule in rules_list:
            try:
                r = rule.evaluate(ctx)
            except Exception as e:  # 单条规则失败不应中断整体
                log.exception("规则 %s 执行失败", getattr(rule, "id", "?"))
                r = RuleResult(
                    rule_id=getattr(rule, "id", "?"),
                    name=getattr(rule, "name", "?"),
                    dimension=getattr(rule, "dimension", "?"),
                    severity=getattr(rule, "severity", "major"),
                    passed=False,
                    total=len(ctx.df),
                    failed=len(ctx.df),
                    failure_rate=1.0,
                    error=f"{type(e).__name__}: {e}",
                    sample_failures=[],
                )
            if r.passed:
                passed += 1
            # 把规则的 type 也带到结果里（报告页可读）
            r.type = getattr(rule, "type", "")
            results.append(r)
        finished = datetime.now()
        return RunSummary(
            started_at=started,
            finished_at=finished,
            dataset=self.dataset,
            rules_total=len(rules_list),
            rules_passed=passed,
            results=results,
        )
