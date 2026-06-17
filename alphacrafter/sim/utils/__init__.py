"""
sim.utils 子包入口

把仿真过程中常用的"程序级"工具函数聚合导出，便于 strategy.py 与上层脚本使用。

各函数用途:
    - add_order / cancel_order:           订单提交 / 撤单（程序接口）
    - get_stock_daily_data:              读取单只股票历史 DataFrame
    - get_index_daily_data:              读取指数历史 DataFrame
    - get_account_dict:                  读取账户原始字典
    - get_date_str:                      读取当前仿真日期字符串
    - finish_check:                      仿真结束条件判断
    - register_hook:                     @register_hook 装饰器
"""

from .add_order import add_order
from .cancel_order import cancel_order
from .get_stock_daily_data import get_stock_daily_data
from .register_hook import register_hook
from .finish_check import finish_check
from .get_account_dict import get_account_dict
from .get_index_daily_data import get_index_daily_data
from .get_date_str import get_date_str

__all__ = [
    "add_order",
    "cancel_order",
    "get_stock_daily_data",
    "register_hook",
    "finish_check",
    "get_account_dict",
    "get_index_daily_data",
    "get_date_str",
]
