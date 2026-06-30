"""页面路由：首页、上传、报告、规则集、历史。"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import GENERATED_DIR, RULESET_DIR
from app.detectors import completeness  # noqa: F401
from app.detectors import conformity  # noqa: F401
from app.detectors import consistency  # noqa: F401
from app.detectors import timeliness  # noqa: F401
from app.detectors import accuracy  # noqa: F401
from app.engine.loader_yaml import load_ruleset_raw, rule_summary
from app.engine.registry import REGISTRY
from app.services import history_service

router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

DIMENSION_LABELS = {
    "completeness": "完整性",
    "uniqueness": "唯一性",
    "conformity": "规范性",
    "accuracy": "准确性",
    "consistency": "一致性",
    "timeliness": "时效性",
}


def _available_datasets() -> list[dict]:
    out = []
    if RULESET_DIR.exists():
        for yp in sorted(RULESET_DIR.glob("*_rules.yaml")):
            name = yp.stem.replace("_rules", "")
            csv = GENERATED_DIR / f"{name}.csv"
            out.append({
                "name": name,
                "yaml": str(yp.relative_to(yp.parents[1])),
                "csv": str(csv.relative_to(csv.parents[2])) if csv.exists() else "(未生成)",
            })
    return out


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    runs = history_service.list_runs(limit=10)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "rule_types": sorted(REGISTRY.keys()),
            "datasets": _available_datasets(),
            "recent_runs": runs,
            "latest": runs[0] if runs else None,
        },
    )


@router.get("/upload", response_class=HTMLResponse)
def upload(request: Request):
    rulesets = sorted(p.stem for p in RULESET_DIR.glob("*.yaml"))
    return templates.TemplateResponse(
        request,
        "upload.html",
        {
            "datasets": [d["name"] for d in _available_datasets()],
            "rulesets": rulesets,
        },
    )


@router.get("/rulesets", response_class=HTMLResponse)
def rulesets(request: Request):
    items = []
    for yp in sorted(RULESET_DIR.glob("*.yaml")):
        try:
            raw = load_ruleset_raw(yp)
        except Exception as e:
            items.append({
                "name": yp.stem,
                "path": str(yp),
                "content": yp.read_text(encoding="utf-8"),
                "error": str(e),
                "rules": [],
                "description": "",
                "default_severity": "major",
            })
            continue
        default_severity = (raw.get("defaults") or {}).get("severity", "major")
        rule_rows = [rule_summary(r, default_severity) for r in raw.get("rules", [])]
        items.append({
            "name": yp.stem,
            "path": str(yp),
            "content": yp.read_text(encoding="utf-8"),
            "description": raw.get("description", ""),
            "default_severity": default_severity,
            "rules": rule_rows,
        })
    return templates.TemplateResponse(
        request,
        "rulesets.html",
        {"items": items, "dimension_labels": DIMENSION_LABELS},
    )


@router.get("/rulesets/{name}/edit", response_class=HTMLResponse)
def ruleset_edit(request: Request, name: str):
    path = RULESET_DIR / f"{name}.yaml"
    if not path.exists():
        return RedirectResponse(url="/rulesets", status_code=303)
    return templates.TemplateResponse(
        request,
        "ruleset_edit.html",
        {"name": name, "content": path.read_text(encoding="utf-8")},
    )


@router.post("/rulesets/{name}/edit")
def ruleset_edit_save(request: Request, name: str, content: str = Form(...)):
    path = RULESET_DIR / f"{name}.yaml"
    if not path.exists():
        return RedirectResponse(url="/rulesets", status_code=303)
    # 简单 YAML 语法校验（不能 parse 就回写）
    try:
        import yaml
        yaml.safe_load(content)
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "ruleset_edit.html",
            {"name": name, "content": content, "flash": {"type": "error", "message": f"YAML 解析失败: {e}"}},
        )
    path.write_text(content, encoding="utf-8")
    return RedirectResponse(url="/rulesets", status_code=303)


@router.get("/report/{run_id}", response_class=HTMLResponse)
def report(request: Request, run_id: int):
    report_data = history_service.get_run(run_id)
    if report_data is None:
        return templates.TemplateResponse(
            request,
            "upload.html",
            {
                "datasets": [d["name"] for d in _available_datasets()],
                "rulesets": [],
                "flash": {"type": "warning", "message": f"找不到 run_id={run_id} 的报告"},
            },
        )
    return templates.TemplateResponse(
        request,
        "report.html",
        {"report": report_data, "dimension_labels": DIMENSION_LABELS},
    )


@router.get("/report/{run_id}/rule/{rule_id}", response_class=HTMLResponse)
def report_rule_detail(request: Request, run_id: int, rule_id: str):
    rule_data = history_service.get_rule_result(run_id, rule_id)
    report_data = history_service.get_run(run_id)
    if rule_data is None or report_data is None:
        return RedirectResponse(url=f"/report/{run_id}", status_code=303)
    return templates.TemplateResponse(
        request,
        "rule_detail.html",
        {
            "rule": rule_data,
            "run_id": run_id,
            "report": report_data,
            "dimension_labels": DIMENSION_LABELS,
        },
    )


@router.get("/history", response_class=HTMLResponse)
def history(request: Request):
    runs = history_service.list_runs(limit=100)
    # 计算趋势点（按 created_at 升序）
    runs_asc = sorted(runs, key=lambda r: r["created_at"])
    trend = json.dumps(
        [{"x": r["created_at"], "y": r["total_score"], "dataset": r["dataset"]} for r in runs_asc]
    )
    return templates.TemplateResponse(
        request,
        "history.html",
        {"runs": runs, "trend_json": trend},
    )