"""Конфигурация приложения."""

from decimal import Decimal
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Проверенные параметры приложения, загружаемые из окружения и .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    openai_api_key: SecretStr = Field(alias="OPENAI_API_KEY")
    model_name: str = "openai:gpt-6-luna"
    max_output_tokens: int = Field(default=16384, ge=4096, le=32768)
    daily_budget_usd: Decimal = Field(default=Decimal("1.00"), gt=0)
    web_search_call_cost_usd: Decimal = Field(default=Decimal("0.01"), ge=0)
    log_level: str = "INFO"
    log_retention_days: int = Field(default=30, ge=1)
    git_main_branch: str = "main"
    git_remote_url: str = "git@github.com:indeed-aa/dunno.git"
    git_ssh_key_path: Path = Path("~/.ssh/dunno-deploy")
    git_push_enabled: bool = True
    docker_image: str = "selfagent:candidate"
    docker_timeout_seconds: int = Field(default=900, ge=30)
    repository_root: Path = Field(default_factory=Path.cwd)
    log_root: Path = Path("logs")
    budget_database: Path = Path(".selfagent/budget.sqlite3")

    @field_validator("openai_api_key")
    @classmethod
    def require_real_api_key(cls, value: SecretStr) -> SecretStr:
        """Не запускать запросы с заглушкой из примера настроек."""
        if not value.get_secret_value() or value.get_secret_value().startswith(
            "ВСТАВЬТЕ_"
        ):
            raise ValueError(
                "Укажите действительный OPENAI_API_KEY в локальном файле .env."
            )
        return value

    @property
    def api_key(self) -> str:
        """Вернуть секрет для передачи провайдеру без его журналирования."""
        return self.openai_api_key.get_secret_value()
