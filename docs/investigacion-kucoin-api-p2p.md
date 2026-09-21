# Investigación: ¿API de KuCoin para historial P2P? (para armar `sync_kucoin`)

_Consultado 2026-07-13. Fuentes oficiales de KuCoin cruzadas en ≥2 páginas._

## Resumen ejecutivo
- **CONFIRMADO: la API oficial de KuCoin NO expone el historial de órdenes P2P / Fast Trade / OTC / Fiat.** No hay ningún endpoint REST autenticado que devuelva tus compras/ventas P2P con contraparte, precio ARS y monto. `Sólido`.
- La API cubre solo **spot / margin / futures / earn / convert / transfer / withdrawal**. Ninguna sección P2P/OTC/Fiat/C2C en la navegación de la doc. `Sólido`.
- **No hay scope de API key para P2P.** Los permisos disponibles son General, Spot, Margin, Futures, Earn, Withdrawal, FlexTransfers, Unified, LeadtradeFutures. `Sólido`.
- **No hay `bizType` de P2P en ningún ledger** (clásico, unified, trade_hf): los enums son cerrados y ninguno incluye P2P/OTC/Fiat. `Sólido`.
- La cuenta P2P (Main/Funding) **ni siquiera es un `accountType` direccionable** en la API de transferencias (`MAIN, TRADE, CONTRACT, MARGIN, ISOLATED, MARGIN_V2, ISOLATED_V2, UNIFIED`). `Sólido`.
- Reconstruir la operación por API (detectar solo el neto de USDT que entra/sale de Main vía `TRANSFER`) es teóricamente posible pero **no trae precio ni contraparte** → inútil para registro con precio real. `Probable`.

**Conclusión: no se puede armar un `sync_kucoin` como el de Binance/Bybit.** KuCoin se queda en carga por captura, igual que OKX.

## Hallazgos

### 1. No existe endpoint de historial P2P
La navegación de la doc nueva (`docs-new`) lista: Spot, Margin, Futures, Earn, Copy Trading, Convert, VIP Lending, Affiliate, Broker, Web3 Wallet. **Nada de P2P/OTC/Fiat/Fast Buy.** Los "Get Order History" que aparecen son de spot y futures (fills de orderbook cripto, sin contraparte fiat). El Broker "Fast API" es OAuth para conectar cuentas, tampoco lee P2P. El SDK oficial `python-kucoin` no tiene métodos P2P/fiat (lo único "fiat" es `get_fiat_prices()`, cotización de conversión, no historial).
- https://www.kucoin.com/docs-new/introduction
- https://www.kucoin.com/api
- https://github.com/Kucoin/kucoin-python-sdk

### 2. Permisos de API key y rate limits
Permiso para leer read-only = **General** (consulta cuenta/órdenes, no opera ni retira, sin IP whitelist, **no expira**). No hay permiso P2P.
Rate limit por "weight" sobre un pool que resetea cada 30s; VIP0 = 4000 de cupo spot/30s (de sobra). 429 code 429000 al agotar.
- https://www.kucoin.com/docs-new/introduction
- https://www.kucoin.com/support/360015102174 (actualizado 17/12/2025)
- https://www.kucoin.com/docs-new/rate-limit

### 3. El ledger no etiqueta P2P
Tres ledgers independientes con enum `bizType` cerrado, ninguno con P2P/OTC/Fiat:
- Spot/Margin `GET /api/v1/accounts/ledgers`: lo más cercano es `Buy Crypto`/`Sell Crypto` (= pasarela de **tarjeta**, no P2P) e `Instant Exchange` (convert on-exchange).
- Unified `GET /api/ua/v1/account/ledger` y Trade_hf `GET /api/v1/hf/accounts/ledgers`: sin P2P.
- https://www.kucoin.com/docs-new/rest/account-info/account-funding/get-account-ledgers-spot-margin

## Incógnitas
- No está documentado bajo qué `bizType` (si alguno) aterriza el *fill* P2P en la Main account. Solo se cerraría empíricamente: hacer una compra P2P chica y leer `GET /api/v1/accounts/ledgers?currency=USDT` de MAIN. Aun así no traería precio ARS ni contraparte.

## Recomendación
1. **KuCoin sigue por captura** (skill `cargar-captura`), como ya hacemos. Es el camino correcto y confiable.
2. No invertir en un `sync_kucoin` por API: la data que necesitamos (precio real, contraparte) no existe por esa vía.
3. Si algún día KuCoin permite **export CSV** del panel P2P web, ese sí sería un buen input para un importador batch (a evaluar).
