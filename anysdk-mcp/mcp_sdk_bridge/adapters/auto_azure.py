# anysdk-mcp/mcp_sdk_bridge/adapters/auto_azure.py

"""
Azure Auto-Adapter for MCP SDK Bridge

Comprehensive auto-discovery of Azure Management SDK operations with:
- LRO (Long Running Operations) support for begin_* methods
- Automatic client instantiation with credential discovery
- Rich serialization using Azure model as_dict() methods
- Comprehensive coverage of azure.mgmt.* packages
"""

from typing import List, Dict, Any, Tuple, Optional, Union
import importlib
import inspect
import pkgutil
import os
import asyncio
from dataclasses import dataclass, asdict
from pathlib import Path

from ..core.discover import SDKMethod, SDKDiscoverer
from ..core.schema import SchemaGenerator
from ..core.wrap import SDKWrapper
from ..core.classify import classify_method, get_operation_risk_level
from ..core.lro import LROHandler, LROConfig
from ..core.serialize import ResponseSerializer
from ..core.safety import SafetyWrapper

# Common Azure management SDK packages to discover
AZURE_ROOTS = [
    "azure.mgmt.compute",
    "azure.mgmt.resource", 
    "azure.mgmt.network",
    "azure.mgmt.storage",
    "azure.mgmt.keyvault",
    "azure.mgmt.sql",
    "azure.mgmt.web",
    "azure.mgmt.monitor",
    "azure.mgmt.authorization",
    "azure.mgmt.containerservice",
    "azure.mgmt.cosmosdb",
    "azure.mgmt.redis",
    "azure.mgmt.servicebus",
    "azure.mgmt.eventhub",
    "azure.mgmt.batch",
    "azure.mgmt.cdn",
    "azure.mgmt.dns",
    "azure.mgmt.trafficmanager"
]

@dataclass
class AzureAutoConfig:
    """Configuration for Azure Auto Adapter"""
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    subscription_id: Optional[str] = None
    discover_roots: Optional[List[str]] = None
    max_methods_per_class: int = 100
    include_private: bool = False
    lro_poll_interval: float = 2.0

    def __post_init__(self):
        # Auto-discover from environment if not provided
        self.tenant_id = self.tenant_id or os.environ.get("AZURE_TENANT_ID")
        self.client_id = self.client_id or os.environ.get("AZURE_CLIENT_ID")
        self.client_secret = self.client_secret or os.environ.get("AZURE_CLIENT_SECRET")
        self.subscription_id = self.subscription_id or os.environ.get("AZURE_SUBSCRIPTION_ID")
        
        if not self.discover_roots:
            self.discover_roots = AZURE_ROOTS

@dataclass
class AzureDiscoveryResult:
    """Result of Azure SDK discovery"""
    schemas: List[Dict[str, Any]]
    tools: Dict[str, Any]
    stats: Dict[str, Any]
    client_factories: Dict[str, Any]

