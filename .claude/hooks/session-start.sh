#!/bin/bash
# SessionStart hook — installs backend + frontend dependencies so the Definition-of-Done
# gates (ruff/mypy/pytest, tsc/eslint/prettier/vitest/build, playwright) work immediately in
# a Claude Code on the web session. See docs/engineering/handoff.md.
set -euo pipefail

# Only run in the remote (web) environment; local machines manage their own deps.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

# The backend requires Python >=3.12 (CI pins 3.12); the container's default `python3` may be
# older (e.g. 3.11), which `pip install -e` will refuse. Pick a >=3.12 interpreter explicitly.
PY=""
for cand in python3.12 python3.13 python3; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 12) else 1)' 2>/dev/null; then
    PY="$cand"; break
  fi
done
if [ -z "$PY" ]; then
  echo "[session-start] ERROR: no Python >=3.12 found (backend requires it)." >&2
  exit 1
fi

# Install the backend into a project venv. The system Python is externally managed (PEP 668)
# and refuses a global `pip install`; a venv is also more reproducible. Idempotent: reused if
# already present. `.venv` is gitignored.
VENV="$ROOT/backend/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  echo "[session-start] creating venv at backend/.venv ($("$PY" --version 2>&1))"
  "$PY" -m venv "$VENV"
fi
echo "[session-start] backend: pip install -e .[dev] into backend/.venv"
"$VENV/bin/python" -m pip install --quiet --disable-pip-version-check --upgrade pip
"$VENV/bin/python" -m pip install --quiet --disable-pip-version-check -e "$ROOT/backend[dev]"

# Put the venv on PATH for the session so `python`, `ruff`, `mypy`, `pytest` resolve to it.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PATH=\"$VENV/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi

echo "[session-start] frontend: npm ci (Node $(node --version 2>&1))"
# Chromium is pre-installed in this environment (PLAYWRIGHT_BROWSERS_PATH); do NOT run
# `playwright install`. npm ci gives the exact locked tree the strict gates expect.
( cd "$ROOT/frontend" && npm ci --no-audit --no-fund )

echo "[session-start] deps ready. Gates (backend venv is on PATH):"
echo "  backend  (cd backend):  ruff check . && ruff format --check . && mypy app && pytest"
echo "  frontend (cd frontend): npx tsc --noEmit && npx eslint . --max-warnings 0 && npx prettier --check . && npx vitest run --coverage && npx vite build && CI=1 npx playwright test"
