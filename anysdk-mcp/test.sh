#!/bin/bash
# anysdk-mcp/test.sh

cd "$(dirname "$0")"
uv run pytest -q "$@"
