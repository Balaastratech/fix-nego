#!/usr/bin/env bash
# Phase D5 — idle-reclaim avoidance.
# Oracle Always-Free reclaims a VM only when, over a 7-day window, it is BELOW
# all of: ~20% CPU, 20% network, 20% memory (95th percentile). A periodic health
# hit generates a little CPU + inbound network so the instance isn't flagged idle.
#
# Install (every 10 min):
#   crontab -e
#   */10 * * * * /opt/companion/deploy/keepalive.sh >/dev/null 2>&1
#
# This is a backstop, not a guarantee — accept the occasional restart (systemd
# brings the service back automatically). Hitting the PUBLIC https URL exercises
# Caddy + TLS + the network path, which counts toward the network metric.
set -euo pipefail
DOMAIN="${DOMAIN:-api.balaastratech.com}"
curl -fsS --max-time 10 "https://${DOMAIN}/health" >/dev/null || true
