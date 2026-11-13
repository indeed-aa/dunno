"""Типы Pydantic для результатов работы агентов."""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


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


class ReviewDecision(BaseModel):
    """Вердикт независимого ревьюера."""

    approved: bool
    findings: list[str] = Field(default_factory=list)
    rationale: str
