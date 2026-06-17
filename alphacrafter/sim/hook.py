"""
策略钩子加载器（Hook）

功能概述：
    负责从外部 strategy.py 中加载由 `@register_hook` 装饰的策略函数，
    并在每个仿真交易日触发该函数（"tick"）。

设计意图：
    - 让 Agent 把策略代码写到 workspace/strategy.py，仿真循环就能在每个
      pre_tick/post_tick 之间执行它
    - 装饰器只标记函数为"钩子"，Hook 通过 importlib 动态加载并扫一遍
      找到第一个带 `_is_hook` 属性的可调用对象
"""

from pathlib import Path
from typing import Callable, Dict, Any, Optional
import os
import traceback
import importlib.util
import sys


class Hook:
    """加载并执行 strategy.py 中由 @register_hook 装饰的策略函数。"""

    def __init__(self, strategy_file_path: str):
        """初始化钩子加载器。

        参数:
            strategy_file_path: 策略 Python 文件路径（通常为 ./strategy.py）。
        """
        # 转绝对路径便于日志
        self.file_path = Path(strategy_file_path).absolute()
        print(f"🔍 Looking for strategy file at: {self.file_path}")

        self.hook_function: Optional[Callable] = None
        self._load_hooks()

    # ── 钩子加载 ───────────────────────────

    def _load_hooks(self) -> None:
        """用 importlib 动态加载 strategy.py，扫到第一个带 `_is_hook` 标记的函数。"""
        if not self.file_path.exists():
            print(f"❌ File does not exist: {self.file_path}")
            print(f"   Current working directory: {Path.cwd()}")
            print(f"   Please check if the file exists and the path is correct")
            raise FileNotFoundError(f"File not found: {self.file_path}")

        print(f"✅ Found strategy file: {self.file_path}")

        try:
            module_name = self.file_path.stem

            # 用 importlib 把 strategy.py 当独立模块加载
            spec = importlib.util.spec_from_file_location(module_name, self.file_path)
            if spec is None or spec.loader is None:
                print(f"❌ Failed to create module spec for {self.file_path}")
                return

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            print(f"✅ File imported successfully as module: {module_name}")

            # 扫描模块属性，找到第一个被 @register_hook 标记的函数
            print("🔍 Searching for hook functions...")
            hook_found = False

            for name in dir(module):
                obj = getattr(module, name)
                if callable(obj) and hasattr(obj, '_is_hook'):
                    self.hook_function = obj
                    print(f"✅ Hook loaded: {name}")
                    hook_found = True
                    return

            if not hook_found:
                # 没有 hook 时不抛错，仿真仍然可推进（策略层"缺席"）
                print("⚠️ No registered hook function found in strategy file")
                print("   Make sure your strategy file has a function decorated with @register_hook")

        except Exception as e:
            print(f"❌ Error loading hook file: {e}")
            traceback.print_exc()
            raise

    # ── 钩子触发 ───────────────────────────

    def on_tick(self) -> Any:
        """执行一次钩子函数（每个仿真交易日调用一次）。

        返回值:
            钩子函数的返回值（当前实现未使用，仅透传）。

        异常:
            当未注册钩子或钩子执行失败时抛出 RuntimeError / 原始异常。
        """
        if self.hook_function is None:
            error_msg = (
                "No hook function registered. "
                "Make sure to decorate your strategy function with @register_hook"
            )
            print(f"❌ {error_msg}")
            raise RuntimeError(error_msg)

        try:
            print(f"🔄 Executing hook function...")
            result = self.hook_function()
            print(f"✅ Hook execution completed")
            return result
        except Exception as e:
            print(f"❌ Hook execution failed: {e}")
            print("📋 Traceback:")
            traceback.print_exc()
            raise
