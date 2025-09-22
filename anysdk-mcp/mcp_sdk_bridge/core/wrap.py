# anysdk-mcp/mcp_sdk_bridge/core/wrap.py

"""
SDK Wrapper Module

Wraps SDK methods to make them compatible with MCP tool interface.
"""

from typing import Any, Dict, Callable, Optional, List
import asyncio
import functools
import traceback
from .discover import SDKMethod
from .serialize import ResponseSerializer


class SDKWrapper:
    """Wraps SDK methods for MCP compatibility"""
    
    def __init__(self, serializer: Optional[ResponseSerializer] = None):
        self.serializer = serializer or ResponseSerializer()
        self.wrapped_methods: Dict[str, Callable] = {}
    
    def wrap_method(self, method: SDKMethod, sdk_instance: Any) -> Callable:
        """Wrap an SDK method for MCP tool usage"""
        original_func = getattr(sdk_instance, method.name)
        
        if method.is_async:
            return self._wrap_async_method(method, original_func)
        else:
            return self._wrap_sync_method(method, original_func)
    
    def _wrap_sync_method(self, method: SDKMethod, func: Callable) -> Callable:
        """Wrap a synchronous method"""
        @functools.wraps(func)
        def wrapper(**kwargs) -> Dict[str, Any]:
            try:
                # Filter kwargs to only include method parameters
                filtered_kwargs = self._filter_kwargs(method, kwargs)
                result = func(**filtered_kwargs)
                return self.serializer.serialize_response(result)
            except Exception as e:
                return self._handle_error(e, method.name)
        
        return wrapper
    
    def _wrap_async_method(self, method: SDKMethod, func: Callable) -> Callable:
        """Wrap an asynchronous method"""
        @functools.wraps(func)
        async def wrapper(**kwargs) -> Dict[str, Any]:
            try:
                # Filter kwargs to only include method parameters
                filtered_kwargs = self._filter_kwargs(method, kwargs)
                result = await func(**filtered_kwargs)
                return self.serializer.serialize_response(result)
            except Exception as e:
                return self._handle_error(e, method.name)
        
        return wrapper
    
    def _filter_kwargs(self, method: SDKMethod, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Filter kwargs to only include valid method parameters"""
        filtered = {}
        for param_name in method.parameters.keys():
            if param_name != "self" and param_name in kwargs:
                filtered[param_name] = kwargs[param_name]
        return filtered
    
    def _handle_error(self, error: Exception, method_name: str) -> Dict[str, Any]:
        """Handle and serialize errors"""
        return {
            "error": {
                "type": type(error).__name__,
                "message": str(error),
                "method": method_name,
                "traceback": traceback.format_exc()
            }
        }
    
    def register_wrapped_method(self, tool_name: str, wrapped_method: Callable):
        """Register a wrapped method by tool name"""
        self.wrapped_methods[tool_name] = wrapped_method
    
    def get_wrapped_method(self, tool_name: str) -> Optional[Callable]:
        """Get a wrapped method by tool name"""
        return self.wrapped_methods.get(tool_name)


class BatchWrapper:
    """Handles batch operations for SDK methods"""
    
    def __init__(self, wrapper: SDKWrapper):
        self.wrapper = wrapper
    
    async def execute_batch(self, operations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute a batch of operations"""
        results = []
        
        for operation in operations:
            tool_name = operation.get("tool")
            arguments = operation.get("arguments", {})
            
            wrapped_method = self.wrapper.get_wrapped_method(tool_name)
            if wrapped_method:
                try:
                    if asyncio.iscoroutinefunction(wrapped_method):
                        result = await wrapped_method(**arguments)
                    else:
                        result = wrapped_method(**arguments)
                    results.append(result)
                except Exception as e:
                    results.append(self.wrapper._handle_error(e, tool_name))
            else:
                results.append({
                    "error": {
                        "type": "MethodNotFound",
                        "message": f"Tool {tool_name} not found",
                        "tool": tool_name
                    }
                })
        
        return results
