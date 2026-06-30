"""SQLite 连接 + 建表 + 轻量迁移（每次启动时自动建表 + 给老表加新列）。"""
from __future__ import annotations

import logging

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

from app.config import DATABASE_PATH

log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class CheckRun(Base):
    __tablename__ = "check_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset = Column(String(64), nullable=False, index=True)
    source_file = Column(String(255))
    ruleset_file = Column(String(255))
    row_count = Column(Integer, nullable=False, default=0)  # 数据总行数
    columns_json = Column(JSON)  # 列名列表
    total_score = Column(Float, nullable=False)
    grade = Column(String(16), nullable=False)
    rules_total = Column(Integer, nullable=False)
    rules_passed = Column(Integer, nullable=False)
    rules_failed = Column(Integer, nullable=False)
    dimension_scores = Column(JSON, nullable=False)
    severity_summary = Column(JSON, nullable=False)
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, nullable=False)
    duration_ms = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False)
    rule_results = relationship("RuleResultRow", back_populates="run", cascade="all, delete-orphan")


class RuleResultRow(Base):
    __tablename__ = "rule_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("check_runs.id"), nullable=False, index=True)
    rule_id = Column(String(64), nullable=False)
    name = Column(String(128), nullable=False)
    dimension = Column(String(32), nullable=False)
    severity = Column(String(16), nullable=False)
    passed = Column(Boolean, nullable=False)
    total = Column(Integer, nullable=False)
    failed = Column(Integer, nullable=False)
    failure_rate = Column(Float, nullable=False)
    message = Column(Text, default="")
    error = Column(Text, nullable=True)
    sample_failures = Column(JSON, nullable=False, default=list)
    run = relationship("CheckRun", back_populates="rule_results")


engine = create_engine(f"sqlite:///{DATABASE_PATH}", echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)


def init_db() -> None:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    _migrate()  # 轻量迁移：给老表加新列


# 期望的 (列名, 类型) 集合，用于给老 SQLite 补列。type 仅为文档，实际用 SQL 类型。
_EXPECTED_COLUMNS: list[tuple[str, str]] = [
    ("row_count", "INTEGER NOT NULL DEFAULT 0"),
    ("columns_json", "JSON"),
]


def _migrate() -> None:
    """检测 check_runs 是否缺新列，缺则 ALTER TABLE ADD COLUMN。
    SQLite 不支持 IF NOT EXISTS for ADD COLUMN，所以先用 inspect 查。
    """
    insp = inspect(engine)
    if "check_runs" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("check_runs")}
    with engine.begin() as conn:
        for col, ddl in _EXPECTED_COLUMNS:
            if col not in existing:
                log.info("迁移：ALTER TABLE check_runs ADD COLUMN %s", col)
                conn.execute(text(f"ALTER TABLE check_runs ADD COLUMN {col} {ddl}"))
