#!/usr/bin/env python3
"""
MCP SDK Bridge Server

A simple entry point for running the MCP SDK Bridge server.
This can be used directly with MCP investigator or other MCP clients.

Usage:
    python mcp_server.py [--sdk SDK_NAME] [--config CONFIG_FILE]

Environment variables:
    MCP_SDK: SDK to use (github, k8s, github-auto, k8s-auto)
    GITHUB_TOKEN: GitHub token for authenticated access
    KUBECONFIG: Path to kubeconfig file for K8s access
"""

import sys
import os
import argparse
from pathlib import Path

# Add the current directory to Python path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent))

from mcp_sdk_bridge.cli import MCPBridgeServer, load_config, find_config_file


def main():
    """Main entry point for MCP server"""
    parser = argparse.ArgumentParser(
        description="MCP SDK Bridge Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  MCP_SDK        SDK to use (github, k8s, github-auto, k8s-auto, azure-auto)
  GITHUB_TOKEN   GitHub authentication token
  KUBECONFIG     Path to Kubernetes config file
  AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_SUBSCRIPTION_ID

Examples:
  python mcp_server.py --sdk github-auto
  python mcp_server.py --sdk azure-auto
  MCP_SDK=github-auto python mcp_server.py
  GITHUB_TOKEN=ghp_xxx python mcp_server.py --sdk github
        """
    )
    
    parser.add_argument(
        "--sdk", 
        default=os.environ.get("MCP_SDK", "github-auto"),
        choices=["github", "k8s", "github-auto", "k8s-auto", "azure-auto"],
        help="SDK to bridge (default: github-auto)"
    )
    
    parser.add_argument(
        "--config", 
        help="Path to configuration file (auto-detected if not provided)"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true", 
        help="Enable debug output"
    )
    
    args = parser.parse_args()
    
    if args.debug:
        print(f"🚀 Starting MCP SDK Bridge Server")
        print(f"   SDK: {args.sdk}")
        print(f"   Config: {args.config or 'auto-detect'}")
        print(f"   Debug: {args.debug}")
    
    # Load configuration
    config_file = args.config or find_config_file(args.sdk.replace("-auto", ""))
    config = load_config(config_file) if config_file else {}
    
    if args.debug and config_file:
        print(f"   Using config: {config_file}")
    
    # Create and run server
    try:
        server = MCPBridgeServer(args.sdk, config)
        
        if args.debug:
            print(f"📡 MCP server starting for {args.sdk}...")
            print("   Press Ctrl+C to stop")
        
        server.run()
        
    except KeyboardInterrupt:
        if args.debug:
            print("\n👋 Server stopped by user")
    except Exception as e:
        print(f"❌ Error starting server: {e}", file=sys.stderr)
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
