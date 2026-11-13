"""Контролируемый цикл самоулучшения."""

import asyncio
import re
import subprocess
from decimal import Decimal
from pathlib import Path, PurePosixPath

from pydantic_ai.usage import UsageLimits

from selfagent.agents.team import AgentExecutionError, AgentTeam
from selfagent.config import Settings
from selfagent.core.budget import BudgetExceeded, BudgetLedger
from selfagent.core.git import GitRepository
from selfagent.core.runner import CandidateRunner
from selfagent.logging import Logging


class EvolutionCycle:
    """Планирует улучшение, ревьюит патч, проверяет и локально сливает."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.git = GitRepository(
            settings.repository_root,
            settings.git_main_branch,
            settings.git_ssh_key_path,
        )
        self.budget = BudgetLedger(settings.budget_database, settings.daily_budget_usd)
        self.team = AgentTeam(settings)
        self.runner = CandidateRunner(settings)
        self.log = Logging.for_class(type(self))
        self._recovery_instruction: str | None = None

    def _snapshot(self) -> str:
        paths = self.git.run(
            "ls-files", "src", "tests", "README.md", "pyproject.toml"
        ).splitlines()
        chunks: list[str] = []
        for name in paths:
            path = self.settings.repository_root / name
            if path.is_file():
                content = path.read_text(encoding="utf-8")
                chunks.append(f"\n### {name}\n{content[:10000]}")
        return "".join(chunks)[:45000]

    def _budget(self, reserve: Decimal = Decimal("0")) -> UsageLimits:
        remaining = self.budget.ensure_budget() - reserve
        if remaining <= 0:
            raise RuntimeError("Недостаточно остатка бюджета для следующего этапа.")
        return UsageLimits(cost_limit=float(remaining), request_limit=3)

    def _tracked_changes(self) -> str:
        return self.git.run("diff", "--", "src", "tests", "README.md", "pyproject.toml")

    def _write_patch(self, patch: object) -> None:
        for change in patch.changes:
            relative = PurePosixPath(change.path)
            if not relative.parts or relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"Недопустимый путь изменения: {change.path}")
            if not (relative.parts[0] in {"src", "tests"}):
                raise ValueError(f"Изменение этого файла запрещено: {change.path}")
            target = (self.settings.repository_root / Path(*relative.parts)).resolve()
            allowed_root = self.settings.repository_root.resolve() / relative.parts[0]
            if allowed_root.resolve() not in target.parents:
                raise ValueError("Изменение выходит за пределы разрешённого каталога.")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(change.content, encoding="utf-8")

    def _verify_candidate_git_state(self) -> None:
        status = self.git.run("status", "--porcelain")
        if status:
            raise RuntimeError(
                "Репозиторий содержит незакоммиченные изменения. "
                "Сохраните или отмените их перед запуском цикла."
            )
        branch = self.git.run("branch", "--show-current")
        if branch != self.settings.git_main_branch:
            raise RuntimeError(
                f"Ожидалась основная ветка {self.settings.git_main_branch}."
            )

    async def run_once(self) -> bool:
        """Выполнить один полный цикл; вернуть True при успешном слиянии."""
        self._verify_candidate_git_state()
        snapshot = self._snapshot()
        recovery_instruction = self._recovery_instruction
        stage = "планировщик"
        plan = None
        patch = None
        diff = ""
        branch: str | None = None
        branch_created = False
        try:
            planning_prompt = snapshot
            if recovery_instruction:
                planning_prompt = (
                    "ПРЕДЫДУЩАЯ ИТЕРАЦИЯ НЕ ПРОШЛА. Сначала спланируй исправление "
                    "указанной причины, не выбирай постороннее улучшение.\n"
                    f"Рекомендация аналитика сбоев:\n{recovery_instruction}\n\n"
                    f"Исходный репозиторий:\n{snapshot}"
                )
            self._recovery_instruction = None
            plan, cost, _ = await self.team.run(
                self.team.planner,
                planning_prompt,
                self._budget(Decimal("0.03")),
            )
            self.budget.record(Decimal(cost))
            self.log.info("План улучшения: {}", plan.summary)

            stage = "разработчик"
            patch, cost, _ = await self.team.run(
                self.team.coder,
                f"План: {plan.model_dump_json()}\n"
                f"Указание по восстановлению: {recovery_instruction or 'нет'}\n"
                f"Содержимое репозитория:\n{snapshot}",
                self._budget(Decimal("0.03")),
            )
            self.budget.record(Decimal(cost))

            branch_slug = re.sub(r"[^a-z0-9-]+", "-", plan.summary.lower())[:32].strip(
                "-"
            )
            branch_slug = branch_slug or "improvement"
            commit_id = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=self.settings.repository_root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            branch = f"selfagent/{branch_slug}-{commit_id}"
            self.git.create_candidate(branch)
            branch_created = True

            self._write_patch(patch)
            self.git.run("add", "--intent-to-add", "--", "src", "tests")
            diff = self._tracked_changes()
            if not diff:
                raise RuntimeError("Кандидат не создал diff для проверяемых файлов.")
            stage = "ревьюер"
            decision, cost, _ = await self.team.run(
                self.team.reviewer,
                f"План:\n{plan.model_dump_json()}\n"
                f"Исходный контекст репозитория до внесения кандидата:\n{snapshot}\n"
                f"Diff кандидата:\n{diff[:30000]}",
                self._budget(),
            )
            self.budget.record(Decimal(cost))
            if not decision.approved:
                raise RuntimeError(
                    "Ревью отклонило кандидата: " + "; ".join(decision.findings)
                )

            stage = "проверка Docker и pytest"
            self.runner.validate()
            self.git.run("add", "--", "src", "tests")
            if (
                subprocess.run(
                    ["git", "diff", "--cached", "--quiet"],
                    cwd=self.settings.repository_root,
                    check=False,
                ).returncode
                == 0
            ):
                raise RuntimeError("Кандидат не содержит индексируемых изменений.")
            description = " ".join(plan.summary.split())
            if len(description) > 61:
                description = (
                    description[:61].rsplit(" ", maxsplit=1)[0] or description[:61]
                )
            self.git.run("commit", "-m", f"Улучшение: {description}")
            self.git.merge_candidate(branch)
            branch_created = False
            if self.settings.git_push_enabled:
                try:
                    self.git.run(
                        "push",
                        self.settings.git_remote_url,
                        self.settings.git_main_branch,
                    )
                except Exception:
                    self.log.exception(
                        "Кандидат слит локально, но отправка в удалённый репозиторий не удалась."
                    )
            return True
        except Exception as error:
            self.log.error(
                "Итерация остановлена на этапе {} ({}): {}",
                stage,
                type(error).__name__,
                error,
            )
            if branch and branch_created:
                try:
                    self.git.discard_candidate(branch)
                except Exception:
                    self.log.exception("Не удалось удалить ветку неудачного кандидата.")
            if isinstance(error, BudgetExceeded):
                raise
            self._recovery_instruction = await self._analyze_failure(
                stage, error, snapshot, plan, patch, diff
            )
            return False

    async def _analyze_failure(
        self,
        stage: str,
        error: Exception,
        snapshot: str,
        plan: object,
        patch: object,
        diff: str,
    ) -> str | None:
        """Запросить разбор сбоя и принять только ограниченные настройки повтора."""
        detail = str(error).replace(self.settings.api_key, "[КЛЮЧ СКРЫТ]")
        detail_lower = detail.casefold()
        non_retryable_markers = (
            "invalid api key",
            "invalid_api_key",
            "unauthorized",
            "authentication",
            "permission denied (publickey)",
            "insufficient_quota",
        )
        if any(marker in detail_lower for marker in non_retryable_markers):
            self.log.warning(
                "Анализатор не вызван: ошибка авторизации требует внешнего исправления."
            )
            return None

        context = (
            f"Этап: {stage}\nТип ошибки: {type(error).__name__}\n"
            f"Текущий лимит ответа агента: {self.settings.max_output_tokens} токенов\n"
            f"Подробности: {detail[:6000]}\n"
            f"План: {getattr(plan, 'model_dump_json', lambda: 'не сформирован')()}\n"
            f"Объяснение разработчика: {getattr(patch, 'explanation', 'нет')}\n"
            f"Diff кандидата:\n{diff[:15000]}\n"
            f"Исходный контекст репозитория:\n{snapshot[:15000]}"
        )
        try:
            analysis, cost = await self.team.analyze_failure(
                context,
                self._budget(Decimal("0.03")),
            )
            self.budget.record(cost)
        except BudgetExceeded:
            self.log.warning(
                "Анализатор не запущен: остатка дневного бюджета недостаточно."
            )
            return None
        except Exception:
            self.log.exception("Не удалось получить разбор неудачной итерации.")
            return None

        token_limit_error = isinstance(error, AgentExecutionError) and (
            "token limit" in error.detail.casefold()
            or "incomplete tool call" in error.detail.casefold()
        )
        if token_limit_error:
            suggested = analysis.recommended_max_output_tokens
            if suggested is None or suggested <= self.settings.max_output_tokens:
                suggested = min(self.settings.max_output_tokens * 2, 32768)
            new_limit = min(max(suggested, self.settings.max_output_tokens), 32768)
            if new_limit > self.settings.max_output_tokens:
                self.settings.max_output_tokens = new_limit
                self.log.warning(
                    "После подтверждённого обрыва вывода лимит ответа повышен "
                    "до {} токенов на время текущего запуска.",
                    new_limit,
                )
            else:
                self.log.warning(
                    "Лимит ответа уже достиг предела 32768 токенов; "
                    "автоматический повтор с тем же лимитом не запускается."
                )
                return None

        if analysis.retry_recommended and analysis.recovery_instruction.strip():
            return analysis.recovery_instruction
        return None

    async def run_loop(self, max_cycles: int | None) -> None:
        """Выполнять циклы с одной целевой попыткой восстановления после сбоя."""
        index = 0
        recovery_attempted = False
        while max_cycles is None or index < max_cycles:
            self.log.info("Начало цикла {}.", index + 1)
            index += 1
            success = await self.run_once()
            if not success:
                if self._recovery_instruction and not recovery_attempted:
                    if max_cycles is not None and index >= max_cycles:
                        self.log.info(
                            "Анализатор подготовил восстановление, но достигнут "
                            "лимит циклов запуска."
                        )
                        break
                    recovery_attempted = True
                    self.log.info(
                        "Анализатор подготовил целевое восстановление; "
                        "запускаю одну повторную итерацию."
                    )
                    await asyncio.sleep(2)
                    continue
                break
            recovery_attempted = False
            await asyncio.sleep(2)
