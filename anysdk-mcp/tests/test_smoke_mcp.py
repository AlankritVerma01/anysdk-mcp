# anysdk-mcp/tests/test_smoke_mcp.py

"""
End-to-End Smoke Tests for MCP SDK Bridge

Tests the complete MCP server functionality by launching servers
and making actual MCP calls.
"""

import pytest
import asyncio
import json
import subprocess
import time
import os
import signal
from pathlib import Path
import sys

# Add the parent directory to sys.path to import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


class MCPServerManager:
    """Context manager for MCP servers"""
    
    def __init__(self, sdk_name: str):
        self.sdk_name = sdk_name
        self.process = None
        self.server_path = Path(__file__).parent.parent / "mcp_server.py"
    
    async def __aenter__(self):
        """Start the MCP server"""
        # Start server process
        self.process = await asyncio.create_subprocess_exec(
            sys.executable, str(self.server_path),
            "--sdk", self.sdk_name,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Give server time to start
        await asyncio.sleep(2)
        
        # Create MCP client
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[str(self.server_path), "--sdk", self.sdk_name]
        )
        
        self.stdio_client = stdio_client(server_params)
        self.session = await self.stdio_client.__aenter__()
        
        return self.session
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up server and client"""
        if hasattr(self, 'stdio_client'):
            await self.stdio_client.__aexit__(exc_type, exc_val, exc_tb)
        
        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()


class TestMCPSmoke:
    """Smoke tests for MCP server functionality"""
    
    @pytest.mark.asyncio
    async def test_github_auto_basic(self):
        """Test basic GitHub auto-adapter functionality"""
        async with MCPServerManager("github-auto") as session:
            # Test ping
            result = await session.ping()
            assert result is not None
            
            # List available tools
            tools_result = await session.list_tools()
            assert len(tools_result.tools) > 0
            
            # Find meta tools
            tool_names = [tool.name for tool in tools_result.tools]
            assert "meta.stats" in tool_names
            assert "tools.search" in tool_names
            
            # Test meta.stats
            stats_result = await session.call_tool("meta.stats", {})
            assert stats_result.content
            stats_data = json.loads(stats_result.content[0].text)
            assert stats_data["sdk"] == "github-auto"
            assert "tool_counts" in stats_data
    
    @pytest.mark.asyncio 
    async def test_tools_search(self):
        """Test the tools.search functionality"""
        async with MCPServerManager("github-auto") as session:
            # Test search for repository tools
            search_result = await session.call_tool("tools.search", {"query": "repo"})
            assert search_result.content
            
            search_data = json.loads(search_result.content[0].text)
            assert search_data["query"] == "repo"
            assert len(search_data["results"]) > 0
            
            # Verify results contain relevant tools
            result_names = [r["name"] for r in search_data["results"]]
            assert any("repo" in name.lower() for name in result_names)
    
    @pytest.mark.asyncio
    async def test_lro_tools_exist(self):
        """Test that LRO management tools are available"""
        async with MCPServerManager("github-auto") as session:
            tools_result = await session.list_tools()
            tool_names = [tool.name for tool in tools_result.tools]
            
            # Check LRO tools exist
            assert "lro.get_status" in tool_names
            assert "lro.wait" in tool_names
            assert "lro.list_operations" in tool_names
            
            # Test listing operations (should be empty initially)
            list_result = await session.call_tool("lro.list_operations", {})
            assert list_result.content
            
            list_data = json.loads(list_result.content[0].text)
            assert "operations" in list_data
            assert list_data["total_count"] == 0
    
    @pytest.mark.asyncio
    async def test_export_tools(self):
        """Test the meta.export_tools functionality"""
        async with MCPServerManager("github-auto") as session:
            # Test JSON export
            export_result = await session.call_tool("meta.export_tools", {
                "format": "json",
                "include_schemas": False
            })
            assert export_result.content
            
            export_data = json.loads(export_result.content[0].text)
            assert export_data["format"] == "json"
            assert "content" in export_data
            
            catalog = export_data["content"]
            assert catalog["sdk"] == "github-auto"
            assert len(catalog["tools"]) > 0
            
            # Test Markdown export
            md_result = await session.call_tool("meta.export_tools", {
                "format": "markdown"
            })
            assert md_result.content
            
            md_data = json.loads(md_result.content[0].text)
            assert md_data["format"] == "markdown"
            assert "# Github-Auto SDK Tools Catalog" in md_data["content"]
    
    @pytest.mark.asyncio
    async def test_plan_apply_pattern_exists(self):
        """Test that plan/apply pattern is available for write operations"""
        async with MCPServerManager("github-auto") as session:
            tools_result = await session.list_tools()
            tool_names = [tool.name for tool in tools_result.tools]
            
            # Look for plan/apply pairs
            plan_tools = [name for name in tool_names if name.endswith('.plan')]
            apply_tools = [name for name in tool_names if name.endswith('.apply')]
            
            # Should have some plan/apply tools for write operations
            assert len(plan_tools) > 0
            assert len(apply_tools) > 0
            
            # Each plan should have a corresponding apply
            for plan_tool in plan_tools:
                base_name = plan_tool[:-5]  # Remove '.plan'
                apply_tool = f"{base_name}.apply"
                assert apply_tool in apply_tools
    
    @pytest.mark.asyncio
    async def test_azure_auto_basic(self):
        """Test basic Azure auto-adapter functionality (without credentials)"""
        async with MCPServerManager("azure-auto") as session:
            # Test ping
            result = await session.ping()
            assert result is not None
            
            # List available tools
            tools_result = await session.list_tools()
            # Even without credentials, should discover tools
            assert len(tools_result.tools) > 0
            
            # Should have meta tools
            tool_names = [tool.name for tool in tools_result.tools]
            assert "meta.stats" in tool_names
            
            # Test stats
            stats_result = await session.call_tool("meta.stats", {})
            assert stats_result.content
            stats_data = json.loads(stats_result.content[0].text)
            assert stats_data["sdk"] == "azure-auto"
    
    @pytest.mark.asyncio
    async def test_k8s_auto_basic(self):
        """Test basic K8s auto-adapter functionality (without cluster)"""
        async with MCPServerManager("k8s-auto") as session:
            # Test ping
            result = await session.ping()
            assert result is not None
            
            # List available tools
            tools_result = await session.list_tools()
            assert len(tools_result.tools) > 0
            
            # Should have meta tools
            tool_names = [tool.name for tool in tools_result.tools]
            assert "meta.stats" in tool_names
            
            # Test stats
            stats_result = await session.call_tool("meta.stats", {})
            assert stats_result.content
            stats_data = json.loads(stats_result.content[0].text)
            assert stats_data["sdk"] == "k8s-auto"


class TestMCPServerValidation:
    """Test server validation and configuration"""
    
    def test_server_starts_github(self):
        """Test that GitHub server starts without errors"""
        result = subprocess.run([
            sys.executable, str(Path(__file__).parent.parent / "mcp_server.py"),
            "--sdk", "github-auto", "--debug"
        ], capture_output=True, text=True, timeout=10)
        
        # Should exit cleanly (0) when no stdin provided
        assert result.returncode == 0
    
    def test_server_starts_azure(self):
        """Test that Azure server starts without errors"""
        result = subprocess.run([
            sys.executable, str(Path(__file__).parent.parent / "mcp_server.py"),
            "--sdk", "azure-auto", "--debug"
        ], capture_output=True, text=True, timeout=10)
        
        # Should exit cleanly (0) when no stdin provided
        assert result.returncode == 0
    
    def test_cli_validation(self):
        """Test CLI validation functionality"""
        result = subprocess.run([
            sys.executable, str(Path(__file__).parent.parent / "mcp_sdk_bridge" / "cli.py"),
            "validate", "--sdk", "github-auto"
        ], capture_output=True, text=True, timeout=10)
        
        assert result.returncode == 0
        assert "github-auto SDK setup is valid" in result.stdout or "validation" in result.stdout.lower()
    
    def test_cli_list(self):
        """Test CLI list functionality"""
        result = subprocess.run([
            sys.executable, str(Path(__file__).parent.parent / "mcp_sdk_bridge" / "cli.py"),
            "list"
        ], capture_output=True, text=True, timeout=10)
        
        assert result.returncode == 0
        assert "Available SDKs:" in result.stdout
        assert "github-auto" in result.stdout
        assert "azure-auto" in result.stdout
        assert "k8s-auto" in result.stdout


if __name__ == '__main__':
    # Run specific test
    pytest.main([__file__, "-v", "-s"])
