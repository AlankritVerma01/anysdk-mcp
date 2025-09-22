# anysdk-mcp/mcp_sdk_bridge/adapters/github.py

"""
GitHub SDK Adapter

Provides MCP integration for GitHub API via PyGithub.
"""

from typing import List, Dict, Any, Optional
import os
from github import Github
from github.Repository import Repository
from github.PullRequest import PullRequest
from github.Issue import Issue

from ..core.discover import SDKDiscoverer, SDKMethod, SDKCapability
from ..core.schema import SchemaGenerator, MCPToolSchema
from ..core.wrap import SDKWrapper
from ..core.paginate import PaginationHandler, PaginationConfig
from ..core.serialize import ResponseSerializer


class GitHubAdapter:
    """GitHub SDK adapter for MCP"""
    
    def __init__(self, token: str = None, config: Dict[str, Any] = None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.config = config or {}
        if not self.token:
            raise ValueError("GitHub token is required. Set GITHUB_TOKEN environment variable or pass token parameter.")
        
        self.github = Github(self.token)
        self.discoverer = SDKDiscoverer("github")
        self.schema_generator = SchemaGenerator()
        self.wrapper = SDKWrapper()
        self.paginator = PaginationHandler()
        self.serializer = ResponseSerializer()
    
    def discover_capabilities(self) -> List[SDKCapability]:
        """Discover GitHub SDK capabilities"""
        capabilities = []
        
        # Repository operations
        repo_methods = [
            SDKMethod(
                name="list_repos",
                description="List repositories for a user or organization",
                parameters={
                    "user": {"type": "str", "required": True, "description": "Username or organization name"},
                    "type": {"type": "str", "required": False, "default": "all", "description": "Repository type: all, owner, member"}
                },
                return_type="List[Repository]",
                module_path="github.user",
                is_async=False
            ),
            SDKMethod(
                name="get_repo",
                description="Get a specific repository",
                parameters={
                    "full_name": {"type": "str", "required": True, "description": "Repository full name (owner/repo)"}
                },
                return_type="Repository",
                module_path="github.repository",
                is_async=False
            ),
            SDKMethod(
                name="create_repo",
                description="Create a new repository",
                parameters={
                    "name": {"type": "str", "required": True, "description": "Repository name"},
                    "description": {"type": "str", "required": False, "description": "Repository description"},
                    "private": {"type": "bool", "required": False, "default": False, "description": "Make repository private"}
                },
                return_type="Repository",
                module_path="github.repository",
                is_async=False
            )
        ]
        
        repo_capability = SDKCapability(
            name="repository_management",
            description="GitHub repository management operations",
            methods=repo_methods,
            requires_auth=True
        )
        capabilities.append(repo_capability)
        
        # Issue operations
        issue_methods = [
            SDKMethod(
                name="list_issues",
                description="List issues for a repository",
                parameters={
                    "repo": {"type": "str", "required": True, "description": "Repository full name (owner/repo)"},
                    "state": {"type": "str", "required": False, "default": "open", "description": "Issue state: open, closed, all"}
                },
                return_type="List[Issue]",
                module_path="github.issue",
                is_async=False
            ),
            SDKMethod(
                name="create_issue",
                description="Create a new issue",
                parameters={
                    "repo": {"type": "str", "required": True, "description": "Repository full name (owner/repo)"},
                    "title": {"type": "str", "required": True, "description": "Issue title"},
                    "body": {"type": "str", "required": False, "description": "Issue body"},
                    "labels": {"type": "List[str]", "required": False, "description": "Issue labels"}
                },
                return_type="Issue",
                module_path="github.issue",
                is_async=False
            )
        ]
        
        issue_capability = SDKCapability(
            name="issue_management",
            description="GitHub issue management operations",
            methods=issue_methods,
            requires_auth=True
        )
        capabilities.append(issue_capability)
        
        # Pull Request operations
        pr_methods = [
            SDKMethod(
                name="list_pull_requests",
                description="List pull requests for a repository",
                parameters={
                    "repo": {"type": "str", "required": True, "description": "Repository full name (owner/repo)"},
                    "state": {"type": "str", "required": False, "default": "open", "description": "PR state: open, closed, all"}
                },
                return_type="List[PullRequest]",
                module_path="github.pullrequest",
                is_async=False
            ),
            SDKMethod(
                name="create_pull_request",
                description="Create a new pull request",
                parameters={
                    "repo": {"type": "str", "required": True, "description": "Repository full name (owner/repo)"},
                    "title": {"type": "str", "required": True, "description": "PR title"},
                    "head": {"type": "str", "required": True, "description": "Head branch"},
                    "base": {"type": "str", "required": True, "description": "Base branch"},
                    "body": {"type": "str", "required": False, "description": "PR body"}
                },
                return_type="PullRequest",
                module_path="github.pullrequest",
                is_async=False
            )
        ]
        
        pr_capability = SDKCapability(
            name="pull_request_management",
            description="GitHub pull request management operations",
            methods=pr_methods,
            requires_auth=True
        )
        capabilities.append(pr_capability)
        
        return capabilities
    
    def generate_mcp_tools(self) -> List[MCPToolSchema]:
        """Generate MCP tool schemas for GitHub operations"""
        capabilities = self.discover_capabilities()
        tools = []
        
        for capability in capabilities:
            for method in capability.methods:
                schema = self.schema_generator.generate_tool_schema(method)
                tools.append(schema)
        
        return tools
    
    def create_tool_implementations(self) -> Dict[str, callable]:
        """Create actual tool implementations"""
        implementations = {}
        
        # Repository tools
        implementations["github.list_repos"] = self._wrap_list_repos
        implementations["github.get_repo"] = self._wrap_get_repo
        implementations["github.create_repo"] = self._wrap_create_repo
        
        # Issue tools
        implementations["github.list_issues"] = self._wrap_list_issues
        implementations["github.create_issue"] = self._wrap_create_issue
        
        # Pull request tools
        implementations["github.list_pull_requests"] = self._wrap_list_pull_requests
        implementations["github.create_pull_request"] = self._wrap_create_pull_request
        
        return implementations
    
    def _wrap_list_repos(self, user: str, type: str = "all") -> Dict[str, Any]:
        """List repositories for a user"""
        try:
            github_user = self.github.get_user(user)
            it = github_user.get_repos(type=type)
            # optional: respect max_items from config if present
            max_items = self.config.get("max_items_per_request", 100)
            repos = list(it[:max_items]) if max_items else list(it)
            
            repo_data = []
            for repo in repos:
                repo_data.append({
                    "name": repo.name,
                    "full_name": repo.full_name,
                    "description": repo.description,
                    "private": repo.private,
                    "html_url": repo.html_url,
                    "clone_url": repo.clone_url,
                    "language": repo.language,
                    "stars": repo.stargazers_count,
                    "forks": repo.forks_count,
                    "created_at": repo.created_at.isoformat() if repo.created_at else None,
                    "updated_at": repo.updated_at.isoformat() if repo.updated_at else None
                })
            
            return self.serializer.serialize_response(repo_data)
            
        except Exception as e:
            return self.serializer.serialize_error(e, {"user": user, "type": type})
    
    def _wrap_get_repo(self, full_name: str) -> Dict[str, Any]:
        """Get a specific repository"""
        try:
            repo = self.github.get_repo(full_name)
            
            repo_data = {
                "name": repo.name,
                "full_name": repo.full_name,
                "description": repo.description,
                "private": repo.private,
                "html_url": repo.html_url,
                "clone_url": repo.clone_url,
                "language": repo.language,
                "stars": repo.stargazers_count,
                "forks": repo.forks_count,
                "issues": repo.open_issues_count,
                "created_at": repo.created_at.isoformat() if repo.created_at else None,
                "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
                "default_branch": repo.default_branch,
                "topics": list(repo.get_topics()) if hasattr(repo, 'get_topics') else []
            }
            
            return self.serializer.serialize_response(repo_data)
            
        except Exception as e:
            return self.serializer.serialize_error(e, {"full_name": full_name})
    
    def _wrap_create_repo(self, name: str, description: str = None, private: bool = False) -> Dict[str, Any]:
        """Create a new repository"""
        try:
            user = self.github.get_user()
            repo = user.create_repo(
                name=name,
                description=description,
                private=private
            )
            
            repo_data = {
                "name": repo.name,
                "full_name": repo.full_name,
                "description": repo.description,
                "private": repo.private,
                "html_url": repo.html_url,
                "clone_url": repo.clone_url,
                "created_at": repo.created_at.isoformat() if repo.created_at else None
            }
            
            return self.serializer.serialize_response(repo_data)
            
        except Exception as e:
            return self.serializer.serialize_error(e, {"name": name, "description": description, "private": private})
    
    def _wrap_list_issues(self, repo: str, state: str = "open") -> Dict[str, Any]:
        """List issues for a repository"""
        try:
            repository = self.github.get_repo(repo)
            it = repository.get_issues(state=state)
            # optional: respect max_items from config if present
            max_items = self.config.get("max_items_per_request", 100)
            issues = list(it[:max_items]) if max_items else list(it)
            
            issue_data = []
            for issue in issues:
                if issue.pull_request is None:  # Exclude pull requests
                    issue_data.append({
                        "number": issue.number,
                        "title": issue.title,
                        "body": issue.body,
                        "state": issue.state,
                        "html_url": issue.html_url,
                        "user": issue.user.login if issue.user else None,
                        "labels": [label.name for label in issue.labels],
                        "created_at": issue.created_at.isoformat() if issue.created_at else None,
                        "updated_at": issue.updated_at.isoformat() if issue.updated_at else None
                    })
            
            return self.serializer.serialize_response(issue_data)
            
        except Exception as e:
            return self.serializer.serialize_error(e, {"repo": repo, "state": state})
    
    def _wrap_create_issue(self, repo: str, title: str, body: str = None, labels: List[str] = None) -> Dict[str, Any]:
        """Create a new issue"""
        try:
            repository = self.github.get_repo(repo)
            issue = repository.create_issue(
                title=title,
                body=body,
                labels=labels or []
            )
            
            issue_data = {
                "number": issue.number,
                "title": issue.title,
                "body": issue.body,
                "state": issue.state,
                "html_url": issue.html_url,
                "user": issue.user.login if issue.user else None,
                "labels": [label.name for label in issue.labels],
                "created_at": issue.created_at.isoformat() if issue.created_at else None
            }
            
            return self.serializer.serialize_response(issue_data)
            
        except Exception as e:
            return self.serializer.serialize_error(e, {"repo": repo, "title": title, "body": body, "labels": labels})
    
    def _wrap_list_pull_requests(self, repo: str, state: str = "open") -> Dict[str, Any]:
        """List pull requests for a repository"""
        try:
            repository = self.github.get_repo(repo)
            it = repository.get_pulls(state=state)
            # optional: respect max_items from config if present
            max_items = self.config.get("max_items_per_request", 100)
            prs = list(it[:max_items]) if max_items else list(it)
            
            pr_data = []
            for pr in prs:
                pr_data.append({
                    "number": pr.number,
                    "title": pr.title,
                    "body": pr.body,
                    "state": pr.state,
                    "html_url": pr.html_url,
                    "user": pr.user.login if pr.user else None,
                    "head": {
                        "ref": pr.head.ref,
                        "sha": pr.head.sha
                    },
                    "base": {
                        "ref": pr.base.ref,
                        "sha": pr.base.sha
                    },
                    "created_at": pr.created_at.isoformat() if pr.created_at else None,
                    "updated_at": pr.updated_at.isoformat() if pr.updated_at else None,
                    "merged": pr.merged,
                    "mergeable": pr.mergeable
                })
            
            return self.serializer.serialize_response(pr_data)
            
        except Exception as e:
            return self.serializer.serialize_error(e, {"repo": repo, "state": state})
    
    def _wrap_create_pull_request(self, repo: str, title: str, head: str, base: str, body: str = None) -> Dict[str, Any]:
        """Create a new pull request"""
        try:
            repository = self.github.get_repo(repo)
            pr = repository.create_pull(
                title=title,
                head=head,
                base=base,
                body=body
            )
            
            pr_data = {
                "number": pr.number,
                "title": pr.title,
                "body": pr.body,
                "state": pr.state,
                "html_url": pr.html_url,
                "user": pr.user.login if pr.user else None,
                "head": {
                    "ref": pr.head.ref,
                    "sha": pr.head.sha
                },
                "base": {
                    "ref": pr.base.ref,
                    "sha": pr.base.sha
                },
                "created_at": pr.created_at.isoformat() if pr.created_at else None
            }
            
            return self.serializer.serialize_response(pr_data)
            
        except Exception as e:
            return self.serializer.serialize_error(e, {"repo": repo, "title": title, "head": head, "base": base, "body": body})
