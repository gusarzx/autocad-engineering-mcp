"""Serializable backend boundary; never return a COM interface through it."""

from typing import Any, Protocol


class Adapter(Protocol):
    """Commands execute in order and return only plain Python data."""

    backend: str

    def execute(self, command: str, arguments: dict[str, Any]) -> dict[str, Any]: ...

    def close(self) -> None: ...
