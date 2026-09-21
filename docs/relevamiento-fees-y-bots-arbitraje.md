# Relevamiento: fees/retiros por exchange + bots de arbitraje existentes

> Dos cosas: (1) fees de trading y de retiro por exchange (con foco en los de
> 0%), y (2) qué proyectos de bots de arbitraje ya existen y cómo lo hacen, para
> copiar el método. Fecha: 2026-06-20.
>
> **Importante:** los fees cambian por tier de volumen y por promos. La tabla de
> abajo es **baseline de referencia** — la fuente de verdad es **traerlos en vivo
> por API** (sección 3). No hardcodear.

---

## 1. Fees de TRADING spot (baseline de referencia, tier 0 / sin VIP)

| Exchange | Maker | Taker | ¿0%? | Notas |
|---|---|---|---|---|
| **MEXC** | **0%** | **0%–0,05%** | **Sí** ⭐ | El campeón del 0% spot. Mucho par exótico. Ojo retiros y liquidez. |
| **Binance** | 0,10% | 0,10% | parcial | 0,075% pagando con BNB. Tuvo pares BTC zero-fee. |
| **Bybit** | 0,10% | 0,10% | **no (mito)** | **NO es 0% en general.** Hubo *promos* de spot sin fee en pares puntuales/períodos. El estándar es 0,1%. |
| **OKX** | 0,08% | 0,10% | no | Baja por tier. |
| **Bitget** | 0,10% | 0,10% | no | |
| **KuCoin** | 0,10% | 0,10% | no | Descuento con KCS. |
| **Gate.io** | ~0,20% | ~0,20% | no | De los más caros en tier 0; baja con GT/volumen. |
| **HTX** | ~0,20% | ~0,20% | no | |

> **Aclaración sobre Bybit (lo que disparó esto):** Bybit **no** cobra 0% por
> comprar/vender en spot de forma general. Lo que existe son **campañas
> promocionales** de "zero-fee spot" sobre pares elegidos y por tiempo limitado.
> El que sí tiene **0% estructural en spot** es **MEXC** (maker 0%, taker muy
> bajo o 0% según par/promo). Conviene **leer el fee en vivo por API** y no
> asumir.

**Por qué importa para triangular:** el umbral a batir = suma de los fees de las
3 patas. En un triángulo todo-MEXC el umbral puede ser **~0%**, contra ~0,3% en
Binance. Eso hace a MEXC atractivo *en teoría* — pero lo compensa con **menos
liquidez/profundidad** y **riesgo de retiro** en los pares chicos.

---

## 2. Fees de RETIRO / red (lo que mata el cross-exchange)

El retiro se cobra **por moneda y por red**, no por exchange en general. Valores
típicos (referencia, verificar en vivo):

| Moneda / red | Fee típico | Comentario |
|---|---|---|
| USDT **TRC20** (Tron) | ~1 USDT | **La más barata** para mover stablecoin entre exchanges. |
| USDT **ERC20** (Ethereum) | ~1–10 USDT | Depende del gas; evitar para montos chicos. |
| USDT **BSC/BEP20** | ~0,3–1 USDT | Barata, no todos los exchanges la soportan igual. |
| USDT Polygon/Arbitrum/Optimism | centavos | Baratísimas si ambos venues la soportan. |
| BTC on-chain | ~0,0001–0,0005 BTC | Caro en USD; usar solo para BTC real. |
| SOL / XRP / TRX nativas | centavos | Rápidas y baratas (útiles como "moneda puente" de transferencia). |

**Reglas para cross-exchange:**
- El fee de retiro **NO es por exchange: es por red**, y varía muchísimo. Hay
  redes con fee **0 o casi 0** (varias L2/L1 baratas, y promos de retiro sin fee
  en exchanges puntuales — Bybit tuvo redes/monedas con retiro gratis). **No
  asumir un número fijo:** bajar la tabla **por red en vivo** y dejar que el
  sistema **elija automáticamente la red más barata que compartan los dos
  venues**.
- **Transferencias internas** (entre cuentas del mismo exchange, o vía Binance
  Pay / Bybit internal transfer) suelen ser **gratis e instantáneas** — sirven
  para rebalancear sin tocar la blockchain cuando ambas puntas están en el mismo
  ecosistema.
- Como atajo razonable cuando hay que ir on-chain: **USDT TRC20** o una nativa
  barata (SOL/XRP/TRX), salvo que la tabla en vivo muestre una red con fee 0.
- El **fee de retiro es fijo** → en montos chicos se come todo. Por eso el modelo
  de **inventario pre-fondeado** (no transferir por operación) es el que cierra.
- Algunos exchanges chicos **traban retiros** (revisión manual, mínimos altos):
  riesgo operativo real, no solo costo.

> **Pendiente de confirmar:** el usuario mencionó una red en Bybit con retiro
> gratis ("atmos/atma" — posible **Aptos (APT)** o **Cosmos (ATOM)**). Verificar
> con `fetch_deposit_withdraw_fees` cuál red da fee 0 en cada venue antes de
> elegir ruta de transferencia.

---

## 3. Cómo traer los fees REALES en vivo (lo accionable)

No hardcodear: cada exchange expone fees por API. Y **CCXT lo unifica**.

| Exchange | Trading fee (API) | Withdraw fee (API) |
|---|---|---|
| Binance | `GET /sapi/v1/asset/tradeFee` (firmado) | `GET /sapi/v1/capital/config/getall` |
| Bybit v5 | `GET /v5/account/fee-rate` | `GET /v5/asset/coin/query-info` |
| OKX | `GET /api/v5/account/trade-fee` | `GET /api/v5/asset/currencies` |
| Bitget | endpoint de account fee | coin-info / withdraw config |
| MEXC | `GET /api/v3/tradeFee` (o 0 por defecto) | `GET /api/v3/capital/config/getall` |
| KuCoin | `GET /api/v1/trade-fees` | `GET /api/v1/withdrawals/quotas` |
| Gate.io | `GET /spot/fee` | `GET /wallet/withdraw_status` |

