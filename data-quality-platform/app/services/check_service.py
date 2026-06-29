"""业务编排层：把数据加载 → 引擎执行 → 报告汇总 → 历史持久化 串起来。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.config import GENERATED_DIR, RULESET_DIR
from app.database import init_db
from app.detectors import completeness  # noqa: F401
from app.detectors import conformity  # noqa: F401
from app.detectors import consistency  # noqa: F401
from app.detectors import timeliness  # noqa: F401
from app.engine import ExecutionContext, RuleRunner, load_ruleset
from app.loaders import get_loader
from app.reporting import build_report
from app.services import history_service


class CheckService:
    """封装一次检测的所有副作用（加载→执行→报告→持久化）。"""

    def __init__(self) -> None:
        init_db()

    def run_for_dataset(self, dataset: str) -> dict[str, Any]:
        ruleset_path = RULESET_DIR / f"{dataset}_rules.yaml"
        csv_path = GENERATED_DIR / f"{dataset}.csv"
        if not ruleset_path.exists():
            raise FileNotFoundError(f"规则集不存在: {ruleset_path}")
        if not csv_path.exists():
            raise FileNotFoundError(f"数据文件不存在: {csv_path}")

        ds_name, _desc, rules = load_ruleset(ruleset_path)
        df = get_loader(csv_path).load(csv_path)
        tables = self._load_related_tables(dataset)
        ctx = ExecutionContext(df=df, tables=tables, config={"now": datetime.now()})
        summary = RuleRunner(dataset=ds_name).run(rules, ctx)
        report = build_report(summary)
        report["source_file"] = str(csv_path.relative_to(GENERATED_DIR.parent.parent))
        report["ruleset_file"] = str(ruleset_path.relative_to(RULESET_DIR.parent.parent))
        report["id"] = history_service.save_report(report)
        return report

    def run_for_uploaded(
        self, dataset: str, csv_path: Path, ruleset_path: Path
    ) -> dict[str, Any]:
        """用户上传文件后的检测（ruleset 必须存在）。"""
        if not ruleset_path.exists():
            raise FileNotFoundError(f"规则集不存在: {ruleset_path}")
        if not csv_path.exists():
            raise FileNotFoundError(f"数据文件不存在: {csv_path}")
        ds_name, _desc, rules = load_ruleset(ruleset_path)
        df = get_loader(csv_path).load(csv_path)
        tables: dict[str, pd.DataFrame] = {}
        if csv_path.parent.exists():
            for p in csv_path.parent.glob("*.csv"):
                if p.resolve() == csv_path.resolve():
                    continue
                try:
                    tables[p.stem] = get_loader(p).load(p)
                except Exception:
                    pass
        ctx = ExecutionContext(df=df, tables=tables, config={"now": datetime.now()})
        summary = RuleRunner(dataset=ds_name).run(rules, ctx)
        report = build_report(summary)
        report["source_file"] = str(csv_path)
        report["ruleset_file"] = str(ruleset_path)
        report["uploaded_filename"] = str(csv_path.name)
        report["id"] = history_service.save_report(report)
        return report

    @staticmethod
    def _load_related_tables(dataset: str) -> dict[str, pd.DataFrame]:
        out: dict[str, pd.DataFrame] = {}
        if not GENERATED_DIR.exists():
            return out
        for p in GENERATED_DIR.glob("*.csv"):
            if p.stem == dataset:
                continue
            try:
                out[p.stem] = get_loader(p).load(p)
            except Exception:
                pass
        return out