class AzureAutoAdapter:
    """Auto-discovering Azure Management SDK adapter"""
    
    def __init__(self, config: Union[AzureAutoConfig, Dict[str, Any], None] = None):
        if isinstance(config, dict):
            self.config = AzureAutoConfig(**config)
        elif isinstance(config, AzureAutoConfig):
            self.config = config
        else:
            self.config = AzureAutoConfig()
            
        self.wrapper = SDKWrapper(ResponseSerializer())
        self.schema_gen = SchemaGenerator()
        self.lro = LROHandler(LROConfig(
            poll_interval=self.config.lro_poll_interval
        ))
        
        # Track discovered items
        self._discovered_operations: List[Tuple[str, Any]] = []
        self._client_factories: Dict[str, Any] = {}
        
        # Cache discovery results to avoid running twice
        self._discovery_cache: Optional[AzureDiscoveryResult] = None
        
    def _iter_azure_modules(self):
        """Iterate through Azure management SDK modules"""
        for root in self.config.discover_roots:
            try:
                pkg = importlib.import_module(root)
                yield root, pkg
                
                # Walk submodules if package has __path__
                if hasattr(pkg, "__path__"):
                    for finder, name, ispkg in pkgutil.walk_packages(
                        pkg.__path__, 
                        prefix=pkg.__name__ + "."
                    ):
                        try:
                            submodule = importlib.import_module(name)
                            yield name, submodule
                        except Exception as e:
                            # Skip modules that can't be imported
                            continue
                            
            except ImportError:
                # Skip packages that aren't installed
                continue
            except Exception as e:
                # Skip other import errors
                continue

    def _setup_client_factories(self) -> Dict[str, Any]:
        """Setup Azure client factories if credentials are available"""
        if not all([
            self.config.tenant_id,
            self.config.client_id, 
            self.config.client_secret,
            self.config.subscription_id
        ]):
            return {}
            
        try:
            from azure.identity import ClientSecretCredential
            
            credential = ClientSecretCredential(
                tenant_id=self.config.tenant_id,
                client_id=self.config.client_id,
                client_secret=self.config.client_secret
            )
            
            factories = {}
            
            # Common management clients
            client_mappings = [
                ("azure.mgmt.compute", "ComputeManagementClient"),
                ("azure.mgmt.network", "NetworkManagementClient"), 
                ("azure.mgmt.resource", "ResourceManagementClient"),
                ("azure.mgmt.storage", "StorageManagementClient"),
                ("azure.mgmt.keyvault", "KeyVaultManagementClient"),
                ("azure.mgmt.sql", "SqlManagementClient"),
                ("azure.mgmt.web", "WebSiteManagementClient"),
                ("azure.mgmt.monitor", "MonitorManagementClient"),
                ("azure.mgmt.authorization", "AuthorizationManagementClient"),
                ("azure.mgmt.containerservice", "ContainerServiceClient"),
                ("azure.mgmt.cosmosdb", "CosmosDBManagementClient"),
                ("azure.mgmt.redis", "RedisManagementClient"),
                ("azure.mgmt.servicebus", "ServiceBusManagementClient"),
                ("azure.mgmt.eventhub", "EventHubManagementClient"),
                ("azure.mgmt.batch", "BatchManagementClient"),
                ("azure.mgmt.cdn", "CdnManagementClient"),
                ("azure.mgmt.dns", "DnsManagementClient"),
                ("azure.mgmt.trafficmanager", "TrafficManagerManagementClient")
            ]
            
            for module_name, client_class in client_mappings:
                try:
                    module = importlib.import_module(module_name)
                    if hasattr(module, client_class):
                        client_cls = getattr(module, client_class)
                        factories[client_class] = lambda cls=client_cls: cls(
                            credential, self.config.subscription_id
                        )
                except ImportError:
                    continue
                    
            return factories
            
        except ImportError:
            # azure-identity not available
            return {}
        except Exception:
            # Other credential setup errors
            return {}

    def _is_public_method(self, name: str) -> bool:
        """Check if method name should be included"""
        if name.startswith("_"):
            return False
        if name in ["serialize", "deserialize", "as_dict", "from_dict"]:
            return False
        return True

    def _discover_operations_classes(self) -> List[Tuple[str, Any]]:
        """Discover Azure Operations classes"""
        operations = []
        
        for module_name, module in self._iter_azure_modules():
            for name, obj in inspect.getmembers(module):
                if (self._is_public_method(name) and 
                    inspect.isclass(obj) and 
                    name.endswith("Operations")):
                    fqcn = f"{module_name}.{name}"
                    operations.append((fqcn, obj))
                    
        return operations

    def _serialize_azure_object(self, obj: Any) -> Any:
        """Serialize Azure objects using as_dict() when available"""
        if obj is None:
            return None
            
        # Azure models often have as_dict method
        if hasattr(obj, "as_dict") and callable(getattr(obj, "as_dict")):
            try:
                return obj.as_dict()
            except Exception:
                pass
                
        # Handle Azure enums
        if hasattr(obj, "value"):
            return obj.value
            
        # Handle common Python types
        if isinstance(obj, (str, int, float, bool)):
            return obj
            
        if isinstance(obj, (list, tuple)):
            return [self._serialize_azure_object(item) for item in obj]
            
        if isinstance(obj, dict):
            return {k: self._serialize_azure_object(v) for k, v in obj.items()}
            
        # Fallback to __dict__ for objects
        if hasattr(obj, "__dict__"):
            return {
                k: self._serialize_azure_object(v) 
                for k, v in obj.__dict__.items() 
                if not k.startswith("_")
            }
            
        # Convert to string as last resort
        return str(obj)

    def _create_method_wrapper(self, method_name: str, method_func: Any, 
                             is_lro: bool = False, client_instance: Any = None) -> Any:
        """Create a wrapped method that handles Azure-specific concerns"""
        
        async def azure_method_wrapper(**kwargs):
            try:
                # Bind method to instance if available
                if client_instance is not None:
                    bound_method = method_func.__get__(client_instance, type(client_instance))
                    result = bound_method(**kwargs)
                else:
                    result = method_func(**kwargs)
                
                # Handle Long Running Operations (LRO)
                if is_lro and hasattr(result, "result"):
                    # This is an Azure Poller - wait for completion
                    try:
                        # Use asyncio.to_thread to avoid blocking the event loop
                        value = await asyncio.to_thread(result.result)
                        return {
                            "status": "succeeded", 
                            "result": self._serialize_azure_object(value)
                        }
                    except Exception as e:
                        return {
                            "status": "failed", 
                            "error": str(e),
                            "error_type": type(e).__name__
                        }
                
                # Handle regular responses
                return self._serialize_azure_object(result)
                
            except Exception as e:
                return {
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "method": method_name
                }
        
        return azure_method_wrapper

    def discover_tools(self) -> AzureDiscoveryResult:
        """Discover all Azure management tools"""
        schemas: List[Dict[str, Any]] = []
        tools: Dict[str, Any] = {}
        stats = {
            "operations_classes": 0,
            "methods": 0,
            "lro_methods": 0,
            "read_methods": 0,
            "write_methods": 0,
            "modules_scanned": 0,
            "client_factories": 0,
            "live_clients": 0
        }
        
        # Setup client factories and create live operations objects
        client_factories = self._setup_client_factories()
        stats["client_factories"] = len(client_factories)
        
        # Get live operations objects from real clients
        live_ops: List[Tuple[str, Any]] = []
        
        for client_name, factory in client_factories.items():
            try:
                client = factory()
                stats["live_clients"] += 1
                
                # Find all operations objects on this client
                for attr_name in dir(client):
                    if attr_name.startswith("_"):
                        continue
                    
                    try:
                        ops_obj = getattr(client, attr_name)
                        ops_class_name = type(ops_obj).__name__
                        
                        if ops_class_name.endswith("Operations"):
                            fqcn = f"{type(client).__module__}.{ops_class_name}"
                            live_ops.append((fqcn, ops_obj))
                    except Exception:
                        continue
                        
            except Exception as e:
                # Skip clients that can't be instantiated
                continue
        
        # If no live clients available, fall back to class-based discovery
        if not live_ops:
            operations_classes = self._discover_operations_classes()
            for fqcn, operations_class in operations_classes:
                try:
                    # Create a dummy instance for method inspection
                    instance = operations_class.__new__(operations_class)
                    live_ops.append((fqcn, instance))
                except Exception:
                    live_ops.append((fqcn, None))
        
        # Discover methods from live operations objects
        discoverer = SDKDiscoverer("azure")
        
        for fqcn, ops_obj in live_ops:
            stats["operations_classes"] += 1
            
            if ops_obj is None:
                continue
                
            # Get the operations class for method inspection
            operations_class = type(ops_obj) if ops_obj else None
            if not operations_class:
                continue
            
            # Track methods per class to enforce limits properly
            methods_in_this_class = 0
            
            # Discover methods in the operations class
            for method_name, method_func in inspect.getmembers(
                operations_class, predicate=inspect.isfunction
            ):
                if not self._is_public_method(method_name):
                    continue
                    
                # Skip constructor and special methods
                if method_name in ["__init__", "__new__"]:
                    continue
                
                # Classify method
                is_lro = method_name.startswith("begin_")
                operation_type = classify_method(method_name)
                risk_level = get_operation_risk_level(method_name)
                
                if is_lro:
                    stats["lro_methods"] += 1
                    operation_type = "write"  # LRO operations are always writes
                    
                if operation_type == "read":
                    stats["read_methods"] += 1
                elif operation_type == "write":
                    stats["write_methods"] += 1
                
                # Create tool name
                class_name = fqcn.split(".")[-1]  # e.g., "VirtualMachinesOperations"
                tool_name = f"azure.{class_name}_{method_name}"
                
                # Analyze method signature
                try:
                    method_info = discoverer._analyze_method(method_name, method_func, fqcn)
                    if not method_info:
                        continue
                        
                    # Create wrapped implementation using the live ops_obj
                    wrapped_method = self._create_method_wrapper(
                        method_name, method_func, is_lro, ops_obj
                    )
                    
                    tools[tool_name] = wrapped_method
                    
                    # Generate schema
                    schema = self.schema_gen.generate_tool_schema(method_info)
                    schema_dict = {
                        "name": tool_name,
                        "description": f"{schema.description} [Type: {operation_type}, Risk: {risk_level}]",
                        "inputSchema": schema.inputSchema
                    }
                    
                    # Add LRO metadata
                    if is_lro:
                        schema_dict["description"] += " [Long Running Operation]"
                        schema_dict["lro"] = True
                    
                    schemas.append(schema_dict)
                    stats["methods"] += 1
                    methods_in_this_class += 1
                    
                    # Limit methods per class to avoid overwhelming output
                    if methods_in_this_class >= self.config.max_methods_per_class:
                        break
                        
                except Exception as e:
                    # Skip methods that can't be analyzed
                    continue
        
        return AzureDiscoveryResult(
            schemas=schemas,
            tools=tools, 
            stats=stats,
            client_factories=client_factories
        )

    def _discover_cached(self) -> AzureDiscoveryResult:
        """Get cached discovery results or run discovery if not cached"""
        if self._discovery_cache is None:
            self._discovery_cache = self.discover_tools()
        return self._discovery_cache

    def create_tool_implementations(self) -> Dict[str, Any]:
        """Create tool implementations for MCP"""
        return self._discover_cached().tools

    def generate_mcp_tools(self) -> List[Any]:
        """Generate MCP tool schemas"""
        from mcp.types import Tool
        
        result = self._discover_cached()
        tools = []
        
        for schema in result.schemas:
            tool = Tool(
                name=schema["name"],
                description=schema["description"],
                inputSchema=schema["inputSchema"]
            )
            tools.append(tool)
            
        return tools

    def get_stats(self) -> Dict[str, Any]:
        """Get adapter statistics"""
        return self._discover_cached().stats
