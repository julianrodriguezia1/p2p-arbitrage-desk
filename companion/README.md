# Compañero de sync

El **compañero** es un proceso liviano que corre en tu PC con Windows. Su función
es hacer el fetch de órdenes de Binance y Bybit (APIs que bloquean IPs de
datacenter con 451/403) y empujar los movimientos nuevos al VPS vía
`POST /api/movement`. El VPS no puede hacer esto solo; el compañero es el
puente.

Además expone un endpoint `POST /sync` que el bot de Telegram puede llamar
para disparar el sync a demanda (comando `/actualizar`).

---

## Cómo correrlo

```
python -m companion
```

Levanta un ícono en la bandeja del sistema. Desde ahí podés:

- **"Actualizar ahora"** — dispara el sync inmediatamente.
- **"Salir"** — cierra el compañero.

El compañero también escucha en `http://0.0.0.0:SYNC_BRIDGE_PORT/sync` para
recibir el gatillo del bot de Telegram.

---

## Variables de entorno necesarias

Copiá `.env.example` a `.env` y completá:

| Variable | Para qué |
|---|---|
| `BINANCE_API_KEY` / `BINANCE_API_SECRET` | fetch de órdenes Binance (read-only) |
| `SYNC_BRIDGE_TOKEN` | secreto compartido con el bot (protege el `/sync`) |
| `SYNC_BRIDGE_PORT` | puerto donde escucha el compañero (default `8765`) |

El VPS necesita además `SYNC_BRIDGE_URL` apuntando a tu IP Tailscale (ver abajo).

---

## Obtener la IP de Tailscale de tu PC

En la terminal de tu PC:

```
tailscale ip -4
```

Esa IP (algo como `100.x.x.x`) es la que va en `SYNC_BRIDGE_URL` del `.env`
del VPS:

```
SYNC_BRIDGE_URL=http://100.x.x.x:8765/sync
```

---

## Autostart en Windows (sin ventana de consola)

1. Abrí el explorador y escribí `shell:startup` en la barra de direcciones.
2. En esa carpeta creá un acceso directo nuevo.
3. En "Ubicación del elemento" poné:
   ```
   pythonw -m companion
   ```
   (con `pythonw` en lugar de `python` para que no abra ventana de consola).
4. Guardá. A partir del próximo inicio de sesión el compañero arranca solo.

---

## Bot de Telegram (corre en el VPS)

```
python -m bot.telegram_bot
```

El bot necesita estas variables en el `.env` del VPS:

| Variable | Para qué |
|---|---|
| `TELEGRAM_BOT_TOKEN` | token de tu bot (te lo da `@BotFather`) |
| `TELEGRAM_CHAT_ID` | tu chat id (te lo dice `@userinfobot`) |
| `SYNC_BRIDGE_URL` | URL del compañero en tu PC via Tailscale |
| `SYNC_BRIDGE_TOKEN` | el mismo secreto que usa el compañero |

---

## Seguridad

- **`SYNC_BRIDGE_TOKEN`**: el endpoint `/sync` del compañero exige este token
  en el header `X-Token`. Sin él, devuelve 401. Generá uno random con
  `python -c "import secrets; print(secrets.token_hex(32))"` y poné el mismo
  valor en el `.env` de la PC y del VPS.
- **`TELEGRAM_CHAT_ID`**: el bot sólo responde a los chat IDs de la allowlist.
  Si alguien más encuentra el bot, los comandos no tienen efecto.

---

## Prueba end-to-end (manual, con tokens reales)

1. En la PC: `python -m companion` (ícono en bandeja).
2. En el VPS: `python -m bot.telegram_bot`.
3. Desde el celular: mandar `/actualizar` al bot.
   - Esperado: "Buscando..." y luego "Sync listo - Binance: N nuevas...".
   - Verificar en el dashboard del VPS que los movimientos aparecen.
4. Apagar el compañero y repetir `/actualizar`.
   - Esperado: "No me pude conectar con tu compu...".
