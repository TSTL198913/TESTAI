import os
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 可选配置项
    MONGO_URI: Optional[str] = Field(None, json_schema_extra={"env": "MONGO_URI"})
    MONGO_DB_NAME: str = Field("testai", json_schema_extra={"env": "MONGO_DB_NAME"})

    # 【新增】：将 API Key 纳入配置契约，强制必填
    DEEPSEEK_API_KEY: str = Field(..., json_schema_extra={"env": "DEEPSEEK_API_KEY"})

    # 性能调优配置
    HTTP_TIMEOUT: float = Field(10.0, json_schema_extra={"env": "HTTP_TIMEOUT"})
    HTTP_MAX_CONNECTIONS: int = Field(
        100, json_schema_extra={"env": "HTTP_MAX_CONNECTIONS"}
    )

    model_config = SettingsConfigDict(
        env_file=os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("MONGO_URI")
    @classmethod
    def validate_mongo_uri(cls, v: str) -> str:
        clean_v = v.strip()
        if not clean_v.startswith("mongodb://"):
            raise ValueError("Invalid MongoDB URI: Must start with 'mongodb://'")
        return clean_v


settings = Settings()
