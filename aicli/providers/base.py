"""
providers/base.py — Abstract base class for all inference providers.
"""
from abc import ABC, abstractmethod
from typing import AsyncGenerator


class BaseProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def stream(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        requires_vision: bool = False,
    ) -> AsyncGenerator[str, None]: ...

    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        requires_vision: bool = False,
    ) -> str: ...

    def __repr__(self) -> str:
        return f"<Provider: {self.name}>"
