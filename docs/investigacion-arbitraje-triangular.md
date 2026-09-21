# Investigación: arbitraje por triangulación de monedas

> Investigación profunda de métodos de arbitraje triangular aplicables a tu
> operatoria (P2P ARS en Argentina, exchanges del whitelist, datos de CriptoYa +
> orderbooks). Fecha: 2026-06-20.

---

## 0. TL;DR — qué conviene mirar primero

Ordenado por **realismo para tu caso** (no por glamour):

1. **Rulo cambiario con tipos de dólar** (ARS → USDT cripto ↔ dólar banco/MEP → ARS).
   Es lo que ya hacés, pero la "triangulación" aparece cuando metés el **dólar
   oficial/banco** o el **MEP** como tercer vértice. Contra cripto **no hay cepo**
   (la restricción cruzada del BCRA de 90 días es solo oficial↔MEP/CCL). **Mayor
   ganancia, fricción que ya conocés.**
2. **Depeg de stablecoins cruzado contra ARS** (USDT/ARS vs USDC/ARS vs DAI/ARS
   desalineados). Detectable **con la data que ya bajás**, y si tenés saldo en
   ambos lados **no hay transferencia de red**. Riesgo medio-bajo.
3. **Triangular cross-asset cross-exchange** (comprar BTC barato en X, convertir
   BTC→USDT donde ese par está desalineado, USDT→ARS). Aprovecha desalineaciones
   que el spread de una sola moneda no ve. Riesgo medio.
4. **Triangular spot puro intra-exchange** (USDT→BTC→ETH→USDT en un solo libro).
   Académicamente lindo, pero **competís contra bots HFT** y pagás fee taker ×3.
   Para vos, baja prioridad.

El **enemigo común** de todo arbitraje triangular es que **no es atómico**: entre
pata y pata el mercado se mueve. En cripto-cripto son segundos; en P2P/ARS son
**minutos** (y rige tu regla de oro: **nunca liberar sin acreditación bancaria**).
Eso convierte varias triangulaciones "teóricas" en riesgo de mercado puro.

---

## 1. Qué es una triangulación (la matemática)

Un arbitraje triangular es un **ciclo cerrado** de conversiones A → B → C → A
(pueden ser 3 o más patas) donde el **producto de los tipos de cambio supera 1**
después de fees.

Si `r(X→Y)` es cuántas unidades de Y obtenés por 1 de X (ya neto de comisión):

```
ganancia_bruta = r(A→B) · r(B→C) · r(C→A)
```

- `> 1` ⇒ el ciclo deja ganancia.
- `= 1` ⇒ mercado eficiente (lo normal).
- `< 1` ⇒ perdés.

Ejemplo cripto puro en un exchange:
```
1 USDT → BTC → ETH → USDT
r = (1/precio_BTCUSDT) · (precio_BTCETH) · (precio_ETHUSDT)
```

**Detección automática (el método correcto):** modelás cada moneda como un nodo
de un grafo y cada par/exchange como una arista con peso `-log(r)`. Un ciclo cuyo
producto de `r` es `> 1` equivale a un **ciclo de peso negativo** en logaritmos.
Se detecta con **Bellman-Ford** (o Floyd-Warshall para todos los pares). Esto es
clave: no buscás "spread de una moneda", buscás **ciclos rentables en toda la
matriz** de {ARS, USDT, USDC, BTC, ETH, SOL, XRP} × exchanges de una sola pasada.

> Tu dashboard hoy hace el caso particular de **2 patas** (comprar en X, vender
> en Y, misma moneda, contra ARS). La triangulación generaliza eso a **ciclos de
> 3+** y a **cambiar de moneda en el medio**.

---

## 2. Familias de triangulación (de menor a mayor fricción)

### A) Triangular spot puro (intra-exchange)
`USDT → BTC → ETH → USDT` dentro de un mismo exchange spot (Binance, OKX, Bybit).

- **Pro:** una sola cuenta, sin transferencias de red, "casi" atómico (3 órdenes
  market seguidas), sin riesgo P2P.
- **Contra:** los desbalances duran **milisegundos**; hay bots de HFT colocados
  en el mismo datacenter. Pagás **fee taker ×3** (~0.1%×3 = 0.3% que el ciclo
  tiene que superar). **Para un operador manual/semi-auto es prácticamente
  inalcanzable.**
- **Veredicto para vos:** detectarlo sí (es gratis con la matriz), ejecutarlo a
  mano no. Solo tendría sentido con bot co-locado y API de baja latencia.

### B) Rulo cambiario / triangulación con ARS y tipos de dólar  ⭐
La versión argentina. El vértice no es solo "USDT" sino **los distintos dólares**:
oficial/banco, MEP, CCL, cripto (USDT), tarjeta, blue.

