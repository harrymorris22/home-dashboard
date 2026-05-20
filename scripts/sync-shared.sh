#!/usr/bin/env bash
# Sync packages/ui/ → each Add-on's frontend/src/_shared/.
#
# Why this script exists: HA Add-on builds set the slug directory as the Docker
# build context. The build context can't reach sibling directories like
# packages/. To keep a single source of truth without that constraint, we
# commit a copy of packages/ui/src/ into each Add-on as _shared/, regenerated
# by this script.
#
# Contract: NEVER edit `<addon>/frontend/src/_shared/*` directly. Edit
# `packages/ui/src/*`, run this script, commit both the source and the synced
# copies in the same commit.
#
# Usage: bash scripts/sync-shared.sh
# CI can run this and `git diff --exit-code` to catch drift.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$REPO_ROOT/packages/ui/src"

[ -d "$SRC" ] || { echo "ERROR: $SRC not found"; exit 1; }

ADDONS=(loft_climate desk)

for addon in "${ADDONS[@]}"; do
  DST="$REPO_ROOT/$addon/frontend/src/_shared"
  if [ ! -d "$REPO_ROOT/$addon" ]; then
    echo "[sync-shared] skip: $addon does not exist yet"
    continue
  fi
  mkdir -p "$DST"
  # rsync with --delete so removed files in packages/ui are also removed here.
  rsync -a --delete "$SRC/" "$DST/"
  echo "[sync-shared] synced packages/ui/src → $addon/frontend/src/_shared"

  # Tailwind tokens — copied into frontend root so tailwind.config.ts can
  # import it locally (Docker build context can't reach ../../packages/).
  cp "$REPO_ROOT/packages/ui/tailwind-tokens.cjs" "$REPO_ROOT/$addon/frontend/tailwind-tokens.cjs"
  echo "[sync-shared] synced tailwind-tokens.cjs → $addon/frontend/"
done
