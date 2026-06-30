"""FastAPI 入口。"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import ensure_dirs
from app.database import init_db
# 必须 import 子包以触发 @register，否则 REGISTRY 在某些 reload/uwsgi 场景下为空
from app.detectors import (  # noqa: F401
    accuracy, completeness, conformity, consistency, timeliness,
)
from app.routers import checks_router, pages_router

app = FastAPI(title="数据质量监测平台", version="0.3.0")

_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.on_event("startup")
def _startup() -> None:
    ensure_dirs()
    init_db()


app.include_router(pages_router)
app.include_router(checks_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}