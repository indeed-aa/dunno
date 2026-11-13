"""Проверки очистки неудачной кандидатной ветки Git."""

import subprocess
from pathlib import Path

from selfagent.core.git import GitRepository


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_discard_candidate_removes_intent_to_add_files(tmp_path: Path) -> None:
    """Очистка удаляет новые файлы и вложенные каталоги кандидата."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "tracked.py").write_text("value = 1\n", encoding="utf-8")
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "config", "user.name", "SelfAgent test")
    _git(tmp_path, "config", "user.email", "selfagent-test@localhost")
    _git(tmp_path, "add", "src/tracked.py")
    _git(tmp_path, "commit", "-m", "Подготовить тестовый репозиторий")

    repository = GitRepository(tmp_path, "main", Path("~/.ssh/dunno-deploy"))
    branch = "selfagent/test-cleanup"
    repository.create_candidate(branch)
    tracked_file = tmp_path / "src" / "tracked.py"
    tracked_file.write_text("value = 2\n", encoding="utf-8")
    candidate_file = tmp_path / "tests" / "new_test.py"
    candidate_file.write_text("def test_new():\n    assert True\n", encoding="utf-8")
    nested_candidate_file = tmp_path / "src" / "candidate" / "nested.py"
    nested_candidate_file.parent.mkdir()
    nested_candidate_file.write_text("value = 3\n", encoding="utf-8")
    _git(tmp_path, "add", "--intent-to-add", "--", "tests", "src/candidate")

    repository.discard_candidate(branch)

    assert not candidate_file.exists()
    assert not nested_candidate_file.parent.exists()
    assert tracked_file.read_text(encoding="utf-8") == "value = 1\n"
    assert repository.run("status", "--porcelain") == ""
    assert repository.run("branch", "--list", branch) == ""
