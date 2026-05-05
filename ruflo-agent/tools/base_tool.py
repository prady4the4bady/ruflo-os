from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class BaseTool(ABC):
    """Base class for all Ruflo Agent tools."""

    name: str = "base_tool"
    description: str = "Base tool"

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        pass

    def validate_params(self, **kwargs) -> bool:
        return True