"""
读文件工具（ReadFileTool）

功能概述：
    暴露给 LLM Agent 使用的"读取本地文件"工具。
    适用于读取策略文件、日志、临时数据等任意文本文件。

设计要点：
    - 简单异常捕获：将所有 IO 错误转为字符串消息返回给 Agent，
      避免工具调用抛出未处理异常导致 Agent run 中断。
    - 统一 UTF-8 编码：与项目其它文件保持一致。
"""

from typing import Dict, Any, Callable
from .base import BaseTool


class ReadFileTool(BaseTool):
    """读取文件内容的工具。

    该工具以 UTF-8 编码读取指定路径的文本文件并返回其内容字符串。
    若文件不存在或读取失败，将返回形如 "Failed to read file: ..." 的错误信息。
    """

    def get_name(self) -> str:
        """工具注册名（必须与 LLM 调用的 `name` 字段一致）。"""
        return "read_file"

    def get_implementation(self) -> Callable:
        """构造真正的读取函数闭包并返回。

        使用闭包形式封装逻辑，可在未来加入额外的实例参数
        （如工作目录、文件大小限制等）而不影响 Agent 调用方式。
        """
        def read_file(file_path: str) -> str:
            """读取文件全部内容。

            参数:
                file_path: 目标文件的绝对路径或相对路径。

            返回值:
                文件内容字符串；失败时返回错误描述。
            """
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                # 任何 IO 错误都转成可读字符串，LLM 更容易据此决定下一步操作
                return f"Failed to read file: {str(e)}"
        return read_file

    def get_description(self, producer: str = "OpenAI") -> Dict[str, Any]:
        """返回符合 OpenAI 工具调用规范的描述字典。

        参数:
            producer: 当前使用的 LLM 生产方；当前实现仅支持 OpenAI。
        """
        if producer in ("OpenAI", "MiniMax"):
            return {
                "type": "function",
                "name": self.get_name(),
                "description": "Read content from a specified file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the file to read",
                        }
                    },
                    "required": ["file_path"],
                },
            }

        raise ValueError(f"Unsupported producer: {producer}")
