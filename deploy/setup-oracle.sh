#!/usr/bin/env bash
# Phase D — one-shot provisioning for the Oracle Ampere A1 (Ubuntu LTS, aarch64).
# Idempotent-ish: safe to re-run. Run as the 'ubuntu' user with sudo available.
#
#   chmod +x deploy/setup-oracle.sh && ./deploy/setup-oracle.sh
#
# What it does:
#   1. Installs Python 3.11+, venv, build basics, Caddy.
#   2. Creates the venv and installs requirements-desktop.txt (LEAN profile).
#   3. Opens the VM firewall for 80/443 (OCI images block by default).
#   4. Installs + starts the backend + Caddy systemd services.
#
# It does NOT create your backend/.env (secrets) or the OCI Security List rule —
# do those manually per DEPLOY.md. Set APP_DIR/DOMAIN below if yours differ.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/companion}"
REPO_BACKEND="$APP_DIR/backend"
DOMAIN="${DOMAIN:-api.balaastratech.com}"

echo "==> [1/6] System packages"
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv python3-pip git curl debian-keyring debian-archive-keyring apt-transport-https

echo "==> [2/6] Caddy (official apt repo)"
if ! command -v caddy >/dev/null 2>&1; then
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y caddy
fi

echo "==> [3/6] Python venv + LEAN requirements"
if [ ! -d "$REPO_BACKEND" ]; then
  echo "!! $REPO_BACKEND not found. Clone/copy the repo to $APP_DIR first (see DEPLOY.md)." >&2
  exit 1
fi
cd "$REPO_BACKEND"
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements-desktop.txt

echo "==> [4/6] VM firewall (iptables) for 80/443 — OCI images block these by default"
sudo iptables -I INPUT -p tcp --dport 80  -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
# Persist iptables across reboots
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent || true
sudo netfilter-persistent save || sudo bash -c 'iptables-save > /etc/iptables/rules.v4' || true

echo "==> [5/6] Caddyfile"
sudo mkdir -p /var/log/caddy
sudo cp "$APP_DIR/deploy/Caddyfile" /etc/caddy/Caddyfile
# If your domain differs from the default, rewrite the hostname line in place.
if [ "$DOMAIN" != "api.balaastratech.com" ]; then
  sudo sed -i "s/api.balaastratech.com/${DOMAIN}/" /etc/caddy/Caddyfile
fi

echo "==> [6/6] systemd services"
sudo cp "$APP_DIR/deploy/companion-backend.service" /etc/systemd/system/companion-backend.service
sudo systemctl daemon-reload
if [ ! -f "$REPO_BACKEND/.env" ]; then
  echo "!! $REPO_BACKEND/.env missing — copy deploy/.env.oracle.example, fill the token, chmod 600, THEN:" >&2
  echo "   sudo systemctl enable --now companion-backend && sudo systemctl reload caddy" >&2
else
  sudo systemctl enable --now companion-backend
  sudo systemctl enable --now caddy
  sudo systemctl reload caddy || true
fi

echo "==> Done. Verify:  curl -s https://${DOMAIN}/health"
echo "    Backend logs:  journalctl -u companion-backend -f"
echo "    Caddy logs:    journalctl -u caddy -f"
