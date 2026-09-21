# Investigación a fondo: arbitraje triangular cripto-cripto (intra-exchange)

> Método puro: dentro de UN exchange, comprar y vender cruzando 3 pares cripto
> (ej. `USDT→BTC→ETH→USDT`) buscando que el ciclo deje ganancia. Monitorear todos
> los pares y detectar el ciclo rentable. Fecha: 2026-06-20.

---

## 1. La mecánica exacta

Tenés 3 monedas (A, B, C) y los 3 pares que las conectan. Hacés un **ciclo
cerrado** de 3 órdenes y volvés a la moneda inicial:

```
A → B → C → A      (ej: USDT → BTC → ETH → USDT)
```

Cada conversión usa la **mejor punta** del libro (comprás al `ask`, vendés al
`bid`) y paga **fee de trading**. La ganancia del ciclo es el producto de las 3
tasas netas:

```
ganancia = r(A→B) · r(B→C) · r(C→A)        ( >1 ⇒ ganás )
```

donde cada `r` ya descuenta el fee taker (`1 − f`, con f ≈ 0,1%).

### Ejemplo numérico (Binance, fee 0,1% por pata)
Supongamos:
- BTC/USDT ask = 60.000  → con 1.000 USDT comprás `1000/60000·(1−0.001) = 0,016650 BTC`
- ETH/BTC bid… (convertís BTC→ETH)
- ETH/USDT bid… (convertís ETH→USDT)

Si los 3 precios están perfectamente alineados, volvés con **998,5 USDT**: perdés
los **3 fees (≈0,3%)**. Para ganar, la **desalineación** entre los 3 pares tiene
que superar ese 0,3%. Ese es el punto central: **el umbral a batir no es 0, es la
suma de los 3 fees.**

> Hay 2 sentidos por triángulo: `A→B→C→A` y `A→C→B→A`. Si uno deja −0,4%, el
> inverso NO necesariamente deja +0,4% (los fees siempre restan en ambos). Hay
> que evaluar los dos.

---

## 2. Cómo se detecta (los dos algoritmos)

### Opción 1 — Enumeración de triángulos (lo práctico para empezar)
Elegís unas **monedas base/puente** (USDT, BTC, ETH, BNB) y enumerás todos los
triángulos que pasan por ellas. Para cada uno calculás el producto en los dos
sentidos y te quedás con los que superan el umbral de fees.

