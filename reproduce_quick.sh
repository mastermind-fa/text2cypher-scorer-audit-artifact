#!/usr/bin/env bash
# Quick reproduction (no network): recompute every paper claim from frozen verdicts; pass the dataset repository root as $1.
set -euo pipefail
cd "$(dirname "$0")"
exec ./reproduce.sh --quick "$@"
