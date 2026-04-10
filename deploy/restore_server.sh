#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Использование: $0 /path/to/bundle.tar.gz [app_user] [target_dir]" >&2
  exit 1
fi

BUNDLE_PATH="$(readlink -f "$1")"
APP_USER="${2:-chudibot}"
TARGET_DIR="${3:-/home/$APP_USER/kind_n_bot}"
APP_GROUP="$APP_USER"
TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

if [[ $EUID -ne 0 ]]; then
  echo "Скрипт нужно запускать от root." >&2
  exit 1
fi

if [[ ! -f "$BUNDLE_PATH" ]]; then
  echo "Не найден архив $BUNDLE_PATH" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-venv python3-pip postgresql postgresql-contrib postgresql-client rsync curl ca-certificates screen

if ! command -v cloudflared >/dev/null 2>&1; then
  cd "$TMP_DIR"
  curl -L -o cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
  dpkg -i "$TMP_DIR/cloudflared.deb" || apt-get install -f -y
fi

if ! id "$APP_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$APP_USER"
fi

mkdir -p "$TARGET_DIR"
tar -C "$TMP_DIR" -xzf "$BUNDLE_PATH"

BUNDLE_ROOT="$(find "$TMP_DIR" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
if [[ -z "$BUNDLE_ROOT" ]]; then
  echo "Не удалось распаковать архив." >&2
  exit 1
fi

rsync -a --delete "$BUNDLE_ROOT/project/" "$TARGET_DIR/"
chown -R "$APP_USER:$APP_GROUP" "$TARGET_DIR"

if [[ -f "$TARGET_DIR/.env" ]]; then
  set -a
  . "$TARGET_DIR/.env"
  set +a
else
  echo "В архиве нет .env" >&2
  exit 1
fi

if [[ "${DB_HOST:-localhost}" == "localhost" || "${DB_HOST:-127.0.0.1}" == "127.0.0.1" ]]; then
  systemctl enable --now postgresql

  if ! su - postgres -c "psql -Atqc \"SELECT 1 FROM pg_roles WHERE rolname = '$DB_USER'\"" | grep -q 1; then
    su - postgres -c "psql -c \"CREATE USER \\\"$DB_USER\\\" WITH PASSWORD '$DB_PASS';\""
  fi

  if ! su - postgres -c "psql -Atqc \"SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'\"" | grep -q 1; then
    su - postgres -c "psql -c \"CREATE DATABASE \\\"$DB_NAME\\\" OWNER \\\"$DB_USER\\\";\""
  fi

  if [[ -f "$BUNDLE_ROOT/database.sql" ]]; then
    PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$BUNDLE_ROOT/database.sql"
  fi
fi

su - "$APP_USER" -c "python3 -m venv '$TARGET_DIR/chudivenv'"
su - "$APP_USER" -c "'$TARGET_DIR/chudivenv/bin/pip' install --upgrade pip"
su - "$APP_USER" -c "'$TARGET_DIR/chudivenv/bin/pip' install -r '$TARGET_DIR/requirements.txt'"

if [[ -d "$BUNDLE_ROOT/cloudflared/etc" ]]; then
  mkdir -p /etc/cloudflared
  rsync -a "$BUNDLE_ROOT/cloudflared/etc/" /etc/cloudflared/
fi

if [[ -d "$BUNDLE_ROOT/cloudflared/home" ]]; then
  mkdir -p "/home/$APP_USER/.cloudflared"
  rsync -a "$BUNDLE_ROOT/cloudflared/home/" "/home/$APP_USER/.cloudflared/"
  chown -R "$APP_USER:$APP_GROUP" "/home/$APP_USER/.cloudflared"
fi

cat > /etc/systemd/system/chudi-bot.service <<EOF
[Unit]
Description=Chudi Bot
After=network.target postgresql.service

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$TARGET_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$TARGET_DIR/chudivenv/bin/python -m bot.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/chudi-webapp.service <<EOF
[Unit]
Description=Chudi WebApp
After=network.target postgresql.service

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$TARGET_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$TARGET_DIR/chudivenv/bin/uvicorn webapp.main:app --host 0.0.0.0 --port 8356
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/chudi-scheduler.service <<EOF
[Unit]
Description=Chudi Scheduler
After=network.target postgresql.service

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$TARGET_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$TARGET_DIR/chudivenv/bin/python -m core.scheduler
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now chudi-bot.service chudi-webapp.service chudi-scheduler.service

if [[ -f /etc/cloudflared/config.yml ]]; then
  cloudflared service install || true
  systemctl enable --now cloudflared || true
fi

echo "Готово: проект восстановлен в $TARGET_DIR"
