# anysdk-mcp/mcp_sdk_bridge/adapters/auto_github.py

"""
Adapterless GitHub SDK Adapter

Automatically discovers and exposes GitHub API methods through reflection of the PyGithub library.
This provides comprehensive coverage of the GitHub API without manual curation.
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
class GitHubAutoConfig:
    """Configuration for adapterless GitHub adapter"""
    token: Optional[str] = None
    base_url: str = "https://api.github.com"


class GitHubAutoAdapter:
    """
    Adapterless GitHub adapter that automatically discovers and exposes
    all methods from the PyGithub Github root object.
    """
    
    def __init__(self, config: GitHubAutoConfig = None):
        self.config = config or GitHubAutoConfig()
        self.token = self.config.token or os.environ.get("GITHUB_TOKEN")
        self.serializer = ResponseSerializer()
        self.schema_generator = SchemaGenerator()
        self.wrapper = SDKWrapper()
        self._github_available = False
        self.github = None
        
        self._setup_client()
    
    def _setup_client(self):
        """Setup GitHub client"""
        try:
            from github import Github
            
            # Create GitHub client (works without token for public repos, but with rate limits)
            if self.token:
                self.github = Github(self.token, base_url=self.config.base_url)
                print("✅ GitHub Auto Adapter: Authenticated client ready")
            else:
                self.github = Github(base_url=self.config.base_url)
                print("⚠️  GitHub Auto Adapter: Unauthenticated client (rate limited)")
            
            self._github_available = True
            
        except ImportError:
            print("Warning: PyGithub package not installed. GitHub auto adapter will use mock data.")
            self._github_available = False
        except Exception as e:
            print(f"Warning: Failed to setup GitHub client: {e}")
            self._github_available = False
    
    def discover_capabilities(self) -> List[SDKCapability]:
        """Discover GitHub API capabilities by reflecting Github root object methods"""
        if not self._github_available or not self.github:
            return []
        
        capabilities = []
        methods = []
        
        # Reflect all public methods from the Github root object
        for method_name, method in inspect.getmembers(self.github, predicate=inspect.ismethod):
            if method_name.startswith("_"):
                continue
            
            try:
                # Get method signature
                sig = inspect.signature(method)
                doc = inspect.getdoc(method) or f"GitHub API method: {method_name}"
                
                # Build parameters dict
                parameters = {}
                for param_name, param in sig.parameters.items():
                    if param_name == "self":
                        continue
                    
                    param_type = "Any"
                    if param.annotation != inspect.Parameter.empty:
                        param_type = getattr(param.annotation, "__name__", str(param.annotation))
                    
                    # Handle common GitHub parameter types
                    if param_name in ["login", "name", "full_name", "owner", "repo"]:
                        param_type = "str"
                    elif param_name in ["id", "number", "page", "per_page"]:
                        param_type = "int"
                    elif param_name in ["private", "has_issues", "has_wiki"]:
                        param_type = "bool"
                    
                    parameters[param_name] = {
                        "type": param_type,
                        "default": param.default if param.default != inspect.Parameter.empty else None,
                        "required": param.default == inspect.Parameter.empty,
                        "description": f"Parameter {param_name} for {method_name}"
                    }
                
                # Create SDK method
                sdk_method = SDKMethod(
                    name=f"github.{method_name}",
                    description=doc,
                    parameters=parameters,
                    return_type="Any",
                    module_path="github",
                    is_async=False
                )
                methods.append(sdk_method)
                
            except Exception as e:
                print(f"Warning: Failed to analyze method github.{method_name}: {e}")
                continue
        
        if methods:
            capability = SDKCapability(
                name="github_root_operations",
                description="Auto-discovered operations from GitHub root object",
                methods=methods,
                requires_auth=False  # Many operations work without auth
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
                    method_name = method.name.split(".")[-1]  # Get method name without prefix
                    op_type = classify_method(method_name)
                    risk_level = get_operation_risk_level(method_name)
                    
                    # Add metadata to description
                    schema.description = f"{schema.description} [Operation: {op_type}, Risk: {risk_level}]"
                    
                    # Add authentication info
                    auth_info = "Requires auth" if self.token else "Public (rate limited)"
                    schema.description = f"{schema.description} [{auth_info}]"
                    
                    schemas.append(schema)
                    
                except Exception as e:
                    print(f"Warning: Failed to generate schema for {method.name}: {e}")
                    continue
        
        return schemas
    
    def create_tool_implementations(self) -> Dict[str, callable]:
        """Create callable implementations for all discovered methods"""
        if not self._github_available or not self.github:
            return {}
        
        implementations = {}
        
        for method_name, method in inspect.getmembers(self.github, predicate=inspect.ismethod):
            if method_name.startswith("_"):
                continue
            
            full_name = f"github.{method_name}"
            
            # Create implementation with proper closure
            def make_implementation(target_method=method, tool_name=full_name):
                def implementation(**kwargs):
                    try:
                        # Execute the GitHub API call
                        result = target_method(**kwargs)
                        
                        # Serialize the response
                        return self.serializer.serialize_response(result)
                        
                    except Exception as e:
                        # Serialize the error with context
                        return self.serializer.serialize_error(e, {
                            "method": tool_name,
                            "args": kwargs,
                            "authenticated": bool(self.token),
                            "base_url": self.config.base_url
                        })
                
                return implementation
            
            implementations[full_name] = make_implementation()
        
        return implementations
    
    def get_popular_methods(self) -> List[str]:
        """Get list of commonly used GitHub methods for demo purposes"""
        popular = [
            "github.get_user",
            "github.get_repo", 
            "github.get_organization",
            "github.search_repositories",
            "github.search_users",
            "github.search_issues",
            "github.get_rate_limit",
            "github.get_repos",
            "github.get_gists"
        ]
        
        # Filter to only methods that actually exist
        available_methods = {f"github.{name}" for name, _ in inspect.getmembers(self.github, predicate=inspect.ismethod) if not name.startswith("_")}
        
        return [method for method in popular if method in available_methods]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get adapter statistics"""
        if not self._github_available or not self.github:
            return {
                "adapter_type": "adapterless",
                "sdk": "github",
                "available": False,
                "error": "GitHub client not available"
            }
        
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
            "sdk": "github",
            "available": self._github_available,
            "authenticated": bool(self.token),
            "total_methods": total_methods,
            "read_operations": read_count,
            "write_operations": write_count,
            "capabilities": len(capabilities),
            "popular_methods": self.get_popular_methods()
        }

