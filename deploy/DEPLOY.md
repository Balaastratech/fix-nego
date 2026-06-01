# Oracle Cloud Deployment — Phase C/D Walkthrough

Stand up the lean backend on an Oracle Always-Free Ampere A1 VM, behind Caddy
(auto HTTPS/WSS), reachable at `https://api.balaastratech.com`, gated by a shared
token. Companion to `docs/plans/2026-05-30-desktop-oracle-deploy-plan.md`
(Phases C + D). Artifacts referenced live in this `deploy/` folder.

> **No-breakage note:** the shared token (Phase C) is OFF until you set
> `COMPANION_SHARED_TOKEN`. With it empty, the backend behaves exactly as it does
> on localhost today. Set it on the VM **and** in the desktop build together.

---

## 0. Prerequisites
- An Oracle Cloud tenancy (Always-Free eligible).
- DNS control for `balaastratech.com` (to add the `api` A record).
- A desktop build whose `COMPANION_SHARED_TOKEN` matches the VM's.

Generate the shared token once (use the same value both sides):
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 1. Create the VM (Phase D1)
1. OCI Console → **Compute → Instances → Create instance**.
2. Image: **Ubuntu 22.04 LTS** (or newer). Shape: **Ampere A1 Flex**,
   1–2 OCPU / 6–12 GB RAM (plenty for the lean profile; no torch).
3. Region/AD: Ashburn or Phoenix are the most reliable for A1 capacity. If you
   hit "Out of host capacity", retry or switch AD.
4. Add your SSH public key. Create.
5. Note the **public IP**.

## 2. Open ports (Phase D2) — TWO layers, both required
Oracle blocks ingress at the cloud layer AND inside the VM image.

**a) OCI Security List** (cloud firewall):
- VCN → your subnet → Security List → **Add Ingress Rules**:
  - Source `0.0.0.0/0`, TCP, dest port **80**
  - Source `0.0.0.0/0`, TCP, dest port **443**

**b) VM firewall** (iptables) — handled by `setup-oracle.sh` step 4, or manually:
```bash
sudo iptables -I INPUT -p tcp --dport 80  -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo apt-get install -y iptables-persistent && sudo netfilter-persistent save
```
> Do **not** open 8000 publicly — uvicorn binds to `127.0.0.1` and Caddy fronts it.

## 3. DNS (Phase C2)
Add an **A record**: `api.balaastratech.com` → `<VM public IP>`. Wait for it to
resolve (`nslookup api.balaastratech.com`) before starting Caddy, or Let's
Encrypt issuance will fail.

## 4. Get the code onto the VM (Phase D3)
SSH in, then either clone (preferred) or rsync the backend:
```bash
sudo mkdir -p /opt/companion && sudo chown ubuntu:ubuntu /opt/companion
git clone <your-repo-url> /opt/companion        # private repo: use a deploy key
# (or, from your PC, copy only the backend minus dev/PII files:)
# rsync -av --exclude-from=deploy/rsync-exclude.txt backend/ ubuntu@<IP>:/opt/companion/backend/
```

## 5. Backend env (Phase D6 + C1)
```bash
cd /opt/companion/backend
cp ../deploy/.env.oracle.example .env
nano .env          # set COMPANION_SHARED_TOKEN; leave AI keys EMPTY (BYOK)
chmod 600 .env
```
This profile is AI-Studio/BYOK (not Vertex) and disables every heavy speaker/
diarization path, so nothing imports a package the lean wheel set omits.

## 6. Provision (Phase D3/D4) — one command
```bash
chmod +x /opt/companion/deploy/setup-oracle.sh
/opt/companion/deploy/setup-oracle.sh
```
Installs Python + Caddy, builds the venv from `requirements-desktop.txt`, opens
the VM firewall, installs the Caddyfile, and enables the `companion-backend` +
`caddy` systemd services. Re-runnable.

> If you skipped step 5, the script stops and tells you to create `.env` first,
> then run: `sudo systemctl enable --now companion-backend && sudo systemctl reload caddy`.

## 7. Verify (Phase D acceptance)
```bash
# On the VM:
journalctl -u companion-backend -f      # look for "Backend marked ready for sessions"
journalctl -u caddy -f                   # cert obtained for api.balaastratech.com

# From your PC:
curl -s https://api.balaastratech.com/health           # {"status":"healthy"}
curl -s https://api.balaastratech.com/api/ready         # {"ready":true,...} after ~1-2s

# Token gate (with a token set in .env):
curl -s -o /dev/null -w "%{http_code}\n" https://api.balaastratech.com/api/providers/config
#   -> 401  (no token)
curl -s -o /dev/null -w "%{http_code}\n" \
     -H "X-Companion-Token: <YOUR_TOKEN>" https://api.balaastratech.com/api/providers/config
#   -> 200
```
Then point the desktop app at the VM (set `COMPANION_BACKEND_WS=wss://api.balaastratech.com/ws`
and `COMPANION_SHARED_TOKEN=<same token>` in `desktop/.env`, or rely on the
packaged production default) and confirm a session connects over `wss://`. A
wrong/missing token closes the WS during the handshake (code 1008).

## 8. Stay alive (Phase D5)
```bash
crontab -e
# */10 * * * * /opt/companion/deploy/keepalive.sh >/dev/null 2>&1
```
Backstop against Oracle's 7-day idle reclaim. systemd auto-restarts the service
if the VM is ever stopped/rebooted.

---

## Operations cheat-sheet
| Action | Command |
|---|---|
| Restart backend | `sudo systemctl restart companion-backend` |
| Tail backend logs | `journalctl -u companion-backend -f` |
| Reload Caddy after Caddyfile edit | `sudo systemctl reload caddy` |
| Rotate the shared token | edit `.env` → `sudo systemctl restart companion-backend` → update desktop builds |
| Update code | `git pull` in `/opt/companion` → `pip install -r requirements-desktop.txt` (if deps changed) → restart backend |

## Rollback / kill-switch
- Disable auth instantly: blank `COMPANION_SHARED_TOKEN` in `.env` → restart.
- Revert provider-runtime layer: `PROVIDER_RUNTIME_OVERRIDE_ENABLED=false`.
- Stop serving entirely: `sudo systemctl stop companion-backend caddy`.
