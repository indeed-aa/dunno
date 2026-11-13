"""Настройка журналирования по дате и имени класса."""

from datetime import date, timedelta
from pathlib import Path
import sys
from threading import Lock

from loguru import logger


class DailyClassSink:
    """Направляет каждую запись в файл класса и календарной даты."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._lock = Lock()

    def __call__(self, message: object) -> None:
        record = message.record
        day = record["time"].strftime("%Y-%m-%d")
        component = record["extra"].get("component", "Библиотека")
        path = self.root / day / f"{component}.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, path.open("a", encoding="utf-8") as log_file:
            log_file.write(str(message))


class Logging:
    """Создаёт русскоязычные файлы журналов для компонентов приложения."""

    _configured = False
    _sink: DailyClassSink | None = None

    @staticmethod
    def _ensure_component(record: dict) -> bool:
        """Подставить имя компонента для сообщений библиотек без привязки."""
        record["extra"].setdefault("component", "Библиотека")
        return True

    @classmethod
    def configure(cls, root: Path, level: str, retention_days: int) -> None:
        """Настроить консольный вывод и ротацию файлов по календарной дате."""
        if cls._configured:
            return
        logger.remove()
        logger.add(
            sink=sys.stdout,
            filter=cls._ensure_component,
            level=level.upper(),
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | {extra[component]} | {message}",
        )
        root.mkdir(parents=True, exist_ok=True)
        logger.add(
            cls._get_sink(root),
            filter=cls._ensure_component,
            level=level.upper(),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {extra[component]} | {message}",
        )
        cls._remove_expired_logs(root, retention_days)
        cls._configured = True

    @classmethod
    def _get_sink(cls, root: Path) -> DailyClassSink:
        if cls._sink is None:
            cls._sink = DailyClassSink(root)
        return cls._sink

    @staticmethod
    def _remove_expired_logs(root: Path, retention_days: int) -> None:
        cutoff = date.today() - timedelta(days=retention_days)
        for day_directory in root.iterdir():
            if not day_directory.is_dir():
                continue
            try:
                log_day = date.fromisoformat(day_directory.name)
            except ValueError:
                continue
            if log_day < cutoff:
                for log_file in day_directory.glob("*.log"):
                    log_file.unlink(missing_ok=True)
                if not any(day_directory.iterdir()):
                    day_directory.rmdir()

    @classmethod
    def for_class(cls, owner: type) -> object:
        """Вернуть логгер, привязанный к классу-владельцу метода."""
        return logger.bind(component=owner.__name__)
