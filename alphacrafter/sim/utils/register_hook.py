from collections.abc import Callable

def register_hook(func: Callable) -> Callable:
    """
    Decorator to mark a function as a hook.
    
    Args:
        func: Function to be marked as hook
        
    Returns:
        The same function with _is_hook attribute set to True
    """
    func._is_hook = True
    return func