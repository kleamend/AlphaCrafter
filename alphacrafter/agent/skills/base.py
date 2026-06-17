"""
技能系统抽象基类

功能概述：
    定义 Agent "技能"（Skill）的统一接口。
    与 Tool 不同的是，Skill 通常是一段被注入到 system prompt 中的
    领域知识（如 "如何挖因子"、"如何管理仓位"），而非可调用函数。

设计意图：
    - 让 LLM 在 prompt 层面掌握特定领域的"操作手册"
    - 三个抽象方法分别对应 system prompt 中的"名称 / 简介 / 详细说明"
"""

from abc import ABC, abstractmethod


class BaseSkill(ABC):
    """所有技能类的抽象基类。"""

    @abstractmethod
    def get_name(self) -> str:
        """返回技能名称（在 Agent 初始化时打印，便于调试）。"""
        pass

    @abstractmethod
    def get_description(self) -> str:
        """返回简短描述（一句话说明该技能的作用）。"""
        pass

    @abstractmethod
    def get_details(self) -> str:
        """返回详细的技能说明（Markdown 文本，会被完整注入到 system prompt）。"""
        pass
