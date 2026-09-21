# Investigación: ¿es REALMENTE rentable el arbitraje triangular con criptos?

> Pregunta: escuché que hay maneras de hacer arbitraje rentable con
> triangulaciones entre distintas criptomonedas. ¿Es verdad, y cómo?
> Hecho con el skill `deep-research` (fuentes primarias + caso real + cruce).
> Fecha: 2026-06-22.

---

## Resumen ejecutivo

- **Sí existen oportunidades de triangular, pero el margen NETO es minúsculo y se
  lo llevan los más rápidos.** En estudios sobre datos reales, ~95% de los
  triángulos dan ganancia *bruta*, pero el retorno **neto promedio es ~0,09%**
  (9,3 puntos básicos) — y para un trader **sin VIP, casi todas desaparecen tras
  fees**. `Sólido`
- **Duran segundos o menos:** ~65% de las oportunidades viven **≤1 segundo**.
  Ganarlas es una carrera de latencia contra bots institucionales. `Sólido`
- **Caso real, no teoría:** un dev corrió un bot triangular en Binance **69 horas
  reales** y ganó… **US$ 0,13** (ejecutó 1 de 156 oportunidades). En *testnet*
  (mercado simulado) el mismo bot "ganaba" US$ 60.000 — la diferencia es toda la
  historia. `Sólido`
- **Para vos (merchant P2P en ARS), el triangular puro cripto-cripto NO es tu
  juego:** perdés la carrera de milisegundos contra HFT. Tu ventaja real está en
  las patas **P2P/ARS**, donde la lentitud es la barrera (y vos podés ser
  *maker*). `Probable`
- **Fee killer:** el umbral a vencer son los 3 fees juntos. **MEXC (0% spot)** es
  el único que casi lo anula; **Bybit NO es 0%** (es 0,1%, era un mito). `Sólido`

---

## Hallazgos

### 1. La evidencia académica: rentable en bruto, marginal en neto  `Sólido`
Estudios sobre datos reales de exchanges:
- En un set analizado, los triángulos fueron rentables el **94,97%** de las veces,
  pero con un **retorno neto equiponderado de solo 9,3 puntos básicos (~0,093%)**.
- **El acceso al fee tier lo cambia todo:** para un **VIP 9** quedaban **150
  oportunidades** por encima de los costos; para un **inversor común, solo 18**.
- La mayoría de las oportunidades ofrecían entre **0% y 0,025% bruto**, y **al
  meter los fees reales, se eliminaban**.
- En una semana se detectaron **4.879 oportunidades** potenciales, casi todas
  marginales.
- **Duración:** ~**65% duran ≤1 segundo**; solo **15,72% más de 5 segundos**. La
  ventana es de segundos o menos.

