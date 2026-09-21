# Investigación: ¿Qué exchange argentino tiene el order book USDT/ARS más profundo y el spread más chico?

> Consulta de datos en vivo: **CriptoYa API, 2026-07-01 ~18:23 (-03)**, endpoint
> `https://criptoya.com/api/usdt/ars/{volumen}`. Cruzada con prensa 2026 y con el
> comportamiento observado a distintos volúmenes.

## Resumen ejecutivo

- **Spread más chico a volumen chico/medio (≤10k USDT): Binance P2P** (spread
  efectivo all-in ~0,58% hoy) y, entre CEX con order book, **Bitso Alpha**
  (~0,08% de punta a 1k, ~1,3% all-in con fees). `Sólido` (dato propio en vivo).
- **Order book más PROFUNDO para ARS = Binance P2P.** Es el único que aguanta el
  spread casi plano al escalar: ~0,58% a 1k → ~0,99% a 200k USDT. Todos los demás
  se abren feo a volumen grande. `Sólido`.
- **Trampa de la "profundidad" de Binance spot (convert):** figura con spread
  0,01% a 1k, pero es humo a volumen: salta a **2,0% a 100k y 2,48% a 200k**. Su
  order book USDT/ARS es fino. Lo mismo Bitso Alpha (0,08%→1,43% a 200k) y
  RipioExchange (0,17%→2,07% a 50k). `Sólido`.
- **Belo, Fiwind, Cocos, Let'sBit = cotización de conversión, NO order book.** El
  precio es "flat": no cambia con el volumen porque no hay libro; el spread está
  horneado en la cotización (Belo/Cocos 1,28%, Fiwind 0,9%). Para lotes grandes
  eso es una ventaja (precio garantizado) pero es peor spread que P2P. `Sólido`.
- **Los peores spreads all-in hoy: Lemon (3,8% P2P / 5,3% conversión),
  Decrypto (3,25%), SatoshiTango (2,84%), Ripio wallet (2,75%), Buenbit (2,51%).**
  `Sólido` (dato propio).
- **Pasada adversarial:** el "buen precio" de Binance P2P esconde tiempo y riesgo
  de contraparte (no es click-and-done); Lemon muestra buena punta pero cobra
  ~0,5–1,5% de spread oculto en el total; los CEX locales cobran fee además del
  spread de punta (Bitso/Ripio/Satoshi/Lemon 0,5%). `Sólido`.

---

## Datos en vivo — CriptoYa `usdt/ars/1000`, 2026-07-01

### Spread de PUNTA (bid/ask, sin fees) — 1.000 USDT

| Exchange | Bid | Ask | Spread punta |
|---|---|---|---|
| binance (spot/convert) | 1577,2 | 1577,3 | **0,01%** |
| bitsoalpha | 1560,3 | 1561,5 | 0,08% |
| ripioexchange | 1563,2 | 1565,3 | 0,17% |
| binancep2p | 1557,6 | 1566,1 | 0,55% |
| lemoncashp2p | 1555,3 | 1567,0 | 0,75% |
| fiwind | 1559 | 1573 | 0,90% |
| cocoscrypto | 1558 | 1578 | 1,28% |
| belo | 1558 | 1578 | 1,28% |
| satoshitango | 1557,6 | 1585,9 | 1,82% |
| ripio (wallet) | 1548,0 | 1582,7 | 2,24% |
| letsbit | 1546,3 | 1581,8 | 2,29% |
| buenbit | 1557,6 | 1593,5 | 2,30% |
| decrypto | 1549,4 | 1588,5 | 2,53% |
| lemoncash (conversión) | 1523,3 | 1588,2 | 4,26% |

### Spread EFECTIVO all-in (totalAsk vs totalBid, con fees) — lo que importa

Esto es lo que **pagás para comprar** vs **cobrás para vender**, ya con comisión:

| Exchange | Pagás (compra) | Cobrás (venta) | **Spread efectivo** |
|---|---|---|---|
| **binancep2p** | 1566,6 | 1557,6 | **0,58%** ✅ mejor |
| fiwind | 1573 | 1559 | 0,90% |
| ripioexchange | 1573,3 | 1555,4 | 1,15% |
| binance (convert) | 1578,5 | 1560,3 | 1,17% |
| belo | 1578 | 1558 | 1,28% |
| cocoscrypto | 1578 | 1558 | 1,28% |
| bitsoalpha | 1570,8 | 1550,9 | 1,28% |
| letsbit | 1581,8 | 1546,3 | 2,29% |
| buenbit | 1595,1 | 1556,1 | 2,51% |
| ripio (wallet) | 1582,7 | 1540,3 | 2,75% |
| satoshitango | 1593,8 | 1549,8 | 2,84% |
| decrypto | 1594,0 | 1543,9 | 3,25% |
| lemoncashp2p | 1590,5 | 1532,0 | 3,82% |
| lemoncash (conversión) | 1596,1 | 1515,6 | **5,31%** ❌ peor |

