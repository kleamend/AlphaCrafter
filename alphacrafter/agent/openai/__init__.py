"""
agent.openai 子包入口

该文件保持为空；当前对外暴露三个 Agent 实现：
    - agent.Agent        ：OpenAI Responses API 版（原生 function calling 协议）
    - agent.GeneralAgent ：Chat Completions + XML 工具调用（兜底通用版）
    - chat_agent.ChatAgent：Chat Completions + 原生 tool calling（OpenAI 兼容端点首选，
                            如 MiniMax-M3）
"""

from .agent import Agent
from .general_agent import Agent as GeneralAgent
from .chat_agent import ChatAgent

__all__ = ["Agent", "GeneralAgent", "ChatAgent"]
