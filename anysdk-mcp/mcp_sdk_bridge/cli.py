# anysdk-mcp/mcp_sdk_bridge/cli.py

"""
CLI Module for MCP SDK Bridge

Provides command-line interface for launching MCP servers with different SDK adapters.
"""

import argparse
import os
import sys
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
import asyncio
from datetime import datetime

from mcp.server.fastmcp import FastMCP
# Lazy imports inside setup_adapter to avoid hard deps on curated adapters
from .adapters.auto_k8s import K8sAutoAdapter, K8sAutoConfig
from .adapters.auto_github import GitHubAutoAdapter, GitHubAutoConfig
from .adapters.auto_azure import AzureAutoAdapter, AzureAutoConfig
from .core.safety import SafetyWrapper, SafetyConfig, RateLimitConfig, SecurityContext
from .core.classify import classify_method, get_operation_risk_level
from .core.planapply import Planner


class MCPBridgeServer:
    """MCP Bridge Server that dynamically loads SDK adapters"""
    
    def __init__(self, sdk_name: str, config: Dict[str, Any] = None):
        self.sdk_name = sdk_name
        self.config = config or {}
        self.adapter = None
        self.mcp = FastMCP(f"anysdk-{sdk_name}-bridge")
        
        # Setup safety wrapper with config from YAML
        safety_cfg = self.config.get("safety", {}) or {}
        rate_cfg = self.config.get("rate_limit", {}) or {}
        self.safety = SafetyWrapper(
            SafetyConfig(
                max_response_size_mb=safety_cfg.get("max_response_size_mb", 10),
                max_execution_time_seconds=safety_cfg.get("max_execution_time_seconds", 300),
                allowed_methods=set(safety_cfg.get("allowed_operations", []) or []),
                blocked_methods=set(safety_cfg.get("blocked_operations", []) or []),
                require_auth=bool(safety_cfg.get("require_auth", False)),  # Default to false for auto-adapters
                sanitize_inputs=bool(safety_cfg.get("sanitize_inputs", True)),
                log_operations=bool(safety_cfg.get("log_operations", True)),
            ),
            RateLimitConfig(
                requests_per_minute=rate_cfg.get("requests_per_minute", 120),
                requests_per_hour=rate_cfg.get("requests_per_hour", 3000),
                burst_size=rate_cfg.get("burst_size", 20),
            )
        )
        
        # Setup planner for write operations
        self.planner = Planner()
        
    def setup_adapter(self):
        """Setup the appropriate SDK adapter"""
        if self.sdk_name == "github":
            from .adapters.github import GitHubAdapter
            token = self.config.get("token") or os.environ.get("GITHUB_TOKEN")
            if not token:
                raise ValueError("GitHub token is required. Set GITHUB_TOKEN environment variable or provide in config.")
            self.adapter = GitHubAdapter(token=token, config=self.config)
            
        elif self.sdk_name == "k8s":
            from .adapters.k8s import K8sAdapter, K8sConfig
            k8s_config = K8sConfig(
                kubeconfig_path=self.config.get("kubeconfig_path"),
                context=self.config.get("context"),
                namespace=self.config.get("namespace", "default")
            )
            self.adapter = K8sAdapter(config=k8s_config)
            
        elif self.sdk_name == "k8s-auto":
            k8s_config = K8sAutoConfig(
                kubeconfig_path=self.config.get("kubeconfig_path"),
                context=self.config.get("context"),
                namespace=self.config.get("namespace", "default")
            )
            self.adapter = K8sAutoAdapter(config=k8s_config)
            
        elif self.sdk_name == "github-auto":
            github_config = GitHubAutoConfig(
                token=self.config.get("token") or os.environ.get("GITHUB_TOKEN")
            )
            self.adapter = GitHubAutoAdapter(config=github_config)
            
        elif self.sdk_name == "azure-auto":
            azure_config = AzureAutoConfig(
                tenant_id=self.config.get("tenant_id") or os.environ.get("AZURE_TENANT_ID"),
                client_id=self.config.get("client_id") or os.environ.get("AZURE_CLIENT_ID"),
                client_secret=self.config.get("client_secret") or os.environ.get("AZURE_CLIENT_SECRET"),
                subscription_id=self.config.get("subscription_id") or os.environ.get("AZURE_SUBSCRIPTION_ID"),
                discover_roots=self.config.get("azure", {}).get("discover", {}).get("roots"),
                lro_poll_interval=self.config.get("azure", {}).get("lro", {}).get("poll_interval_seconds", 2.0)
            )
            self.adapter = AzureAutoAdapter(config=azure_config)
            
        else:
            raise ValueError(f"Unsupported SDK: {self.sdk_name}. Available: github, k8s, k8s-auto, github-auto, azure-auto")
    
    def register_tools(self):
        """Register MCP tools from the adapter"""
        if not self.adapter:
            raise RuntimeError("Adapter not setup. Call setup_adapter() first.")
        
        # Get tool implementations from adapter
        implementations = self.adapter.create_tool_implementations()
        
        # Generate schemas once and index by name
        schemas = {s.name: s for s in self.adapter.generate_mcp_tools()}
        
        # Register each tool with FastMCP
        registered = 0
        read_count = 0
        write_count = 0
        
        for tool_name, implementation in implementations.items():
            tool_schema = schemas.get(tool_name)
            if not tool_schema:
                continue
            
            # Classify operation type - extract actual method name from tool name
            # e.g. "azure.VirtualMachinesOperations_begin_delete" -> "begin_delete"
            raw_method = tool_name.split(".", 1)[1] if "." in tool_name else tool_name
            actual_method = raw_method.split("_", 1)[1] if "_" in raw_method else raw_method
            op_type = classify_method(actual_method)
            risk_level = get_operation_risk_level(actual_method)
            
            # Wrap with safety controls and inject default security context for auto-adapters
            def with_default_context(fn):
                """Inject default security context for local development"""
                def _wrapped(**kwargs):
                    from .core.safety import SecurityContext
                    return fn(_security_context=SecurityContext(user_id="local-dev"), **kwargs)
                return _wrapped
            
            safe_impl = with_default_context(self.safety.safe_wrap(implementation, method_name=tool_name))
            
            if op_type == "write":
                write_count += 1
                # For write operations, expose both .plan and .apply tools
                def make_plan_impl(name=tool_name):
                    def _plan(**kwargs):
                        return self.planner.plan(
                            tool_name=name,
                            args=kwargs,
                            risk_level=risk_level,
                            description=f"Plan to execute {name}"
                        )
                    return _plan
                
                def make_apply_impl(name=tool_name, impl=safe_impl):
                    async def _apply(plan_id: str):
                        plan = self.planner.get_plan(plan_id)
                        if not plan:
                            return {"error": {"type": "PlanNotFound", "message": f"Plan {plan_id} not found"}}
                        
                        # Execute the implementation (handling both sync and async)
                        try:
                            # Inject security context for plan execution
                            from .core.safety import SecurityContext
                            plan_args = {**plan.args, '_security_context': SecurityContext(user_id="local-dev")}
                            
                            if asyncio.iscoroutinefunction(impl):
                                result = await impl(**plan_args)
                            else:
                                result = await asyncio.to_thread(impl, **plan_args)
                            
                            # Apply the plan with the result
                            return self.planner.apply(plan_id, lambda: result)
                        except Exception as e:
                            return {"error": {"type": type(e).__name__, "message": str(e)}}
                    return _apply
                
                # Register plan tool
                self.mcp.tool(
                    name=f"{tool_name}.plan",
                    description=f"Plan {tool_schema.description} [Risk: {risk_level}]"
                )(make_plan_impl())
                
                # Register apply tool  
                self.mcp.tool(
                    name=f"{tool_name}.apply", 
                    description=f"Apply a previously planned {tool_name} operation"
                )(make_apply_impl())
                
                registered += 2  # plan + apply
                
            else:
                read_count += 1
                # For read operations, register directly
                self.mcp.tool(
                    name=tool_name,
                    description=f"{tool_schema.description} [Operation: {op_type}]"
                )(safe_impl)
                registered += 1
        
        # Register LRO management tools
        self._register_lro_tools()
        
        # Register meta tools for discovery and introspection
        self._register_meta_tools()
        
        # Print comprehensive stats on boot
        print(f"🔧 Registered {registered} tools for {self.sdk_name}")
        print(f"   📖 Read operations: {read_count}")
        print(f"   ✏️  Write operations: {write_count} (with plan/apply)")
        
        if hasattr(self.adapter, "get_stats"):
            stats = self.adapter.get_stats()
            print("📊 Adapter stats:", stats)
    
    def _register_lro_tools(self):
        """Register Long Running Operation management tools"""
        
        @self.mcp.tool(
            name="lro.get_status",
            description="Get status of a long running operation"
        )
        def lro_get_status(operation_id: str):
            """Get the status of a long running operation"""
            try:
                status = self.lro.get_operation_status(operation_id)
                return {
                    "operation_id": operation_id,
                    "status": status.status.value,
                    "progress": status.progress,
                    "result": status.result,
                    "error": status.error,
                    "started_at": status.started_at.isoformat() if status.started_at else None,
                    "completed_at": status.completed_at.isoformat() if status.completed_at else None
                }
            except Exception as e:
                return {
                    "error": f"Operation {operation_id} not found or error: {str(e)}",
                    "operation_id": operation_id
                }
        
        @self.mcp.tool(
            name="lro.wait",
            description="Wait for a long running operation to complete"
        )
        async def lro_wait(operation_id: str, timeout_seconds: int = 300):
            """Wait for a long running operation to complete"""
            try:
                result = await self.lro.wait_for_completion(operation_id, timeout_seconds)
                return {
                    "operation_id": operation_id,
                    "status": "completed",
                    "result": result.result,
                    "completed_at": result.completed_at.isoformat() if result.completed_at else None
                }
            except TimeoutError:
                return {
                    "error": f"Operation {operation_id} timed out after {timeout_seconds} seconds",
                    "operation_id": operation_id,
                    "status": "timeout"
                }
            except Exception as e:
                return {
                    "error": f"Error waiting for operation {operation_id}: {str(e)}",
                    "operation_id": operation_id,
                    "status": "error"
                }
        
        @self.mcp.tool(
            name="lro.list_operations", 
            description="List all active long running operations"
        )
        def lro_list_operations():
            """List all tracked long running operations"""
            try:
                operations = self.lro.list_operations()
                return {
                    "operations": [
                        {
                            "operation_id": op_id,
                            "status": op.status.value,
                            "progress": op.progress,
                            "started_at": op.started_at.isoformat() if op.started_at else None
                        }
                        for op_id, op in operations.items()
                    ],
                    "total_count": len(operations)
                }
            except Exception as e:
                return {
                    "error": f"Error listing operations: {str(e)}",
                    "operations": []
                }
    
    def _register_meta_tools(self):
        """Register meta tools for discovery and introspection"""
        
        @self.mcp.tool(
            name="tools.search",
            description="Search for tools by name or description"
        )
        def tools_search(query: str, limit: int = 10):
            """Search for tools matching the query"""
            try:
                # Get all tool implementations and schemas
                implementations = self.adapter.create_tool_implementations()
                schemas = {s.name: s for s in self.adapter.generate_mcp_tools()}
                
                results = []
                query_lower = query.lower()
                
                for tool_name in implementations.keys():
                    schema = schemas.get(tool_name)
                    if not schema:
                        continue
                    
                    # Search in name and description
                    name_match = query_lower in tool_name.lower()
                    desc_match = query_lower in schema.description.lower()
                    
                    if name_match or desc_match:
                        results.append({
                            "name": tool_name,
                            "description": schema.description,
                            "match_type": "name" if name_match else "description",
                            "input_schema": schema.inputSchema
                        })
                
                # Sort by relevance (name matches first, then description matches)
                results.sort(key=lambda x: (x["match_type"] != "name", x["name"]))
                
                return {
                    "query": query,
                    "results": results[:limit],
                    "total_matches": len(results),
                    "showing": min(len(results), limit)
                }
            except Exception as e:
                return {
                    "error": f"Error searching tools: {str(e)}",
                    "query": query,
                    "results": []
                }
        
        @self.mcp.tool(
            name="meta.stats",
            description="Get comprehensive statistics about available tools"
        )
        def meta_stats():
            """Get statistics about the SDK adapter and available tools"""
            try:
                # Get adapter stats
                adapter_stats = self.adapter.get_stats() if hasattr(self.adapter, "get_stats") else {}
                
                # Get tool counts by type
                implementations = self.adapter.create_tool_implementations()
                schemas = {s.name: s for s in self.adapter.generate_mcp_tools()}
                
                read_tools = []
                write_tools = []
                lro_tools = []
                plan_tools = []
                apply_tools = []
                
                for tool_name in implementations.keys():
                    if tool_name.endswith('.plan'):
                        plan_tools.append(tool_name)
                    elif tool_name.endswith('.apply'):
                        apply_tools.append(tool_name)
                    elif 'begin_' in tool_name or tool_name.startswith('lro.'):
                        lro_tools.append(tool_name)
                    elif any(verb in tool_name.lower() for verb in ['create', 'delete', 'update', 'set', 'add', 'remove']):
                        write_tools.append(tool_name)
                    else:
                        read_tools.append(tool_name)
                
                return {
                    "sdk": self.sdk_name,
                    "adapter_stats": adapter_stats,
                    "tool_counts": {
                        "total": len(implementations),
                        "read": len(read_tools),
                        "write": len(write_tools),
                        "lro": len(lro_tools),
                        "plan": len(plan_tools),
                        "apply": len(apply_tools)
                    },
                    "tool_breakdown": {
                        "read_tools": read_tools[:10],  # Show first 10
                        "write_tools": write_tools[:10],
                        "lro_tools": lro_tools[:10]
                    }
                }
            except Exception as e:
                return {
                    "error": f"Error getting stats: {str(e)}",
                    "sdk": self.sdk_name
                }
        
        @self.mcp.tool(
            name="meta.export_tools",
            description="Export tool catalog in JSON or Markdown format"
        )
        def meta_export_tools(format: str = "json", include_schemas: bool = True):
            """Export a comprehensive catalog of all available tools"""
            try:
                implementations = self.adapter.create_tool_implementations()
                schemas = {s.name: s for s in self.adapter.generate_mcp_tools()}
                
                catalog = {
                    "sdk": self.sdk_name,
                    "generated_at": datetime.now().isoformat(),
                    "total_tools": len(implementations),
                    "tools": []
                }
                
                for tool_name in sorted(implementations.keys()):
                    schema = schemas.get(tool_name)
                    tool_info = {
                        "name": tool_name,
                        "description": schema.description if schema else "No description available"
                    }
                    
                    if include_schemas and schema:
                        tool_info["input_schema"] = schema.inputSchema
                    
                    # Add classification info
                    if tool_name.endswith('.plan'):
                        tool_info["type"] = "plan"
                    elif tool_name.endswith('.apply'):
                        tool_info["type"] = "apply"
                    elif 'begin_' in tool_name:
                        tool_info["type"] = "lro"
                    elif any(verb in tool_name.lower() for verb in ['create', 'delete', 'update', 'set']):
                        tool_info["type"] = "write"
                    else:
                        tool_info["type"] = "read"
                    
                    catalog["tools"].append(tool_info)
                
                if format.lower() == "markdown":
                    # Generate Markdown format
                    md_lines = [
                        f"# {self.sdk_name.title()} SDK Tools Catalog",
                        f"",
                        f"Generated: {catalog['generated_at']}",
                        f"Total Tools: {catalog['total_tools']}",
                        f"",
                        f"## Tools by Type",
                        f""
                    ]
                    
                    # Group by type
                    by_type = {}
                    for tool in catalog["tools"]:
                        tool_type = tool["type"]
                        if tool_type not in by_type:
                            by_type[tool_type] = []
                        by_type[tool_type].append(tool)
                    
                    for tool_type, tools in sorted(by_type.items()):
                        md_lines.append(f"### {tool_type.title()} Operations ({len(tools)})")
                        md_lines.append("")
                        for tool in tools:
                            md_lines.append(f"- **{tool['name']}**: {tool['description']}")
                        md_lines.append("")
                    
                    return {
                        "format": "markdown",
                        "content": "\n".join(md_lines)
                    }
                else:
                    return {
                        "format": "json", 
                        "content": catalog
                    }
                    
            except Exception as e:
                return {
                    "error": f"Error exporting tools: {str(e)}",
                    "format": format
                }
    
    def run(self):
        """Run the MCP server"""
        self.setup_adapter()
        self.register_tools()
        self.mcp.run()


