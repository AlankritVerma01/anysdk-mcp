# MCP SDK Bridge

A bridge between MCP (Model Context Protocol) servers and various SDK APIs, enabling seamless integration of different services through a unified MCP interface.

## 🚀 Ready for MCP Investigator!

The MCP SDK Bridge is now **ready to use with MCP investigator** and other MCP clients. It provides auto-discovery of SDK methods with safety controls.

## Quick Start

### For MCP Investigator Users

**Step 1**: Install dependencies
```bash
cd /path/to/anysdk-mcp/
uv sync
```

**Step 2**: Add server to MCP investigator
```json
{
  "mcpServers": {
    "anysdk-github": {
      "command": "python",
      "args": ["/path/to/anysdk-mcp/mcp_server.py", "--sdk", "github-auto"],
      "env": {"PYTHONPATH": "/path/to/anysdk-mcp"}
    }
  }
}
```

**Step 3**: Start using tools!
- GitHub: `github.get_user`, `github.search_repositories`, `github.get_rate_limit`
- Kubernetes: `k8s.CoreV1Api_list_namespaced_pod`, `k8s.AppsV1Api_list_namespaced_deployment`

### Standalone Testing

```bash
# Test GitHub auto-discovery (works without token)
python mcp_server.py --sdk github-auto --debug

# Test with authentication for full access
GITHUB_TOKEN=your_token python mcp_server.py --sdk github-auto --debug

# Test Kubernetes auto-discovery
python mcp_server.py --sdk k8s-auto --debug
```

## Available SDKs

### 🤖 Auto-Discovery Adapters (Recommended)

**`github-auto`** - Comprehensive GitHub API access
- ✅ Auto-discovers ~50 GitHub API methods
- ✅ Works without authentication (rate limited)
- ✅ Set `GITHUB_TOKEN` for full access
- ✅ Examples: `github.get_user`, `github.search_repositories`

**`k8s-auto`** - Comprehensive Kubernetes API access  
- ✅ Auto-discovers ~100 Kubernetes API methods
- ✅ Covers CoreV1Api, AppsV1Api, NetworkingV1Api, etc.
- ✅ Uses your kubeconfig automatically
- ✅ Examples: `k8s.CoreV1Api_list_namespaced_pod`

### 📝 Curated Adapters

**`github`** - Hand-selected GitHub operations
- Common repository, issue, and PR operations
- `github.list_repos`, `github.create_repo`, `github.list_issues`

**`k8s`** - Hand-selected Kubernetes operations  
- Common pod, deployment, and service operations
- `k8s.list_pods`, `k8s.scale_deployment`, `k8s.get_pod_logs`

## 🛡️ Safety Features

### Plan/Apply Pattern for Write Operations

Write operations (create, delete, update) use a safe two-step process:

1. **Plan**: `github.create_repo.plan {"name": "my-repo"}` → Returns plan ID
2. **Apply**: `github.create_repo.apply {"plan_id": "uuid-here"}` → Executes operation

This prevents accidental destructive operations and allows review before execution.

### Operation Classification

- **Read operations**: Execute immediately (low risk)
- **Write operations**: Require plan/apply (medium/high risk)
- **Risk levels**: Low, Medium, High based on potential impact

### Rate Limiting & Safety

- Configurable rate limiting per SDK
- Input validation and sanitization
- Response size limits
- Execution timeouts
- Operation logging

## Configuration Files

Each SDK can be customized via YAML configuration:

- `configs/github.yaml` - GitHub settings, rate limits, safety rules
- `configs/k8s.yaml` - Kubernetes settings, namespace restrictions

## Environment Variables

- **`GITHUB_TOKEN`**: GitHub personal access token for authenticated requests
- **`KUBECONFIG`**: Path to Kubernetes configuration file  
- **`MCP_SDK`**: Default SDK to use (github-auto, k8s-auto, github, k8s)

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   MCP Client    │    │   SDK Bridge     │    │   Target SDK    │
│ (Investigator,  │◄──►│   (FastMCP)      │◄──►│   (GitHub,      │
│   Claude, etc.) │    │                  │    │    K8s, etc.)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌──────────────┐
                       │ Auto-Discovery│
                       │ + Plan/Apply  │
                       │ + Safety      │
                       └──────────────┘
```

### Core Components

- **Auto-Discovery**: Automatically finds SDK methods using reflection
- **Schema Generation**: Creates MCP tool schemas from method signatures  
- **Plan/Apply**: Safe execution pattern for write operations
- **Safety Controls**: Rate limiting, input validation, risk assessment
- **Multi-SDK Support**: GitHub, Kubernetes, extensible to any Python SDK

## Troubleshooting

### GitHub Issues
```bash
# Test GitHub access
python -c "from github import Github; print(Github().get_rate_limit())"

# Test with token  
GITHUB_TOKEN=your_token python -c "from github import Github; print(Github('your_token').get_rate_limit())"
```

### Kubernetes Issues
```bash
# Check cluster access
kubectl cluster-info

# Check current context
kubectl config current-context
```

### Server Issues
```bash
# Test server startup
python mcp_server.py --sdk github-auto --debug

# Check dependencies
uv run python -c "import mcp_sdk_bridge; print('✅ Package imported')"
```

## Development

### Adding New SDKs

The bridge supports any Python SDK through auto-discovery:

1. Install the SDK package
2. Create a minimal auto-adapter (see `adapters/auto_github.py`)  
3. Add to CLI choices and validation
4. The bridge will automatically discover methods and create tools

### Running Tests

```bash
# Run all tests
PYTHONPATH=/path/to/anysdk-mcp uv run pytest

# Run specific tests
PYTHONPATH=/path/to/anysdk-mcp uv run pytest tests/test_e2e.py -v

# Test individual components
python tests/test_e2e.py  # Runs sync tests
```

## Example MCP Investigator Session

Once connected, you can use natural language with the auto-discovered tools:

**"List my GitHub repositories"**
→ Uses `github.get_user` + `github.search_repositories`

**"Show pods in the default namespace"** 
→ Uses `k8s.CoreV1Api_list_namespaced_pod`

**"Create a new repository called 'test-project'"**
→ Uses `github.create_repo.plan` → Review → `github.create_repo.apply`

The auto-discovery adapters provide comprehensive access to SDK APIs while maintaining safety through the plan/apply pattern for potentially destructive operations.

---

**🎉 Ready to use with MCP investigator!** Just add the server configuration and start exploring SDK APIs through natural language.