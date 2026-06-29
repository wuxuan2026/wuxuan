"""集中配置：路径、阈值、评分权重。"""
from pathlib import Path

import pandas as pd  # noqa: F401  (保证依赖可见)

from app.settings import settings

# 路径（基于 settings，默认相对项目根目录）
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / settings.data_dir
UPLOAD_DIR = BASE_DIR / settings.upload_dir
GENERATED_DIR = BASE_DIR / settings.generated_dir
RULESET_DIR = BASE_DIR / settings.ruleset_dir
DATABASE_PATH = BASE_DIR / "data" / "quality.db"

# 失败样本展示上限
SAMPLE_LIMIT = settings.sample_limit

# 评分权重（可调）
DIMENSION_WEIGHTS = {
    "completeness": 0.35,
    "consistency": 0.25,
    "conformity": 0.25,
    "timeliness": 0.15,
}

# 规则严重等级权重
SEVERITY_WEIGHTS = {
    "blocker": 3,
    "major": 2,
    "minor": 1,
}

# 评分分级
def grade_of(score: float) -> str:
    if score >= 90:
        return "优秀"
    if score >= 75:
        return "良好"
    if score >= 60:
        return "合格"
    return "不合格"


def ensure_dirs() -> None:
    """启动时确保所需目录存在。"""
    for d in (DATA_DIR, UPLOAD_DIR, GENERATED_DIR, RULESET_DIR, DATABASE_PATH.parent):
        d.mkdir(parents=True, exist_ok=True)
