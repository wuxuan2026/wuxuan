"""MySQL 连接管理：CRUD 页面 + 表单提交。"""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.services import mysql_config_service as svc

router = APIRouter()
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@router.get("/mysql/connections", response_class=HTMLResponse)
def connections_page(request: Request):
    """连接管理主页：列表 + 入口。"""
    connections = svc.list_connections_masked()
    return templates.TemplateResponse(
        request,
        "mysql_connections.html",
        {"connections": connections},
    )


@router.get("/mysql/connections/new", response_class=HTMLResponse)
def new_connection_page(request: Request):
    """新增连接表单。"""
    return templates.TemplateResponse(
        request,
        "mysql_connection_edit.html",
        {
            "is_new": True,
            "form_action": "/mysql/connections/new",
            "conn": {
                "name": "",
                "host": "127.0.0.1",
                "port": 3306,
                "user": "root",
                "database": "",
                "password": "",
            },
        },
    )


@router.post("/mysql/connections/new")
def new_connection_submit(
    name: str = Form(...),
    host: str = Form(...),
    port: int = Form(3306),
    user: str = Form(...),
    password: str = Form(""),
    database: str = Form(...),
):
    if not name.strip():
        return RedirectResponse(url="/mysql/connections?error=name_required", status_code=303)
    if svc.get_connection(name):
        return RedirectResponse(url="/mysql/connections?error=name_exists", status_code=303)
    svc.upsert_connection(name=name, host=host, port=port, user=user, password=password, database=database)
    return RedirectResponse(url="/mysql/connections?ok=created", status_code=303)


@router.get("/mysql/connections/{name}/edit", response_class=HTMLResponse)
def edit_connection_page(request: Request, name: str):
    cfg = svc.get_connection(name)
    if not cfg:
        return RedirectResponse(url="/mysql/connections?error=not_found", status_code=303)
    # 密码不回显，让用户重新输入；UI 上用 "******" 占位
    masked = dict(cfg)
    masked["password"] = "******" if cfg.get("password") else ""
    return templates.TemplateResponse(
        request,
        "mysql_connection_edit.html",
        {
            "is_new": False,
            "form_action": f"/mysql/connections/{name}/edit",
            "conn": masked,
        },
    )


@router.post("/mysql/connections/{name}/edit")
def edit_connection_submit(
    name: str,
    host: str = Form(...),
    port: int = Form(3306),
    user: str = Form(...),
    password: str = Form(""),
    database: str = Form(...),
):
    if not svc.get_connection(name):
        return RedirectResponse(url="/mysql/connections?error=not_found", status_code=303)
    svc.upsert_connection(name=name, host=host, port=port, user=user, password=password, database=database)
    return RedirectResponse(url="/mysql/connections?ok=updated", status_code=303)


@router.post("/mysql/connections/{name}/delete")
def delete_connection(name: str):
    if not svc.delete_connection(name):
        return RedirectResponse(url="/mysql/connections?error=not_found", status_code=303)
    return RedirectResponse(url="/mysql/connections?ok=deleted", status_code=303)


@router.post("/mysql/connections/{name}/test")
def test_connection(name: str):
    result = svc.test_connection(name)
    return JSONResponse(result)


@router.get("/api/mysql/config")
def api_list():
    return JSONResponse({"connections": svc.list_connections_masked()})