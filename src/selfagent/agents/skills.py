"""Подключение проектных навыков Pydantic к ролям агента."""

import re
from pathlib import Path, PurePosixPath

from pydantic_ai.workspaces import (
    FileEntry,
    SupportsFilesystem,
    SupportsRealpath,
    WorkspaceRef,
)
from pydantic_ai_harness import Skills

from selfagent.config import Settings

PROJECT_SKILLS = {
    "pydantic",
    "pydantic-ai-harness",
    "building-pydantic-ai-agents",
}


class LocalReadOnlyWorkspaceBackend(SupportsFilesystem, SupportsRealpath):
    """Предоставляет Harness Skills доступ только на чтение к навыкам проекта."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._ref = WorkspaceRef(provider="local", id=self.root.as_posix())

    @property
    def ref(self) -> WorkspaceRef:
        return self._ref

    async def working_dir(self) -> str:
        return self._workspace_path(self.root)

    @staticmethod
    def _workspace_path(path: Path) -> str:
        rendered = path.as_posix()
        if re.match(r"^[A-Za-z]:/", rendered):
            return f"/{rendered}"
        return rendered

    def _path(self, path: str) -> Path:
        path = re.sub(r"^/([A-Za-z]:/)", r"\1", path)
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.root.joinpath(*PurePosixPath(path).parts)
        resolved = candidate.resolve(strict=False)
        if not resolved.is_relative_to(self.root):
            raise PermissionError("Доступ к файлу за пределами корня навыков запрещён.")
        return resolved

    async def read_bytes(self, path: str) -> bytes:
        target = self._path(path)
        if not target.is_file():
            if target.is_dir():
                raise IsADirectoryError(path)
            raise FileNotFoundError(path)
        return target.read_bytes()

    async def stat(self, path: str) -> FileEntry:
        target = self._path(path)
        info = target.stat()
        return FileEntry(
            name=target.name or self.root.name,
            path=self._workspace_path(target),
            is_dir=target.is_dir(),
            size=None if target.is_dir() else info.st_size,
        )

    async def list_dir(self, path: str) -> tuple[FileEntry, ...]:
        target = self._path(path)
        if not target.is_dir():
            if target.exists():
                raise NotADirectoryError(path)
            raise FileNotFoundError(path)
        entries = []
        for child in target.iterdir():
            info = child.stat()
            entries.append(
                FileEntry(
                    name=child.name,
                    path=self._workspace_path(child.resolve(strict=False)),
                    is_dir=child.is_dir(),
                    size=None if child.is_dir() else info.st_size,
                )
            )
        return tuple(entries)

    async def realpath(self, path: str) -> str:
        return self._workspace_path(self._path(path))

    async def exists(self, path: str) -> bool:
        return self._path(path).exists()

    async def write_bytes(self, path: str, data: bytes) -> None:
        raise PermissionError("Изменение файлов навыков запрещено.")

    async def make_dir(self, path: str) -> None:
        raise PermissionError("Создание файлов навыков запрещено.")

    async def remove(self, path: str) -> None:
        raise PermissionError("Удаление файлов навыков запрещено.")


def project_skills(settings: Settings) -> Skills:
    """Создать отложенный каталог доверенных навыков проекта."""
    return Skills(
        Path(".agents") / "skills",
        include=PROJECT_SKILLS,
        workspace=LocalReadOnlyWorkspaceBackend(settings.repository_root),
    )
