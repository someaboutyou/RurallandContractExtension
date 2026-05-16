#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FRONTEND_PATH="$PROJECT_ROOT/frontend"
BACKEND_PATH="$PROJECT_ROOT/backend"
SETUP_SCRIPT="$BACKEND_PATH/setup_cython.py"
STATE_DIR="$PROJECT_ROOT/runtime/.state"
BUILD_MARKER="$STATE_DIR/built.json"

SKIP_FRONTEND="${SKIP_FRONTEND:-0}"
SKIP_BACKEND="${SKIP_BACKEND:-0}"

if [[ "${1:-}" == "--skip-frontend" ]]; then
  SKIP_FRONTEND=1
fi
if [[ "${1:-}" == "--skip-backend" ]]; then
  SKIP_BACKEND=1
fi

# ── Frontend ────────────────────────────────────────────────────────
if [[ "$SKIP_FRONTEND" -ne 1 ]]; then
  echo "=== Building frontend ==="
  if [[ ! -f "$FRONTEND_PATH/package.json" ]]; then
    echo "frontend/package.json not found." >&2
    exit 1
  fi
  cd "$FRONTEND_PATH"
  if ! command -v npm &>/dev/null; then
    echo "npm not found. Install Node.js to build the frontend." >&2
    exit 1
  fi
  echo "  npm install..."
  npm install --silent
  echo "  npm run build..."
  npm run build --silent

  if [[ ! -f "$FRONTEND_PATH/dist/index.html" ]]; then
    echo "Frontend build output not found: frontend/dist/index.html" >&2
    exit 1
  fi
  echo "  Frontend build complete: frontend/dist/"
  echo ""
fi

# ── Backend ─────────────────────────────────────────────────────────
if [[ "$SKIP_BACKEND" -ne 1 ]]; then
  echo "=== Building backend (Cython) ==="

  PYTHON_EXE=""
  for candidate in \
    "$PROJECT_ROOT/runtime/linux/python/bin/python" \
    "$(command -v python3 2>/dev/null || true)" \
    "$(command -v python 2>/dev/null || true)"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
      if "$candidate" -c "import Cython" >/dev/null 2>&1; then
        PYTHON_EXE="$candidate"
        break
      fi
    fi
  done

  if [[ -z "$PYTHON_EXE" ]]; then
    echo "  Cython not found in any Python. Installing into runtime Python..."
    RUNTIME_PYTHON="$PROJECT_ROOT/runtime/linux/python/bin/python"
    if [[ ! -x "$RUNTIME_PYTHON" ]]; then
      echo "Runtime Python not found at runtime/linux/python/bin/python. Cannot install Cython." >&2
      exit 1
    fi
    "$RUNTIME_PYTHON" -m pip install cython --break-system-packages 2>&1 | tail -1
    PYTHON_EXE="$RUNTIME_PYTHON"
  fi

  echo "  Python: $PYTHON_EXE"
  echo "  Compiling backend/app/**/*.py → backend/dist/.so"

  cd "$BACKEND_PATH"

  # Clean previous build artifacts and dist
  rm -rf "$BACKEND_PATH/build"
  rm -rf "$BACKEND_PATH/dist"

  if ! "$PYTHON_EXE" "$SETUP_SCRIPT" build_ext --build-lib dist; then
    echo "Cython compilation failed." >&2
    exit 1
  fi

  # Remove the cython build cache
  rm -rf "$BACKEND_PATH/build"

  # Remove __pycache__ directories from dist
  find "$BACKEND_PATH/dist" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

  # Verify compilation from dist/
  echo "  Verifying compilation..."
  cd "$BACKEND_PATH/dist"
  if ! "$PYTHON_EXE" -c "from app.main import app; print('  Import OK')"; then
    echo "Post-build import check failed. The compiled backend cannot be imported." >&2
    exit 1
  fi

  echo "  Backend build complete."
  echo ""
fi

# ── Marker ──────────────────────────────────────────────────────────
mkdir -p "$STATE_DIR"
cat > "$BUILD_MARKER" <<EOF
{
  "builtAt": "$(date -Iseconds)",
  "platform": "linux"
}
EOF

echo "=== Build complete ==="
echo "  Frontend: frontend/dist/"
echo "  Backend:  backend/app/ (compiled .so)"
echo ""
echo "Next: bash ./scripts/package.sh"
