# Deploy de la alerta de spread (VPS)

Requisitos previos en el `.env` del VPS (`/opt/arbitrador/.env`):
- `TELEGRAM_BOT_TOKEN` (de @BotFather)
- `TELEGRAM_CHAT_ID` (de @userinfobot)
- (opcional) overrides de `SPREAD_ALERT_*`

Pasos (en `ssh root@<vps>`):

1. Traer el código: `cd /opt/arbitrador && ./deploy.sh` (hace git pull --ff-only).
2. Probar a mano una pasada:
   `/opt/arbitrador/.venv/bin/python -m cli.spread_alert --once`
   (debería imprimir "Sin oportunidades nuevas" o mandar un aviso al Telegram).
3. Instalar las units:
   `cp deploy/spread-alert.service deploy/spread-alert.timer /etc/systemd/system/`
4. `systemctl daemon-reload`
5. `systemctl enable --now spread-alert.timer`
6. Verificar: `systemctl list-timers spread-alert.timer`
   y `journalctl -u spread-alert.service -n 20`.

Nota: el estado vive en `/opt/arbitrador/data/spread_alert_state.json`
(no trackeado en git; se crea solo en la primera corrida).
