# Deploy del bot de comandos (VPS)

Requisitos en el `.env` del VPS (`/opt/arbitrador/.env`):
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (ya cargados)
- `DASHBOARD_URL` opcional (default `http://127.0.0.1:8002`)

Pasos (`ssh root@<vps>`):

1. Traer el código: `cd /opt/arbitrador && ./deploy.sh`.
2. Probar a mano (Ctrl-C para cortar): `/opt/arbitrador/.venv/bin/python -m bot.telegram_bot`
   y mandar `/spread` desde el celu.
3. Instalar la unit: `cp deploy/telegram-bot.service /etc/systemd/system/`
4. `systemctl daemon-reload`
5. `systemctl enable --now telegram-bot.service`
6. Verificar: `systemctl status telegram-bot.service` y
   `journalctl -u telegram-bot.service -n 30 -f`.

Es un proceso largo (polling), NO un timer: queda prendido 24/7.
`/spread`/`/precio`/`/stock` pegan al dashboard local. `/actualizar` solo
funciona si el companion corre en la PC.
