"""Excel 加载器。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.loaders.base import DataLoader


class ExcelLoader(DataLoader):
    """读 xlsx/xls。"""

    def _read(self, path: Path) -> pd.DataFrame:
        engine = "openpyxl" if path.suffix.lower() in {".xlsx", ".xlsm"} else "xlrd"
        return pd.read_excel(path, dtype=str, keep_default_na=False, engine=engine)
