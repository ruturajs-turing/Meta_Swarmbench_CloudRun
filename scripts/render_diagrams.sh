#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/diagrams/src"
OUT="$ROOT/diagrams/rendered"
PUPPETEER_CONFIG="$ROOT/scripts/puppeteer-config.json"

mkdir -p "$OUT"

for file in "$SRC"/*.mmd; do
  name="$(basename "$file" .mmd)"
  mmdc -p "$PUPPETEER_CONFIG" -i "$file" -o "$OUT/$name.png" -b white
  mmdc -p "$PUPPETEER_CONFIG" -i "$file" -o "$OUT/$name.svg" -b white
done

echo "Rendered diagrams to $OUT"
