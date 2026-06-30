"""Excel 加载器。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.loaders.base import DataLoader


class ExcelLoader(DataLoader):
    """读 xlsx/xls（按后缀选 engine）。"""

    def _read(self, path: Path) -> pd.DataFrame:
        suffix = path.suffix.lower()
        try:
            if suffix in {".xlsx", ".xlsm"}:
                engine = "openpyxl"
            elif suffix == ".xls":
                engine = "xlrd"
            else:
                raise ValueError(f"不支持的 Excel 后缀: {suffix}")
            return pd.read_excel(
                path, dtype=str, keep_default_na=False, engine=engine,
            )
        except ImportError as e:
            missing = "openpyxl" if engine == "openpyxl" else "xlrd"
            raise RuntimeError(
                f"读取 {suffix} 需要安装 {missing}：pip install {missing}"
            ) from e
