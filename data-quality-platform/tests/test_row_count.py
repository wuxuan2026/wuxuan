"""报告对象必须包含 row_count（数据总行数）和 columns（列名列表）。"""
from __future__ import annotations

from pathlib import Path


def test_check_service_includes_row_count_for_dataset():
    """run_for_dataset 报告里必须有 row_count（数据总行数）。

    注：删除 demo 数据后 run_for_dataset 会用内置 fallback 测试数据。
    """
    from app.services.check_service import CheckService
    svc = CheckService()
    r = svc.run_for_dataset("orders")
    assert "row_count" in r, "报告缺少 row_count"
    assert isinstance(r["row_count"], int)
    assert r["row_count"] > 0, f"row_count 应 > 0，实际 {r['row_count']}"


def test_check_service_includes_columns():
    from app.services.check_service import CheckService
    svc = CheckService()
    r = svc.run_for_dataset("orders")
    assert "columns" in r
    assert isinstance(r["columns"], list)
    assert len(r["columns"]) > 0
    # 关键列要在
    for col in ("order_id", "customer_id", "order_amount", "order_status"):
        assert col in r["columns"]


def test_uploaded_check_includes_row_count():
    """上传路径：row_count 必须正确反映上传文件的行数。"""
    import tempfile
    from app.services.check_service import CheckService
    csv = (
        "order_id,customer_id,order_date,order_amount,discount,paid_amount,refund_amount,order_status,customer_email\n"
        "O000001,C00001,2026-06-29,100.0,10.0,90.0,0.0,paid,a@b.com\n"
        "O000002,C00002,2026-06-29,200.0,20.0,180.0,0.0,paid,a@b.com\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(csv)
        tmp = f.name
    try:
        svc = CheckService()
        r = svc.run_for_uploaded(
            dataset="orders",
            csv_path=Path(tmp),
            ruleset_path=Path("data/rulesets/orders_rules.yaml"),
        )
        assert r["row_count"] == 2
        assert len(r["columns"]) > 0
    finally:
        Path(tmp).unlink()


def test_persistence_includes_row_count():
    """历史数据库的 check_runs 表必须持久化 row_count。"""
    from app.database import SessionLocal, CheckRun
    from app.services.check_service import CheckService
    svc = CheckService()
    r = svc.run_for_dataset("orders")
    # 再次从 db 读出来验证
    with SessionLocal() as s:
        run = s.get(CheckRun, r["id"])
        assert run is not None
        assert run.row_count > 0
        assert run.columns_json is not None
        assert len(run.columns_json) > 0


def test_report_page_renders_row_count():
    """报告页 HTML 必须显示 row_count。"""
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    # 先跑一次得到 run_id
    from app.services.check_service import CheckService
    svc = CheckService()
    r = svc.run_for_dataset("orders")
    run_id = r["id"]
    # 拉页面
    resp = c.get(f"/report/{run_id}")
    assert resp.status_code == 200
    assert "数据条数" in resp.text
    assert str(r["row_count"]) in resp.text


def test_db_migration_adds_row_count_column():
    """模拟从老 db（无 row_count 列）升级：_migrate 应自动 ALTER TABLE。"""
    import sqlite3
    import tempfile
    from pathlib import Path
    from sqlalchemy import create_engine

    # 1) 手工建老 schema（无 row_count / columns_json）
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        old_db = f.name
    conn = sqlite3.connect(old_db)
    conn.executescript("""
        CREATE TABLE check_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dataset VARCHAR(64) NOT NULL,
            source_file VARCHAR(255),
            ruleset_file VARCHAR(255),
            total_score FLOAT NOT NULL,
            grade VARCHAR(16) NOT NULL,
            rules_total INTEGER NOT NULL,
            rules_passed INTEGER NOT NULL,
            rules_failed INTEGER NOT NULL,
            dimension_scores JSON NOT NULL,
            severity_summary JSON NOT NULL,
            started_at DATETIME NOT NULL,
            finished_at DATETIME NOT NULL,
            duration_ms INTEGER NOT NULL,
            created_at DATETIME NOT NULL
        );
        CREATE TABLE rule_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            rule_id VARCHAR(64) NOT NULL,
            name VARCHAR(128) NOT NULL,
            dimension VARCHAR(32) NOT NULL,
            severity VARCHAR(16) NOT NULL,
            passed BOOLEAN NOT NULL,
            total INTEGER NOT NULL,
            failed INTEGER NOT NULL,
            failure_rate FLOAT NOT NULL,
            message TEXT DEFAULT '',
            error TEXT,
            sample_failures JSON NOT NULL DEFAULT '[]'
        );
    """)
    conn.commit()
    conn.close()

    # 2) 拿这个老 db 跑 _migrate
    from app import database as db_mod
    old_engine = create_engine(f"sqlite:///{old_db}", future=True)
    # 替换 module 里的 engine
    orig_engine = db_mod.engine
    orig_session = db_mod.SessionLocal
    db_mod.engine = old_engine
    db_mod.SessionLocal = db_mod.sessionmaker(bind=old_engine, autoflush=False, future=True)
    try:
        db_mod._migrate()
        insp = db_mod.inspect(old_engine)
        cols = {c["name"] for c in insp.get_columns("check_runs")}
        assert "row_count" in cols
        assert "columns_json" in cols
    finally:
        db_mod.engine = orig_engine
        db_mod.SessionLocal = orig_session
        try:
            Path(old_db).unlink()
        except OSError:
            pass  # Windows 下文件句柄偶尔未释放