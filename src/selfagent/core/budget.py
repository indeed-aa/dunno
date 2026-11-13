"""Учёт расходов по дням в локальной базе SQLite."""

import sqlite3
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from selfagent.logging import Logging


class BudgetExceeded(RuntimeError):
    """Дневной лимит расходов исчерпан."""


class BudgetLedger:
    """Хранит фактическую стоимость обращений к модели."""

    def __init__(self, path: Path, daily_limit: Decimal) -> None:
        self.path = path
        self.daily_limit = daily_limit
        self.log = Logging.for_class(type(self))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS usage "
                "(id INTEGER PRIMARY KEY, day TEXT NOT NULL, cost TEXT NOT NULL, created_at TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def spent_today(self) -> Decimal:
        """Вернуть сумму расходов за текущую локальную дату."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT cost FROM usage WHERE day = ?", (date.today().isoformat(),)
            ).fetchall()
        return sum((Decimal(row[0]) for row in rows), start=Decimal("0"))

    def remaining(self) -> Decimal:
        """Вернуть остаток дневного бюджета."""
        return max(Decimal("0"), self.daily_limit - self.spent_today())

    def ensure_budget(self) -> Decimal:
        """Остановить новый цикл, если лимит уже израсходован."""
        left = self.remaining()
        if left <= 0:
            raise BudgetExceeded("Дневной лимит расходов исчерпан.")
        return left

    def record(self, cost: Decimal) -> None:
        """Записать фактическую стоимость завершённого обращения."""
        if cost <= 0:
            return
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO usage(day, cost, created_at) VALUES (?, ?, ?)",
                (date.today().isoformat(), str(cost), datetime.now(UTC).isoformat()),
            )
        self.log.info("Учтены расходы на этап агентов: ${:.6f}", cost)
