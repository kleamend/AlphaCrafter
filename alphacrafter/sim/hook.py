from pathlib import Path
from typing import Callable, Dict, Any, Optional
import os
import traceback
import importlib.util
import sys


class Hook:
    """Simple hook system that loads and executes registered hook functions from a Python file."""
    
    def __init__(self, strategy_file_path: str):
        """
        Initialize hook with path to strategy file.
        
        Args:
            strategy_file_path: Path to the Python file containing registered hooks
        """
        self.file_path = Path(strategy_file_path).absolute()
        print(f"🔍 Looking for strategy file at: {self.file_path}")
        
        self.hook_function: Optional[Callable] = None
        self._load_hooks()
    
    def _load_hooks(self) -> None:
        """Load the first function decorated with @register_hook from the strategy file using importlib."""
        if not self.file_path.exists():
            print(f"❌ File does not exist: {self.file_path}")
            print(f"   Current working directory: {Path.cwd()}")
            print(f"   Please check if the file exists and the path is correct")
            raise FileNotFoundError(f"File not found: {self.file_path}")
        
        print(f"✅ Found strategy file: {self.file_path}")
        
        try:
            module_name = self.file_path.stem
            
            spec = importlib.util.spec_from_file_location(module_name, self.file_path)
            if spec is None or spec.loader is None:
                print(f"❌ Failed to create module spec for {self.file_path}")
                return
            
            module = importlib.util.module_from_spec(spec)

            sys.modules[module_name] = module

            spec.loader.exec_module(module)
            
            print(f"✅ File imported successfully as module: {module_name}")
            
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
                print("⚠️ No registered hook function found in strategy file")
                print("   Make sure your strategy file has a function decorated with @register_hook")
                
        except Exception as e:
            print(f"❌ Error loading hook file: {e}")
            traceback.print_exc()
            raise
    
    def on_tick(self) -> Any:
        """
        Execute the registered hook function.
        
        Returns:
            Result of the hook function execution
        
        Raises:
            Exception: When hook function fails or is not registered
        """
        if self.hook_function is None:
            error_msg = "No hook function registered. Make sure to decorate your strategy function with @register_hook"
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