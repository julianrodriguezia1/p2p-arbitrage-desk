# Investigación a fondo: arbitraje triangular CROSS-exchange

> Buscar ciclos de 3 patas combinando pares de **distintos exchanges** (comprar
> en uno, convertir en otro, cerrar en un tercero). Primero: qué exchanges tienen
> API pública usable; después: cómo es el método, sus fricciones y si es viable.
> Fecha: 2026-06-20.

---

## 1. Antes que nada: aclaración del concepto

"Triangular entre distintos exchanges" mezcla dos ideas que conviene separar,
porque tienen fricciones muy distintas:

- **Triangular puro (intra-exchange):** las 3 patas en un mismo lugar, sin mover
  fondos. (Ver `investigacion-triangular-cripto-cripto.md`.)
- **Cross-exchange (2 patas):** misma moneda, comprar barato en A / vender caro
  en B. Es lo que tu dashboard ya hace conceptualmente para ARS. Requiere
  **transferir** o tener saldo en ambos.
- **Triangular CROSS-exchange (lo que pediste):** el ciclo de 3 patas **cruza
  venues**. Ej:
  ```
  Exchange A:  USDT → BTC      (comprás BTC con USDT en A)
  Exchange B:  BTC  → ETH      (convertís en B, donde ETH/BTC rinde más)
  Exchange C:  ETH  → USDT     (cerrás en C, el que mejor paga)
  ```
  Aprovecha que la **misma relación entre dos monedas (cross-rate) cotiza
  distinto en distintos lugares**. El spread cross-exchange suele ser **más grande
  y dura más** que el intra-exchange (justamente porque mover capital entre venues
  es difícil). Ese mismo "difícil" es la fricción que hay que vencer.

**Insight central:** ejecutar esto transfiriendo en cada pata es inviable
(minutos de blockchain + fee de retiro por pata). Los que lo hacen de verdad
mantienen **inventario pre-fondeado en cada exchange** y ejecutan las patas
**en paralelo contra los saldos que ya tienen**; las transferencias se hacen
**cada tanto, para rebalancear**, no en cada operación. Eso cambia toda la
economía (y es la diferencia entre "teórico" y "ejecutable").

---

## 1.bis — El P2P como pata de la triangulación (TU edge real)

La investigación de arriba está armada sobre **orderbooks spot**. Pero vos operás
**P2P** y sos (o vas a ser) **merchant**: ahí tenés una ventaja que un arbitrajista
spot no tiene. El P2P puede ser **una de las 3 patas del ciclo**, sobre todo las
que tocan **ARS**:

```
ARS  → USDT   (comprás USDT barato en P2P)      ← pata P2P
USDT → BTC    (spot, en el exchange más conveniente)
BTC  → ARS    (vendés BTC caro en P2P)          ← pata P2P
```

o mezclando un cross-rate cripto en el medio. El P2P entra al **mismo grafo** que
los pares spot, solo que la arista P2P tiene propiedades distintas:

| Dimensión | Pata spot (orderbook) | Pata P2P |
|---|---|---|
| Precio | bid/ask del libro | mejor aviso P2P (ya lo bajás de CriptoYa: `binancep2p`, etc. y de tu `/api/p2p/cheapest`) |
| "Fee" | taker % | **el spread del aviso** (no es un % fijo) + comisión merchant si aplica |
| Velocidad | ms | **minutos** (transferencia bancaria + confirmación) |
| Atomicidad | casi atómica | **no atómica** — y rige la regla: **nunca liberar sin acreditación** |
| Tu rol | tomador de precio | **podés ser maker**: poné el aviso y que vengan a vos |

**Por qué importa:**
- Las patas **ARS↔cripto** del triángulo, para vos, **son P2P** — no spot. Tu
  dashboard ya mezcla precios P2P y CEX, así que **la data ya está medio
  integrada**.
- Como **merchant** no solo *tomás* el spread: lo *ponés*. Eso cambia el juego —
  en vez de cazar una ineficiencia de milisegundos, **vos creás la pata** a tu
  precio y esperás. El "arbitraje" se vuelve **market-making con cobertura**:
  publicás compra de USDT barato en P2P y, cuando te entra, cerrás el ciclo en
  spot/otro P2P.
- El cuello de botella deja de ser la **latencia** (donde perdés contra bots) y
  pasa a ser el **timing bancario y el riesgo de contraparte** (donde tu
  experiencia P2P es la ventaja).

