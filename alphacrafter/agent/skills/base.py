from abc import ABC, abstractmethod

class BaseSkill(ABC):
    """Abstract base class for all skills"""
    
    @abstractmethod
    def get_name(self) -> str:
        """Get skill name"""
        pass
    
    @abstractmethod
    def get_description(self) -> str:
        """Get skill description"""
        pass
    
    @abstractmethod
    def get_details(self) -> str:
        """Get detailed skill instructions"""
        pass