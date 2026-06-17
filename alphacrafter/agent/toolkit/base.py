"""
工具系统抽象基类

功能概述：
    定义 AlphaCrafter 工具系统中所有具体工具类必须遵循的抽象接口。
    通过统一的 ABC 协议，Agent 可以一致地加载、调用和管理任意数量的工具。

设计意图：
    - 解耦"工具如何实现"与"工具如何被 Agent 调用"
    - 支持多厂商描述（OpenAI / Anthropic / Google 等），便于切换 LLM 提供方
    - 通过函数引用（Callable）实现延迟绑定，避免循环导入
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Callable


class BaseTool(ABC):
    """所有工具类的抽象基类。

    任何被 Agent 加载的工具必须继承该类并实现三个抽象方法。
    这种统一接口使得 Agent 在运行期可以通过 get_name() / get_implementation() /
    get_description() 三步完成工具的注册与调用。
    """

    @abstractmethod
    def get_name(self) -> str:
        """返回工具的唯一名称。

        名称必须与 LLM 在工具调用请求中使用的 `name` 字段完全一致，
        Agent 会以此为键将工具函数注册到 `function_map` 中。
        """
        pass

    @abstractmethod
    def get_implementation(self) -> Callable:
        """返回工具函数的可调用实现。

        返回一个闭包或普通函数，Agent 将通过 `**arguments` 形式直接调用。
        采用工厂方法模式，便于注入实例状态（如文件路径、缓存等）。
        """
        pass

    @abstractmethod
    def get_description(self, producer: str = "OpenAI") -> Dict[str, Any]:
        """返回符合 LLM 工具调用协议的描述字典。

        参数:
            producer: 模型生产方标识，例如 "OpenAI"、"Anthropic"、"Google" 等。
                     不同厂商对工具 schema 的字段名 / 格式要求不同，
                     通过该参数做适配，可避免上层 Agent 关心差异。

        返回值:
            一个字典，遵循选定 LLM 厂商的工具描述规范（function / parameters 等）。
        """
        pass