Rutas típicas:
```
ARS → dólar oficial (banco, $1.160) → USDT → vender USDT cripto ($1.204) → ARS
ARS → USDT (P2P barato) → USD en cuenta (Buenbit/CEX con salida USD) → ARS
ARS → MEP (bonos) → USD → USDT → vender cripto → ARS
```
- **Pro:** la **brecha entre tipos de dólar** suele ser mucho mayor que un spread
  cripto-cripto (puntos porcentuales, no centésimas). Es donde está la guita real
  en Argentina.
- **Contra:** límites de compra de oficial (cupo USD 200/banco), **restricción
  cruzada BCRA**: si comprás oficial no podés MEP/CCL por 90 días — **pero contra
  cripto NO hay cepo**. Timing bancario (horario), y tu riesgo real: **bloqueo
  AML/UIF** si movés mucho. No es atómico (minutos/horas).
- **Veredicto:** **la de mayor retorno** y la más alineada a lo que ya hacés.
  Falta data: el tipo `dólar` de CriptoYa (`/api/dolar`).

### C) Triangular cross-asset cross-exchange  ⭐
No vendés la misma moneda que compraste; **cambiás de activo en el camino** para
explotar que la *relación* entre dos cryptos difiere entre dos lugares.
```
ARS → (compro BTC barato en Exchange X)
    → (BTC→USDT en Exchange Y, donde BTC/USDT rinde más)
    → (USDT→ARS en Exchange Z, el que paga más)
```
- **Pro:** captura ineficiencias que el spread mono-moneda **no ve**. Te da más
  rutas candidatas.
- **Contra:** 2 transferencias de red (fees + tiempo + riesgo de precio), y la
  pata cripto-cripto te expone a la volatilidad de BTC/ETH mientras transferís.
- **Veredicto:** interesante para detectar; ejecutar solo si las patas con
  volatilidad son cortas (idealmente conversión interna sin transferir).

### D) Triangulación de stablecoins / depeg  ⭐
Stablecoins que **deberían** valer lo mismo pero no:
```
Intra-exchange:  USDT → USDC → DAI → USDT  (cuando una se despega)
Cross-ARS:       USDT/ARS  vs  USDC/ARS  vs  DAI/ARS  desalineados
```
- **Pro:** **detectable con la data que ya bajás** (tenés USDT/USDC y antes DAI).
  Si mantenés saldo en los dos lados, **sin transferencia de red**. Bajo riesgo
  direccional (todas valen ~1 USD).
- **Contra:** spreads chicos y poca liquidez en las stablecoins menos usadas;
  ojo con **quotes obsoletos** (justo el caso DAI/Lemon que viste: precio
  congelado de hace 71 días → ya lo filtramos por antigüedad).
- **Veredicto:** **buen punto de entrada de bajo riesgo**, y ya tenés media
  infraestructura.

### E) Arbitraje de método de pago (sub-tipo P2P)
Dentro de P2P, el "tercer vértice" es el **método de cobro**:
```
ARS (transferencia común) → USDT → ARS (cobrado por un método premium / CVU que paga más)
```
- Ya está en tu doc de estrategias. Es triangulación "de rieles de pago", no de
  monedas, pero comparte la lógica de ciclo. Fricción baja, ganancia chica-media.

---

## 3. Cómo detectarlo con tu stack (concreto)

Ya tenés el 70%: el dashboard baja `criptoya.com/api/{coin}/ARS/{vol}` por moneda
y arma la lista de exchanges con `totalAsk`/`totalBid`. Para triangular:

1. **Sumá el endpoint de dólares:** `GET https://criptoya.com/api/dolar`
   (oficial, MEP/bolsa, CCL, cripto, blue, tarjeta, mayorista). Cada uno es un
   "nodo dólar" con su compra/venta. Esto habilita la familia B (la jugosa).

2. **Armá la matriz de cambio** con todos los nodos:
   `{ARS, USD_oficial, USD_mep, USDT, USDC, BTC, ETH, SOL, XRP}` × cada exchange.
   Cada par operable = arista con `r` neto de fee (trading + red si hay que
   transferir).

3. **Corré Bellman-Ford** desde ARS buscando ciclos con producto `> 1` (peso
   negativo en `-log r`). Devolvés las rutas rentables ordenadas por ganancia
   neta, igual que hoy ordenás los spreads de 2 patas.

4. **Penalizá cada arista con su fricción real:**
   - fee de trading taker del exchange (tu editor de comisiones ya lo tiene),
   - fee de red si la pata implica **transferir** (tu `getNetworkFee`),
   - **profundidad/slippage**: el `totalAsk/totalBid` de CriptoYa es la mejor
     punta; para volumen real necesitás el **orderbook** (Binance/OKX/Bybit
     públicos) y caminar el libro. Sin esto, las rutas se ven mejores de lo que
     son.
   - **haircut por no-atomicidad**: a cada pata que tarda (P2P, transferencia)
     restale un colchón por riesgo de que el precio se mueva.

