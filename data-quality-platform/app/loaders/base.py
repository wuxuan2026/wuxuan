"""数据加载层抽象基类 + 工厂。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd


class DataLoader(ABC):
    """加载数据文件并做基础规范化：列名去空白。"""

    def load(self, path: str | Path) -> pd.DataFrame:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"数据文件不存在: {path}")
        df = self._read(path)
        df.columns = [str(c).strip() for c in df.columns]
        return df.reset_index(drop=True)

    @abstractmethod
    def _read(self, path: Path) -> pd.DataFrame:
        ...


def get_loader(path: str | Path) -> DataLoader:
    """工厂：按文件后缀选择加载器。"""
    from app.loaders.csv_loader import CSVLoader
    from app.loaders.excel_loader import ExcelLoader

    suffix = Path(path).suffix.lower()
    if suffix in {".csv", ".txt"}:
        return CSVLoader()
    if suffix in {".xls", ".xlsx", ".xlsm"}:
        return ExcelLoader()
    raise ValueError(f"不支持的文件类型: {suffix}（支持 csv/txt/xls/xlsx）")