#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: reproduce_one.sh <RUN_ID>"
  exit 2
fi

RUN_ID="$1"
python3 -m omniforge.cli reproduce --run-id "$RUN_ID"