5. **Filtros que ya aplican** y hay que mantener: whitelist/blacklist (nunca
   DolarApp/Takenos/etc. como destino), filtro de fantasmas (±6% de la mediana),
   filtro de **quotes obsoletos** (>30 min, el de DAI/Lemon).

---

## 4. Las fricciones que matan el arbitraje triangular

| Fricción | Impacto | Cómo modelarla |
|---|---|---|
| Fee taker ×N patas | ~0.1% por pata; un ciclo de 3 arranca −0.3% | restar en cada arista |
| Fee de red al transferir | fijo en la moneda; brutal en montos chicos | `getNetworkFee`, evitar patas que transfieren |
| Slippage / profundidad | el spread real < el de la mejor punta | caminar orderbook, no usar solo `totalAsk` |
| Latencia / no-atomicidad | el precio se mueve entre patas | haircut por pata lenta; preferir ciclos cortos |
| Tiempo P2P (minutos) | riesgo de mercado + **regla: no liberar sin acreditación** | tratar P2P como pata "lenta", nunca automatizar la liberación |
| Límites y AML/UIF bancario | **tu riesgo real**, no el spread | límites de volumen, diversificar cuentas, no es un parámetro del modelo sino operativo |
| Restricción cruzada BCRA | 90 días oficial↔MEP/CCL | marcar rutas que la disparan; **cripto está exenta** |

Regla práctica: **cuantas más patas y más transferencias, más teórica es la
ganancia**. El arbitraje triangular rentable de verdad suele tener **0 o 1
transferencia de red** y patas que se resuelven rápido.

---

## 5. Priorización para tu caso

| Familia | Retorno | Fricción | ¿Data que ya tenés? | Prioridad |
|---|---|---|---|---|
| B) Rulo + tipos de dólar | Alto | Media (la que ya manejás) | Falta `/api/dolar` | **1** |
| D) Stablecoin depeg cross-ARS | Bajo-medio | Baja (sin transferir si hay saldo) | **Sí** | **2** |
| C) Cross-asset cross-exchange | Medio | Media-alta (transferencias) | Casi (falta orderbook) | 3 |
| E) Método de pago P2P | Bajo-medio | Baja | Parcial | 3 |
| A) Triangular spot puro | Muy bajo p/ manual | Baja técnica, alta competencia | Sí | 4 (solo con bot) |

---

## 6. Propuesta concreta de construcción (si querés avanzar)

**Pestaña nueva "Triangulaciones"** en el dashboard, reusando la infra actual:

- **Fase 1 (bajo riesgo, alto valor):** módulo de **tipos de dólar**
  (`/api/dolar`) + detector de **rulo de 3 patas** ARS↔dólar↔USDT, mostrando
  ganancia neta y marcando si dispara la restricción cruzada BCRA. + detector de
  **depeg de stablecoins** cross-ARS con la data que ya bajás.
- **Fase 2:** **matriz de cambio + Bellman-Ford** sobre todas las monedas y
  exchanges, con fees y filtro de obsolescencia, devolviendo rutas de 3+ patas
  ordenadas por ganancia neta (la generalización de la tabla actual).
- **Fase 3:** integrar **orderbook real** (profundidad) para que la ganancia sea
  ejecutable y no de la mejor punta; haircut por no-atomicidad.

Todo en **modo detección/alerta** — siguiendo el principio del proyecto: el
sistema sugiere, **nunca libera ni opera solo**.

---

## 7. Fuentes

- [CriptoYa API Docs — Argentina](https://docs.criptoya.com/argentina) (endpoints; no hay endpoint de triangulación: se arma con `/api/{coin}/{fiat}/{vol}` + `/api/dolar`)
- [CriptoYa — Arbitrajes](https://criptoya.com/eu/arbitrajes)
- [Triangular arbitrage — Wikipedia](https://en.wikipedia.org/wiki/Triangular_arbitrage) (modelo de ciclo y detección)
- [Locademia Cripto — Guía de arbitraje financiero](https://www.locademiacripto.com/p/arbitraje.html)
- [iProUP — Vuelve el rulo cripto: operatoria y ganancia](https://www.iproup.com/economia-digital/49243-en-que-invierto-hoy-que-es-el-arbitraje-de-criptomonedas-y-cuanto-se-gana)
- [iProUP — Nuevo rulo por el fin del cepo](https://www.iproup.com/finanzas/55341-nuevo-rulo-por-el-fin-del-cepo-como-funciona-y-cuanto-se-gana)
- [Chequeado — BCRA prohibió el rulo oficial↔financieros (restricción cruzada)](https://chequeado.com/el-explicador/el-banco-central-prohibio-el-rulo-entre-el-dolar-oficial-y-los-financieros-la-brecha-cambiaria-es-la-mas-alta-desde-la-salida-del-cepo/)
- [El Observador — el mercado busca otra vía de arbitraje](https://www.elobservador.com.uy/argentina/economia-y-negocios/el-bcra-frena-el-rulo-dolares-financieros-pero-el-mercado-ya-busca-otra-via-arbitraje-n6018648)
