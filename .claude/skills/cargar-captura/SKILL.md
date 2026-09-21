---
name: cargar-captura
description: Use when the user sends a screenshot/photo of a P2P operation (Lemon, Bitget, Binance, etc.) and asks to add/load it ("agregá esta compra/venta", "cargá este screen", manda una captura por Telegram). Parsea la captura y la carga a la planilla + trades.db.
---

# Cargar captura de operación P2P → planilla + DB

Cuando el usuario manda una captura de una operación P2P (compra/venta USDT/USDC),
leerla, confirmar los datos y cargarla con `cli/push_movement` (postea al VPS, que
escribe la Google Sheet **y** la `trades.db` del VPS; el dashboard del VPS lee de ahí).
CLI Binance: `cli/sync_binance`.

**FUENTE ÚNICA = el VPS (Fase 2 activada 2026-06-18).** Claude ya NO escribe en la
DB local: usar `cli/push_movement` (NO `cli/add_movement`), que hace POST a
`{VPS_API_URL}/api/movement`. El dashboard a mirar es el del VPS
(`http://TU_VPS_IP:8002`, por Tailscale), no el local. `cli/add_movement`
queda solo como fallback si el VPS no responde.

## Flujo (SIEMPRE)

1. **Leer la captura** (la imagen llega en el mensaje; mirala directo). Extraer:
   lado, fecha, monto USDT, cotización, comisión, total ARS, exchange, contraparte, ID.
2. **Cargar de una si el patrón es conocido.** Si es Lemon/Binance/Bitget con datos
   legibles y cuentas que cuadran (el redondo da, la comisión cierra), **cargar directo
   y después reportar** — NO mostrar la tabla y preguntar "¿te lo cargo?" (gasta tokens
   al pedo).
   Pedir confirmación SOLO si hay ambigüedad real: dato ilegible, exchange nuevo sin
   regla guardada, lado dudoso, o un monto que no cierra. (Regla de seguridad del
   negocio intacta: nunca liberar cripto sin cobrar; registrar una op ya completada NO
   es liberar fondos.)
3. **Dedupe**: el endpoint del VPS saltea si el `order_id` existe → devuelve
   `409 Ya cargado`. Si el usuario reenvía la misma captura, avisar "ya cargada".
4. **Cargar**: `python -m cli.push_movement --json '{...}'`. Imprime
   `201 {...}` (OK) o `409 {"detail":"Ya cargado #..."}`. Mismo JSON que abajo.
   (Fallback local si el VPS no responde: `python -m cli.add_movement --yes --json '{...}'`.)

## JSON de `add_movement`

```json
{"side":"COMPRA|VENTA","date":"YYYY-MM-DD","order_id":"<id>",
 "usd_gross":"..","commission":"..","usd_net":"..","price":"..",
 "total_ars":"..","exchange_coin":"<Exchange> / USDT","bank":".."}
```
`usd_net` opcional (default `gross - commission`). Montos como string (precisión).

## Maña CRÍTICA de Lemon (el monto redondo)

En Lemon "Intercambio con Lemmy", la captura muestra **"Cambio por X ARS"** y un
**monto USDT grande** (= lo que entró a la wallet, el **NETO**). Pero de la cuenta
del usuario sale un **número REDONDO** (50.000, 100.000…), no el "Cambio por".
La diferencia (~500 / ~1.000) **es el 1% de comisión** (la comisión `0,34`/`0,68`
USDT ≈ ese 1% en ARS).

**FÓRMULA GENERAL (usar siempre, no adivinar el redondo):** el "Cambio por" es el
**99% del total** (te descuentan el 1%). Entonces:

> **`total_ars` = "Cambio por" ÷ 0,99**

Es **EXACTO** (Lemon cobra 1% sobre el total), **aunque NO dé redondo y tenga
centavos**. NO buscar "el redondo" ni preguntar cada vez: el ÷0,99 ES el débito.
Confirmado con el usuario: `139.590 ÷ 0,99 = 141.000` (redondo) y
`95.013,02 ÷ 0,99 = 95.972,75` (con centavos, el banco debitó eso exacto).

Entonces para Lemon:
- `total_ars` = `"Cambio por" ÷ 0,99` (el débito real del banco; cargar con centavos).
- `usd_net` = el monto USDT grande de la captura (lo recibido).
- `usd_gross` = `total_ars ÷ cotización`.
- `commission` = `(total_ars − "Cambio por") ÷ cotización` = `total_ars × 0,01 ÷ cotiz`.
  **NO usar la comisión que muestra la captura**: está redondeada a 2 decimales
  (muestra 0,65 cuando la real es 0,6524) y rompe la cuenta.
- `price` = la cotización de la captura (referencia; el precio REAL lo calcula la
  planilla/dashboard como Total ÷ Neto, que ya incluye la comisión).

Ejemplo confirmado: "Cambio por 95.013,02, cotiz 1.471" → total **95.972,75**,
neto 64,59077, bruto 65,243203, com 0,652433 → precio real **1.485,86**.

**OJO — Lemon parte un intercambio en varios Lemmers:** la pantalla "Recibiste X
USDT A cambio de Y ARS" es el **TOTAL**; cada detalle con Lemoner/CUIT/ID es una
**PATA**. **NO cargar las patas por separado (duplica)** — cargar UNA sola con el
total. Ej: 94,894629 = 50,475867 (Valentín) + 44,418762, débito único 141.000.

## Otros exchanges
- **Bitget / Binance**: el monto USDT suele ser el **bruto**; comisión aparte
  (Binance: monto fijo 0,07/0,14/0,19 USDT, no %). `usd_net = gross - commission`.
- `exchange_coin` con el nombre real: `Bitget / USDT`, `Lemon / USDT`,
  `Binance / USDC`, etc. `bank` = método de pago (Mercadopago, Lemon, UalaNew…).
- Para Binance conviene `cli/sync_binance --today` (trae por API, con comisión real)
  en vez de parsear capturas. Ver [[actualizar-movimientos]].

## Después de cargar
La dashboard (http://127.0.0.1:8000) lee de `trades.db`: con un reload aparece.
La columna PRECIO y el Promedio muestran el precio real (Total ÷ Neto, con comisión).
