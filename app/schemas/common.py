"""app/schemas/common.py — Shared Pydantic types."""
from __future__ import annotations

from math import ceil

from fastapi import Query
from pydantic import BaseModel, Field, model_validator

from app.core.config import get_settings

settings = get_settings()


class PaginationParams(BaseModel):
    """Dependency-injectable pagination. Use with Depends()."""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=settings.default_page_size, ge=1, le=settings.max_page_size)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class PaginatedResponse(BaseModel):
    """Envelope for all paginated list endpoints."""

    items: list
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool

    @classmethod
    def create(cls, items: list, total: int, pagination: PaginationParams) -> "PaginatedResponse":
        total_pages = max(1, ceil(total / pagination.page_size))
        return cls(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
            total_pages=total_pages,
            has_next=pagination.page < total_pages,
            has_prev=pagination.page > 1,
        )


class MessageResponse(BaseModel):
    message: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict | None = None
