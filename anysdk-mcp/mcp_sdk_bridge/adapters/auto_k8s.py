# anysdk-mcp/mcp_sdk_bridge/adapters/auto_k8s.py

"""
Adapterless Kubernetes SDK Adapter

Automatically discovers and exposes all Kubernetes client API methods through reflection.
This provides comprehensive coverage of the Kubernetes API without manual curation.
"""

import inspect
import os
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass

from ..core.discover import SDKMethod, SDKCapability
from ..core.schema import SchemaGenerator, MCPToolSchema
from ..core.wrap import SDKWrapper
from ..core.serialize import ResponseSerializer
from ..core.classify import classify_method, get_operation_risk_level


@dataclass
class K8sAutoConfig:
    """Configuration for adapterless Kubernetes adapter"""
    kubeconfig_path: Optional[str] = None
    context: Optional[str] = None
    namespace: str = "default"


class K8sAutoAdapter:
    """
    Adapterless Kubernetes adapter that automatically discovers and exposes
    all methods from kubernetes.client.*Api classes.
    """
    
    def __init__(self, config: K8sAutoConfig = None):
        self.config = config or K8sAutoConfig()
        self.serializer = ResponseSerializer()
        self.schema_generator = SchemaGenerator()
        self.wrapper = SDKWrapper()
        self.clients: List[tuple[str, Any]] = []
        self._k8s_available = False
        
        self._setup_clients()
    
    def _setup_clients(self):
        """Setup Kubernetes clients by reflecting all *Api classes"""
        try:
            # Import kubernetes client
            from kubernetes import client as k8s_client, config as k8s_config
            
            # Configure kubernetes client
            if self.config.kubeconfig_path:
                k8s_config.load_kube_config(
                    config_file=os.path.expanduser(self.config.kubeconfig_path), 
                    context=self.config.context
                )
            else:
                try:
                    k8s_config.load_kube_config(context=self.config.context)
                except Exception:
                    # Fallback to in-cluster config
                    k8s_config.load_incluster_config()
            
            # Discover all *Api classes
            for name, cls in inspect.getmembers(k8s_client, inspect.isclass):
                if name.endswith("Api") and hasattr(cls, "__init__"):
                    try:
                        # Instantiate the API client
                        client_instance = cls()
                        self.clients.append((f"k8s.{name}", client_instance))
                    except Exception as e:
                        # Skip clients that fail to instantiate
                        print(f"Warning: Failed to instantiate {name}: {e}")
                        continue
            
            self._k8s_available = True
            print(f"✅ K8s Auto Adapter: Discovered {len(self.clients)} API clients")
            
        except ImportError:
            print("Warning: kubernetes package not installed. K8s auto adapter will use mock data.")
            self._k8s_available = False
        except Exception as e:
            print(f"Warning: Failed to setup K8s clients: {e}. Discovery will work but calls may fail.")
            # Still allow discovery without a working cluster
            try:
                from kubernetes import client as k8s_client
                for name, cls in inspect.getmembers(k8s_client, inspect.isclass):
                    if name.endswith("Api"):
                        self.clients.append((f"k8s.{name}", None))  # None indicates no instance
            except ImportError:
                pass
    
    def discover_capabilities(self) -> List[SDKCapability]:
        """Discover all Kubernetes API capabilities by reflecting client methods"""
        capabilities = []
        
        for client_name, client_instance in self.clients:
            methods = []
            
            # Get all public methods from the client class (not instance, to avoid connection issues)
            client_class = type(client_instance) if client_instance else None
            if not client_class:
                continue
                
            for method_name, method in inspect.getmembers(client_class, predicate=inspect.isfunction):
                if method_name.startswith("_"):
                    continue
                
                try:
                    # Get method signature
                    sig = inspect.signature(method)
                    doc = inspect.getdoc(method) or f"{client_name}.{method_name}"
                    
                    # Build parameters dict
                    parameters = {}
                    for param_name, param in sig.parameters.items():
                        if param_name == "self":
                            continue
                        
                        param_type = "Any"
                        if param.annotation != inspect.Parameter.empty:
                            param_type = getattr(param.annotation, "__name__", str(param.annotation))
                        
                        parameters[param_name] = {
                            "type": param_type,
                            "default": param.default if param.default != inspect.Parameter.empty else None,
                            "required": param.default == inspect.Parameter.empty,
                            "description": f"Parameter {param_name} for {method_name}"
                        }
                    
                    # Create SDK method
                    sdk_method = SDKMethod(
                        name=f"{client_name}.{method_name}",
                        description=doc,
                        parameters=parameters,
                        return_type="Any",
                        module_path="kubernetes.client",
                        is_async=False
                    )
                    methods.append(sdk_method)
                    
                except Exception as e:
                    print(f"Warning: Failed to analyze method {client_name}.{method_name}: {e}")
                    continue
            
            if methods:
                capability = SDKCapability(
                    name=f"{client_name.lower()}_operations",
                    description=f"Auto-discovered operations for {client_name}",
                    methods=methods,
                    requires_auth=True
                )
                capabilities.append(capability)
        
        return capabilities
    
    def generate_mcp_tools(self) -> List[MCPToolSchema]:
        """Generate MCP tool schemas for all discovered methods"""
        schemas = []
        
        for capability in self.discover_capabilities():
            for method in capability.methods:
                try:
                    # Generate base schema
                    schema = self.schema_generator.generate_tool_schema(method)
                    
                    # Override name to use full qualified name
                    schema.name = method.name
                    
                    # Add operation type and risk level as metadata
                    op_type = classify_method(method.name.split(".")[-1])  # Get method name without class prefix
                    risk_level = get_operation_risk_level(method.name.split(".")[-1])
                    
                    # Add metadata to description
                    schema.description = f"{schema.description} [Operation: {op_type}, Risk: {risk_level}]"
                    
                    schemas.append(schema)
                    
                except Exception as e:
                    print(f"Warning: Failed to generate schema for {method.name}: {e}")
                    continue
        
        return schemas
    
    def create_tool_implementations(self) -> Dict[str, callable]:
        """Create callable implementations for all discovered methods"""
        implementations = {}
        
        for client_name, client_instance in self.clients:
            if not client_instance:
                continue
                
            for method_name, method in inspect.getmembers(client_instance, predicate=inspect.ismethod):
                if method_name.startswith("_"):
                    continue
                
                full_name = f"{client_name}.{method_name}"
                
                # Create implementation with proper closure
                def make_implementation(target_method=method, tool_name=full_name):
                    def implementation(**kwargs):
                        try:
                            # Execute the Kubernetes API call
                            result = target_method(**kwargs)
                            
                            # Serialize the response
                            return self.serializer.serialize_response(result)
                            
                        except Exception as e:
                            # Serialize the error with context
                            return self.serializer.serialize_error(e, {
                                "method": tool_name,
                                "args": kwargs,
                                "kubernetes_context": self.config.context,
                                "namespace": self.config.namespace
                            })
                    
                    return implementation
                
                implementations[full_name] = make_implementation()
        
        return implementations
    
    def get_stats(self) -> Dict[str, Any]:
        """Get adapter statistics"""
        capabilities = self.discover_capabilities()
        total_methods = sum(len(cap.methods) for cap in capabilities)
        
        # Count by operation type
        read_count = 0
        write_count = 0
        
        for cap in capabilities:
            for method in cap.methods:
                method_name = method.name.split(".")[-1]
                op_type = classify_method(method_name)
                if op_type == "read":
                    read_count += 1
                else:
                    write_count += 1
        
        return {
            "adapter_type": "adapterless",
            "sdk": "kubernetes",
            "available": self._k8s_available,
            "api_clients": len(self.clients),
            "total_methods": total_methods,
            "read_operations": read_count,
            "write_operations": write_count,
            "capabilities": len(capabilities)
        }

