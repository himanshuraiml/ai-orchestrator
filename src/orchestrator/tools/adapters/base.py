from abc import ABC, abstractmethod


class ToolAdapter(ABC):
    """What ToolExecutor dispatches to — arch doc §22/§24."""

    @abstractmethod
    async def invoke(self, arguments: dict) -> dict:
        raise NotImplementedError
