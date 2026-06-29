"""检测路由：触发一次检测并跳转到报告页（带 run_id）。"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse

from app.config import RULESET_DIR, UPLOAD_DIR
from app.services import CheckService

router = APIRouter()
service = CheckService()


@router.post("/checks/run")
def run_check(request: Request, dataset: str = Form(...)):
    try:
        report = service.run_for_dataset(dataset)
    except FileNotFoundError as e:
        request.session["flash"] = {"type": "error", "message": str(e)} if hasattr(request, "session") else None
        return RedirectResponse(url="/upload?error=1", status_code=303)
    return RedirectResponse(url=f"/report/{report.get('id')}", status_code=303)


@router.post("/uploads")
async def upload_and_check(
    request: Request,
    file: UploadFile = File(...),
    ruleset: str = Form(...),
):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex[:8]}_{Path(file.filename).name}"
    dest = UPLOAD_DIR / safe_name
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    ruleset_path = RULESET_DIR / f"{ruleset}.yaml"
    try:
        report = service.run_for_uploaded(
            dataset=Path(file.filename).stem,
            csv_path=dest,
            ruleset_path=ruleset_path,
        )
        return RedirectResponse(url=f"/report/{report.get('id')}", status_code=303)
    except FileNotFoundError as e:
        return RedirectResponse(url=f"/upload?error={e}", status_code=303)