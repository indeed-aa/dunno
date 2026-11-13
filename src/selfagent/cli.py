"""Командная строка проекта."""

import argparse
import asyncio
import sys
from decimal import Decimal

from selfagent.config import Settings
from selfagent.core.budget import BudgetExceeded, BudgetLedger
from selfagent.core.evolution import EvolutionCycle
from selfagent.logging import Logging


def main() -> None:
    """Запустить одно улучшение, несколько циклов или показать состояние."""
    parser = argparse.ArgumentParser(
        description="Контролируемое самоулучшение проекта."
    )
    parser.add_argument(
        "--cycles", type=int, default=1, help="Число последовательных циклов"
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Повторять циклы до отказа кандидата или исчерпания дневного бюджета",
    )
    parser.add_argument(
        "--budget", action="store_true", help="Показать расходы за сегодня"
    )
    args = parser.parse_args()
    if args.cycles < 1 and not args.continuous:
        parser.error("Число циклов должно быть не меньше одного.")
    try:
        settings = Settings()
        Logging.configure(
            settings.log_root, settings.log_level, settings.log_retention_days
        )
        ledger = BudgetLedger(settings.budget_database, settings.daily_budget_usd)
        if args.budget:
            print(
                f"Расходы сегодня: ${ledger.spent_today():.6f}; лимит: ${settings.daily_budget_usd:.2f}"
            )
            return
        max_cycles = None if args.continuous else args.cycles
        asyncio.run(EvolutionCycle(settings).run_loop(max_cycles))
    except BudgetExceeded as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from error
    except Exception as error:
        print(f"Ошибка запуска: {error}", file=sys.stderr)
        raise SystemExit(1) from error
