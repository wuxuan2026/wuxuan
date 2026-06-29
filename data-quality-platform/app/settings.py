"""环境变量配置（pydantic-settings）。"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "数据质量监测平台"
    data_dir: str = "data"
    upload_dir: str = "data/uploads"
    generated_dir: str = "data/generated"
    ruleset_dir: str = "data/rulesets"
    sample_limit: int = 50


settings = Settings()
