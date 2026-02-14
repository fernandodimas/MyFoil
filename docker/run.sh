#!/usr/bin/env bash
set -euo pipefail
# Simple run helper kept for compatibility with existing Dockerfile
exec /app/entrypoint.sh "$@"
