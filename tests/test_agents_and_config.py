import pytest
from pydantic import ValidationError

from selfagent.agents.team import AgentTeam
from selfagent.config import Settings
from selfagent.models import CandidatePatch


def test_settings_reject_example_api_key():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, OPENAI_API_KEY="ВСТАВЬТЕ_НОВЫЙ_КЛЮЧ")


def test_agent_team_builds_all_roles_without_network():
    settings = Settings(_env_file=None, OPENAI_API_KEY="sk-test")
    team = AgentTeam(settings)
    assert [team.planner.name, team.coder.name, team.reviewer.name] == [
        "планировщик",
        "разработчик",
        "ревьюер",
    ]


def test_candidate_patch_rejects_path_aliases():
    with pytest.raises(ValidationError, match="уникальными"):
        CandidatePatch(
            changes=[
                {"path": "src/Module.py", "content": "первый вариант"},
                {"path": "src/./module.py", "content": "второй вариант"},
            ],
            explanation="Проверка неоднозначных путей.",
        )
