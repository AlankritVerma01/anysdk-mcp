# anysdk-mcp/mcp_sdk_bridge/adapters/auto_github.py

"""
Auto-Discovery GitHub Adapter

Automatically discovers all GitHub API methods using reflection.
"""

import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from ..core.discover import SDKDiscoverer, SDKMethod, SDKCapability
from ..core.schema import SchemaGenerator, MCPToolSchema
from ..core.serialize import ResponseSerializer


@dataclass
class GitHubAutoConfig:
    """Configuration for auto GitHub adapter"""
    token: Optional[str] = None
    max_methods: int = 50  # Limit discovery to prevent overwhelming
    include_patterns: List[str] = None  # Method name patterns to include
    exclude_patterns: List[str] = None  # Method name patterns to exclude


class GitHubAutoAdapter:
    """Auto-discovery GitHub adapter"""
    
    def __init__(self, config: GitHubAutoConfig):
        self.config = config
        self.token = config.token or os.environ.get("GITHUB_TOKEN")
        self.discoverer = SDKDiscoverer("github")
        self.schema_generator = SchemaGenerator()
        self.serializer = ResponseSerializer()
        self.github = None
        self.discovered_methods: List[SDKMethod] = []
        
        self._setup_github()
        self._discover_methods()
    
    def _setup_github(self):
        """Setup GitHub client"""
        try:
            from github import Github
            
            if self.token:
                self.github = Github(self.token)
                print(f"✅ GitHub authenticated with token")
            else:
                self.github = Github()
                print(f"⚠️  GitHub unauthenticated (rate limited)")
                
        except ImportError:
            print("❌ PyGithub not installed. Install with: pip install PyGithub")
            raise
    
    def _discover_methods(self):
        """Discover GitHub API methods"""
        if not self.github:
            return
        
        print(f"🔍 Auto-discovering GitHub API methods...")
        
        # Discover methods from main GitHub client
        github_methods = self.discoverer.discover_client_methods(self.github, "github.Github")
        
        # Filter methods based on config
        filtered_methods = []
        for method in github_methods:
            if self._should_include_method(method.name):
                filtered_methods.append(method)
        
        # Limit to max_methods to avoid overwhelming
        self.discovered_methods = filtered_methods[:self.config.max_methods]
        
        print(f"📊 Discovered {len(self.discovered_methods)} GitHub methods")
    
    def _should_include_method(self, method_name: str) -> bool:
        """Check if method should be included based on patterns"""
        # Skip private methods
        if method_name.startswith("_"):
            return False
        
        # Skip some noisy/complex methods
        skip_methods = {
            "get_hooks", "get_keys", "get_subscriptions", "get_watched",
            "get_organization", "get_gists", "get_notifications"
        }
        
        if method_name in skip_methods:
            return False
        
        # Include patterns
        if self.config.include_patterns:
            if not any(pattern in method_name for pattern in self.config.include_patterns):
                return False
        
        # Exclude patterns
        if self.config.exclude_patterns:
            if any(pattern in method_name for pattern in self.config.exclude_patterns):
                return False
        
        return True
    
    def discover_capabilities(self) -> List[SDKCapability]:
        """Return discovered capabilities"""
        return [SDKCapability(
            name="github_auto",
            description="Auto-discovered GitHub API methods",
            methods=self.discovered_methods,
            requires_auth=False  # Some methods work without auth
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
            tool_name = f"github.{method.name}"
            implementations[tool_name] = self._create_method_wrapper(method)
        
        return implementations
    
    def _create_method_wrapper(self, method: SDKMethod):
        """Create a wrapper for a discovered method"""
        def wrapper(**kwargs):
            try:
                if not self.github:
                    return self.serializer.serialize_error(
                        Exception("GitHub client not available"), 
                        {"method": method.name}
                    )
                
                # Get the actual method from GitHub client
                github_method = getattr(self.github, method.name, None)
                if not github_method:
                    return self.serializer.serialize_error(
                        AttributeError(f"Method {method.name} not found"),
                        {"method": method.name}
                    )
                
                # Debug logging
                print(f"🔍 DEBUG: {method.name} called with kwargs: {kwargs}")
                print(f"🔍 DEBUG: Expected parameters: {list(method.parameters.keys())}")
                
                # Handle special case where MCP Inspector sends single string as kwargs
                if len(kwargs) == 1 and 'kwargs' in kwargs and isinstance(kwargs['kwargs'], str):
                    # This is a common case where Inspector sends {"kwargs": "value"} instead of {"param": "value"}
                    # Try to map it to the first required parameter
                    required_params = [name for name, info in method.parameters.items() if info.get('required', False)]
                    if required_params:
                        first_param = required_params[0]
                        kwargs = {first_param: kwargs['kwargs']}
                        print(f"🔧 DEBUG: Remapped kwargs to {first_param}: {kwargs[first_param]}")
                
                # Filter kwargs to only include valid parameters
                filtered_kwargs = {}
                for param_name, param_info in method.parameters.items():
                    if param_name in kwargs:
                        filtered_kwargs[param_name] = kwargs[param_name]
                
                # Validate that we have all required parameters (excluding **kwargs)
                required_params = [
                    name for name, info in method.parameters.items() 
                    if info.get('required', False) and not info.get('is_kwargs', False)
                ]
                missing_params = [param for param in required_params if param not in filtered_kwargs]
                
                if missing_params:
                    raise ValueError(f"Missing required parameters: {missing_params}. Provided: {list(kwargs.keys())}")
                
                print(f"🔧 DEBUG: Final filtered_kwargs: {filtered_kwargs}")
                
                # Call the method
                result = github_method(**filtered_kwargs)
                
                # Handle different result types
                if hasattr(result, '__iter__') and not isinstance(result, (str, dict)):
                    # Convert iterables to lists (limited)
                    try:
                        result_list = list(result)[:100]  # Limit to prevent huge responses
                        # Convert GitHub objects to dicts
                        serialized_list = []
                        for item in result_list:
                            if hasattr(item, '_rawData'):
                                serialized_list.append(item._rawData)
                            elif hasattr(item, 'raw_data'):
                                serialized_list.append(item.raw_data)
                            else:
                                serialized_list.append(str(item))
                        result = serialized_list
                    except Exception:
                        result = f"<iterable with {len(list(result))} items>"
                
                elif hasattr(result, '_rawData'):
                    # GitHub object with raw data
                    result = result._rawData
                elif hasattr(result, 'raw_data'):
                    result = result.raw_data
                
                return self.serializer.serialize_response(result)
                
            except Exception as e:
                return self.serializer.serialize_error(e, {
                    "method": method.name,
                    "args": kwargs
                })
        
        return wrapper
    
    def get_stats(self) -> Dict[str, Any]:
        """Get adapter statistics"""
        return {
            "adapter_type": "adapterless",
            "sdk": "github",
            "methods_discovered": len(self.discovered_methods),
            "authenticated": bool(self.token),
            "max_methods_limit": self.config.max_methods,
            "sample_methods": [m.name for m in self.discovered_methods[:5]]
        }