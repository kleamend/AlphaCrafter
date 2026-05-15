from typing import Dict, Any, Callable
from .base import BaseTool


class WriteFileTool(BaseTool):
    """Tool for writing content to files."""
    
    def get_name(self) -> str:
        return "write_file"
    
    def get_implementation(self) -> Callable:
        def write_file(file_path: str, content: str) -> str:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                return f"Successfully wrote to file: {file_path}"
            except Exception as e:
                return f"Failed to write file: {str(e)}"
        return write_file
    
    def get_description(self, producer: str = "OpenAI") -> Dict[str, Any]:
        """
        Return tool description based on the producer.
        
        Args:
            producer: The model producer (currently supports "OpenAI")
        """
        if producer == "OpenAI":
            return {
                "type": "function",
                "name": self.get_name(),
                "description": "Write content to a specified file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the target file"
                        },
                        "content": {
                            "type": "string",
                            "description": "Content to write to the file"
                        }
                    },
                    "required": ["file_path", "content"]
                }
            }

        else:
            raise ValueError(f"Unsupported producer: {producer}")