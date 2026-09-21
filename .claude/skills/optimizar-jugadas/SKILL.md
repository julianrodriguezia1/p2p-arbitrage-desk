---
name: optimizar-jugadas
description: Use when the user asks to find/optimize arbitrage opportunities beyond the single "best play" — "buscá oportunidades", "optimizá la estrategia", "armame una estrategia", "dónde gano más con volumen", "qué jugadas hay", "analizá el spread a fondo", "cuál conviene de verdad", or types /jugadas or /optimizar. Ranks routes by MONEY PER HOUR (not by %), filters out books with no real volume, and explains the trade-off. For a quick single answer use estrategia-spread instead.
---

# Optimizar jugadas (el buscador con criterio)

Es el escalón de arriba de `estrategia-spread`. Aquel da **la** mejor jugada del
momento; éste **busca y compara** todas, aplica el criterio de volumen y arma una
recomendación razonada.

## La regla que ordena todo

> **El porcentaje miente si nadie opera.** Un 2,17% sobre un libro que mueve
> 0 USD/hora rinde exactamente cero.

Medido el 2026-08-23: la ruta que salía **primera por neto** (doble maker en ETH,
2,17%) rinde **cero** — el libro de ETH no movió un dólar en 7 minutos y 34
avisos seguidos. Ver `docs/estrategias-rutas-ars.md`.

**Nunca rankees por `net_pct` a secas.** Rankeá por plata por hora, o al menos
mostrá el volumen al lado del porcentaje.

## Qué correr

Elegí según lo que pida. No corras todo si con uno alcanza.

**1) Foto rápida + la jugada con volumen** (lo más común):
```bash
curl -s "http://TU_VPS_IP:8002/api/estrategia?volume=1000"
```
Devuelve `best`, `alternatives`, `con_volumen` y `liquidez` por venue.
`con_volumen` es la mejor jugada **ejecutable en tamaño**; viene `null` cuando la
mejor ya es líquida (no hay nada que aclarar).

**2) Todas las rutas posibles** (cuando pide "buscá", "optimizá", "qué hay):
```bash
python -m cli.rutas --venues binance bybit okx --max-pasos 4 --solo-creibles
python -m cli.rutas --flujo flujo.json --fx 1590     # rankea por ARS/hora
```
Arma el grafo completo (tomar / publicar / spot / transferir) y busca **todos**
los ciclos ARS→…→ARS. Tarda ~2 min: avisale antes de correrlo.

**3) La prima por activo** (cuando pregunta por BTC o alts):
```bash
python -m cli.prima_alt --solo-creibles --min-cobertura 2
```

**4) La serie histórica** (cuándo se abre la prima):
```bash
ssh root@TU_VPS_IP "cd /opt/arbitrador && .venv/bin/python -m cli.prima_report --csv data/prima_log.csv"
```
El logger corre en el VPS cada 15 min desde el 2026-08-23.

## Los filtros que NO se saltean

Antes de recomendar algo, verificá las tres cosas:

1. **Libro con volumen.** Piso: **≥10 avisos y ≥10.000 USD** de stock en la punta
   que vas a usar, y que llene el monto pedido (`venue_liquido` en
   `core/strategy.py`). Un libro de 2-8 avisos con un precio espectacular es
   precio que nadie disputa. **Los CEX no publican orderbook: no se los mide y no
   se los castiga.**
2. **Cuántas patas dependen de que te tomen.** Publicar es esperar. Una jugada de
   2 patas publicadas necesita **dos** fills: si sólo cierra una, quedaste con
   posición y el número se evapora. A igual plata por hora, **preferí siempre la
   que expone una sola pata**.
3. **Volatilidad vs margen.** `cobertura = neto / cuánto se mueve el activo en los
   20 min que dura una orden`. Abajo de ~2x el ruido se come el margen. BTC cubre
   ~2,8x; ADA/DOGE/XRP no llegan a 1,5x.

## Lo que ya está medido (no lo recalcules salvo que pida)

| jugada | neto | techo ARS/hora | patas expuestas |
|---|---|---|---|
| Doble maker en BTC | 1,54% | ~26.300 | **2** |
| Tomar USDT → spot → publicar BTC | 0,82% | ~24.700 | **1** ← mejor ajustada por riesgo |
| Idem publicando también el USDT | 0,73% | ~22.000 | 2 |
| Doble maker en ETH | 2,17% | **0** | 2 |

Flujo medido (USD/hora, Binance): USDT te-venden 111.236 / te-compran 10.361 ·
BTC te-compran 1.901 / te-venden 1.074 · **ETH 0 y 0**.

**Los ARS/hora son un TECHO**, suponen capturar el 100% del flujo estando primero
en el libro siempre. Decilo cuando los uses.

## Reglas de negocio que atraviesan todo

- **Nunca comprar BTC por el libro P2P**: armarlo vía `USDT → spot` ahorra
  0,85-1,2%. Vender BTC por P2P sí está bien (rinde igual que vender USDT). Está
  en `CLAUDE.md`, sección "Regla de BTC".
- **Si publicás en BTC o alts, el aviso va FLOTANTE**, nunca a precio fijo: a
  precio fijo sólo te toman cuando el movimiento te juega en contra. El 62% de los
  avisos de BTC repreciaron en 19 min contra el 8% en USDT.
- **En USDT publicar no paga**: el ancho (0,18%) es menor al maker de Binance
  (0,20%). Sólo conviene si el ancho se abre.
- **Publicar es gratis en Bybit/OKX/Bitget/KuCoin** (maker 0%) y cuesta 0,20% en
  Binance. Pero esos venues suelen tener los libros flacos: chequeá el punto 1.
- Whitelist/blacklist de `CLAUDE.md`. **Nunca liberar cripto sin acreditación
  bancaria real.**

## Cómo responder

- En criollo, corto, con el número primero.
- **Siempre mostrá el volumen al lado del porcentaje.** "+0,61% pero 6 avisos y
  $7.500" es la información completa; "+0,61%" sola es engañosa.
- Si la mejor jugada se apoya en un libro flaco, **decilo y ofrecé la de abajo**.
- Nunca uses "ask"/"bid" en la respuesta (nomenclatura interna): decí "el que te
  vende" / "el que te compra", o "publicando" / "tomando".
- Si una fuente no responde, **decí FALTA**. No estimes ni completes.

## FALTA (aclararlo cuando sea relevante)

- **El maker de BTC/alts en Binance no está publicado.** Se asume el 0,20% del
  USDT. La jugada de doble maker lo paga **dos veces**, así que es la más
  sensible. Verificar logueado en `binance.com/en/fee/p2pFeeRate`.
- **El flujo medido son ventanas de 7-19 minutos.** Alcanza para separar "opera"
  de "no opera" (1.900 contra 0 es contundente) pero no para un caudal diario. El
  número bueno sale del logger de la semana.
