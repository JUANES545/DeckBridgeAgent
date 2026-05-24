#!/usr/bin/env bash
# Install pre-commit hooks for development
# Run once after cloning: ./builds/install-dev-hooks.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Install pre-commit in the project venv
if [[ -f ".venv/bin/python" ]]; then
  .venv/bin/pip install pre-commit -q --index-url https://pypi.org/simple
  .venv/bin/pre-commit install
  echo "✓ pre-commit hooks installed"
else
  echo "ERROR: .venv not found. Run ./builds/mac/build_mac_app.sh first."
  exit 1
fi
