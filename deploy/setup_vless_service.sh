#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Использование: $0 'vless://...'" >&2
  exit 1
fi

VLESS_URI="$1"
SERVICE_NAME="${SERVICE_NAME:-chudi-vpn}"
INSTALL_DIR="${INSTALL_DIR:-/opt/sing-box}"
CONFIG_DIR="${CONFIG_DIR:-/etc/sing-box}"
CONFIG_PATH="$CONFIG_DIR/config.json"
BIN_PATH="/usr/local/bin/sing-box"
MODE="${MODE:-tun}"
SOCKS_PORT="${SOCKS_PORT:-2080}"
HTTP_PORT="${HTTP_PORT:-2081}"
TUN_NAME="${TUN_NAME:-sb-tun0}"
TUN_IPV4="${TUN_IPV4:-172.19.0.1/30}"
TUN_IPV6="${TUN_IPV6:-fdfe:dcba:9876::1/126}"

if [[ $EUID -ne 0 ]]; then
  echo "Скрипт нужно запускать от root." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 curl tar jq ca-certificates

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

eval "$(python3 - <<'PY' "$VLESS_URI"
import sys
from urllib.parse import urlparse, parse_qs, unquote

uri = sys.argv[1]
parsed = urlparse(uri)

if parsed.scheme != "vless":
    raise SystemExit("Ожидается ссылка vless://")

query = parse_qs(parsed.query)

def pick(name, default=""):
    return query.get(name, [default])[0]

uuid = parsed.username or ""
server = parsed.hostname or ""
port = parsed.port or ""

if not uuid or not server or not port:
    raise SystemExit("В ссылке не хватает uuid/server/port")

mapping = {
    "VLESS_UUID": uuid,
    "VLESS_SERVER": server,
    "VLESS_PORT": str(port),
    "VLESS_TYPE": pick("type", "tcp"),
    "VLESS_SECURITY": pick("security", ""),
    "VLESS_PBK": pick("pbk", ""),
    "VLESS_FP": pick("fp", "chrome"),
    "VLESS_SNI": pick("sni", ""),
    "VLESS_SID": pick("sid", ""),
    "VLESS_FLOW": pick("flow", ""),
    "VLESS_SPX": unquote(pick("spx", "/")),
}

for key, value in mapping.items():
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    print(f'{key}="{escaped}"')
PY
)"

if [[ "$VLESS_TYPE" != "tcp" ]]; then
  echo "Скрипт сейчас рассчитан на VLESS Reality поверх TCP." >&2
  exit 1
fi

if [[ "$VLESS_SECURITY" != "reality" ]]; then
  echo "Скрипт сейчас рассчитан на VLESS Reality." >&2
  exit 1
fi

RELEASE_JSON="$(curl -fsSL https://api.github.com/repos/SagerNet/sing-box/releases/latest)"
VERSION="$(printf '%s' "$RELEASE_JSON" | jq -r '.tag_name')"

if [[ -z "$VERSION" || "$VERSION" == "null" ]]; then
  echo "Не удалось определить последнюю версию sing-box." >&2
  exit 1
fi

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64) ASSET_ARCH="amd64" ;;
  aarch64|arm64) ASSET_ARCH="arm64" ;;
  *)
    echo "Неподдерживаемая архитектура: $ARCH" >&2
    exit 1
    ;;
esac

ASSET_URL="https://github.com/SagerNet/sing-box/releases/download/${VERSION}/sing-box-${VERSION#v}-linux-${ASSET_ARCH}.tar.gz"

mkdir -p "$INSTALL_DIR" "$CONFIG_DIR"
curl -fsSL "$ASSET_URL" -o "$TMP_DIR/sing-box.tar.gz"
tar -xzf "$TMP_DIR/sing-box.tar.gz" -C "$TMP_DIR"

EXTRACTED_DIR="$(find "$TMP_DIR" -mindepth 1 -maxdepth 1 -type d -name "sing-box-*linux-${ASSET_ARCH}" | head -n 1)"
if [[ -z "$EXTRACTED_DIR" ]]; then
  echo "Не удалось распаковать sing-box." >&2
  exit 1
fi

install -m 755 "$EXTRACTED_DIR/sing-box" "$BIN_PATH"

if [[ "$MODE" == "tun" ]]; then
  cat > "$CONFIG_PATH" <<EOF
{
  "log": {
    "level": "info"
  },
  "inbounds": [
    {
      "type": "tun",
      "interface_name": "$TUN_NAME",
      "address": [
        "$TUN_IPV4",
        "$TUN_IPV6"
      ],
      "auto_route": true,
      "strict_route": false,
      "stack": "system",
      "sniff": true
    }
  ],
  "outbounds": [
    {
      "type": "vless",
      "tag": "proxy",
      "server": "$VLESS_SERVER",
      "server_port": $VLESS_PORT,
      "uuid": "$VLESS_UUID",
      "flow": "$VLESS_FLOW",
      "packet_encoding": "xudp",
      "tls": {
        "enabled": true,
        "server_name": "$VLESS_SNI",
        "utls": {
          "enabled": true,
          "fingerprint": "$VLESS_FP"
        },
        "reality": {
          "enabled": true,
          "public_key": "$VLESS_PBK",
          "short_id": "$VLESS_SID"
        }
      }
    },
    {
      "type": "direct",
      "tag": "direct"
    }
  ],
  "route": {
    "auto_detect_interface": true,
    "final": "proxy"
  }
}
EOF
else
  cat > "$CONFIG_PATH" <<EOF
{
  "log": {
    "level": "info"
  },
  "inbounds": [
    {
      "type": "socks",
      "tag": "socks-in",
      "listen": "127.0.0.1",
      "listen_port": $SOCKS_PORT,
      "sniff": true
    },
    {
      "type": "http",
      "tag": "http-in",
      "listen": "127.0.0.1",
      "listen_port": $HTTP_PORT
    }
  ],
  "outbounds": [
    {
      "type": "vless",
      "tag": "proxy",
      "server": "$VLESS_SERVER",
      "server_port": $VLESS_PORT,
      "uuid": "$VLESS_UUID",
      "flow": "$VLESS_FLOW",
      "packet_encoding": "xudp",
      "tls": {
        "enabled": true,
        "server_name": "$VLESS_SNI",
        "utls": {
          "enabled": true,
          "fingerprint": "$VLESS_FP"
        },
        "reality": {
          "enabled": true,
          "public_key": "$VLESS_PBK",
          "short_id": "$VLESS_SID"
        }
      }
    },
    {
      "type": "direct",
      "tag": "direct"
    }
  ],
  "route": {
    "auto_detect_interface": true,
    "final": "proxy"
  }
}
EOF
fi

cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Sing-box VLESS client
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$BIN_PATH run -c $CONFIG_PATH
Restart=always
RestartSec=5
LimitNOFILE=1048576
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_NET_RAW
CapabilityBoundingSet=CAP_NET_ADMIN CAP_NET_BIND_SERVICE CAP_NET_RAW

[Install]
WantedBy=multi-user.target
EOF

"$BIN_PATH" check -c "$CONFIG_PATH"
systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}.service"

echo "Готово."
echo "Сервис: ${SERVICE_NAME}.service"
echo "Конфиг: $CONFIG_PATH"
if [[ "$MODE" == "tun" ]]; then
  echo "Режим: tun"
else
  echo "Режим: socks/http"
  echo "SOCKS5: 127.0.0.1:$SOCKS_PORT"
  echo "HTTP: 127.0.0.1:$HTTP_PORT"
fi
