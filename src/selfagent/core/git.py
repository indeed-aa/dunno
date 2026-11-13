"""Работа с кандидатными ветками Git."""

import os
import shlex
import subprocess
from pathlib import Path

from selfagent.logging import Logging


class GitRepository:
    """Выполняет Git-команды только в каталоге проекта."""

    def __init__(self, root: Path, main_branch: str, ssh_key_path: Path) -> None:
        self.root = root.resolve()
        self.main_branch = main_branch
        self.ssh_key_path = ssh_key_path.expanduser().resolve()
        self.log = Logging.for_class(type(self))

    def run(self, *args: str, check: bool = True) -> str:
        """Запустить Git без shell и вернуть стандартный вывод."""
        environment = os.environ.copy()
        ssh_key = shlex.quote(self.ssh_key_path.as_posix())
        environment["GIT_SSH_COMMAND"] = f"ssh -i {ssh_key} -o IdentitiesOnly=yes"
        result = subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            env=environment,
        )
        if check and result.returncode:
            raise RuntimeError(f"Git завершился с ошибкой: {result.stderr.strip()}")
        return result.stdout.strip()

    def has_staged_changes(self) -> bool:
        """Явно определить наличие изменений в индексе Git."""
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            check=False,
        )
        if result.returncode == 0:
            return False
        if result.returncode == 1:
            return True
        raise RuntimeError(f"Не удалось проверить индекс Git: {result.stderr.strip()}")

    def create_candidate(self, name: str) -> None:
        """Создать новую ветку от основной ветки."""
        self.run("switch", self.main_branch)
        self.run("switch", "-c", name)

    def discard_candidate(self, branch: str) -> None:
        """Удалить неудачную ветку и оставленные ею файлы-кандидаты."""
        self.run("switch", self.main_branch)
        self.run(
            "restore",
            "--source",
            self.main_branch,
            "--staged",
            "--worktree",
            "--",
            "src",
            "tests",
        )
        self.run("clean", "-fd", "--", "src", "tests")
        self.run("branch", "-D", branch)

    def commit_candidate(self, message: str) -> None:
        """Зафиксировать только уже выбранные изменения."""
        self.run("add", "--", "src", "README.md", "pyproject.toml")
        if not self.has_staged_changes():
            raise RuntimeError("Кандидат не содержит изменений для коммита.")
        self.run("commit", "-m", message)

    def merge_candidate(self, branch: str) -> None:
        """Слить проверенную ветку локально в основную."""
        self.run("switch", self.main_branch)
        self.run("merge", "--no-ff", "--no-edit", branch)
        self.log.info("Ветка {} слита в {}.", branch, self.main_branch)
