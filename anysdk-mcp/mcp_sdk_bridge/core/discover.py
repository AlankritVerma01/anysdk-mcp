# anysdk-mcp/mcp_sdk_bridge/core/discover.py

"""
SDK Discovery Module

Discovers available methods, endpoints, and capabilities from SDK documentation
and runtime inspection.
"""

from typing import Dict, List, Any, Optional
import inspect
import importlib
from dataclasses import dataclass


@dataclass
class SDKMethod:
    """Represents a discoverable SDK method"""
    name: str
    description: str
    parameters: Dict[str, Any]
    return_type: str
    module_path: str
    is_async: bool = False


@dataclass
class SDKCapability:
    """Represents an SDK capability or feature"""
    name: str
    description: str
    methods: List[SDKMethod]
    requires_auth: bool = False


class SDKDiscoverer:
    """Discovers SDK capabilities and methods"""
    
    def __init__(self, sdk_name: str):
        self.sdk_name = sdk_name
        self.discovered_methods: List[SDKMethod] = []
        self.capabilities: List[SDKCapability] = []
    
    def discover_module(self, module_name: str) -> List[SDKMethod]:
        """Discover methods in a given module"""
        try:
            module = importlib.import_module(module_name)
            methods = []
            
            for name, obj in inspect.getmembers(module):
                if inspect.isfunction(obj) or inspect.ismethod(obj):
                    method = self._analyze_method(name, obj, module_name)
                    if method:
                        methods.append(method)
            
            return methods
        except ImportError as e:
            print(f"Failed to import {module_name}: {e}")
            return []
    
    def _analyze_method(self, name: str, func: Any, module_path: str) -> Optional[SDKMethod]:
        """Analyze a function/method to extract metadata"""
        try:
            sig = inspect.signature(func)
            doc = inspect.getdoc(func) or f"Method {name} from {module_path}"
            
            parameters = {}
            for param_name, param in sig.parameters.items():
                parameters[param_name] = {
                    "type": str(param.annotation) if param.annotation != param.empty else "Any",
                    "default": param.default if param.default != param.empty else None,
                    "required": param.default == param.empty
                }
            
            return_type = str(sig.return_annotation) if sig.return_annotation != sig.empty else "Any"
            is_async = inspect.iscoroutinefunction(func)
            
            return SDKMethod(
                name=name,
                description=doc,
                parameters=parameters,
                return_type=return_type,
                module_path=module_path,
                is_async=is_async
            )
        except Exception as e:
            print(f"Failed to analyze method {name}: {e}")
            return None
    
    def discover_capabilities(self) -> List[SDKCapability]:
        """Discover high-level capabilities of the SDK"""
        # This would be implemented based on specific SDK patterns
        # For now, return a basic structure
        return self.capabilities
    
    def get_method_by_name(self, name: str) -> Optional[SDKMethod]:
        """Get a discovered method by name"""
        for method in self.discovered_methods:
            if method.name == name:
                return method
        return None
    
    def discover_client_methods(self, client_obj: Any, module_path: str) -> List[SDKMethod]:
        """Discover public methods on a client instance for adapterless discovery"""
        methods = []
        for name, obj in inspect.getmembers(client_obj, predicate=inspect.ismethod):
            if name.startswith("_"):
                continue
            try:
                sig = inspect.signature(obj)
                params = {}
                for p_name, p in sig.parameters.items():
                    if p_name == "self": 
                        continue
                    
                    # **kwargs parameters should always be optional
                    is_kwargs = p.kind == p.VAR_KEYWORD
                    is_required = p.default == p.empty and not is_kwargs
                    
                    params[p_name] = {
                        "type": getattr(p.annotation, "__name__", str(p.annotation)) if p.annotation != p.empty else "Any",
                        "default": None if p.default == p.empty else p.default,
                        "required": is_required,
                        "is_kwargs": is_kwargs
                    }
                methods.append(SDKMethod(
                    name=name,
                    description=(inspect.getdoc(obj) or f"{module_path}.{name}"),
                    parameters=params,
                    return_type=getattr(sig.return_annotation, "__name__", str(sig.return_annotation)) if sig.return_annotation != sig.empty else "Any",
                    module_path=module_path
                ))
            except Exception as e:
                # Skip methods we can't introspect
                print(f"Warning: Could not introspect method {name}: {e}")
                continue
        return methods
