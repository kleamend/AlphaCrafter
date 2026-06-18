"""
写文件工具（WriteFileTool）

功能概述：
    暴露给 LLM Agent 使用的"覆盖写入本地文件"工具。
    与 read_file 工具配套，常用于保存生成的策略代码、报告与中间结果。

设计要点：
    - 写入采用 UTF-8 编码并覆盖已有内容（与 read_file 行为对称）。
    - 异常以字符串形式返回，使 LLM 收到错误后可决定重试或调整。
"""

from typing import Dict, Any, Callable
from .base import BaseTool


class WriteFileTool(BaseTool):
    """将字符串内容写入指定文件的工具。

    注意：使用 'w' 模式会覆盖已有文件；如需追加请使用其他方式。
    """

    def get_name(self) -> str:
        """工具注册名。"""
        return "write_file"

    def get_implementation(self) -> Callable:
        """构造写入函数闭包。"""
        def write_file(file_path: str, content: str) -> str:
            """将内容写入文件。

            参数:
                file_path: 目标文件路径。
                content:   要写入的完整文本内容。

            返回值:
                成功时返回确认信息；失败时返回错误描述。
            """
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                return f"Successfully wrote to file: {file_path}"
            except Exception as e:
                return f"Failed to write file: {str(e)}"
        return write_file

    def get_description(self, producer: str = "OpenAI") -> Dict[str, Any]:
        """返回 OpenAI 工具描述 schema。"""
        if producer in ("OpenAI", "MiniMax"):
            return {
                "type": "function",
                "name": self.get_name(),
                "description": "Write content to a specified file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the target file",
                        },
                        "content": {
                            "type": "string",
                            "description": "Content to write to the file",
                        },
                    },
                    "required": ["file_path", "content"],
                },
            }

        raise ValueError(f"Unsupported producer: {producer}")
