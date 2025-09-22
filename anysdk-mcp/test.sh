#!/bin/bash
cd "$(dirname "$0")"
uv run pytest -q "$@"
