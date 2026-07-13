#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Building PDF with Docker..."
docker run --rm \
  -v "$SCRIPT_DIR":/workspace \
  -w /workspace \
  texlive/texlive:latest \
  latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
echo ""
echo "Done! PDF -> $SCRIPT_DIR/main.pdf"