- **Pro:** simple, transparente, fácil de mostrar en una tabla ("comprá BTC con
  USDT, comprá ETH con BTC, vendé ETH por USDT → +X% neto"). Suficiente para un
  monitor.
- **Contra:** O(n²) sobre las monedas conectadas a cada base; está bien para
  cientos de pares, no para grafos enormes.

### Opción 2 — Grafo + Bellman-Ford (el método "canónico")
Modelás cada moneda como **nodo** y cada par como **arista dirigida** con peso
`w = −ln(tasa_neta)`. Un **ciclo de peso negativo** equivale a un producto de
tasas `>1`, o sea **arbitraje**. Bellman-Ford detecta ciclos negativos; Johnson
/ Floyd-Warshall si querés todos los pares.

- **Pro:** encuentra ciclos de **3, 4 o más patas** automáticamente, no solo
  triángulos. Es lo que usa la literatura (latencia de detección ~0,002 ms en
  implementaciones optimizadas, 92% de accuracy en datos históricos).
- **Contra:** más código; para "3 patas exactas" la enumeración alcanza y se
  explica mejor al usuario.

**Recomendación:** arrancar con **enumeración de triángulos** (claridad + tabla
mostrable) y dejar Bellman-Ford como evolución si querés ciclos de 4+.

> Tu tabla actual de spreads es el caso de **2 patas, misma moneda, contra ARS**.
> Esto es el de **3 patas cambiando de moneda cripto en el medio**. Misma familia
> de "buscar producto de tasas > 1", distinto grafo.

---

## 3. Los datos: qué le pedís a Binance (1 sola llamada)

- **Todos los precios de una:** `GET https://api.binance.com/api/v3/ticker/bookTicker`
  **sin parámetro `symbol`** devuelve el **mejor bid/ask de TODOS los pares**
  (~3.000 símbolos) en una sola respuesta. Es exactamente lo que necesitás para
  armar el grafo. (La COMPARTIR ya le pega a este endpoint con `?symbol=` para el
  spot de una moneda, así que **CORS desde el navegador ya sabemos que anda**.)
- **Qué pares existen y sus reglas:** `GET /api/v3/exchangeInfo` (lista de
  símbolos, baseAsset/quoteAsset, filtros de precio/lote, mínimos). Se baja **una
  vez** al cargar; con eso sabés qué aristas existen.
- **Frecuencia:** refrescás bookTicker cada N segundos (5–10s razonable para
  monitor). Ojo rate limits, pero una llamada all-symbols pesa por *weight* y es
  manejable.
- **Geobloqueo:** el endpoint es público; desde tu navegador (IP residencial)
  anda. Desde el VPS da 451 — por eso esto vive en el **HTML client-side**, no en
  el server.

---

## 4. Fees: el umbral real a batir

| Escenario | Fee por pata | Umbral del ciclo (×3) |
|---|---|---|
| Spot estándar | 0,100% | **0,300%** |
| Con descuento BNB (−25%) | 0,075% | **0,225%** |
| VIP / alto volumen | 0,02–0,06% | 0,06–0,18% |

El ciclo tiene que dejar **más** que ese umbral para ganar **un peso**. Y eso es
*antes* de slippage. Por eso casi todos los triángulos que vas a ver en majors
dan **levemente negativos**: el mercado ya descontó el fee.

---

## 5. Rentabilidad real (lo que dicen los estudios)

No te endulzo: la evidencia es consistente.

- Las oportunidades en majors rinden **0–0,025% bruto**; al meter fees,
  **se evaporan**. (ainvest, hyrotrader)
- Cuando aparece una viable, **dura 1–5 segundos** (a veces fracciones), y
  **solo el 20–30% más rápido** de los intentos de bots terminan rentables.
- **Profundidad/slippage:** el `bookTicker` es la **mejor punta**. Para volumen
  real caminás el libro y el precio empeora — los pares exóticos donde aparecen
  spreads grandes son justo los de **poca profundidad** (no podés mover tamaño).
- **Partial fills / no-atomicidad:** entre las 3 órdenes el precio se mueve;
  un fill parcial en la pata 2 te deja colgado con la moneda intermedia.
- **Co-location:** alquilar baja latencia cuesta USD 500–2.000/mes y suma
  USD 300–500 sobre cuentas de USD 50k — **antieconómico para retail**.
- El estudio académico *"Wish or reality? On the exploitability of triangular
  arbitrage in cryptocurrency markets"* (ScienceDirect, 2024) concluye que las
  oportunidades **existen pero son difíciles de explotar** una vez que metés
  costos de transacción y riesgo de ejecución.

**Conclusión honesta:** como **máquina de hacer plata por REST para retail, no**.
Como **monitor educativo + radar de pares exóticos/momentos de volatilidad, sí**
tiene valor. Donde realmente aparecen ciclos positivos netos: **pares ilíquidos
o recién listados, exchanges chicos, y picos de volatilidad** — y ahí el cuello
de botella pasa a ser la profundidad y la velocidad, no la detección.

---

## 6. Qué se puede construir realista (sin mentirte)

Un **monitor**, no un ejecutor (coherente con el proyecto: detecta/alerta, nunca
opera solo):

- Baja `exchangeInfo` (una vez) + `bookTicker` all-symbols (cada N seg).
- Arma el grafo de monedas con las aristas que existen.
- Enumera triángulos por monedas puente (USDT, BTC, ETH, BNB), evalúa los 2
  sentidos, descuenta el umbral de fee configurable (con toggle "descuento BNB").
- Muestra una tabla "Top ciclos triangulares" con: las 3 patas, el producto
  bruto, el neto de fees, y un **flag de profundidad** (cuánto volumen aguanta
  la mejor punta antes de que el spread desaparezca) para no engañarte con pares
  ilíquidos.
- Refresco con auto-update y resaltado de los pocos que den **neto positivo**.

Extras opcionales: Bellman-Ford para ciclos de 4+, multi-exchange (cada uno por
separado), o caminar el orderbook (`/api/v3/depth`) para profit ejecutable real.

---

## 7. Riesgos / por qué NO automatizar la ejecución (todavía)

- **No es atómico:** 3 órdenes seguidas; un fill parcial o un tick en contra
  invierte el resultado.
- **Slippage real > spread teórico** en los pares jugosos (ilíquidos).
- **Competencia HFT:** llegás tarde a los de majors.
- Si algún día se ejecuta, sería con **órdenes IOC/market y control de tamaño por
  profundidad**, y aun así con expectativa de ganancia chica y varianza alta.

Por eso la propuesta arranca en **modo monitor**: ver, medir, entender dónde y
cuándo aparecen, antes de pensar en ejecutar.

---

## 8. Fuentes

- [Wish or reality? On the exploitability of triangular arbitrage in cryptocurrency markets — ScienceDirect (2024)](https://www.sciencedirect.com/science/article/pii/S154461232401537X)
- [An innovative approach to identifying triangular arbitrage using Bellman-Ford — BEEI](https://beei.org/index.php/EEI/article/view/10817)
- [Bellman-Ford in Cryptocurrency Arbitrage: Detecting Profitable Trade Cycles — Medium](https://medium.com/@23bt04107/bellman-ford-in-cryptocurrency-arbitrage-detecting-profitable-trade-cycles-2a6264a409b3)
- [Graph algorithms and currency arbitrage, part 2 — Reasonable Deviations](https://reasonabledeviations.com/2019/04/21/currency-arbitrage-graphs-2/)
- [Automated Triangular Arbitrage: Unlocking Profits in Forex and Crypto — ainvest](https://www.ainvest.com/news/automated-triangular-arbitrage-unlocking-profits-forex-crypto-markets-2601/)
- [Crypto Triangular Arbitrage: How Advanced Traders Exploit 3-Way Inefficiencies — HyroTrader](https://www.hyrotrader.com/blog/crypto-triangular-arbitrage/)
- [Binance Spot API — Market Data endpoints (bookTicker, exchangeInfo, depth)](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints)
