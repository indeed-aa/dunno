"""Создание агентов планирования, реализации и ревью."""

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai_harness import SubAgent, SubAgents
from decimal import Decimal

from pydantic_ai.usage import UsageLimits

from selfagent.config import Settings
from selfagent.logging import Logging
from selfagent.models import CandidatePatch, ImprovementPlan, ReviewDecision


class AgentTeam:
    """Команда из трёх ролей с общим провайдером и лимитом расходов."""

    def __init__(self, settings: Settings) -> None:
        model_name = settings.model_name.split(":", maxsplit=1)[-1]
        provider = OpenAIProvider(api_key=settings.api_key)
        model = OpenAIChatModel(model_name, provider=provider)
        self.planner = Agent(
            model,
            name="планировщик",
            output_type=ImprovementPlan,
            instructions=(
                "Изучи краткий снимок репозитория и предложи одно небольшое, "
                "безопасное и проверяемое улучшение. Пиши по-русски. Не проси "
                "раскрывать секреты и не предлагай выводить значения переменных окружения."
            ),
        )
        self.coder = Agent(
            model,
            name="разработчик",
            output_type=CandidatePatch,
            instructions=(
                "Подготовь полное новое содержимое только тех файлов, которые "
                "относятся к улучшению. Изменяй только файлы в src/ или tests/. "
                "Не меняй конфигурацию секретов, Docker, Git, зависимости и "
                "инфраструктурные команды. Код, комментарии и строки интерфейса "
                "пиши на русском."
            ),
        )
        security_reviewer = Agent(
            model,
            name="security_reviewer",
            output_type=ReviewDecision,
            instructions=(
                "Проведи независимую проверку diff на раскрытие секретов, обход "
                "проверок, опасный запуск команд и выход за рамки задачи. "
                "Пиши замечания по-русски."
            ),
        )
        self.reviewer = Agent(
            model,
            name="ревьюер",
            output_type=ReviewDecision,
            capabilities=[
                SubAgents(
                    agents=[
                        SubAgent(
                            security_reviewer,
                            description="Проверяет diff на угрозы и обход ограничений",
                            usage_limits=UsageLimits(request_limit=2),
                            timeout_seconds=120,
                            max_calls=1,
                        )
                    ],
                    forward_usage=True,
                )
            ],
            instructions=(
                "Независимо оцени план и полный diff кандидата. Отклоняй изменения, "
                "если они читают секреты, ослабляют проверки, запускают сеть или "
                "выходят за согласованную задачу. Перед вердиктом обязательно "
                "передай diff специалисту security_reviewer и учти его замечания. "
                "Пиши выводы по-русски."
            ),
        )
        self.log = Logging.for_class(type(self))

    async def run(
        self, agent: Agent, prompt: str, budget: UsageLimits
    ) -> tuple[object, Decimal]:
        """Выполнить один этап с жёстким ограничением стоимости запроса."""
        result = await agent.run(
            prompt,
            usage_limits=budget,
            model_settings={"max_tokens": 2048},
        )
        usage = result.usage()
        estimated_cost = (
            Decimal(usage.input_tokens) * Decimal("0.11")
            + Decimal(usage.output_tokens) * Decimal("0.55")
        ) / Decimal(1_000_000)
        cost = max(usage.cost or Decimal("0"), estimated_cost)
        self.log.info("Этап {}: ${:.6f}", agent.name, cost)
        return result.output, cost
