#!/bin/bash

# Launch MCP Inspector for anysdk-mcp
# This script ensures proper working directory and environment setup

echo "🚀 Starting MCP Inspector for anysdk-mcp..."

# Change to the correct directory
cd "$(dirname "$0")"

# Kill any existing inspector processes
pkill -f "modelcontextprotocol/inspector" 2>/dev/null || true

# Launch inspector with proper working directory
# Create a wrapper script that changes directory first
cat > /tmp/mcp_wrapper.sh << EOF
#!/bin/bash
cd "$(pwd)"
exec uv run python mcp_server.py --sdk github-auto
EOF
chmod +x /tmp/mcp_wrapper.sh

npx @modelcontextprotocol/inspector /tmp/mcp_wrapper.sh