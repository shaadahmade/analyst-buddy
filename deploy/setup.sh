#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${1:?usage: bash deploy/setup.sh <your-domain, e.g. analystbuddy.duckdns.org>}"
APP="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$APP/.env" ] || { echo "Copy your .env into $APP first"; exit 1; }

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y curl gpg debian-keyring debian-archive-keyring apt-transport-https netfilter-persistent iptables-persistent

curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs

curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | sudo gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
sudo apt-get update
sudo apt-get install -y caddy

curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
cd "$APP"
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements.txt

cd "$APP/web"
npm ci
npm run build

sed -e "s|__APP__|$APP|g" -e "s|__USER__|$USER|g" "$APP/deploy/analyst-buddy.service" | sudo tee /etc/systemd/system/analyst-buddy.service >/dev/null
sed -e "s|__DOMAIN__|$DOMAIN|g" "$APP/deploy/Caddyfile" | sudo tee /etc/caddy/Caddyfile >/dev/null

for port in 80 443; do
  sudo iptables -C INPUT -p tcp --dport "$port" -m state --state NEW -j ACCEPT 2>/dev/null \
    || sudo iptables -I INPUT 6 -p tcp --dport "$port" -m state --state NEW -j ACCEPT
done
sudo netfilter-persistent save

sudo systemctl daemon-reload
sudo systemctl enable --now analyst-buddy
sudo systemctl restart caddy

echo "Done. Open https://$DOMAIN (the HTTPS certificate can take a minute)."
echo "Logs: journalctl -u analyst-buddy -f"
