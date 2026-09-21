# Spec: `bot/market_maker.py` (lo único grande que falta)

Market-making por **API oficial de merchant** (NO automatizar la web, es ban
seguro). Requiere ser merchant verificado + API key con permiso P2P.

`get_my_ads()` · `reprice_ad(ad_id, price)` · `cancel_ad(ad_id)` ·
`post_ad(side, price, min, max, methods)` + loop de reposicionamiento contra un
precio de referencia.

## Salvaguardas obligatorias

- API key SOLO con permiso de anuncios P2P. **NUNCA permiso de withdrawal.**
- Circuit breaker: precio mínimo y máximo hardcodeados, para que un bug no
  postee un precio absurdo.
- `--dry-run` primero, que loguee lo que haría sin ejecutar. No conectar a real
  hasta testear exhaustivo.
- Log de toda acción a SQLite.
- **NUNCA auto-liberar fondos.** El bot gestiona anuncios, no libera órdenes.
- Si publica BTC o alts, **el aviso va flotante** (ver "Regla de BTC" en
  `CLAUDE.md`).
