#!/usr/bin/env bash
# Idempotent dependency bootstrap for the ms-artificial-intelligence-core Cloud Agent environment.
# Installs the system libraries WeasyPrint needs for PDF rendering, creates the .venv the
# Makefile's test/coverage targets expect, and installs the pinned Python requirements.
set -euo pipefail

cd "$(dirname "$0")/.."

if command -v sudo >/dev/null 2>&1; then
  SUDO="sudo"
else
  SUDO=""
fi

export DEBIAN_FRONTEND=noninteractive
$SUDO apt-get update -qq
$SUDO apt-get install -y --no-install-recommends \
  python3-venv \
  libpango-1.0-0 \
  libpangocairo-1.0-0 \
  libcairo2 \
  libgdk-pixbuf-2.0-0 \
  libffi-dev \
  shared-mime-info

if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
fi

./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

echo "install.sh: dependency bootstrap complete"