**Atajo CCXT (Python):**
```python
ex = ccxt.mexc()                 # o binance, bybit, okx, ...
ex.load_markets()
fees   = ex.fetch_trading_fees()           # maker/taker por símbolo
wfees  = ex.fetch_deposit_withdraw_fees()  # retiro por moneda/red
# o por mercado: ex.markets['ETH/USDT']['taker']
```
Para un **monitor** podés arrancar con el **default por exchange** (0,1% / 0% MEXC)
y refinar con los reales por API cuando haga falta. Los withdraw fees sí conviene
traerlos reales porque definen el cross-exchange.

---

## 4. Bots de arbitraje existentes — qué hacen y qué copiar

| Proyecto | ⭐ | Tipo | Qué tiene de bueno |
|---|---|---|---|
| **[bmino/binance-triangle-arbitrage](https://github.com/bmino/binance-triangle-arbitrage)** | 1.167 | Triangular intra-Binance (Node) | **La mejor referencia.** WebSocket de tickers, recalcula cada ciclo, HUD, **trackea la EDAD de cada ticker por pata** (descarta stale — valida nuestro filtro de obsolescencia), profit con fee configurable, asume fees en BNB. |
| **[Lakshmi-1212/TriangularArbitrageCryptos](https://github.com/Lakshmi-1212/TriangularArbitrageCryptos)** | 123 | Triangular (Python) | Método limpio en **4 pasos**: combos válidos → calcular → ejecutar simultáneo → bundle. Bueno para entender. |
| **mfaxyz/crypto-triangular-arbitrage-bot** | — | Triangular KuCoin (Python) | **Enumeración con profundidad** (camina el orderbook). **Avisa que la ejecución está rota y perdés plata** → lección: detectar es fácil, ejecutar es lo difícil. |
| **[Hummingbot](https://github.com/hummingbot/hummingbot)** | 18.9k | Framework HFT, 30+ exchanges | El serio para **cross-exchange**: market making cross-exchange, spot-perp arb, conectores a todos. Usa **inventario en ambos venues**. |
| **[CCXT](https://github.com/ccxt/ccxt)** | 43k | Librería de datos | La capa sobre la que se construye todo: tickers, fees, órdenes unificadas de 100+ exchanges. |

### El método que comparten (lo que conviene copiar)
1. **Datos:** para *monitor*, REST "todos los tickers" cada N seg alcanza. Para
   *ejecutar*, **WebSocket** de bookTicker (baja latencia).
2. **Enumerar los triángulos UNA vez** (grafo estático de pares) y **recalcular
   el profit en cada tick** — no re-enumerar.
3. **Edad del ticker por pata:** descartar si alguna pata está vieja (bmino lo
   hace explícito; nosotros ya lo aplicamos con el filtro de `time`).
4. **Profit neto de fees** y disparar solo con **margen de seguridad** sobre el
   umbral (fees + slippage).
5. **Sizing por profundidad:** caminar el orderbook para saber cuánto entra de
   verdad. Es lo que separa el juguete del bot real.
6. **Ejecución = el cuello de botella:** no es atómica; fills parciales y ticks
   en contra invierten el resultado. Todos los proyectos chicos fallan acá. →
   **Empezar en modo monitor** es la decisión correcta.
7. **Cross-exchange:** nadie lo hace transfiriendo por operación. Es **inventario
   pre-fondeado + rebalanceo** (modelo Hummingbot).

---

## 5. Conclusiones para nuestro caso

- **MEXC** es el único con **0% spot estructural** → el mejor candidato para
  triángulos donde el umbral de fee importa. Bybit **no** es 0% (era un mito/promo).
- En **cross-exchange**, el costo decisivo no es el trading fee sino el **retiro
  + el capital inmovilizado**: por eso el modelo realista es inventario en varios
  venues.
- **No hardcodear fees:** traerlos por API/CCXT (trading puede ir con default;
  retiros sí o sí reales).
- **Copiar de bmino:** enumeración estática + recálculo por tick + edad de ticker
  + profit neto. **Copiar de Hummingbot:** el modelo de inventario para
  cross-exchange. **Usar CCXT** como capa de datos/fees para no escribir 8
  fetchers.
- **Lección unánime de los repos:** la **detección es el 80% fácil**; la
  **ejecución es el 20% que funde** (no-atomicidad, slippage, fills parciales).
  Monitor primero.

---

## 6. Fuentes

- [CCXT — librería unificada (tickers, fees, órdenes)](https://github.com/ccxt/ccxt)
- [bmino/binance-triangle-arbitrage (1.167★, referencia triangular)](https://github.com/bmino/binance-triangle-arbitrage)
- [Lakshmi-1212/TriangularArbitrageCryptos (método en 4 pasos)](https://github.com/Lakshmi-1212/TriangularArbitrageCryptos)
- [Hummingbot (framework cross-exchange, 18.9k★)](https://github.com/hummingbot/hummingbot)
- [Binance — withdraw config (`/sapi/v1/capital/config/getall`) y tradeFee](https://developers.binance.com/docs/wallet/asset/trade-fee)
- [Bybit v5 — fee rate / coin info](https://bybit-exchange.github.io/docs/v5/market/tickers)
- [OKX v5 — trade-fee / currencies](https://www.okx.com/docs-v5/en/)