Fuentes: [Wish or reality? On the exploitability of triangular arbitrage in cryptocurrency markets — ScienceDirect (2024)](https://www.sciencedirect.com/science/article/pii/S154461232401537X) · [Empirical Analysis of Indirect Internal Conversions in Cryptocurrency Exchanges — arXiv (2020)](https://arxiv.org/pdf/2002.12274) · [Crypto Triangular Arbitrage — HyroTrader](https://www.hyrotrader.com/blog/crypto-triangular-arbitrage/)

### 2. El caso real que vale por mil teorías: el bot "Harjus"  `Sólido`
Un desarrollador documentó honestamente su bot triangular para Binance
([Shuffling Bytes, 2023](https://shufflingbytes.com/posts/binance-triangular-arbitrage/)):

| Métrica | Testnet (48 h) | **Producción real (69 h)** |
|---|---|---|
| Ganancia | US$ 60.000 | **US$ 0,13** |
| Oportunidades detectadas | 31 | 156 |
| Ejecutadas con éxito | 30 (~97%) | **1 (0,64%)** |
| Ganancia teórica (si agarraba todas) | — | US$ 176,35 |
| Extrapolado mensual | — | ~US$ 1.840 |

- Fee del autor: **0,075%**; el de un **VIP: 0,01725%** → arranca en desventaja.
- **>99% de las oportunidades no se pudieron capturar** por latencia: cuando
  mandaba la orden, ya estaba tomada o cancelada — "hay alguien más rápido".
- Frase clave del autor: *"las oportunidades que yo veo son apenas las sobras que
  los tiburones no llegaron a agarrar"*. Tras 1.300+ commits de optimización su
  conclusión fue que **es muy difícil** sacarle ganancia a la estrategia
  liquidez-taker más simple en el exchange más líquido.

> **Lección:** todo número lindo de triangular que veas suele venir de **backtest
> o testnet** (sin competencia ni latencia real). En vivo, contra HFT, el edge se
> evapora. La brecha 60.000 → 0,13 es exactamente eso.

### 3. Bots open-source: detectar es fácil, ejecutar funde  `Sólido`
- **[Drakkar-Software/Triangular-Arbitrage (OctoBot)](https://github.com/Drakkar-Software/Triangular-Arbitrage)**
  (127★, actualizado jun-2026): en **Python sobre `ccxt`**, detecta ciclos
  **multi-activo** (no solo 3 patas) en Binance, Hyperliquid y 15+ exchanges.
  **Es solo DETECTOR**, y avisa explícito: *"los resultados NO consideran los fees
  durante los trades, lo que puede impactar significativamente la performance"*.
  Su ejemplo muestra un **2,33%** … pero es un ciclo de **7 patas** (DOGE→USDT→
  ETH→ADA→USDC→SOL→BTC) y **antes de fees** → inejecutable en la práctica.
- **[bmino/binance-triangle-arbitrage](https://github.com/bmino/binance-triangle-arbitrage)**
  (1.167★): el más completo como referencia — WebSocket, recalcula por ciclo, y
  **trackea la edad de cada ticker** para descartar viejos (lo que ya aplicamos
  con el filtro de obsolescencia).
- **mfaxyz** (KuCoin): enumeración con profundidad, **avisa que la ejecución está
  rota y perdés plata**.
- **[Hummingbot](https://github.com/hummingbot/hummingbot)** (18,9k★): el serio
  para cross-exchange, con inventario en ambos venues.
- Capa común a todos: **[CCXT](https://github.com/ccxt/ccxt)** (43k★).

**Patrón a copiar:** enumerar ciclos una vez → recalcular por tick → descartar
tickers viejos → profit **neto de fees** con margen de seguridad → sizing por
profundidad. **Conclusión unánime: la detección es el 80% fácil; la ejecución es
el 20% que funde** (no-atómica, fills parciales, latencia).

### 4. Fees de trading y el umbral a vencer  `Sólido`
El triángulo tiene que dejar **más que la suma de los 3 fees**:

| Exchange | Maker/Taker spot | Umbral del ciclo (×3) |
|---|---|---|
| **MEXC** | **0% / 0–0,05%** ⭐ | **~0%** |
| Binance | 0,1% / 0,1% (0,075% c/BNB) | 0,3% (0,225% c/BNB) |
| **Bybit** | **0,1% / 0,1%** (no es 0%) | 0,3% |
| OKX | 0,08% / 0,1% | ~0,28% |
| KuCoin / Bitget | 0,1% / 0,1% | 0,3% |
| Gate / HTX | ~0,2% / ~0,2% | ~0,6% |

→ Por eso **MEXC** es el más atractivo *en teoría* para triangular (umbral ~0),
pero lo paga con **menos liquidez y más riesgo en pares chicos**. `Sólido`

### 5. Fees de retiro y redes sin costo (lo de "atmos/atma")  `Probable`
- **Transferencias internas = GRATIS** (entre cuentas del mismo exchange; Bybit lo
  confirma oficialmente). Sirven para rebalancear sin tocar blockchain. `Sólido`
- **Sí hay monedas/redes con retiro 0:** Bybit lista **512 monedas en 87 cadenas**
  con "fee de retiro más bajo = **Free**". O sea, existen redes sin costo — **pero
  no pude confirmar puntualmente que Aptos o Cosmos sean las gratis** en Bybit hoy
  (hay que mirar la página de retiros en vivo o `fetch_deposit_withdraw_fees`).
  `Incierto`
- Referencia on-chain: **USDT TRC20 ≈ 1 USDT**, **ERC20 ≈ 10 USDT**. Como el fee
  es **fijo**, en montos chicos se come todo → de nuevo, el modelo realista
  cross-exchange es **inventario pre-fondeado**, no transferir por operación.
  `Sólido`

Fuentes: [Bybit — FAQ retiros on-chain](https://www.bybit.com/en/help-center/article/FAQ-Crypto-Withdrawal) · [Bybit withdrawal fees — WithdrawalFees.com (2026)](https://withdrawalfees.com/exchanges/bybit)

---

## Contradicciones e incógnitas

- **Testnet vs real:** la misma estrategia "rinde" US$ 60.000 simulada y US$ 0,13
  real. Cualquier promesa de rentabilidad sin aclarar si es backtest/testnet hay
  que descartarla.
- **Blogs vs evidencia:** muchísimo blog ("ganá con triangular arbitrage", bots
  comerciales) vende la estrategia; la evidencia académica y los reportes reales
  dicen que el neto es marginal y va a los más rápidos. Tratá esos blogs como
  marketing.
- **El "2,33%" del detector OctoBot** es pre-fee y de un ciclo de 7 patas →
  ilustra el método, no una ganancia real.
- **Incógnita abierta:** qué red exacta tiene retiro 0 en Bybit (tu "atmos/atma")
  — se confirma solo con la data de retiros en vivo.

---

## Recomendación para tu caso

1. **Como ejecutor cripto-cripto puro: no.** Perdés la carrera de milisegundos
   contra HFT institucional. El caso Harjus (US$ 0,13 en 69 h) es la prueba.
2. **Como monitor/radar: sí vale** — barato de hacer, educativo, y caza los
   *outliers* en pares exóticos o picos de volatilidad. Reusá el patrón de
   bmino/OctoBot (ccxt + enumeración + edad de ticker + neto de fees).
3. **Tu verdadero edge es el P2P/ARS:** ahí la barrera es la lentitud y el riesgo
   de contraparte (no la latencia), y **podés ser maker**. La triangulación que a
   vos te puede rendir mezcla **1–2 patas P2P en ARS + 1 cripto-cripto en spot**
   (ver `investigacion-arbitraje-triangular.md` y el rulo cambiario), no las 3 en
   orderbook.
4. **Si hacés el monitor:** usá **MEXC** (umbral de fee ~0) para que aparezcan más
   candidatos, traé los **fees de retiro por red en vivo** (CCXT) para elegir la
   red gratis/barata, y mantené el **filtro de obsolescencia** que ya tenemos.

---

## Fuentes

- [Wish or reality? On the exploitability of triangular arbitrage in cryptocurrency markets — ScienceDirect (2024)](https://www.sciencedirect.com/science/article/pii/S154461232401537X)
- [Empirical Analysis of Indirect Internal Conversions in Cryptocurrency Exchanges — arXiv (2020)](https://arxiv.org/pdf/2002.12274)
- [Who are the arbitrageurs? Evidence from Mt. Gox — arXiv (2021)](https://arxiv.org/pdf/2109.10958)
- [Harjus: Triangular Arbitrage Bot for Binance — Shuffling Bytes (caso real, 2023)](https://shufflingbytes.com/posts/binance-triangular-arbitrage/)
- [Drakkar-Software/Triangular-Arbitrage (OctoBot, detector ccxt)](https://github.com/Drakkar-Software/Triangular-Arbitrage)
- [bmino/binance-triangle-arbitrage](https://github.com/bmino/binance-triangle-arbitrage)
- [Hummingbot](https://github.com/hummingbot/hummingbot) · [CCXT](https://github.com/ccxt/ccxt)
- [Crypto Triangular Arbitrage — HyroTrader](https://www.hyrotrader.com/blog/crypto-triangular-arbitrage/)
- [Bybit — FAQ retiros on-chain](https://www.bybit.com/en/help-center/article/FAQ-Crypto-Withdrawal) · [Bybit withdrawal fees 2026 — WithdrawalFees.com](https://withdrawalfees.com/exchanges/bybit)
