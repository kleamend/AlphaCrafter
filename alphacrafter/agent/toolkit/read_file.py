from typing import Dict, Any, Callable
from .base import BaseTool


class ReadFileTool(BaseTool):
    """Tool for reading file contents."""
    
    def get_name(self) -> str:
        return "read_file"
    
    def get_implementation(self) -> Callable:
        def read_file(file_path: str) -> str:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                return f"Failed to read file: {str(e)}"
        return read_file
    
    def get_description(self, producer: str = "OpenAI") -> Dict[str, Any]:
        """
        Return tool description based on the producer.
        
        Args:
            producer: The model producer (currently supports "OpenAI")
                     Can be extended for other providers like Anthropic, Google, etc.
        """
        if producer == "OpenAI":
            return {
                "type": "function",
                "name": self.get_name(),
                "description": "Read content from a specified file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the file to read"
                        }
                    },
                    "required": ["file_path"]
                }
            }
        
        else:
            raise ValueError(f"Unsupported producer: {producer}")