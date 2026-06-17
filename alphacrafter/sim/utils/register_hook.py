"""
@register_hook 装饰器

功能概述：
    把"普通函数"标记为策略钩子（hook），配合 sim.hook.Hook 在扫描时识别。
    实现极简：仅在函数对象上挂一个 `_is_hook = True` 属性。

注意：
    - 一个 strategy.py 内仅第一个被标记的函数会被 Hook 加载并执行
    - 业务规则参见 alphacrafter/sim/hook.py
"""

from collections.abc import Callable


def register_hook(func: Callable) -> Callable:
    """装饰器：把函数标记为可被 Hook 加载的策略钩子。

    用法:
        @register_hook
        def my_strategy():
            ...

    参数:
        func: 待标记的函数。

    返回值:
        原函数对象，仅多出 `_is_hook = True` 属性。
    """
    func._is_hook = True
    return func
