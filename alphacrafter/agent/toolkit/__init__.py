"""
Agent 工具集合（toolkit）入口

将所有具体工具类对外统一暴露，外部模块只需要：
    from agent.toolkit import ReadFileTool, WriteFileTool, ...
即可拿到完整工具集合，无需关心具体实现路径。

该文件本身不包含业务逻辑，仅做"工具类聚合 + __all__ 导出"。
"""

from .read_file import ReadFileTool
from .write_file import WriteFileTool
from .shell import ShellTool
from .add_order import AddOrderTool
from .cancel_order import CancelOrderTool
from .get_stock_data import GetStockDataTool
from .step import StepTool
from .get_news import GetNewsTool
from .get_index_data import GetIndexDataTool
from .get_financial_statements import GetFinancialStatementsTool
from .backtest import BacktestTool
from .search_factor import SearchFactorTool

# ── 显式导出列表 ────────────────────────────────────
# 仅暴露工具类本身，屏蔽具体实现细节；外部 `from agent.toolkit import *`
# 只会得到这些符号，避免命名空间污染。
__all__ = [
    'ReadFileTool',
    'WriteFileTool',
    'ShellTool',
    'AddOrderTool',
    'CancelOrderTool',
    'GetStockDataTool',
    'StepTool',
    'GetNewsTool',
    'GetIndexDataTool',
    'GetFinancialStatementsTool',
    'BacktestTool',
    'SearchFactorTool',
]
