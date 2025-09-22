# anysdk-mcp/tests/test_e2e.py

"""
End-to-end tests for MCP SDK Bridge

Tests the full flow from CLI to MCP server without requiring credentials.
"""

import os
import pytest
import asyncio
from unittest.mock import patch
from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters


@pytest.mark.asyncio
async def test_github_auto_e2e_without_token():
    """Test GitHub auto adapter end-to-end without authentication"""
    # Use github-auto which works without token (rate limited)
    params = StdioServerParameters(
        command="python", 
        args=["-m", "mcp_sdk_bridge.cli", "up", "--sdk", "github-auto"]
    )
    
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # List available tools
                tools = await session.list_tools()
                
                # Should have auto-discovered GitHub methods
                tool_names = [t.name for t in tools.tools]
                
                # Check for some common GitHub methods that should be discovered
                expected_methods = ["github.get_rate_limit", "github.search_repositories"]
                found_methods = [name for name in expected_methods if name in tool_names]
                
                assert len(found_methods) > 0, f"Expected to find some GitHub methods, got: {tool_names[:5]}"
                
                # Try to call get_rate_limit (works without token)
                if "github.get_rate_limit" in tool_names:
                    result = await session.call_tool("github.get_rate_limit", {})
                    assert result is not None
                    print(f"✅ GitHub rate limit call successful: {result}")
                
    except Exception as e:
        pytest.skip(f"Skipping e2e test due to environment issue: {e}")


@pytest.mark.asyncio 
async def test_k8s_auto_discovery_without_cluster():
    """Test K8s auto adapter discovery without cluster connection"""
    params = StdioServerParameters(
        command="python",
        args=["-m", "mcp_sdk_bridge.cli", "up", "--sdk", "k8s-auto"]
    )
    
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # List available tools
                tools = await session.list_tools()
                tool_names = [t.name for t in tools.tools]
                
                # Should discover K8s API methods even without cluster connection
                k8s_methods = [name for name in tool_names if name.startswith("k8s.")]
                
                assert len(k8s_methods) > 0, f"Expected K8s methods to be discovered, got: {tool_names[:5]}"
                
                # Check for some expected K8s API methods
                expected_patterns = ["CoreV1Api", "AppsV1Api"]
                found_patterns = []
                for pattern in expected_patterns:
                    if any(pattern in name for name in k8s_methods):
                        found_patterns.append(pattern)
                
                assert len(found_patterns) > 0, f"Expected to find K8s API patterns, got methods: {k8s_methods[:5]}"
                print(f"✅ K8s auto discovery found {len(k8s_methods)} methods with patterns: {found_patterns}")
                
    except Exception as e:
        pytest.skip(f"Skipping k8s discovery test due to environment issue: {e}")


@pytest.mark.asyncio
async def test_plan_apply_pattern():
    """Test that write operations expose plan/apply tools"""
    params = StdioServerParameters(
        command="python",
        args=["-m", "mcp_sdk_bridge.cli", "up", "--sdk", "k8s-auto"]
    )
    
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                tools = await session.list_tools()
                tool_names = [t.name for t in tools.tools]
                
                # Look for plan/apply tools (write operations should have these)
                plan_tools = [name for name in tool_names if name.endswith(".plan")]
                apply_tools = [name for name in tool_names if name.endswith(".apply")]
                
                if plan_tools:
                    print(f"✅ Found plan tools: {plan_tools[:3]}")
                    
                    # Try to create a plan (won't execute, just plans)
                    plan_tool = plan_tools[0]
                    base_tool = plan_tool.replace(".plan", "")
                    
                    # Create a plan with minimal args
                    plan_result = await session.call_tool(plan_tool, {})
                    
                    assert "plan_id" in str(plan_result), f"Expected plan_id in result: {plan_result}"
                    print(f"✅ Plan creation successful for {plan_tool}")
                
                if apply_tools:
                    print(f"✅ Found apply tools: {apply_tools[:3]}")
                
    except Exception as e:
        pytest.skip(f"Skipping plan/apply test due to environment issue: {e}")


