"""命令行入口：python -m app.cli check <dataset>"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from app.config import GENERATED_DIR, RULESET_DIR
from app.detectors import completeness  # noqa: F401
from app.detectors import conformity  # noqa: F401
from app.detectors import consistency  # noqa: F401
from app.detectors import timeliness  # noqa: F401
from app.engine import ExecutionContext, RuleRunner, load_ruleset
from app.engine.registry import REGISTRY
from app.loaders import get_loader
from app.reporting import build_report


def _load_table(name: str) -> "pd.DataFrame":
    from app.loaders import get_loader as _gl

    path = GENERATED_DIR / f"{name}.csv"
    if not path.exists():
        return None  # type: ignore
    return _gl(path).load(path)


def check_dataset(dataset: str, data_dir: Path | None = None) -> dict:
    ruleset_path = (data_dir or RULESET_DIR) / f"{dataset}_rules.yaml"
    csv_path = (data_dir or GENERATED_DIR) / f"{dataset}.csv"
    if not ruleset_path.exists():
        raise FileNotFoundError(f"规则集不存在: {ruleset_path}")
    if not csv_path.exists():
        raise FileNotFoundError(f"数据文件不存在: {csv_path}")

    ds_name, _desc, rules = load_ruleset(ruleset_path)
    df = get_loader(csv_path).load(csv_path)

    # 关联表：默认把同目录的其它 csv 一并加载（按文件名做 key）
    tables: dict[str, "pd.DataFrame"] = {}
    for p in (data_dir or GENERATED_DIR).glob("*.csv"):
        name = p.stem
        if name == dataset:
            continue
        tables[name] = get_loader(p).load(p)

    ctx = ExecutionContext(df=df, tables=tables, config={"now": datetime.now()})
    summary = RuleRunner(dataset=ds_name).run(rules, ctx)
    return build_report(summary)


def main() -> None:
    parser = argparse.ArgumentParser(description="数据质量检测 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("rules", help="列出所有已注册规则类型")
    p_check = sub.add_parser("check", help="对指定数据集跑规则集")
    p_check.add_argument("dataset", help="数据集名（对应 data/generated/<name>.csv 和 data/rulesets/<name>_rules.yaml）")

    args = parser.parse_args()
    if args.cmd == "rules":
        print("已注册规则类型：")
        for name in sorted(REGISTRY):
            print(f"  - {name}")
        return
    if args.cmd == "check":
        report = check_dataset(args.dataset)
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()