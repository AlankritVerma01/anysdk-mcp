# anysdk-mcp/server.py
from mcp.server.fastmcp import FastMCP
from typing import List
import os


from github import Github

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", None)  
gh = Github(login_or_token=GITHUB_TOKEN)

mcp = FastMCP("anysdk-bridge-demo")

@mcp.tool(name="github.list_repos")
def list_repos(user: str) -> List[str]:
    """List public repos for a GitHub user."""
    return [r.full_name for r in gh.get_user(user).get_repos()]

if __name__ == "__main__":
    
    mcp.run()
