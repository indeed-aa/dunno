"""Изолированная проверка кандидатного образа Docker."""

import subprocess
from pathlib import Path

from selfagent.config import Settings
from selfagent.logging import Logging


class CandidateRunner:
    """Собирает образ кандидата и запускает тесты без сети и секретов."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = settings.repository_root.resolve()
        self.log = Logging.for_class(type(self))

    def _run(self, command: list[str], timeout: int) -> str:
        result = subprocess.run(
            command,
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
        )
        output = (result.stdout + "\n" + result.stderr).strip()
        if result.returncode:
            raise RuntimeError(f"Проверка кандидата не пройдена:\n{output[-6000:]}")
        return output

    def validate(self) -> None:
        """Собрать образ и запустить pytest в контейнере с ограничениями."""
        self.log.info("Сборка изолированного Docker-образа кандидата.")
        self._run(
            ["docker", "build", "--pull", "--tag", self.settings.docker_image, "."],
            self.settings.docker_timeout_seconds,
        )
        self._run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--memory",
                "1g",
                "--cpus",
                "2",
                "--pids-limit",
                "128",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=128m",
                "--entrypoint",
                "python",
                self.settings.docker_image,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
            ],
            self.settings.docker_timeout_seconds,
        )
