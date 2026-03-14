"""
shared/config.py
Pydantic v2 settings for the Attribution MCP stack.
Covers Snowflake, OpenAI, MCP transport, Azure, and Attribution-specific tunables.
"""

from __future__ import annotations

import warnings
from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ── Snowflake ──────────────────────────────────────────────────────────────────

class SnowflakeSettings(BaseSettings):
    account:   str       = Field(..., alias="SNOWFLAKE_ACCOUNT")
    user:      str       = Field(..., alias="SNOWFLAKE_USER")
    password:  SecretStr = Field(..., alias="SNOWFLAKE_PASSWORD")
    warehouse: str       = Field(..., alias="SNOWFLAKE_WAREHOUSE")
    database:  str       = Field(..., alias="SNOWFLAKE_DATABASE")
    schema_:   str       = Field("PUBLIC", alias="SNOWFLAKE_SCHEMA")
    role:      Optional[str] = Field(None, alias="SNOWFLAKE_ROLE")

    model_config = SettingsConfigDict(env_file=".env", populate_by_name=True)


# ── Attribution domain ─────────────────────────────────────────────────────────

class AttributionSettings(BaseSettings):
    """
    Table names and business rules for the attribution data model.
    Override via environment variables to match your Snowflake schema.
    """

    # Core tables
    touchpoints_table:  str = Field("ATTRIBUTION.TOUCHPOINTS",  alias="ATTR_TOUCHPOINTS_TABLE")
    conversions_table:  str = Field("ATTRIBUTION.CONVERSIONS",  alias="ATTR_CONVERSIONS_TABLE")
    sessions_table:     str = Field("ATTRIBUTION.SESSIONS",     alias="ATTR_SESSIONS_TABLE")
    spend_table:        str = Field("ATTRIBUTION.CHANNEL_SPEND",alias="ATTR_SPEND_TABLE")

    # Lookback window in days for attribution analysis
    default_lookback_days: int = Field(30,  alias="ATTR_LOOKBACK_DAYS")

    # Time-decay half-life in days
    time_decay_halflife_days: float = Field(7.0, alias="ATTR_TIME_DECAY_HALFLIFE")

    # Default attribution model shown in reports
    default_model: Literal[
        "first_touch", "last_touch", "linear",
        "time_decay", "position_based", "data_driven"
    ] = Field("linear", alias="ATTR_DEFAULT_MODEL")

    model_config = SettingsConfigDict(env_file=".env", populate_by_name=True)


# ── OpenAI ─────────────────────────────────────────────────────────────────────

class OpenAISettings(BaseSettings):
    api_key: SecretStr = Field(..., alias="OPENAI_API_KEY")
    model:   str       = Field("gpt-4o", alias="OPENAI_MODEL")

    model_config = SettingsConfigDict(env_file=".env", populate_by_name=True)


# ── MCP transport ──────────────────────────────────────────────────────────────

class MCPSettings(BaseSettings):
    server_url:  str = Field("http://localhost:8001/sse", alias="MCP_SERVER_URL")
    server_port: int = Field(8001, alias="MCP_SERVER_PORT")

    model_config = SettingsConfigDict(env_file=".env", populate_by_name=True)


# ── Azure ──────────────────────────────────────────────────────────────────────

class AzureSettings(BaseSettings):
    key_vault_url:  Optional[str]       = Field(None, alias="AZURE_KEY_VAULT_URL")
    client_id:      Optional[str]       = Field(None, alias="AZURE_CLIENT_ID")
    client_secret:  Optional[SecretStr] = Field(None, alias="AZURE_CLIENT_SECRET")
    tenant_id:      Optional[str]       = Field(None, alias="AZURE_TENANT_ID")

    model_config = SettingsConfigDict(env_file=".env", populate_by_name=True)

    @model_validator(mode="after")
    def warn_missing_vault(self) -> "AzureSettings":
        if not self.key_vault_url:
            warnings.warn(
                "AZURE_KEY_VAULT_URL not set — using .env secrets. "
                "Set this in production.",
                stacklevel=2,
            )
        return self


# ── Cached accessors ───────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_snowflake_settings() -> SnowflakeSettings:
    return SnowflakeSettings()  # type: ignore[call-arg]

@lru_cache(maxsize=1)
def get_attribution_settings() -> AttributionSettings:
    return AttributionSettings()

@lru_cache(maxsize=1)
def get_openai_settings() -> OpenAISettings:
    return OpenAISettings()  # type: ignore[call-arg]

@lru_cache(maxsize=1)
def get_mcp_settings() -> MCPSettings:
    return MCPSettings()

@lru_cache(maxsize=1)
def get_azure_settings() -> AzureSettings:
    return AzureSettings()
