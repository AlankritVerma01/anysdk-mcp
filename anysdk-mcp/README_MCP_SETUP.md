# MCP SDK Bridge - Setup for MCP Investigator

This guide shows how to set up the MCP SDK Bridge to work with the MCP investigator or other MCP clients.

## Quick Start

### 1. Install Dependencies

```bash
cd /Users/alankritverma/projects/anysdk-mcp/anysdk-mcp
uv sync
```

### 2. Test the Server

```bash
# Test GitHub auto-discovery (works without token)
python mcp_server.py --sdk github-auto --debug

# Test with GitHub token for full access
GITHUB_TOKEN=your_token_here python mcp_server.py --sdk github-auto --debug

# Test Kubernetes auto-discovery
python mcp_server.py --sdk k8s-auto --debug
```

### 3. Use with MCP Investigator

#### Option A: Direct Command
In your MCP investigator, add a server with:
- **Command**: `python`
- **Args**: `["/Users/alankritverma/projects/anysdk-mcp/anysdk-mcp/mcp_server.py", "--sdk", "github-auto"]`
- **Environment**: `{"PYTHONPATH": "/Users/alankritverma/projects/anysdk-mcp/anysdk-mcp"}`

#### Option B: Use Configuration File
Copy the provided `mcp_config.json` to your MCP investigator configuration:

```json
{
  "mcpServers": {
    "anysdk-github": {
      "command": "python",
      "args": [
        "/Users/alankritverma/projects/anysdk-mcp/anysdk-mcp/mcp_server.py",
        "--sdk", "github-auto"
      ],
      "env": {
        "PYTHONPATH": "/Users/alankritverma/projects/anysdk-mcp/anysdk-mcp"
      }
    }
  }
}
```

## Available SDKs

### Auto-Discovery Adapters (Recommended)

- **`github-auto`**: Auto-discovers all GitHub API methods
  - Works without authentication (rate limited)
  - Set `GITHUB_TOKEN` environment variable for full access
  - Discovers ~50 methods from GitHub API

- **`k8s-auto`**: Auto-discovers all Kubernetes API methods  
  - Discovers methods from CoreV1Api, AppsV1Api, etc.
  - Uses your `~/.kube/config` or `KUBECONFIG` environment variable
  - Discovers ~100 methods from K8s APIs

### Curated Adapters

- **`github`**: Hand-curated GitHub operations (repos, issues, PRs)
- **`k8s`**: Hand-curated Kubernetes operations (pods, deployments, services)

## Features

### Plan/Apply Pattern for Write Operations
Write operations (create, delete, update) use a plan/apply pattern for safety:

1. **Plan**: `github.create_repo.plan` - Creates an execution plan
2. **Apply**: `github.create_repo.apply` - Executes the planned operation

### Safety Controls
- Rate limiting (configurable per SDK)
- Input validation and sanitization
- Operation classification (read vs write)
- Risk level assessment (low, medium, high)

### Configuration
Each SDK can be configured via YAML files in the `configs/` directory:
- `configs/github.yaml` - GitHub settings
- `configs/k8s.yaml` - Kubernetes settings

## Environment Variables

- **`GITHUB_TOKEN`**: GitHub personal access token for authenticated requests
- **`KUBECONFIG`**: Path to Kubernetes configuration file
- **`MCP_SDK`**: Default SDK to use (github-auto, k8s-auto, github, k8s)

## Troubleshooting

### GitHub Issues
```bash
# Check if GitHub is accessible
python -c "from github import Github; print(Github().get_rate_limit())"

# Test with token
GITHUB_TOKEN=your_token python -c "from github import Github; g=Github('your_token'); print(g.get_rate_limit())"
```

### Kubernetes Issues
```bash
# Check kubectl access
kubectl cluster-info

# Check kubeconfig
kubectl config current-context
```

### Server Issues
```bash
# Test server startup
python mcp_server.py --sdk github-auto --debug

# Check dependencies
uv run python -c "import mcp_sdk_bridge; print('✅ Package imported successfully')"
```

## Example Usage

Once connected to MCP investigator, you can use tools like:

**GitHub Auto:**
- `github.get_user` - Get user information
- `github.search_repositories` - Search repositories
- `github.get_rate_limit` - Check API rate limits

**Kubernetes Auto:**
- `k8s.CoreV1Api_list_namespaced_pod` - List pods
- `k8s.AppsV1Api_list_namespaced_deployment` - List deployments
- `k8s.CoreV1Api_read_namespaced_pod` - Get pod details

**Write Operations (with plan/apply):**
- `github.create_repo.plan` → `github.create_repo.apply`
- `k8s.CoreV1Api_create_namespaced_pod.plan` → `k8s.CoreV1Api_create_namespaced_pod.apply`

The auto-discovery adapters provide comprehensive access to the full SDK APIs while maintaining safety through the plan/apply pattern for destructive operations.
