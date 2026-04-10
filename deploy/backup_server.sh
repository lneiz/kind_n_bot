#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
OUTPUT_DIR="${2:-$PROJECT_DIR/backups}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
TMP_DIR="$(mktemp -d)"
BUNDLE_DIR="$TMP_DIR/chudi_bundle_$TIMESTAMP"
PROJECT_BASENAME="$(basename "$PROJECT_DIR")"
ARCHIVE_PATH="$OUTPUT_DIR/${PROJECT_BASENAME}_bundle_${TIMESTAMP}.tar.gz"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

mkdir -p "$OUTPUT_DIR"
mkdir -p "$BUNDLE_DIR"

if [[ ! -f "$PROJECT_DIR/.env" ]]; then
  echo "Не найден файл $PROJECT_DIR/.env" >&2
  exit 1
fi

set -a
. "$PROJECT_DIR/.env"
set +a

if [[ -z "${DB_USER:-}" || -z "${DB_HOST:-}" || -z "${DB_PORT:-}" || -z "${DB_NAME:-}" ]]; then
  echo "В .env не хватает DB_USER/DB_HOST/DB_PORT/DB_NAME" >&2
  exit 1
fi

mkdir -p "$BUNDLE_DIR/project"
rsync -a \
  --exclude '.git' \
  --exclude '__pycache__' \
  --exclude '.pytest_cache' \
  --exclude '.mypy_cache' \
  --exclude 'venv' \
  --exclude '.venv' \
  --exclude 'env' \
  --exclude 'chudivenv' \
  --exclude '*.log' \
  "$PROJECT_DIR/" "$BUNDLE_DIR/project/"

cat > "$BUNDLE_DIR/metadata.env" <<EOF
BACKUP_CREATED_AT=$TIMESTAMP
PROJECT_BASENAME=$PROJECT_BASENAME
ORIGINAL_PROJECT_DIR=$PROJECT_DIR
DB_HOST=${DB_HOST}
DB_PORT=${DB_PORT}
DB_NAME=${DB_NAME}
DB_USER=${DB_USER}
WEB_APP_URL=${WEB_APP_URL:-}
EOF

if [[ -n "${DB_PASS:-}" ]]; then
  PGPASSWORD="$DB_PASS" pg_dump \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --clean \
    --if-exists \
    --no-owner \
    --no-privileges \
    > "$BUNDLE_DIR/database.sql"
else
  pg_dump \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --clean \
    --if-exists \
    --no-owner \
    --no-privileges \
    > "$BUNDLE_DIR/database.sql"
fi

if [[ -d /etc/cloudflared ]]; then
  mkdir -p "$BUNDLE_DIR/cloudflared/etc"
  rsync -a /etc/cloudflared/ "$BUNDLE_DIR/cloudflared/etc/"
fi

if [[ -d "$HOME/.cloudflared" ]]; then
  mkdir -p "$BUNDLE_DIR/cloudflared/home"
  rsync -a "$HOME/.cloudflared/" "$BUNDLE_DIR/cloudflared/home/"
fi

mkdir -p "$BUNDLE_DIR/systemd"
find /etc/systemd/system -maxdepth 1 -type f -name '*.service' -print0 | while IFS= read -r -d '' service_file; do
  if grep -q "$PROJECT_DIR" "$service_file"; then
    cp "$service_file" "$BUNDLE_DIR/systemd/"
  fi
done

if [[ -x "$PROJECT_DIR/chudivenv/bin/pip" ]]; then
  "$PROJECT_DIR/chudivenv/bin/pip" freeze > "$BUNDLE_DIR/pip_freeze.txt" || true
elif [[ -x "$PROJECT_DIR/.venv/bin/pip" ]]; then
  "$PROJECT_DIR/.venv/bin/pip" freeze > "$BUNDLE_DIR/pip_freeze.txt" || true
fi

tar -C "$TMP_DIR" -czf "$ARCHIVE_PATH" "$(basename "$BUNDLE_DIR")"
echo "$ARCHIVE_PATH"
