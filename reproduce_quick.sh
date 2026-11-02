#!/usr/bin/env bash
# Quick reproduction (no network): recompute every reported number from frozen verdicts.
set -euo pipefail
cd "$(dirname "$0")"
exec ./reproduce.sh --quick
