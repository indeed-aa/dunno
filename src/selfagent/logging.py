"""Настройка журналирования по дате и имени класса."""

from datetime import date
from pathlib import Path

from loguru import logger


class Logging:
    """Создаёт русскоязычные файлы журналов для компонентов приложения."""

    _configured = False

    @classmethod
    def configure(cls, root: Path, level: str, retention_days: int) -> None:
        """Настроить консольный вывод и ротацию файлов по календарной дате."""
        if cls._configured:
            return
        logger.remove()
        logger.add(
            sink=lambda message: print(message, end=""),
            level=level.upper(),
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {extra[component]} | {message}",
        )
        root.mkdir(parents=True, exist_ok=True)
        logger.add(
            str(root / "{time:YYYY-MM-DD}" / "{extra[component]}.log"),
            level=level.upper(),
            rotation="00:00",
            retention=f"{retention_days} days",
            encoding="utf-8",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {extra[component]} | {message}",
        )
        cls._configured = True

    @classmethod
    def for_class(cls, owner: type) -> object:
        """Вернуть логгер, привязанный к классу-владельцу метода."""
        return logger.bind(component=owner.__name__)
