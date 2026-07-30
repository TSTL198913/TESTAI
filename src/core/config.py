import os
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MONGO_URI: Optional[str] = None
    MONGO_DB_NAME: str = "testai"
    DEEPSEEK_API_KEY: Optional[str] = None
    HTTP_TIMEOUT: float = 10.0
    HTTP_MAX_CONNECTIONS: int = 100

    model_config = SettingsConfigDict(
        env_file=os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("MONGO_URI")
    @classmethod
    def validate_mongo_uri(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        clean_v = v.strip()
        if not clean_v.startswith("mongodb://"):
            raise ValueError("Invalid MongoDB URI: Must start with 'mongodb://'")
        return clean_v


settings = Settings()
