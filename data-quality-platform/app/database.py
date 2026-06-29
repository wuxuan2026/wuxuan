"""SQLite 连接 + 建表（每次启动时自动建表）。"""
from __future__ import annotations

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
)
from sqlalchemy.orm import DeclarativeBase, relationship, sessionmaker

from app.config import DATABASE_PATH


class Base(DeclarativeBase):
    pass


class CheckRun(Base):
    __tablename__ = "check_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset = Column(String(64), nullable=False, index=True)
    source_file = Column(String(255))
    ruleset_file = Column(String(255))
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
