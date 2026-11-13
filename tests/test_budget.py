from decimal import Decimal

from selfagent.core.budget import BudgetLedger


def test_budget_tracks_expenses_by_day(tmp_path):
    ledger = BudgetLedger(tmp_path / "budget.sqlite3", Decimal("1.00"))
    ledger.record(Decimal("0.25"))
    assert ledger.spent_today() == Decimal("0.25")
    assert ledger.remaining() == Decimal("0.75")
