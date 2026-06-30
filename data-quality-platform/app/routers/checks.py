"""检测路由：用户上传文件后触发检测，跳转到报告页（带 run_id）。"""
from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse

from app.config import RULESET_DIR, UPLOAD_DIR
from app.services import CheckService

router = APIRouter()
service = CheckService()
log = logging.getLogger("checks")


def _resolve_ruleset_path(name: str) -> Path | None:
    """按 name 找规则集文件。支持 orders / orders_rules 两种写法。"""
    for p in (RULESET_DIR / f"{name}.yaml", RULESET_DIR / f"{name}_rules.yaml"):
        if p.exists():
            return p
    return None


@router.post("/uploads")
async def upload_and_check(
    request: Request,
    file: UploadFile = File(...),
    ruleset: str = Form(...),
):
    try:
        filename = file.filename or "uploaded"
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex[:8]}_{Path(filename).name}"
        dest = UPLOAD_DIR / safe_name
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)

        ruleset_path = _resolve_ruleset_path(ruleset)
        if ruleset_path is None:
            raise FileNotFoundError(f"规则集不存在: {RULESET_DIR / f'{ruleset}.yaml'}")
        try:
            report = service.run_for_uploaded(
                dataset=Path(filename).stem,
                csv_path=dest,
                ruleset_path=ruleset_path,
            )
        except FileNotFoundError as e:
            log.warning("上传检测 规则集=%s 报错: %s", ruleset, e)
            return RedirectResponse(url=f"/upload?error={_enc(str(e))}", status_code=303)
        except Exception:
            log.exception("上传检测 失败 file=%s ruleset=%s", filename, ruleset)
            return RedirectResponse(url="/upload?error=internal", status_code=303)
    finally:
        try:
            file.file.close()
        except Exception:
            pass
    return RedirectResponse(url=f"/report/{report.get('id')}", status_code=303)


# ----------------- MySQL 数据源 -----------------


@router.get("/api/mysql/connections")
def mysql_connections():
    """列出所有已配置的 MySQL 连接（来自环境变量）。"""
    from app.loaders.mysql import list_connections
    return JSONResponse({"connections": list_connections()})


@router.get("/api/mysql/tables")
def mysql_tables(conn: str | None = None):
    """列出某连接下的所有表（需连接可用）。"""
    from app.loaders.mysql import list_tables
    try:
        tables = list_tables(conn)
        return JSONResponse({"connection": conn or "DEFAULT", "tables": tables})
    except Exception as e:
        return JSONResponse(
            {"error": str(e), "connection": conn or "DEFAULT"},
            status_code=400,
        )


@router.post("/mysql/check")
def mysql_check(
    request: Request,
    table_spec: str = Form(...),
    ruleset: str = Form(...),
    related_tables: str = Form(""),
    limit: int | None = Form(None),
):
    """从 MySQL 表直接拉取并检测。

    table_spec 形如 "orders" 或 "default/orders"（连接名/表名）
    related_tables: 逗号分隔的关联表名（可选）
    limit: 限制行数（可选）
    """
    ruleset_path = _resolve_ruleset_path(ruleset)
    if ruleset_path is None:
        return RedirectResponse(
            url=f"/upload?error={_enc(f'规则集不存在: {ruleset}')}",
            status_code=303,
        )
    rel = [t.strip() for t in related_tables.split(",") if t.strip()]
    try:
        report = service.run_for_mysql(
            dataset=table_spec.replace("/", "_"),
            table_spec=table_spec,
            ruleset_path=ruleset_path,
            related_tables=rel or None,
            limit=limit,
        )
    except FileNotFoundError as e:
        return RedirectResponse(url=f"/upload?error={_enc(str(e))}", status_code=303)
    except Exception as e:
        log.exception("MySQL 检测失败 table=%s", table_spec)
        return RedirectResponse(url=f"/upload?error={_enc(str(e))}", status_code=303)
    return RedirectResponse(url=f"/report/{report.get('id')}", status_code=303)


def _enc(msg: str) -> str:
    """URL-encode 中文错误消息。"""
    from urllib.parse import quote
    return quote(msg, safe="")