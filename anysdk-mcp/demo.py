# anysdk-mcp/demo.py

"""
Quick demo script to showcase the adapterless MCP SDK Bridge capabilities.

This demonstrates the comprehensive auto-discovery of SDK methods without manual curation.
"""

import asyncio
import sys
from mcp_sdk_bridge.adapters.auto_github import GitHubAutoAdapter, GitHubAutoConfig
from mcp_sdk_bridge.adapters.auto_k8s import K8sAutoAdapter, K8sAutoConfig
from mcp_sdk_bridge.core.classify import classify_method, get_operation_risk_level


def demo_github_auto():
    """Demonstrate GitHub auto-discovery"""
    print("🐙 GitHub Auto-Discovery Demo")
    print("=" * 50)
    
    try:
        adapter = GitHubAutoAdapter(GitHubAutoConfig(token=None))
        stats = adapter.get_stats()
        
        print(f"Adapter Type: {stats['adapter_type']}")
        print(f"SDK: {stats['sdk']}")
        print(f"Available: {stats['available']}")
        print(f"Authenticated: {stats['authenticated']}")
        print(f"Total Methods: {stats.get('total_methods', 'N/A')}")
        print(f"Read Operations: {stats.get('read_operations', 'N/A')}")
        print(f"Write Operations: {stats.get('write_operations', 'N/A')}")
        
        # Show some popular methods
        if 'popular_methods' in stats:
            print(f"\nPopular Methods:")
            for method in stats['popular_methods'][:5]:
                print(f"  - {method}")
        
        # Show a few discovered tools
        schemas = adapter.generate_mcp_tools()
        if schemas:
            print(f"\nFirst 5 Auto-Discovered Tools:")
            for schema in schemas[:5]:
                method_name = schema.name.split(".")[-1]
                op_type = classify_method(method_name)
                risk = get_operation_risk_level(method_name)
                print(f"  - {schema.name} [{op_type}, {risk}]")
        
    except Exception as e:
        print(f"❌ GitHub demo failed: {e}")
    
    print()


def demo_k8s_auto():
    """Demonstrate Kubernetes auto-discovery"""
    print("⚓ Kubernetes Auto-Discovery Demo")
    print("=" * 50)
    
    try:
        adapter = K8sAutoAdapter(K8sAutoConfig())
        stats = adapter.get_stats()
        
        print(f"Adapter Type: {stats['adapter_type']}")
        print(f"SDK: {stats['sdk']}")
        print(f"Available: {stats['available']}")
        print(f"API Clients: {stats.get('api_clients', 'N/A')}")
        print(f"Total Methods: {stats.get('total_methods', 'N/A')}")
        print(f"Read Operations: {stats.get('read_operations', 'N/A')}")
        print(f"Write Operations: {stats.get('write_operations', 'N/A')}")
        print(f"Capabilities: {stats.get('capabilities', 'N/A')}")
        
        # Show some discovered tools by category
        capabilities = adapter.discover_capabilities()
        if capabilities:
            print(f"\nDiscovered API Clients:")
            for cap in capabilities[:3]:
                client_name = cap.name.replace("_operations", "")
                method_count = len(cap.methods)
                print(f"  - {client_name}: {method_count} methods")
                
                # Show a few methods from this client
                for method in cap.methods[:3]:
                    method_name = method.name.split(".")[-1]
                    op_type = classify_method(method_name)
                    risk = get_operation_risk_level(method_name)
                    print(f"    • {method.name} [{op_type}, {risk}]")
        
    except Exception as e:
        print(f"❌ K8s demo failed: {e}")
    
    print()


def demo_classification():
    """Demonstrate operation classification"""
    print("🔍 Operation Classification Demo")
    print("=" * 50)
    
    test_methods = [
        "get_user", "list_repos", "create_repo", "delete_repo",
        "list_namespaced_pod", "create_namespaced_deployment", 
        "delete_namespace", "patch_service", "watch_events"
    ]
    
    for method in test_methods:
        op_type = classify_method(method)
        risk = get_operation_risk_level(method)
        icon = "📖" if op_type == "read" else "✏️"
        risk_icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(risk, "⚪")
        print(f"  {icon} {method:<25} {op_type:>5} {risk_icon} {risk}")
    
    print()


def demo_plan_apply():
    """Demonstrate plan/apply pattern"""
    print("📋 Plan/Apply Pattern Demo")
    print("=" * 50)
    
    from mcp_sdk_bridge.core.planapply import Planner
    
    planner = Planner()
    
    # Create a plan
    plan = planner.plan(
        tool_name="k8s.CoreV1Api.delete_namespaced_pod",
        args={"name": "test-pod", "namespace": "default"},
        risk_level="high",
        description="Delete a test pod"
    )
    
    print(f"Created Plan:")
    print(f"  Plan ID: {plan['plan_id']}")
    print(f"  Tool: {plan['preview']['tool']}")
    print(f"  Args: {plan['preview']['args']}")
    print(f"  Risk: {plan['preview']['risk_level']}")
    print(f"  Expires: {plan['expires_in_seconds']}s")
    
    # Show plan details
    plan_details = planner.get_plan(plan['plan_id'])
    if plan_details:
        print(f"\nPlan Details:")
        print(f"  Description: {plan_details.description}")
        print(f"  Created: {plan_details.created_at}")
    
    # Cancel plan (don't actually execute in demo)
    cancelled = planner.cancel_plan(plan['plan_id'])
    print(f"\nPlan cancelled: {cancelled}")
    
    print()


def main():
    """Run the comprehensive demo"""
    print("🚀 MCP SDK Bridge - Adapterless Demo")
    print("=" * 60)
    print("Showcasing comprehensive auto-discovery without manual curation")
    print()
    
    demo_github_auto()
    demo_k8s_auto() 
    demo_classification()
    demo_plan_apply()
    
    print("✨ Demo Complete!")
    print("\nTo try the live MCP server:")
    print("  python -m mcp_sdk_bridge.cli up --sdk github-auto")
    print("  python -m mcp_sdk_bridge.cli up --sdk k8s-auto --validate")
    print("\nThen connect with MCP Inspector to see all the auto-discovered tools!")


if __name__ == "__main__":
    main()

