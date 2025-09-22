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

from mcp.server.fastmcp import FastMCP
# Lazy imports inside setup_adapter to avoid hard deps on curated adapters
from .adapters.auto_k8s import K8sAutoAdapter, K8sAutoConfig
from .adapters.auto_github import GitHubAutoAdapter, GitHubAutoConfig
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
                require_auth=bool(safety_cfg.get("require_auth", False)),
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
            
        else:
            raise ValueError(f"Unsupported SDK: {self.sdk_name}. Available: github, k8s, k8s-auto, github-auto")
    
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
            
            # Classify operation type
            method_name = tool_name.split(".", 1)[1] if "." in tool_name else tool_name
            op_type = classify_method(method_name)
            risk_level = get_operation_risk_level(method_name)
            
            # Wrap with safety controls
            safe_impl = self.safety.safe_wrap(implementation, method_name=tool_name)
            
            if op_type == "write":
                write_count += 1
                # For write operations, expose both .plan and .apply tools
                def make_plan_impl(name=tool_name, impl=safe_impl):
                    def _plan(**kwargs):
                        return self.planner.plan(
                            tool_name=name,
                            args=kwargs,
                            risk_level=risk_level,
                            description=f"Plan to execute {name}"
                        )
                    return _plan
                
                def make_apply_impl(name=tool_name, impl=safe_impl):
                    def _apply(plan_id: str):
                        def executor():
                            plan = self.planner.get_plan(plan_id)
                            if not plan:
                                raise ValueError(f"Plan {plan_id} not found")
                            return impl(**plan.args)
                        return self.planner.apply(plan_id, executor)
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
        
        # Print comprehensive stats on boot
        print(f"🔧 Registered {registered} tools for {self.sdk_name}")
        print(f"   📖 Read operations: {read_count}")
        print(f"   ✏️  Write operations: {write_count} (with plan/apply)")
        
        if hasattr(self.adapter, "get_stats"):
            stats = self.adapter.get_stats()
            print("📊 Adapter stats:", stats)
    
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
        ("k8s-auto", "Auto-discovered Kubernetes adapter (comprehensive)")
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
    up_parser.add_argument("--sdk", required=True, choices=["github", "k8s", "github-auto", "k8s-auto"], 
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
    validate_parser.add_argument("--sdk", required=True, choices=["github", "k8s", "github-auto", "k8s-auto"],
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
