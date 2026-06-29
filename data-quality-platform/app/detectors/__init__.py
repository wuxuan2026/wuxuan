"""规则检测器实现，导入以触发 @register 装饰器。"""
from app.detectors import completeness  # noqa: F401
from app.detectors import conformity  # noqa: F401
from app.detectors import consistency  # noqa: F401
from app.detectors import timeliness  # noqa: F401