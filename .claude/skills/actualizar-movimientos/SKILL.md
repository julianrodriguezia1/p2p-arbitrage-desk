---
name: actualizar-movimientos
description: Use when the user asks to "actualizar/cargar los movimientos", "cargar las operaciones de hoy", "sincronizar Binance" o subir trades P2P de Binance a la planilla y a trades.db en este repo (arbitrador).
---

# Actualizar movimientos (Binance P2P → planilla + trades.db)

## Qué hace
Trae las órdenes P2P **COMPLETED** de Binance (BUY+SELL) vía API read-only,
deduplica contra `trades.db` por `order_id`, y las escribe en la Google Sheet
nativa (pestaña del mes) y en la DB. CLI: `cli/sync_binance.py`.

## ANTES DE CORRER NADA: chequear el VPS

**El agente de la PC (`companion/agent.py`) ya viene pusheando solo al VPS**, que
es la fuente única. Si corrés `cli.sync_binance` a mano, escribe en la planilla
movimientos que el VPS ya cargó ahí → **filas duplicadas**. Pasó el 2026-08-28:
11 compras duplicadas en la pestaña Agosto.

Primero comparar. Si el VPS ya los tiene, **no hay nada que hacer**:

```bash
ssh root@TU_VPS_IP 'curl -s "http://TU_VPS_IP:8002/api/trades"' | python -c "import sys,json; d=json.load(sys.stdin); print(len(d), 'movimientos en el VPS')"
```

`cli.sync_binance` sólo se usa cuando el agente está caído y hay que cargar a
mano. Si hay que empujar al VPS, el camino es
`python -c "import config; from companion.sync_core import run_sync_default; print(run_sync_default(config))"`
(hace fetch y push, el VPS deduplica por order_id y escribe la planilla una vez).

## Flujo (seguir SIEMPRE en este orden)

1. **Preview primero, sin escribir.** Correr con `n` para ver qué hay nuevo:
   ```
   printf 'n\n' | python -m cli.sync_binance            # todas las nuevas
   printf 'n\n' | python -m cli.sync_binance --today    # solo hoy
   ```
2. **Mostrar la tabla al usuario y preguntar el alcance.** El script carga
   **todas** las nuevas de una. Si el usuario pidió "las de hoy", usar `--today`
   (o `--date YYYY-MM-DD`). Nunca cargar días viejos sin confirmar: pueden ser
   ventas cuyo dinero todavía no impactó (regla innegociable: no registrar como
   hecho lo que no cobraste).
3. **Cargar confirmando.** Una vez que el usuario eligió el alcance:
   ```
   printf 's\n' | python -m cli.sync_binance --today
   ```
   Verificar la salida: cada línea `OK #<order_id> -> <Mes>!A<fila>` = cargado.
   `SALTEADO ... falta la pestaña 'Mes'` = crear esa pestaña en la Sheet y reintentar.

## Banderas
- `--today` — solo movimientos con fecha de hoy (hora Argentina).
- `--date YYYY-MM-DD` — solo esa fecha.
- sin flags — todas las nuevas (pone la planilla al día).

## Errores conocidos
- **`HTTPError 400` / `-1021 Timestamp ... ahead of the server's time`**: el reloj
  de Windows está adelantado. Ya está resuelto: `BinanceP2PClient` sincroniza el
  offset con `/api/v3/time` y lo cachea (`core/binance_p2p.py`). Si reaparece,
  revisar esa sincronización, no subir `recvWindow`.
- **403 en endpoints P2P públicos** (scanner, no este flujo): IP de datacenter
  bloqueada; correr desde IP residencial.

## Reglas
- API key Binance: SOLO lectura. Jamás withdrawal ni gestión de anuncios acá.
- Confirmar con el usuario antes de escribir en la planilla (acción sobre Drive).
- El dedupe es por `order_id` contra `trades.db`: correr de más es seguro, no duplica.

## Tests
`python -m pytest tests/test_sync_binance.py tests/test_binance_p2p.py -q`
