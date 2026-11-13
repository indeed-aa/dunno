"""Контролируемый цикл самоулучшения."""

import asyncio
import re
import subprocess
from decimal import Decimal
from pathlib import Path, PurePosixPath

from pydantic_ai.usage import UsageLimits

from selfagent.agents.team import AgentTeam
from selfagent.config import Settings
from selfagent.core.budget import BudgetLedger
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

    def _snapshot(self) -> str:
        paths = self.git.run(
            "ls-files", "src", "README.md", "pyproject.toml"
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
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"Недопустимый путь изменения: {change.path}")
            if not (relative.parts[0] in {"src", "tests"}):
                raise ValueError(f"Изменение этого файла запрещено: {change.path}")
            tracked = self.git.run("ls-files", "--", change.path)
            if tracked != change.path:
                raise ValueError(
                    f"Можно изменять только уже отслеживаемый файл: {change.path}"
                )
            target = (self.settings.repository_root / Path(*relative.parts)).resolve()
            if self.settings.repository_root.resolve() not in target.parents:
                raise ValueError("Изменение выходит за пределы каталога проекта.")
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
        plan, cost = await self.team.run(
            self.team.planner, snapshot, self._budget(Decimal("0.03"))
        )
        if cost is not None:
            self.budget.record(Decimal(cost) + Decimal("0.03"))
        self.log.info("План улучшения: {}", plan.summary)

        patch, cost = await self.team.run(
            self.team.coder,
            f"План: {plan.model_dump_json()}\nСодержимое репозитория:\n{snapshot}",
            self._budget(),
        )
        if cost is not None:
            self.budget.record(Decimal(cost))

        branch = "selfagent/" + re.sub(r"[^a-z0-9-]+", "-", plan.summary.lower())[
            :32
        ].strip("-")
        branch += (
            "-"
            + subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=self.settings.repository_root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
        self.git.create_candidate(branch)
        try:
            self._write_patch(patch)
            diff = self._tracked_changes()
            if not diff:
                raise RuntimeError("Кандидат не создал diff для проверяемых файлов.")
            decision, cost = await self.team.run(
                self.team.reviewer,
                f"План:\n{plan.model_dump_json()}\nDiff кандидата:\n{diff[:30000]}",
                self._budget(),
            )
            if cost is not None:
                self.budget.record(Decimal(cost))
            if not decision.approved:
                raise RuntimeError(
                    "Ревью отклонило кандидата: " + "; ".join(decision.findings)
                )

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
            self.git.run("commit", "-m", f"Улучшение: {plan.summary[:60]}")
            self.git.merge_candidate(branch)
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
        except Exception:
            self.log.exception("Кандидат не прошёл цикл проверки и не будет принят.")
            self.git.discard_candidate(branch)
            return False

    async def run_loop(self, max_cycles: int | None) -> None:
        """Повторять циклы до отказа кандидата, лимита расходов или итераций."""
        index = 0
        while max_cycles is None or index < max_cycles:
            self.log.info("Начало цикла {}.", index + 1)
            if not await self.run_once():
                break
            index += 1
            await asyncio.sleep(2)