def load_config(config_path: str) -> Dict[str, Any]:
    """Load configuration from YAML file"""
    if not os.path.exists(config_path):
        return {}
    
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Error loading config from {config_path}: {e}")
        return {}


def find_config_file(sdk_name: str) -> Optional[str]:
    """Find configuration file for the SDK"""
    # Look in configs directory
    config_dir = Path(__file__).parent.parent / "configs"
    config_file = config_dir / f"{sdk_name}.yaml"
    
    if config_file.exists():
        return str(config_file)
    
    # Look in current directory
    local_config = Path(f"{sdk_name}.yaml")
    if local_config.exists():
        return str(local_config)
    
    return None


def list_available_sdks():
    """List available SDK adapters"""
    sdks = [
        ("github", "Curated GitHub adapter"),
        ("k8s", "Curated Kubernetes adapter"), 
        ("github-auto", "Auto-discovered GitHub adapter (comprehensive)"),
        ("k8s-auto", "Auto-discovered Kubernetes adapter (comprehensive)"),
        ("azure-auto", "Auto-discovered Azure Management SDK adapter (comprehensive)")
    ]
    print("Available SDKs:")
    for sdk, description in sdks:
        config_file = find_config_file(sdk.replace("-auto", ""))  # Auto adapters use base config
        config_status = "✓" if config_file else "✗"
        print(f"  {sdk:12} {config_status} {description}")
        if config_file:
            print(f"    {'':14} Config: {config_file}")


