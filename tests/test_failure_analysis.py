from decimal import Decimal

import pytest

from selfagent.agents.team import AgentExecutionError
from selfagent.config import Settings
from selfagent.core.evolution import EvolutionCycle
from selfagent.models import FailureAnalysis


def failure_analysis(
    *, recommended_max_output_tokens: int | None = None
) -> FailureAnalysis:
    return FailureAnalysis(
        failure_type="token_limit",
        summary="Не хватило лимита ответа.",
        diagnosis="Модель оборвала аргументы инструмента по лимиту токенов.",
        retry_recommended=True,
        recovery_instruction="Повтори этап после увеличения лимита ответа.",
        recommended_max_output_tokens=recommended_max_output_tokens,
    )


@pytest.mark.asyncio
async def test_failure_analyst_can_raise_limit_after_token_truncation(
    tmp_path, monkeypatch
):
    settings = Settings(
        _env_file=None,
        OPENAI_API_KEY="sk-test",
        repository_root=tmp_path,
        budget_database=tmp_path / "budget.sqlite3",
    )
    cycle = EvolutionCycle(settings)

    async def analyze_failure(prompt, budget):
        assert "Model token limit" in prompt
        return failure_analysis(recommended_max_output_tokens=32768), Decimal("0.001")

    monkeypatch.setattr(cycle.team, "analyze_failure", analyze_failure)

    instruction = await cycle._analyze_failure(
        "разработчик",
        AgentExecutionError(
            "разработчик",
            "IncompleteToolCall",
            "Model token limit (16384) exceeded while generating a tool call.",
        ),
        "снимок",
        None,
        None,
        "",
    )

    assert settings.max_output_tokens == 32768
    assert instruction == "Повтори этап после увеличения лимита ответа."


@pytest.mark.asyncio
async def test_failure_analyst_cannot_raise_limit_for_unrelated_error(
    tmp_path, monkeypatch
):
    settings = Settings(
        _env_file=None,
        OPENAI_API_KEY="sk-test",
        repository_root=tmp_path,
        budget_database=tmp_path / "budget.sqlite3",
    )
    cycle = EvolutionCycle(settings)

    async def analyze_failure(prompt, budget):
        return failure_analysis(recommended_max_output_tokens=32768), Decimal("0.001")

    monkeypatch.setattr(cycle.team, "analyze_failure", analyze_failure)

    await cycle._analyze_failure(
        "разработчик",
        AgentExecutionError("разработчик", "Timeout", "Сеть недоступна."),
        "снимок",
        None,
        None,
        "",
    )

    assert settings.max_output_tokens == 16384


@pytest.mark.asyncio
async def test_run_loop_allows_only_one_recovery_attempt(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None,
        OPENAI_API_KEY="sk-test",
        repository_root=tmp_path,
        budget_database=tmp_path / "budget.sqlite3",
    )
    cycle = EvolutionCycle(settings)
    attempts = 0

    async def failed_cycle():
        nonlocal attempts
        attempts += 1
        cycle._recovery_instruction = "Исправить причину отказа."
        return False

    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(cycle, "run_once", failed_cycle)
    monkeypatch.setattr("selfagent.core.evolution.asyncio.sleep", no_wait)

    await cycle.run_loop(max_cycles=None)

    assert attempts == 2


@pytest.mark.asyncio
async def test_failure_analyst_skips_authentication_errors(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None,
        OPENAI_API_KEY="sk-test",
        repository_root=tmp_path,
        budget_database=tmp_path / "budget.sqlite3",
    )
    cycle = EvolutionCycle(settings)

    async def unexpected_analysis(prompt, budget):
        raise AssertionError("Анализатор не должен вызываться при ошибке ключа.")

    monkeypatch.setattr(cycle.team, "analyze_failure", unexpected_analysis)

    instruction = await cycle._analyze_failure(
        "планировщик",
        AgentExecutionError("планировщик", "AuthenticationError", "Invalid API key"),
        "снимок",
        None,
        None,
        "",
    )

    assert instruction is None
