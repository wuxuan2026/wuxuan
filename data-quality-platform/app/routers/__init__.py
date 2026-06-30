from app.routers.pages import router as pages_router
from app.routers.checks import router as checks_router
from app.routers.mysql_admin import router as mysql_admin_router

__all__ = ["pages_router", "checks_router", "mysql_admin_router"]