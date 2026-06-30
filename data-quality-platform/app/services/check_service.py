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
from app.detectors import accuracy  # noqa: F401
from app.engine import ExecutionContext, RuleRunner, load_ruleset
from app.loaders import get_loader
from app.reporting import build_report
from app.services import history_service


class CheckService:
    """封装一次检测的所有副作用（加载→执行→报告→持久化）。"""

    def __init__(self) -> None:
        init_db()

    def run_for_dataset(self, dataset: str) -> dict[str, Any]:
        """对内置数据集跑检测。

        为了保持向后兼容 + 让测试在不依赖 demo 数据的情况下也能跑通，
        当 GENERATED_DIR 里有 <dataset>.csv 时使用之；否则用一个最小示例。
        """
        ruleset_path = RULESET_DIR / f"{dataset}_rules.yaml"
        if not ruleset_path.exists():
            raise FileNotFoundError(f"规则集不存在: {ruleset_path}")

        csv_path = GENERATED_DIR / f"{dataset}.csv"
        if csv_path.exists():
            df = get_loader(csv_path).load(csv_path)
            tables = self._load_related_tables(dataset)
            source_file = str(csv_path.relative_to(GENERATED_DIR.parent.parent))
        else:
            # 没有 demo 数据 → 用一个最小化测试数据
            df = self._fallback_df_for(dataset)
            tables = {}
            source_file = f"(内置示例数据：{dataset})"

        ds_name, _desc, rules = load_ruleset(ruleset_path)
        ctx = ExecutionContext(df=df, tables=tables, config={"now": datetime.now()})
        summary = RuleRunner(dataset=ds_name).run(rules, ctx)
        report = build_report(summary)
        report["source_file"] = source_file
        report["ruleset_file"] = str(ruleset_path.relative_to(RULESET_DIR.parent.parent))
        report["row_count"] = int(len(df))
        report["columns"] = [str(c) for c in df.columns]
        report["id"] = history_service.save_report(report)
        return report

    @staticmethod
    def _fallback_df_for(dataset: str) -> pd.DataFrame:
        """当 demo CSV 不存在时，给出一份最小可用的样本数据。

        故意包含一些质量问题（缺失、格式错、枚举违规），让 tests 也能跑出有意义的失败样本。
        """
        return pd.DataFrame({
            "order_id": ["O000001", "O000002", "", "O000004", "O000005"],
            "customer_id": ["C00001", "C00002", "C00003", "C00004", "C00005"],
            "order_date": ["2026-06-29", "2026-06-28", "2026-06-29", "bad-date", "2026-06-30"],
            "order_amount": ["100.0", "200.0", "150.0", "300.0", "250.0"],
            "discount": ["10.0", "20.0", "30.0", "0.0", "5.0"],
            "paid_amount": ["90.0", "180.0", "120.0", "300.0", "245.0"],
            "refund_amount": ["0.0", "0.0", "0.0", "0.0", "0.0"],
            "order_status": ["paid", "paid", "shipped", "BAD", "delivered"],
            "customer_email": ["a@b.com", "c@d.com", "e@f.com", "g@h.com", "bad-email"],
        })

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
        report["row_count"] = int(len(df))
        report["columns"] = [str(c) for c in df.columns]
        report["id"] = history_service.save_report(report)
        return report

    def run_for_mysql(
        self,
        dataset: str,
        table_spec: str,
        ruleset_path: Path,
        related_tables: list[str] | None = None,
        query: dict | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """从 MySQL 拉取指定表进行检测。

        table_spec: "table_name" 或 "conn_name/table_name" 或 "mysql://...?table=x"
        related_tables: 同连接下的其它表名（用于外键/关联检查），例如 ["customers", "arrivals"]
        """
        from app.loaders.mysql import MysqlLoader

        if not ruleset_path.exists():
            raise FileNotFoundError(f"规则集不存在: {ruleset_path}")

        ds_name, _desc, rules = load_ruleset(ruleset_path)
        loader = MysqlLoader(query=query, limit=limit)
        df = loader.load(table_spec)
        # 关联表
        tables: dict[str, pd.DataFrame] = {}
        if related_tables:
            # 用同一连接前缀
            for rt in related_tables:
                try:
                    # spec 形如 "conn/table" → 把表名替换
                    rt_spec = self._swap_table(table_spec, rt) if "/" in table_spec else rt
                    rt_loader = MysqlLoader()
                    tables[rt] = rt_loader.load(rt_spec)
                except Exception:
                    pass
        ctx = ExecutionContext(df=df, tables=tables, config={"now": datetime.now()})
        summary = RuleRunner(dataset=ds_name).run(rules, ctx)
        report = build_report(summary)
        report["source_file"] = f"mysql://{table_spec}"
        report["source_type"] = "mysql"
        report["ruleset_file"] = str(ruleset_path)
        report["row_count"] = int(len(df))
        report["columns"] = [str(c) for c in df.columns]
        report["id"] = history_service.save_report(report)
        return report

    @staticmethod
    def _swap_table(spec: str, new_table: str) -> str:
        """把 "conn/table" 中的 table 换成 new_table。"""
        if "/" in spec:
            conn, _ = spec.split("/", 1)
            return f"{conn}/{new_table}"
        return new_table

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