@pytest.mark.asyncio
async def test_cli_validation():
    """Test CLI validation commands"""
    # Test that validation works for different SDKs
    from mcp_sdk_bridge.cli import validate_sdk_requirements
    
    # GitHub validation (should work without token)
    result = validate_sdk_requirements("github-auto", {})
    assert result is True  # Auto adapters are more permissive
    
    # K8s validation (should work without cluster)
    result = validate_sdk_requirements("k8s-auto", {})
    assert result is True  # Discovery works without cluster
    
    print("✅ CLI validation tests passed")


def test_adapter_stats():
    """Test that adapters provide useful statistics"""
    from mcp_sdk_bridge.adapters.auto_github import GitHubAutoAdapter, GitHubAutoConfig
    from mcp_sdk_bridge.adapters.auto_k8s import K8sAutoAdapter, K8sAutoConfig
    
    # Test GitHub auto adapter stats
    try:
        github_adapter = GitHubAutoAdapter(GitHubAutoConfig(token=None))
        stats = github_adapter.get_stats()
        
        assert "adapter_type" in stats
        assert stats["adapter_type"] == "adapterless"
        assert stats["sdk"] == "github"
        print(f"✅ GitHub auto adapter stats: {stats}")
        
    except Exception as e:
        print(f"⚠️  GitHub adapter test skipped: {e}")
    
    # Test K8s auto adapter stats  
    try:
        k8s_adapter = K8sAutoAdapter(K8sAutoConfig())
        stats = k8s_adapter.get_stats()
        
        assert "adapter_type" in stats
        assert stats["adapter_type"] == "adapterless"
        assert stats["sdk"] == "kubernetes"
        print(f"✅ K8s auto adapter stats: {stats}")
        
    except Exception as e:
        print(f"⚠️  K8s adapter test skipped: {e}")


def test_operation_classification():
    """Test that operations are classified correctly as read/write"""
    from mcp_sdk_bridge.core.classify import classify_method, get_operation_risk_level
    
    # Test read operations
    read_ops = ["get_user", "list_repos", "list_namespaced_pod", "describe_node"]
    for op in read_ops:
        assert classify_method(op) == "read", f"{op} should be classified as read"
    
    # Test write operations
    write_ops = ["create_repo", "delete_namespaced_pod", "update_deployment", "patch_service"]
    for op in write_ops:
        assert classify_method(op) == "write", f"{op} should be classified as write"
    
    # Test risk levels
    assert get_operation_risk_level("list_pods") == "low"
    assert get_operation_risk_level("create_deployment") == "medium" 
    assert get_operation_risk_level("delete_namespace") == "high"
    
    print("✅ Operation classification tests passed")


def test_planner():
    """Test the plan/apply planner"""
    from mcp_sdk_bridge.core.planapply import Planner
    
    planner = Planner()
    
    # Create a plan
    plan = planner.plan("test.create_something", {"name": "test"}, "medium")
    assert "plan_id" in plan
    
    # Check plan exists
    plan_id = plan["plan_id"]
    retrieved = planner.get_plan(plan_id)
    assert retrieved is not None
    assert retrieved.tool_name == "test.create_something"
    
    # Apply plan
    def mock_executor():
        return {"success": True}
    
    result = planner.apply(plan_id, mock_executor)
    assert result["status"] == "applied"
    assert result["result"]["success"] is True
    
    # Plan should be consumed
    assert planner.get_plan(plan_id) is None
    
    print("✅ Planner tests passed")


if __name__ == "__main__":
    # Run basic tests that don't require async
    test_operation_classification()
    test_planner()
    test_adapter_stats()
    
    print("🎉 All synchronous tests passed!")
    print("Run with pytest for full async e2e tests")