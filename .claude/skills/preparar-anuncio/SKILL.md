---
name: preparar-anuncio
description: Use when the user asks "prepará/armá un anuncio", "a qué precio publico/vendo/compro", "precio para vender/comprar USDT en Binance" — sugiere precio de publicación P2P (no publica).
---

# Preparar anuncio (asistente de publicación P2P)

Sugiere a qué precio publicar un anuncio en Binance P2P y arma el bloque para
copiar/pegar. **No publica nada** (el usuario no es merchant; automatizar la web
es ban). Solo lee datos públicos. CLI: `cli/prepare_ad.py`.

## Uso
```
python -m cli.prepare_ad --side vender --asset USDT --min 30000 --max 150000
python -m cli.prepare_ad --side comprar --asset USDT
```

## Qué devuelve
- Precio **competitivo** (supera al mejor rival por 1 tick).
- Precio **por margen** sobre tu costo promedio (de `trades.db`; solo lado vender).
- Precio **sugerido** = `max(competitivo, piso de margen)` en el lado vender.
- Referencia **CriptoYa** (mejor bid/ask de tu whitelist local): informativa al
  vender; al comprar actúa como **techo** (no pagar por encima del mercado).
- Bloque de anuncio listo para pegar.

## Reglas
- Solo lectura pública: no toca API privada, no postea, no automatiza la web.
- Circuit breaker: precios fuera de `[PRICE_FLOOR_ARS, PRICE_CEIL_ARS]` se descartan.
- 403 al traer rivales = bloqueo de IP de datacenter; correr desde IP residencial.

## Fases siguientes (no implementadas)
- Fase 3: entrega por Telegram.

## Tests
`python -m pytest tests/test_pricing.py tests/test_prepare_ad.py -q`