**Implicancia para el detector:** el grafo no es solo spot multi-exchange; tiene
que incluir **nodos/aristas P2P para ARS** (y eventualmente otros fiat). La pata
P2P se modela con su precio real (el del aviso, ya filtrado de fantasmas y de
quotes viejos) y con un **haircut por no-atomicidad** mayor que el de spot. Esto
conecta directo con el otro documento, el del **rulo cambiario**
(`investigacion-arbitraje-triangular.md`): en la práctica, **tu triangulación más
rentable probablemente tenga 1–2 patas P2P en ARS y 1 pata cripto-cripto en
spot**, no las 3 en orderbook.

---

## 2. Exchanges con API pública + endpoint de "todos los tickers" en una llamada

Todos estos tienen **market-data público (sin login)** y un endpoint que devuelve
el mejor bid/ask de **todos los pares spot de una sola vez** — justo lo que
necesitás para armar el grafo multi-exchange:

| Exchange | Endpoint "todos los tickers" | Pares spot aprox. | Notas |
|---|---|---|---|
| **Binance** | `GET /api/v3/ticker/bookTicker` (sin symbol) | ~3.000 | El más líquido. CORS browser OK (ya lo usás). |
| **Bybit** | `GET /v5/market/tickers?category=spot` | ~1.000+ | bid1Price/ask1Price. Ya tenés key read-only. |
| **OKX** | `GET /api/v5/market/tickers?instType=SPOT` | ~505 | bidPx/askPx. |
| **Bitget** | `GET /api/v2/spot/market/tickers` | ~800+ | bidPr/askPr. |
| **MEXC** | `GET /api/v3/ticker/bookTicker` | ~2.400+ | API spot **clon de Binance**. Muchos pares exóticos. |
| **KuCoin** | `GET /api/v1/market/allTickers` | ~1.300 | buy/sell. |
| **Gate.io** | `GET /api/v4/spot/tickers` | ~2.500+ | highest_bid/lowest_ask. |
| **HTX (Huobi)** | `GET /market/tickers` | ~900 | bid/ask. |

