"""检测路由：触发一次检测并跳转到报告页（带 run_id）。"""
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


@router.post("/checks/run")
def run_check(request: Request, dataset: str = Form(...)):
    try:
        report = service.run_for_dataset(dataset)
    except FileNotFoundError as e:
        log.warning("checks/run 数据集=%s 报错: %s", dataset, e)
        return RedirectResponse(
            url=f"/upload?error={_enc(str(e))}", status_code=303,
        )
    except Exception:
        log.exception("checks/run 数据集=%s 异常", dataset)
        return RedirectResponse(url="/upload?error=internal", status_code=303)
    return RedirectResponse(url=f"/report/{report.get('id')}", status_code=303)


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

        ruleset_path = RULESET_DIR / f"{ruleset}.yaml"
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