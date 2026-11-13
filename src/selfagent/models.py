"""Типы Pydantic для результатов работы агентов."""

from typing import Annotated, Literal
from pathlib import PurePosixPath

from pydantic import BaseModel, Field, StringConstraints, model_validator


class ImprovementPlan(BaseModel):
    """Краткий план одного небольшого улучшения."""

    summary: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=8, max_length=160),
    ] = Field(description="Краткое описание улучшения на русском")
    rationale: str = Field(description="Обоснование на русском")
    files_to_read: list[str] = Field(default_factory=list)


class FileChange(BaseModel):
    """Полное содержимое одного изменяемого файла."""

    path: str = Field(description="Относительный путь внутри репозитория")
    content: str = Field(description="Полное новое содержимое файла")


class CandidatePatch(BaseModel):
    """Набор ограниченных изменений для одной ветки-кандидата."""

    changes: list[FileChange] = Field(min_length=1, max_length=8)
    explanation: str

    @model_validator(mode="after")
    def require_unique_paths(self) -> "CandidatePatch":
        """Отклонить пути, которые совпадают после нормализации."""
        paths = [
            PurePosixPath(change.path).as_posix().casefold() for change in self.changes
        ]
        if len(paths) != len(set(paths)):
            raise ValueError("Пути файлов в патче должны быть уникальными.")
        return self


class ReviewDecision(BaseModel):
    """Вердикт независимого ревьюера."""

    approved: bool
    findings: list[str] = Field(default_factory=list)
    rationale: str


class FailureAnalysis(BaseModel):
    """Разбор сбоя и безопасная рекомендация для одной попытки восстановления."""

    failure_type: Literal[
        "token_limit",
        "candidate_rejected",
        "validation_failed",
        "provider_error",
        "git_error",
        "unknown",
    ]
    summary: str = Field(description="Краткий вывод на русском языке")
    diagnosis: str = Field(description="Причина сбоя, подтверждённая журналом")
    retry_recommended: bool = Field(
        description="Можно ли безопасно повторить цикл с целевой коррекцией"
    )
    recovery_instruction: str = Field(
        description="Конкретная инструкция планировщику и разработчику на русском"
    )
    recommended_max_output_tokens: int | None = Field(default=None, ge=4096, le=32768)
