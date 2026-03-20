"""
app/config.py
Centralised settings loaded from environment / .env file.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Azure
    azure_storage_connection_string: str = ""
    azure_storage_account_name:      str = ""
    azure_storage_account_key:       str = ""
    azure_sas_token:                 str = ""

    # OpenAI
    openai_api_key:    str  = ""
    openai_model:      str  = "gpt-4o"
    openai_max_tokens: int  = 600

    # Service
    app_env:           str  = "development"
    log_level:         str  = "INFO"
    max_file_size_mb:  int  = 500
    chunk_size_rows:   int  = 100_000
    job_ttl_seconds:   int  = 3600
    max_preview_rows:  int  = 500      # max diff rows returned in JSON response

    # Export
    export_max_rows:   int  = 1_000_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
