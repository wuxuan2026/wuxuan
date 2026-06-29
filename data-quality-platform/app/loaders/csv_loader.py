"""CSV 加载器，处理 Windows 中文 CSV 常见的 GBK 编码。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.loaders.base import DataLoader


class CSVLoader(DataLoader):
    """读 CSV，自动探测 utf-8 / gbk / gb18030 编码。"""

    def _read(self, path: Path) -> pd.DataFrame:
        for encoding in ("utf-8", "gbk", "gb18030"):
            try:
                return pd.read_csv(path, encoding=encoding, dtype=str, keep_default_na=False)
            except UnicodeDecodeError:
                continue
        return pd.read_csv(path, dtype=str, keep_default_na=False)