def validate_sdk_requirements(sdk_name: str, config: Dict[str, Any]) -> bool:
    """Validate that SDK requirements are met"""
    base_sdk = sdk_name.replace("-auto", "")  # Auto adapters use same validation as base
    
    if base_sdk == "github":
        token = config.get("token") or os.environ.get("GITHUB_TOKEN")
        if not token:
            print("⚠️  GitHub token not found. Auto adapter will work with rate limits for public repos.")
            print("   Set GITHUB_TOKEN environment variable for full access.")
        else:
            print("✅ GitHub token found")
        
        # Auto adapters always work (with or without token)
        if sdk_name == "github-auto":
            print("🚀 GitHub auto adapter will discover all available methods")
        
    elif base_sdk == "k8s":
        kubeconfig = config.get("kubeconfig_path") or os.environ.get("KUBECONFIG") or "~/.kube/config"
        if not os.path.exists(os.path.expanduser(kubeconfig)):
            print(f"⚠️  Kubeconfig not found at {kubeconfig}.")
            if sdk_name == "k8s-auto":
                print("   Auto adapter will still discover methods but calls will fail without cluster access.")
        else:
            print(f"✅ Kubeconfig found at {kubeconfig}")
        
        if sdk_name == "k8s-auto":
            print("🚀 K8s auto adapter will discover all *Api client methods")
    
    elif base_sdk == "azure":
        tenant_id = config.get("tenant_id") or os.environ.get("AZURE_TENANT_ID")
        client_id = config.get("client_id") or os.environ.get("AZURE_CLIENT_ID")
        client_secret = config.get("client_secret") or os.environ.get("AZURE_CLIENT_SECRET")
        subscription_id = config.get("subscription_id") or os.environ.get("AZURE_SUBSCRIPTION_ID")
        
        missing_vars = []
        if not tenant_id:
            missing_vars.append("AZURE_TENANT_ID")
        if not client_id:
            missing_vars.append("AZURE_CLIENT_ID")
        if not client_secret:
            missing_vars.append("AZURE_CLIENT_SECRET")
        if not subscription_id:
            missing_vars.append("AZURE_SUBSCRIPTION_ID")
            
        if missing_vars:
            print(f"⚠️  Azure credentials not found: {', '.join(missing_vars)}")
            print("   Auto adapter will discover methods but calls will fail without proper authentication.")
        else:
            print("✅ Azure credentials found")
        
        if sdk_name == "azure-auto":
            print("🚀 Azure auto adapter will discover all Azure Management SDK operations")
    
    return True


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="MCP SDK Bridge - Launch MCP servers for various SDKs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s up --sdk github                    # Launch curated GitHub MCP server
  %(prog)s up --sdk github-auto               # Launch auto-discovered GitHub server (comprehensive)
  %(prog)s up --sdk k8s-auto --validate       # Launch auto-discovered K8s server (all API methods)
  %(prog)s up --sdk k8s --config k8s.yaml     # Launch curated K8s server with config
  %(prog)s list                               # List available SDKs
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Up command
    up_parser = subparsers.add_parser("up", help="Launch MCP server")
    up_parser.add_argument("--sdk", required=True, choices=["github", "k8s", "github-auto", "k8s-auto", "azure-auto"], 
                          help="SDK to bridge")
    up_parser.add_argument("--config", help="Path to configuration file")
    up_parser.add_argument("--validate", action="store_true", 
                          help="Validate SDK requirements before starting")
    up_parser.add_argument("--port", type=int, help="Port for development server (optional)")
    up_parser.add_argument("--dev", action="store_true", 
                          help="Run in development mode with web interface")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List available SDKs")
    
    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate SDK setup")
    validate_parser.add_argument("--sdk", required=True, choices=["github", "k8s", "github-auto", "k8s-auto", "azure-auto"],
                               help="SDK to validate")
    validate_parser.add_argument("--config", help="Path to configuration file")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    if args.command == "list":
        list_available_sdks()
        return
    
    if args.command == "validate":
        config_file = args.config or find_config_file(args.sdk)
        config = load_config(config_file) if config_file else {}
        
        print(f"Validating {args.sdk} SDK setup...")
        if validate_sdk_requirements(args.sdk, config):
            print(f"✅ {args.sdk} SDK setup is valid")
        else:
            print(f"❌ {args.sdk} SDK setup has issues")
            sys.exit(1)
        return
    
    if args.command == "up":
        # Load configuration
        config_file = args.config or find_config_file(args.sdk)
        config = load_config(config_file) if config_file else {}
        
        if config_file:
            print(f"Using config: {config_file}")
        else:
            print(f"No config file found for {args.sdk}, using environment variables and defaults")
        
        # Validate if requested
        if args.validate:
            print(f"Validating {args.sdk} SDK setup...")
            if not validate_sdk_requirements(args.sdk, config):
                print(f"❌ {args.sdk} SDK validation failed")
                sys.exit(1)
            print("✅ Validation passed")
        
        # Create and run server
        try:
            print(f"🚀 Starting MCP server for {args.sdk}...")
            server = MCPBridgeServer(args.sdk, config)
            
            if args.dev:
                print(f"🔧 Development mode enabled")
                if args.port:
                    print(f"🌐 Web interface will be available at http://localhost:{args.port}")
                # In dev mode, you might want to add FastMCP's dev server capabilities
                # This would require additional setup in FastMCP
            
            print(f"📡 MCP server ready for {args.sdk} operations")
            print("Press Ctrl+C to stop...")
            
            server.run()
            
        except KeyboardInterrupt:
            print("\n👋 Server stopped by user")
        except Exception as e:
            print(f"❌ Error starting server: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
