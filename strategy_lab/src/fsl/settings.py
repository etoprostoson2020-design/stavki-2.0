"""Конфигурация. Секреты берутся только из окружения, никогда из репозитория."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FSL_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    env: str = "dev"
    log_level: str = "INFO"

    postgres_dsn: str = "postgresql+psycopg://fsl:fsl_dev@127.0.0.1:5432/fsl"
    redis_url: str = "redis://127.0.0.1:6379/0"

    storage_root: Path = Path("./storage")

    footballdata_base_url: str = "https://www.football-data.co.uk/mmz4281"
    apifootball_key: str = Field(default="", repr=False)  # никогда не логируется

    @property
    def raw_dir(self) -> Path:
        return self.storage_root / "raw"

    @property
    def parquet_dir(self) -> Path:
        return self.storage_root / "parquet"

    def ensure_dirs(self) -> None:
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.parquet_dir.mkdir(parents=True, exist_ok=True)

    def safe_dump(self) -> dict:
        """Представление для логов и отчётов: без секретов."""
        d = self.model_dump(mode="json")
        d["apifootball_key"] = "<set>" if self.apifootball_key else "<unset>"
        d["postgres_dsn"] = self.postgres_dsn.split("@")[-1]
        return d


@lru_cache
def get_settings() -> Settings:
    return Settings()
