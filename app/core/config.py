from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    APP_NAME: str = "Validator Dashboard"
    APP_VERSION: str = "0.1.0"
    APP_ENV: str = "dev"
    DEBUG: bool = True

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    DATABASE_URL: str = "sqlite:///./validator_dashboard_chainid.db"
    API_V1_PREFIX: str = "/api/v1"

    ROOT_DIR: Path = ROOT_DIR
    DATA_DIR: Path = Field(default_factory=lambda: ROOT_DIR / "data")
    CONFIG_DIR: Path = Field(default_factory=lambda: ROOT_DIR / "config")
    CHAIN_REGISTRY_DIR: Path = Field(default_factory=lambda: ROOT_DIR / "chain-registry")
    POSTHUMAN_ENDPOINTS_FILE: Path = Field(default_factory=lambda: ROOT_DIR / "config" / "posthuman_endpoints.txt")
    METRICS_SOURCE_FILE: Path = Field(default_factory=lambda: ROOT_DIR / "config" / "source_metric_chain.yaml")

    COLLECTOR_TIMEOUT: int = 10
    COLLECTOR_CONCURRENCY: int = 8

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