> Nota metodológica: en CriptoYa, `bid/ask` = punta del libro; `totalAsk/totalBid`
> = precio ya con la comisión del exchange. Lo confirmé con los datos: en
> Belo/Cocos/Fiwind/Let'sBit/BinanceP2P `bid=totalBid` y `ask=totalAsk` (0% de fee
> agregado → el costo está TODO en el spread de conversión), mientras que en
> Bitso/Ripio/Satoshi/Lemon/Decrypto hay un fee extra de 0,35–0,60% sobre la punta,
> y en Binance spot 0,08%/1,07%. `Sólido` (derivado del dato).

---

## Hallazgos por sub-pregunta

### 1. ¿Cuál tiene el order book USDT/ARS más profundo? — **Binance P2P**

Prueba de profundidad (cómo se abre el spread al subir el volumen):

| Volumen | Binance P2P | Bitso Alpha | Binance spot |
|---|---|---|---|
| 1.000 | 0,44% | 0,08% | 0,01% |
| 20.000 | 0,66% | 0,26% | 0,35% |
| 100.000 | 0,88% | 1,29% | 2,00% |
| 200.000 | **0,99%** | 1,43% | **2,48%** |

- **Binance P2P** es el único que mantiene el spread bajo control a lotes grandes
  (200k USDT ≈ 315M ARS y sigue en ~1%). Es la liquidez profunda de verdad para
  ARS. `Sólido` (dato propio en vivo).
- **Binance spot/convert y RipioExchange** tienen la punta más fina del mercado a
  volumen chico, pero su libro es delgado: a 50k–200k el spread explota. Su
  "0,01%" es engañoso para operar en serio. `Sólido`.
- **Bitso Alpha** aguanta razonable hasta ~20k, después se abre. Segundo mejor
  order book real. `Sólido`.

### 2. Order book real vs cotización de conversión

