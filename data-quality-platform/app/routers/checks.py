"""检测路由：用户上传文件后触发检测，跳转到报告页（带 run_id）。"""
from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse

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


def _enc(msg: str) -> str:
    """URL-encode 中文错误消息。"""
    from urllib.parse import quote
    return quote(msg, safe="")