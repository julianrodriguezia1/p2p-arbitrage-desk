---
name: estrategia-spread
description: Use when the user asks "¿qué hago?", "¿qué me conviene?", "dame la estrategia", "dónde gano más spread", "mejor jugada", or types /estrategia or /hago — da la mejor jugada de spread ahora (comprar/vender × tomar/publicar, cross-venue, neta de comisiones y fee de red).
---

# Estrategia de spread (la mejor jugada ahora)

Cuando el usuario pide la estrategia / "¿qué hago?" / "¿qué me conviene?" / `/estrategia` / `/hago`:

1. Pegá al endpoint del VPS (fuente única de verdad, mismo dato que usa el bot de Telegram):
   `curl -s "http://TU_VPS_IP:8002/api/estrategia?volume=1000"`
   (volumen configurable si el usuario lo pide; default 1000 USDT.)

2. Presentá el resultado en criollo, corto, con este molde:
   - **Headline:** `🚀 MEJOR AHORA — +X,XX% neto (~$ARS / 1000 USDT)` + la ruta
     "Comprá {modo} en {venue} @precio → vendé {modo} en {venue} @precio" + la etiqueta
     de la jugada (`media` = ⏳ esperás de un lado, `mm` = 🟠 market-making 2 puntas,
     `instant` = ⚡ instantáneo).
   - **Hasta 2 alternativas** (las otras jugadas), una línea cada una.
   - **Aviso** si viene `outside_note`: "⚠️ Ojo: {venue} paga {precio} (fuera de tu
     whitelist, verificá liquidez)".
   - NUNCA uses las palabras "ask"/"bid" en la respuesta (nomenclatura interna).

3. Si el VPS no responde (curl falla o timeout), avisá que no pudiste leer la estrategia
   ahora y ofrecé reintentar. No inventes números.

## Por qué cada jugada conviene (contexto para explicar si el usuario pregunta)

- **Publicar siempre da mejor precio que tomar** (comprás al bid / vendés al ask). Por eso
  el motor evalúa tomar vs publicar en cada punta.
- **Market-making intra-venue** (mm): publicás compra y venta en el mismo venue (ej. KuCoin)
  y te quedás con el spread interno, sin mover USDT (no paga fee de red).
- **Ruta cross-venue:** comprás barato en un lado y vendés caro en otro; paga fee de red
  por mover el USDT (ya descontado en el neto).
- Ver `docs/` para tácticas adicionales (arbitraje de método
  de pago, timing, multiactivo).
