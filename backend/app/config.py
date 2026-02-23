from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8765, alias="APP_PORT")

    siliconflow_base_url: str = Field(default="https://api.siliconflow.cn/v1", alias="SILICONFLOW_BASE_URL")
    siliconflow_model: str = Field(default="Qwen/Qwen3-VL-32B-Instruct", alias="SILICONFLOW_MODEL")
    siliconflow_api_key: str = Field(default="", alias="SILICONFLOW_API_KEY")
    siliconflow_models: str = Field(
        default="Qwen/Qwen3-VL-32B-Instruct,Qwen/Qwen3-VL-8B-Instruct,Qwen/Qwen3-VL-30B-A3B-Instruct",
        alias="SILICONFLOW_MODELS",
    )
    filename_template: str = Field(default="{date}-{category}-{amount}", alias="FILENAME_TEMPLATE")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
