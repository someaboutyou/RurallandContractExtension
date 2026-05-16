#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_NAME="$(basename "$PROJECT_ROOT")"
VERSION="${1:-0.1.0}"
SKIP_BUILD="${SKIP_BUILD:-0}"
DATE_SUFFIX=$(date +%Y%m%d)
OUTPUT_NAME="${PROJECT_NAME}-v${VERSION}-${DATE_SUFFIX}"
OUTPUT_DIR="${OUTPUT_DIR:-$PROJECT_ROOT/dist}"

mkdir -p "$OUTPUT_DIR"

# ── Build ───────────────────────────────────────────────────────────
if [[ "$SKIP_BUILD" -ne 1 ]]; then
  echo "=== Running build (frontend + backend) ==="
  "$SCRIPT_DIR/build.sh"
  echo ""
else
  echo "Skipping build (SKIP_BUILD=1). Using existing build artifacts."
  if [[ ! -f "$PROJECT_ROOT/frontend/dist/index.html" ]]; then
    echo "WARNING: frontend/dist/ not found. Package will not include frontend UI."
  fi
fi

# ── Copy to temp ────────────────────────────────────────────────────
TEMP_DIR="$(mktemp -d)/pkg-${PROJECT_NAME}"
echo "Copying project to temporary packaging directory..."
echo "  Source: $PROJECT_ROOT"
echo "  Temp:   $TEMP_DIR"

mkdir -p "$TEMP_DIR"

rsync -a \
  --exclude='runtime/data' \
  --exclude='runtime/logs' \
  --exclude='runtime/.state' \
  --exclude='runtime/windows/postgresql/pgAdmin 4' \
  --exclude='runtime/windows/geoserver/data_dir/gwc' \
  --exclude='runtime/windows/geoserver/data_dir/gwc-layers' \
  --exclude='runtime/windows/geoserver/data_dir/logs' \
  --exclude='runtime/windows/geoserver/data_dir/workspaces' \
  --exclude='runtime/windows/jdk/jmods' \
  --exclude='frontend' \
  --exclude='backend/app' \
  --exclude='backend/__pycache__' \
  --exclude='backend/.venv' \
  --exclude='backend/.env' \
  --exclude='backend/build' \
  --exclude='backend/dist' \
  --exclude='docs' \
  --exclude='datas' \
  --exclude='.claude' \
  --exclude='.git' \
  --exclude='.pytest_cache' \
  --exclude='.mypy_cache' \
  --exclude='dist' \
  --exclude='*.pyc' \
  --exclude='*.c' \
  --exclude='*.pdb' \
  --exclude='src.zip' \
  --exclude='*.md' \
  --exclude='*.docx' \
  --exclude='*.pdf' \
  --exclude='.DS_Store' \
  --exclude='Thumbs.db' \
  "$PROJECT_ROOT/" "$TEMP_DIR/"

if [[ -f "$PROJECT_ROOT/frontend/dist/index.html" ]]; then
  mkdir -p "$TEMP_DIR/frontend"
  rsync -a "$PROJECT_ROOT/frontend/dist" "$TEMP_DIR/frontend/"
else
  echo "WARNING: frontend/dist/index.html not found. Package will not include frontend UI."
fi

# Copy compiled backend dist/ into temp
if [[ -d "$PROJECT_ROOT/backend/dist" ]]; then
  mkdir -p "$TEMP_DIR/backend"
  rsync -a "$PROJECT_ROOT/backend/dist/" "$TEMP_DIR/backend/dist/"
else
  echo "ERROR: backend/dist/ not found. Run build first." >&2
  exit 1
fi

# Remove __pycache__ dirs (just in case)
find "$TEMP_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# ── Package ─────────────────────────────────────────────────────────
ARCHIVE_PATH="$OUTPUT_DIR/${OUTPUT_NAME}.tar.gz"

echo "Creating archive: $ARCHIVE_PATH"

cd "$TEMP_DIR"
tar -czf "$ARCHIVE_PATH" .

rm -rf "$(dirname "$TEMP_DIR")"

SIZE=$(du -h "$ARCHIVE_PATH" | cut -f1)

echo ""
echo "Package created: $ARCHIVE_PATH"
echo "Size: $SIZE"
echo ""
echo "Deployment steps on target machine:"
echo "  1. Extract ${OUTPUT_NAME}.tar.gz"
echo "  2. Run: bash ./scripts/install.sh"
echo "  3. Run: bash ./scripts/init.sh"
echo "  4. Run: bash ./scripts/start-all.sh"

if [[ "$SKIP_BUILD" -ne 1 ]]; then
  echo ""
  echo "NOTE: Compiled backend output is in backend/dist/."
  echo "Source .py files under backend/app/ are preserved for continued development."
fi
