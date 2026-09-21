---
name: cotizar-cliente
description: Use when the user asks to quote crypto for a client who sends PESOS — "cotizar BTC para Daniel", "cotizame Bitcoin", "un cliente me manda 660 mil para comprar BTC", "a cuánto le vendo 500 mil en USDT", or types /cotizar. Devuelve en 3 renglones qué comprar, a cuánto cotizarle y cuánto se gana; BTC siempre por la ruta ARS→USDT→spot. No carga la operación.
---

# Cotizar a un cliente (BTC o USDT) en 3 renglones

## Cuándo
El usuario pide cotizar cripto para alguien que le manda **pesos**:
"cotizar BTC para Daniel", "cotizame Bitcoin", "un cliente me manda 660 mil
para comprar BTC", "a cuánto le vendo 500 mil en USDT", `/cotizar`.

## Qué hace
Corre el comando y **pega la salida tal cual**. Nada más: no carga la operación
(se carga después con las capturas reales, cuando ya se ejecutó).

```bash
python -m cli.cotizar_cliente <ARS> --asset BTC --cliente <Nombre>
```

- `<ARS>`: los pesos que manda el cliente. Sin puntos: `660000`.
- `--asset`: `BTC` (default) o `USDT`.
- `--margen`: el % que se le gana. Si no se dice, usa `COTIZA_MARGEN_PCT` del
  config. El usuario suele trabajar con **0,5**.
- `--cliente`: sólo para el título del mensaje.

Salida (ejemplo real del 03/09/2026):

```
COTIZAR BTC · Daniel · 660.000 ARS

1. Comprás 415,12 USDT en binancep2p a 1.581,98 → 656.716 ARS
2. Comprás BTC en spot a 81.482,4 USDT → 0,00508953 BTC
3. Le retirás 0,00508953 BTC; con el fee de red (0,00002000) le LLEGAN 0,00506953 BTC

LE DECÍS: 130.189.505 ARS por BTC
           82.295,09 USDT por BTC
           recibe 0,00506953 BTC

Ganás 3.284 ARS (0,50%)
```

Están los cuatro datos que el usuario necesita para operar: a cuánto compra el
USDT, a cuánto compra el BTC, qué cotización le canta al cliente (**en pesos y
en USDT**, porque el cliente pregunta las dos) y **cuánto BTC le llega** al
cliente después del fee de red.

## Reglas que ya están adentro (no rehacerlas a mano)
- **BTC nunca se compra por el libro P2P**: la ruta es siempre
  `ARS → USDT (P2P) → BTC (spot)`. Comprarlo directo sale ~1% más caro.
- El precio de compra es **ejecutable por profundidad** para ese monto, no la
  mejor punta de la vidriera, y ya tiene adentro la comisión del venue.
- El **fee del spot (0,1%)** está contado: el margen que sale es limpio.
- La base del margen es el **costo de reposición de ahora**, no un costo viejo.
- Avisa si la punta elegida no tiene stock para el monto.
- **El fee de red lo absorbe el usuario, cobrado dentro del precio**
  (decisión del 03/09/2026; `BTC_NETWORK_FEE` = 0,00002 BTC, medido). Se compra
  de más para cubrir el retiro, así que **al cliente le llega EXACTO lo
  cotizado** y la ganancia que muestra el comando ya es neta del fee. Nunca
  cotizar sobre el bruto: ese día se prometió 0,00508768 y llegaron 0,00507.

## Después de pasar la cotización
- El precio se mueve: si pasan más de unos minutos, **recotizar** antes de cerrar.
- Cuando el usuario diga que la hizo, **no inventar los montos ejecutados**:
  correr el sync de Binance y pedirle las capturas del spot y de la entrega.
  Ver `.claude/skills/cargar-captura/SKILL.md`.
- Nunca liberar la cripto antes de que el dinero impacte en el banco.

## Si algo falla
- `No hay ninguna punta de compra disponible ahora` → el libro quedó sin ofertas
  para ese monto; probar con menos o reintentar en un rato.
- `VPS_API_URL no configurada` → falta la variable en el `.env`.
