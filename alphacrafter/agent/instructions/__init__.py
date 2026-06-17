"""
指令模板集合（instructions）入口

把不同 Agent / 不同市场使用的 system prompt 字符串统一暴露，
方便外部模块按名称直接 import。

各字符串的语义:
    - QUANTITATIVE_TRADING_INSTRUCTION_A: A 股市场通用规则
    - QUANTITATIVE_TRADING_INSTRUCTION_US: 美股市场通用规则
    - MINER_INSTRUCTION: 因子挖掘 Agent 的角色与工作流
    - SCREENER_INSTRUCTION: 因子筛选 Agent 的角色与工作流
    - TRADER_INSTRUCTION: 组合交易 Agent 的角色与工作流
"""

from .quantitative_trading_a import QUANTITATIVE_TRADING_INSTRUCTION_A
from .quantitative_trading_us import QUANTITATIVE_TRADING_INSTRUCTION_US
from .miner import MINER_INSTRUCTION
from .trader import TRADER_INSTRUCTION
from .screener import SCREENER_INSTRUCTION

# ── 显式导出列表 ────────────────────────────────────
__all__ = [
    "QUANTITATIVE_TRADING_INSTRUCTION_A",
    "QUANTITATIVE_TRADING_INSTRUCTION_US",
    "MINER_INSTRUCTION",
    "TRADER_INSTRUCTION",
    "SCREENER_INSTRUCTION",
]