### El atajo: CCXT
[CCXT](https://github.com/ccxt/ccxt) es una librería (Python/JS) que unifica
**100+ exchanges** detrás de una sola interfaz. `exchange.fetch_tickers()` o
`fetch_bids_asks()` te devuelve todos los pares con bid/ask normalizado, sin que
tengas que parsear el formato de cada uno. **Para un proyecto multi-exchange es
el camino sano** (en vez de escribir 8 fetchers a mano). Tu repo ya es Python.

---

## 3. Dos fricciones que en cross-exchange son DECISIVAS

### a) Geobloqueo y CORS (clave para tu arquitectura)
- Binance bookTicker anda desde el navegador (CORS abierto). **El resto NO
  garantiza CORS** → un fetcher multi-exchange **client-side se va a romper** por
  CORS en varios.
- Además, desde tu **VPS** algunos exchanges responden **451** (geobloqueo), como
  ya viste con la API privada de Binance/Bybit.
- **Conclusión de arquitectura:** el barrido multi-exchange conviene hacerlo
  **server-side**, y muy probablemente desde el **"compañero de sync"** (tu PC,
  IP residencial) que ya planeaste para esquivar el 451 — no desde el VPS ni
  desde el HTML. Esto reusa infra que ya está en el roadmap.

### b) Transferencias vs inventario pre-fondeado
| Modelo | Cómo | Costo | Para vos |
|---|---|---|---|
| Transferir por operación | retirás/depositás en cada pata | fee de red + 1–30 min de confirmaciones por pata → **mata el arb rápido** | inviable para triangular |
| **Inventario pre-fondeado** | tenés saldo en los 3 venues, ejecutás en paralelo, rebalanceás cada tanto | capital inmovilizado en varios exchanges + riesgo de inventario + costo de rebalanceo periódico | **el único realista**, pero exige capital repartido y disciplina |

---

## 4. El método (matemática + detección)

Igual que el triangular puro, pero el grafo ahora tiene **aristas etiquetadas por
exchange**:

- **Nodos:** monedas (USDT, BTC, ETH, SOL, …).
- **Aristas de trade:** una por cada par **en cada exchange** (peso `−ln(tasa
  neta de fee de ESE exchange)`). El fee taker varía por venue.
- **(Opcional) Aristas de transferencia:** moneda X de exchange A → exchange B,
  con peso = fee de red. Solo si modelás el caso "con transferencia".
- **Detección:** **Bellman-Ford** sobre el grafo → ciclos de producto `>1` (peso
  negativo). Los ciclos que mezclan aristas de distintos exchanges son tus
  triangulaciones cross-exchange.

**Forma simple y mostrable (sin grafo):** para cada par de monedas (X,Y), comparás
la **tasa directa** `X/Y` de cada exchange contra la **tasa sintética** vía un
puente (USDT): `X/USDT ÷ Y/USDT` tomada de otro exchange. Cuando difieren más que
los fees combinados, hay ciclo. Es el caso de 3 patas escrito como comparación de
cross-rates.

**Umbral a batir:** suma de los fees taker de las 3 patas (pueden ser de 3
exchanges distintos, ej. 0,1% + 0,1% + 0,1% = 0,3%) **+** colchón por slippage y
por el desfase temporal de ejecutar en venues distintos.

---

## 5. Rentabilidad real (lo honesto)

- Los spreads **cross-exchange son más grandes y persistentes** que los
  intra-exchange, porque el capital no fluye libre entre venues. **Esa es la buena
  noticia.**
- La mala: ese spread existe **porque mover el capital cuesta**. Si transferís por
  operación, el fee de red + tiempo se comen el edge y te exponen a que el precio
  cambie. Si pre-fondeás, inmovilizás capital en N exchanges y cargás riesgo de
  inventario.
- En 2025 el arbitraje cripto está **dominado por automatización**; la
  rentabilidad consistente depende de software/bots que simulan el resultado
  post-fee y disparan solo con margen de seguridad.
- Los pares con spreads jugosos suelen ser **exóticos/ilíquidos** (MEXC, Gate
  tienen miles): ahí el cuello de botella es **profundidad** (no movés volumen) y
  **riesgo de retiro** (a veces el exchange chico te traba el withdrawal).

**Veredicto:** como **monitor multi-exchange** que te muestra dónde están las
desalineaciones de cross-rate netas de fee, **es valioso y factible**. Como
**ejecutor automático rentable**, requiere inventario pre-fondeado en varios
venues + bot + gestión de riesgo — un proyecto serio, no un script. Y siempre con
la regla del proyecto: **detecta/alerta, no opera solo**.

---

## 6. Si en algún momento se construye (boceto, NO ahora)

- **Fetcher multi-exchange server-side vía CCXT**, corriendo en el compañero
  residencial (esquiva 451/CORS), refrescando `fetch_tickers()` de N exchanges.
- **Normalización** de símbolos (cada exchange nombra distinto; CCXT ayuda).
- **Filtros heredados:** whitelist/blacklist, fantasmas (±6% de la mediana),
  **obsolescencia** (el filtro de `time` que pusimos por DAI/Lemon), y un
  **filtro de profundidad** (caminar orderbook de los candidatos).
- **Detector:** matriz de cross-rates + Bellman-Ford; salida = ciclos netos de
  fee, marcando para cada uno qué venues toca y si necesita transferencia o se
  ejecuta contra inventario.
- **Modo monitor** primero; ejecución, mucho después y con topes de tamaño por
  profundidad.

---

## 7. Fuentes

- [CCXT — librería unificada de 100+ exchanges (fetch_tickers / fetch_bids_asks)](https://github.com/ccxt/ccxt)
- [Bybit v5 — Get Tickers (`/v5/market/tickers?category=spot`)](https://bybit-exchange.github.io/docs/v5/market/tickers)
- [OKX v5 — Market Tickers (`/api/v5/market/tickers?instType=SPOT`)](https://www.okx.com/docs-v5/en/)
- [Binance Spot API — Market Data (bookTicker, exchangeInfo, depth)](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints)
- [HyroTrader — Crypto Triangular Arbitrage (3-way inefficiencies, cross-rate)](https://www.hyrotrader.com/blog/crypto-triangular-arbitrage/)
- [Cross-Exchange Arbitrage in Crypto: How It Works (inventory, rebalancing)](https://cryptotrade.wiki/en/articles/cross-exchange-arbitrage-platforms)
- [Empirical Analysis of Indirect Internal Conversions in Cryptocurrency Exchanges — arXiv](https://arxiv.org/pdf/2002.12274)
- [Wish or reality? On the exploitability of triangular arbitrage — ScienceDirect (2024)](https://www.sciencedirect.com/science/article/pii/S154461232401537X)