- **Order book real (el precio se mueve con el volumen):** Binance P2P, Binance
  spot, Bitso Alpha, RipioExchange, Buenbit. `Sólido` (dato) + prensa confirma que
  **Buenbit es el único wallet local con interfaz tipo CEX, órdenes límite y order
  book** ([CopyTradeInsider, 2026-05-19](https://www.copytradeinsider.com/blog/best-crypto-exchanges-argentina-2026/)).
- **Cotización de conversión (precio flat, sin libro):** Belo, Fiwind, Cocos,
  Let'sBit, y el modo "conversión" de Lemon/Ripio wallet. El precio no cambia con
  el volumen porque no hay libro; te dan un precio garantizado con el spread ya
  metido adentro. `Sólido` (dato: bid/ask idénticos a cualquier volumen).

### 3. Comparaciones concretas entre exchanges (hoy)

- Para **vender** USDT y cobrar más ARS: Binance P2P (1557,6) ≈ Fiwind (1559) ≈
  Bitso/Belo/Cocos (~1558) > Buenbit (1556) > Satoshi (1549,8) > Lemon (1532/1515).
- Para **comprar** USDT más barato: Binance P2P (1566,6) < Fiwind (1573) <
  RipioExchange (1573,3) < Belo/Cocos (1578) < Buenbit (1595)/Lemon (1590–1596).
- **Buenbit, pese a tener order book, hoy tiene spread all-in feo (2,51%)** porque
  su punta de compra está cara. Order book ≠ buen precio automáticamente. `Sólido`.

### 4. Reputación por liquidez/spread (prensa; Reddit no accesible)

- **Bitso**: reputación de "spreads bajos (~0,3%) y liquidez institucional",
  competitivo incluso fuera de horario ([Rankia, 2026-05-07](https://www.rankia.com.ar/blog/cripto/7064850-billeteras-criptomonedas-argentina-mas-usadas-como-elegir-ideal)).
  Coincide con mi dato: Bitso Alpha es de los mejores order books locales. `Probable`.
- **Lemon y Belo**: prensa los cita con "los spreads más ajustados (0,5–0,6%)"
  para conversión de consumidor ([CopyTradeInsider](https://www.copytradeinsider.com/blog/best-crypto-exchanges-argentina-2026/)).
  ⚠️ Esto CHOCA con mi dato en vivo (Lemon 3,8–5,3% all-in, Belo 1,28%). Ver
  Contradicciones. `Incierto`.
- **Comisiones citadas** ([Rankia](https://www.rankia.com.ar/blog/cripto/7064850-billeteras-criptomonedas-argentina-mas-usadas-como-elegir-ideal)):
  Bitso 0,3%, Ripio 0,8%, Lemon 1,2%, Belo <1%. `Probable`.

---

## Pasada adversarial — real vs humo

- **"Binance P2P tiene la mejor liquidez profunda" → cierto, PERO esconde tiempo y
  riesgo de contraparte.** No es click-and-done como un CEX: publicás/tomás un
  anuncio, esperás la transferencia bancaria, liberás manualmente. A lotes grandes
  se fracciona en varias contrapartes. El spread ~1% no incluye el costo de tu
  tiempo ni el riesgo de que te caiga plata "marcada" (bloqueo bancario AML/UIF, el
  riesgo real de la operatoria). El número es real; el "costo total" es mayor.
  `Sólido` (operatoria conocida + brief del proyecto).
- **Binance spot/convert "0,01%" es humo para volumen.** Sirve para montos
  chicos; a 100k+ es de los peores (2%+). `Sólido` (dato).
- **Lemon = spread oculto.** Muestra punta razonable pero el total te come 0,5%
  (P2P) a 1,5% (conversión) por encima, y en modo conversión el spread all-in es el
  PEOR del mercado (5,3%). Esto es la "maña Lemon" ya conocida: el total sale del
  monto redondo y la comisión ~1% no se ve en la captura. Fuente que confirma
  "spreads ocultos y límites de retiro" en Lemon:
  [usdt.com.ar](https://usdt.com.ar/blog/conviene-comprar-usdt-en-lemon-analizamos-comisiones-y-beneficios). `Sólido`.
- **Los "sin comisión" (Fiwind, Belo, Cocos) NO son gratis.** No cobran fee
  explícito porque la ganancia está en el spread de conversión (0,9–1,28%). Es un
  spread, no un regalo. `Sólido` (dato: fee=0% pero spread ancho).
- **Fees de retiro a ARS:** ninguna fuente accesible cuantificó un fee fijo de
  transferencia a CBU/CVU (la mayoría publicita "retiro sin costo"). El costo real
  de sacar a pesos está en el spread de venta, no en un cargo de retiro. Fiwind
  publicita 0 comisión de depósito/retiro. `Probable` (falta confirmar caso por
  caso en cada web oficial).

---

## Contradicciones e incógnitas

- **Lemon: prensa dice 0,5–0,6% de spread ajustado; mi dato en vivo dice
  3,8–5,3% all-in.** Probable explicación: la prensa mide la punta o un tier
  premium; CriptoYa mide el total real que cobra al usuario común (con la maña del
  redondo). Me quedo con el dato en vivo para operar. `Incierto` la cifra de prensa.
- **Reddit r/CryptoArgentina inaccesible** desde todas las herramientas de fetch
  (Reddit bloquea; firecrawl CLI no instalado). No pude traer citas textuales de
  traders. La reputación quedó apoyada solo en prensa 2026. `Incógnita`.
- **CriptoYa no documenta oficialmente** qué incluye `totalAsk/totalBid`; lo
  inferí empíricamente de los datos (ver nota metodológica). Sólido pero no oficial.
- **Un solo snapshot temporal (1 día).** El ranking de spread cambia hora a hora,
  sobre todo en P2P. La conclusión estructural (P2P = más profundo; conversión =
  flat; spot fino a volumen) es estable; el orden exacto del ranking no.

---

## Recomendación para tu operatoria

- **Volumen grande / arbitraje serio:** **Binance P2P** es tu order book más
  profundo para ARS y el mejor spread efectivo hoy. El costo es tiempo + riesgo de
  contraparte, ya contemplado en tu operatoria (nunca liberar sin plata acreditada).
- **Precio garantizado sin mover el mercado (lote grande, rápido):** conversión
  flat de **Fiwind (0,9%)** o **Belo/Cocos (1,28%)** — sabés el precio de antemano,
  no hay slippage, pero pagás el spread.
- **CEX con order book y punta fina para montos chicos:** **Bitso Alpha**; para
  micro-montos, Binance spot/RipioExchange (ojo: humo a volumen).
- **Evitá para vender caro:** Lemon (conversión), Decrypto, SatoshiTango, Ripio
  wallet, Buenbit — hoy tienen el peor spread all-in.
- Tu dashboard ya hace esto bien (precios depth-aware VWAP pisando CriptoYa): esta
  investigación confirma que el enfoque **depth-aware es el correcto**, porque la
  punta miente a volumen.

---

## Fuentes

- [CriptoYa API — usdt/ars](https://criptoya.com/api/usdt/ars/1000) (consulta 2026-07-01, dato primario)
- [CopyTradeInsider — Best Crypto Exchanges Argentina 2026](https://www.copytradeinsider.com/blog/best-crypto-exchanges-argentina-2026/) (2026-05-19)
- [Rankia — Billeteras cripto Argentina 2026](https://www.rankia.com.ar/blog/cripto/7064850-billeteras-criptomonedas-argentina-mas-usadas-como-elegir-ideal) (2026-05-07)
- [MiFinGuía — Buenbit vs Lemon vs Ripio](https://mifinguia.com/comparativas/buenbit-vs-lemon-cash-vs-ripio-argentina/) (2026-02-22)
- [usdt.com.ar — Comisiones reales de Lemon](https://usdt.com.ar/blog/conviene-comprar-usdt-en-lemon-analizamos-comisiones-y-beneficios)
- [Fiwind — Comisiones](https://www.fiwind.io/comisiones)
- [Dolarito — cotización cripto USDT hoy](https://www.dolarito.ar/cotizacion/cripto-usdt-hoy)
- Reddit r/CryptoArgentina: **no accesible** (bloqueo de fetch) — pendiente
