"""
shared/config.py
Centralised Pydantic v2 settings — loaded once, reused everywhere.
Azure Key Vault overrides are applied when AZURE_KEY_VAULT_URL is set.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SnowflakeSettings(BaseSettings):
    account: str = Field(..., alias="SNOWFLAKE_ACCOUNT")
    user: str = Field(..., alias="SNOWFLAKE_USER")
    password: SecretStr = Field(..., alias="SNOWFLAKE_PASSWORD")
    warehouse: str = Field(..., alias="SNOWFLAKE_WAREHOUSE")
    database: str = Field(..., alias="SNOWFLAKE_DATABASE")
    schema_: str = Field("PUBLIC", alias="SNOWFLAKE_SCHEMA")
    role: Optional[str] = Field(None, alias="SNOWFLAKE_ROLE")

    model_config = SettingsConfigDict(env_file=".env", populate_by_name=True)


class OpenAISettings(BaseSettings):
    api_key: SecretStr = Field(..., alias="OPENAI_API_KEY")
    model: str = Field("gpt-4o", alias="OPENAI_MODEL")

    model_config = SettingsConfigDict(env_file=".env", populate_by_name=True)


class MCPSettings(BaseSettings):
    server_url: str = Field("http://localhost:8001/sse", alias="MCP_SERVER_URL")
    server_port: int = Field(8001, alias="MCP_SERVER_PORT")

    model_config = SettingsConfigDict(env_file=".env", populate_by_name=True)


class AzureSettings(BaseSettings):
    key_vault_url: Optional[str] = Field(None, alias="AZURE_KEY_VAULT_URL")
    client_id: Optional[str] = Field(None, alias="AZURE_CLIENT_ID")
    client_secret: Optional[SecretStr] = Field(None, alias="AZURE_CLIENT_SECRET")
    tenant_id: Optional[str] = Field(None, alias="AZURE_TENANT_ID")

    model_config = SettingsConfigDict(env_file=".env", populate_by_name=True)

    @model_validator(mode="after")
    def warn_missing_vault(self) -> "AzureSettings":
        if not self.key_vault_url:
            import warnings
            warnings.warn(
                "AZURE_KEY_VAULT_URL not set — using .env secrets directly. "
                "Set this in production.",
                stacklevel=2,
            )
        return self


@lru_cache(maxsize=1)
def get_snowflake_settings() -> SnowflakeSettings:
    return SnowflakeSettings()  # type: ignore[call-arg]


@lru_cache(maxsize=1)
def get_openai_settings() -> OpenAISettings:
    return OpenAISettings()  # type: ignore[call-arg]


@lru_cache(maxsize=1)
def get_mcp_settings() -> MCPSettings:
    return MCPSettings()


@lru_cache(maxsize=1)
def get_azure_settings() -> AzureSettings:
    return AzureSettings()
