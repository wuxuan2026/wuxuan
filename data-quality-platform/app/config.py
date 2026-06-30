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

# 评分权重（可调）。6 维度平均 0.1666，可按业务侧重调整。
DIMENSION_WEIGHTS = {
    "completeness": 0.20,
    "uniqueness": 0.15,
    "conformity": 0.15,
    "accuracy": 0.20,
    "consistency": 0.15,
    "timeliness": 0.15,
}

# 规则严重等级权重
SEVERITY_WEIGHTS = {
    "blocker": 3,
    "major": 2,
    "minor": 1,
}

# 严重等级的中文标签（前端显示用）
SEVERITY_LABELS = {
    "blocker": "阻断",
    "major": "主要",
    "minor": "次要",
}

# 规则类型的中文标签（key=注册表 type 名，value=展示用中文）
# 未知类型会原样展示英文（不报错），所以新加规则类型不强制改这里。
RULE_TYPE_LABELS = {
    "not_null": "非空检查",
    "no_duplicates": "无重复",
    "range": "值域范围",
    "primary_key": "主键唯一",
    "type": "类型检查",
    "regex": "正则匹配",
    "enum": "枚举值",
    "sum_check": "求和校验",
    "statistical": "统计异常",
    "cross_field": "跨字段比较",
    "foreign_key": "外键引用",
    "freshness": "新鲜度",
    "arrival": "到达及时",
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
