#!/usr/bin/env bash
# Deploy en el VPS. Correr EN el VPS (por Tailscale):
#   ssh root@TU_VPS_IP 'cd /opt/arbitrador && bash deploy.sh'
# Hace: pull de origin/master + deps + restart de AMBOS servicios (dashboard y bot).
# No toca .env ni la trades.db (fuente única en el VPS). Los HTML con PII se suben
# aparte por scp (no están en git).
set -e
cd /opt/arbitrador
echo "== pull =="
git pull --ff-only
echo "== deps =="
.venv/bin/pip install -q -r requirements.txt
echo "== restart =="
systemctl restart arbitrador telegram-bot
sleep 2
echo "deploy OK: $(git rev-parse --short HEAD) | servicios: $(systemctl is-active arbitrador telegram-bot | tr '\n' ' ')"
