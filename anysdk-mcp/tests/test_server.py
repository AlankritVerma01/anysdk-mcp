# anysdk-mcp/tests/test_server.py

import asyncio
import os
import pytest

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

@pytest.mark.asyncio
async def test_github_list_repos_smoke():
    server_params = StdioServerParameters(
        command="python",
        args=["server.py"],
        env=dict(os.environ),  # inherit env, include GITHUB_TOKEN if set
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Tools should include our tool
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            assert "github.list_repos" in names

            # Call the tool
            result = await session.call_tool("github.list_repos", {"user": "octocat"})

            # Parse result: prefer structuredContent if present; otherwise text content.
            repos = None
            if hasattr(result, "structuredContent") and result.structuredContent:
                repos = result.structuredContent
            else:
                # Fallback: parse first text blob as JSON if your server returns text
                texts = [c.text for c in result.content if isinstance(c, types.TextContent)]
                if texts:
                    import json
                    try:
                        repos = json.loads(texts[0])
                    except Exception:
                        repos = texts

            # Handle case where result is wrapped in a dictionary with 'result' key
            if isinstance(repos, dict) and 'result' in repos:
                repos = repos['result']

            assert isinstance(repos, (list, tuple))
            assert any("octocat" in str(r).lower() for r in repos)
