from abc import ABC, abstractmethod
from typing import Dict, Any, Callable


class BaseTool(ABC):
    """Abstract base class for all tools."""

    @abstractmethod
    def get_name(self) -> str:
        """Return the name of the tool."""
        pass
    
    @abstractmethod
    def get_implementation(self) -> Callable:
        """Return the actual function implementation."""
        pass
    
    @abstractmethod
    def get_description(self, producer: str = "OpenAI") -> Dict[str, Any]:
        """
        Return the tool description in dictionary format based on the producer.
        
        Args:
            producer: The model producer (e.g., "OpenAI", "Anthropic", etc.)
                     Different producers may have different SDK formats.
        
        Returns:
            Dictionary containing the tool description in the appropriate format.
        """
        pass