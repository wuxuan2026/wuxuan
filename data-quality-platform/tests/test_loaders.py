"""loader 单元测试。"""
from pathlib import Path

import pandas as pd
import pytest

from app.loaders import get_loader
from app.loaders.base import DataLoader
from app.loaders.csv_loader import CSVLoader
from app.loaders.excel_loader import ExcelLoader


def test_factory_returns_csv_loader():
    assert isinstance(get_loader("foo.csv"), CSVLoader)
    assert isinstance(get_loader("foo.txt"), CSVLoader)


def test_factory_returns_excel_loader():
    assert isinstance(get_loader("foo.xlsx"), ExcelLoader)
    assert isinstance(get_loader("foo.xls"), ExcelLoader)


def test_factory_rejects_unknown_ext():
    with pytest.raises(ValueError, match="不支持"):
        get_loader("foo.json")


def test_csv_loader_normalizes_columns(tmp_path: Path):
    p = tmp_path / "x.csv"
    p.write_text(" a , b \n1,2\n", encoding="utf-8")
    df = get_loader(p).load(p)
    assert list(df.columns) == ["a", "b"]
    assert len(df) == 1


def test_csv_loader_handles_gbk(tmp_path: Path):
    p = tmp_path / "x.csv"
    p.write_text("name,city\n张三,北京\n", encoding="gbk")
    df = get_loader(p).load(p)
    assert df.iloc[0]["name"] == "张三"
    assert df.iloc[0]["city"] == "北京"


def test_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        get_loader(tmp_path / "nope.csv").load(tmp_path / "nope.csv")
