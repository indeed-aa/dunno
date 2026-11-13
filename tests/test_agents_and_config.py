import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic import ValidationError

from selfagent.agents.team import AgentTeam
from selfagent.agents.skills import project_skills
from selfagent.config import Settings
from selfagent.models import CandidatePatch, FailureAnalysis


def test_settings_reject_example_api_key():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, OPENAI_API_KEY="ВСТАВЬТЕ_НОВЫЙ_КЛЮЧ")


def test_agent_team_builds_all_roles_without_network():
    settings = Settings(_env_file=None, OPENAI_API_KEY="sk-test")
    team = AgentTeam(settings)
    assert [
        team.planner.name,
        team.coder.name,
        team.reviewer.name,
        team.failure_analyst.name,
    ] == [
        "планировщик",
        "разработчик",
        "ревьюер",
        "аналитик_сбоев",
    ]


@pytest.mark.asyncio
async def test_project_skills_are_available_to_agents():
    settings = Settings(_env_file=None, OPENAI_API_KEY="sk-test")

    catalog = await project_skills(settings).load()

    assert {skill.name for skill in catalog.skills} == {
        "pydantic",
        "pydantic-ai-harness",
        "building-pydantic-ai-agents",
    }
    assert not catalog.skipped

    model = TestModel(call_tools=[])
    agent = Agent(model, capabilities=[project_skills(settings)])
    await agent.run("Проверь доступность навыков.")

    assert [
        tool.name for tool in model.last_model_request_parameters.function_tools
    ] == ["load_capability"]


def test_failure_analysis_bounds_recommended_token_limit():
    analysis = FailureAnalysis(
        failure_type="token_limit",
        summary="Превышен лимит ответа.",
        diagnosis="Аргументы инструмента не поместились в лимит ответа.",
        retry_recommended=True,
        recovery_instruction="Повторить разработку после увеличения лимита.",
        recommended_max_output_tokens=32768,
    )

    assert analysis.recommended_max_output_tokens == 32768
    with pytest.raises(ValidationError):
        FailureAnalysis(
            failure_type="token_limit",
            summary="Ошибка лимита.",
            diagnosis="Подтверждённый обрыв.",
            retry_recommended=True,
            recovery_instruction="Повторить этап.",
            recommended_max_output_tokens=65536,
        )


def test_candidate_patch_rejects_path_aliases():
    with pytest.raises(ValidationError, match="уникальными"):
        CandidatePatch(
            changes=[
                {"path": "src/Module.py", "content": "первый вариант"},
                {"path": "src/./module.py", "content": "второй вариант"},
            ],
            explanation="Проверка неоднозначных путей.",
        )
