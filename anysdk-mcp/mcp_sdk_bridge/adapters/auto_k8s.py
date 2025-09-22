# anysdk-mcp/mcp_sdk_bridge/adapters/auto_k8s.py

"""
Auto-Discovery Kubernetes Adapter

Automatically discovers all Kubernetes API methods using reflection.
"""

import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from ..core.discover import SDKDiscoverer, SDKMethod, SDKCapability
from ..core.schema import SchemaGenerator, MCPToolSchema
from ..core.serialize import ResponseSerializer


@dataclass
class K8sAutoConfig:
    """Configuration for auto K8s adapter"""
    kubeconfig_path: Optional[str] = None
    context: Optional[str] = None
    namespace: str = "default"
    max_methods: int = 100  # K8s has many APIs
    include_apis: List[str] = None  # Which API classes to include
    exclude_methods: List[str] = None  # Method patterns to exclude


class K8sAutoAdapter:
    """Auto-discovery Kubernetes adapter"""
    
    def __init__(self, config: K8sAutoConfig):
        self.config = config
        self.discoverer = SDKDiscoverer("k8s")
        self.schema_generator = SchemaGenerator()
        self.serializer = ResponseSerializer()
        self.api_clients = {}
        self.discovered_methods: List[SDKMethod] = []
        
        self._setup_k8s()
        self._discover_methods()
    
    def _setup_k8s(self):
        """Setup Kubernetes clients"""
        try:
            from kubernetes import client, config as k8s_config
            
            # Load kubeconfig
            if self.config.kubeconfig_path:
                k8s_config.load_kube_config(
                    config_file=os.path.expanduser(self.config.kubeconfig_path),
                    context=self.config.context
                )
            else:
                try:
                    k8s_config.load_kube_config(context=self.config.context)
                except Exception:
                    print("⚠️  No kubeconfig found, will discover methods but calls may fail")
            
            # Initialize common API clients
            self.api_clients = {
                "CoreV1Api": client.CoreV1Api(),
                "AppsV1Api": client.AppsV1Api(),
                "NetworkingV1Api": client.NetworkingV1Api(),
                "RbacAuthorizationV1Api": client.RbacAuthorizationV1Api(),
                "StorageV1Api": client.StorageV1Api(),
            }
            
            print(f"✅ Kubernetes clients initialized for {len(self.api_clients)} APIs")
            
        except ImportError:
            print("❌ kubernetes package not installed. Install with: pip install kubernetes")
            self.api_clients = {}
        except Exception as e:
            print(f"⚠️  Kubernetes setup warning: {e}")
            # Still try to initialize clients for discovery
            try:
                from kubernetes import client
                self.api_clients = {
                    "CoreV1Api": client.CoreV1Api(),
                    "AppsV1Api": client.AppsV1Api(),
                }
            except Exception:
                self.api_clients = {}
    
    def _discover_methods(self):
        """Discover Kubernetes API methods"""
        if not self.api_clients:
            print("⚠️  No K8s clients available for discovery")
            return
        
        print(f"🔍 Auto-discovering Kubernetes API methods...")
        
        all_methods = []
        
        # Discover methods from each API client
        for api_name, api_client in self.api_clients.items():
            if self.config.include_apis and api_name not in self.config.include_apis:
                continue
                
            methods = self.discoverer.discover_client_methods(api_client, f"k8s.{api_name}")
            
            # Filter methods
            filtered_methods = []
            for method in methods:
                if self._should_include_method(method.name, api_name):
                    # Prefix with API name for clarity
                    method.name = f"{api_name}_{method.name}"
                    filtered_methods.append(method)
            
            all_methods.extend(filtered_methods)
            print(f"   {api_name}: {len(filtered_methods)} methods")
        
        # Limit total methods
        self.discovered_methods = all_methods[:self.config.max_methods]
        
        print(f"📊 Discovered {len(self.discovered_methods)} K8s methods total")
    
    def _should_include_method(self, method_name: str, api_name: str) -> bool:
        """Check if method should be included"""
        # Skip private methods
        if method_name.startswith("_"):
            return False
        
        # Skip some complex/dangerous methods
        skip_patterns = [
            "api_client", "sanitize_for_serialization", "deserialize",
            "call_api", "update_params_for_auth", "files_parameters",
            "select_header_accept", "select_header_content_type"
        ]
        
        for pattern in skip_patterns:
            if pattern in method_name:
                return False
        
        # Exclude patterns from config
        if self.config.exclude_methods:
            for pattern in self.config.exclude_methods:
                if pattern in method_name:
                    return False
        
        return True
    
    def discover_capabilities(self) -> List[SDKCapability]:
        """Return discovered capabilities"""
        return [SDKCapability(
            name="k8s_auto",
            description="Auto-discovered Kubernetes API methods",
            methods=self.discovered_methods,
            requires_auth=True  # K8s requires cluster access
        )]
    
    def generate_mcp_tools(self) -> List[MCPToolSchema]:
        """Generate MCP tool schemas"""
        tools = []
        for method in self.discovered_methods:
            schema = self.schema_generator.generate_tool_schema(method)
            tools.append(schema)
        return tools
    
    def create_tool_implementations(self) -> Dict[str, callable]:
        """Create tool implementations"""
        implementations = {}
        
        for method in self.discovered_methods:
            tool_name = f"k8s.{method.name}"
            implementations[tool_name] = self._create_method_wrapper(method)
        
        return implementations
    
    def _create_method_wrapper(self, method: SDKMethod):
        """Create a wrapper for a discovered method"""
        def wrapper(**kwargs):
            try:
                # Extract API name from method name
                api_name = method.name.split("_")[0]  # e.g., "CoreV1Api_list_pod" -> "CoreV1Api"
                actual_method_name = "_".join(method.name.split("_")[1:])  # -> "list_pod"
                
                api_client = self.api_clients.get(api_name)
                if not api_client:
                    return self.serializer.serialize_error(
                        Exception(f"API client {api_name} not available"),
                        {"method": method.name}
                    )
                
                # Get the actual method
                k8s_method = getattr(api_client, actual_method_name, None)
                if not k8s_method:
                    return self.serializer.serialize_error(
                        AttributeError(f"Method {actual_method_name} not found on {api_name}"),
                        {"method": method.name}
                    )
                
                # Filter kwargs to only include valid parameters
                filtered_kwargs = {}
                for param_name, param_info in method.parameters.items():
                    if param_name in kwargs:
                        filtered_kwargs[param_name] = kwargs[param_name]
                
                # Add default namespace if needed and not provided
                if "namespace" in method.parameters and "namespace" not in filtered_kwargs:
                    if "namespaced" in actual_method_name:
                        filtered_kwargs["namespace"] = self.config.namespace
                
                # Call the method
                result = k8s_method(**filtered_kwargs)
                
                # Handle K8s response objects
                if hasattr(result, 'to_dict'):
                    result = result.to_dict()
                elif hasattr(result, 'items'):
                    # List response
                    items = []
                    for item in result.items[:50]:  # Limit items
                        if hasattr(item, 'to_dict'):
                            items.append(item.to_dict())
                        else:
                            items.append(str(item))
                    result = {
                        "items": items,
                        "metadata": result.metadata.to_dict() if hasattr(result.metadata, 'to_dict') else str(result.metadata)
                    }
                
                return self.serializer.serialize_response(result)
                
            except Exception as e:
                return self.serializer.serialize_error(e, {
                    "method": method.name,
                    "args": kwargs
                })
        
        return wrapper
    
    def get_stats(self) -> Dict[str, Any]:
        """Get adapter statistics"""
        api_stats = {}
        for api_name in self.api_clients.keys():
            count = len([m for m in self.discovered_methods if m.name.startswith(api_name)])
            api_stats[api_name] = count
        
        return {
            "adapter_type": "adapterless", 
            "sdk": "kubernetes",
            "methods_discovered": len(self.discovered_methods),
            "api_clients": list(self.api_clients.keys()),
            "methods_per_api": api_stats,
            "max_methods_limit": self.config.max_methods,
            "default_namespace": self.config.namespace
        }