"""Проверки операций Git с индексом."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from selfagent.core.git import GitRepository


def создать_репозиторий(временный_каталог: Path) -> GitRepository:
    """Создать объект репозитория для тестирования."""
    return GitRepository(временный_каталог, "main", временный_каталог / "ключ")


@pytest.mark.parametrize(
    ("код_завершения", "есть_изменения"),
    [(0, False), (1, True)],
)
def test_проверка_индекса_обрабатывает_коды_git(
    tmp_path: Path, код_завершения: int, есть_изменения: bool
) -> None:
    """Коды 0 и 1 означают отсутствие и наличие staged-изменений."""
    репозиторий = создать_репозиторий(tmp_path)
    результат = SimpleNamespace(returncode=код_завершения, stdout="", stderr="")

    with patch("selfagent.core.git.subprocess.run", return_value=результат) as запуск:
        assert репозиторий.has_staged_changes() is есть_изменения

    assert запуск.call_args.args[0] == ["git", "diff", "--cached", "--quiet"]
    assert запуск.call_args.kwargs["check"] is False


def test_проверка_индекса_считает_прочие_коды_ошибкой(tmp_path: Path) -> None:
    """Код, отличный от 0 и 1, не принимается за обычный diff."""
    репозиторий = создать_репозиторий(tmp_path)
    результат = SimpleNamespace(returncode=2, stdout="", stderr="ошибка Git")

    with (
        patch("selfagent.core.git.subprocess.run", return_value=результат),
        pytest.raises(RuntimeError, match="ошибка Git"),
    ):
        репозиторий.has_staged_changes()
