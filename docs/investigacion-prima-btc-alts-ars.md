# Investigación: la punta ancha de BTC/ARS — ¿se puede cobrar?

> Pregunta: el libro de BTC contra pesos tiene una punta muchísimo más ancha que
> el de USDT. ¿Hay una estrategia para cobrar ese ancho, ojalá ~2%, algo que en
> USDT es imposible? Todo medido en vivo desde la IP residencial.
> Fecha: **2026-08-22, ~20:00 ART (sábado)**.

---

## Resumen ejecutivo

1. **El ancho de BTC NO se puede cobrar cruzando las dos puntas.** Comprar BTC y
   venderlo al toque pierde ~1,4%. No existe arbitraje de tomador. `Medido`
2. **Lo que sí existe es una prima de conveniencia**: el que compra BTC contra
   pesos paga **+1,1%/+1,2% sobre lo que cuesta comprar USDT**, mientras que el
   que vende BTC cobra **casi lo mismo** que vendiendo USDT (−0,2%). La prima
   está casi toda del lado de la compra. `Medido`
3. **La forma de cobrarla es PUBLICAR la venta**, fondeándose por el mercado
   líquido: `ARS →(tomo P2P) USDT →(spot 0,1%) BTC →(publico) ARS`. Deja
   **0,72%–0,92% neto** en Binance, contra un USDT donde publicar da **negativo**
   (ancho 0,18% < 0,20% de maker). `Medido`
4. **El 2% existe pero no está en BTC: está en las alts.** ETH, BNB, SOL, XRP,
   DOGE y ADA cotizan la misma prima o más alta (hasta +1,9%). `Medido`
5. **Pero la prima alta se paga con volatilidad**, y BTC gana el ranking
   ajustado por riesgo: cubre 2,8 veces su propio ruido, DOGE apenas 1,2. `Medido`
6. **El 9,8% de OKX es humo.** Es un libro de 3 avisos sin nadie que lo dispute
   — exactamente la trampa del 21/08. La herramienta ahora lo marca sola. `Medido`
7. **El cuello de botella real es el volumen del lado que hay que disputar:**
   ~235 USD/h en el lado ask de BTC contra ~34.000 USD/h en USDT. `Medido, ventana corta`

---

## 1. El experimento central: traducir todo a "ARS por dólar"

Un BTC de 123 millones y un USDT de 1.588 no se comparan. Se vuelven comparables
dividiendo el precio en ARS por el precio del activo en USD:

```
fx implícito = precio_ARS / precio_USD_del_activo
```

Eso responde la pregunta única que importa: **¿a cuántos pesos por dólar estoy
comprando o vendiendo, vaya por donde vaya?**

### Binance, 2026-08-22 ~20:00 ART (spot BTC 77.094 USD, OKX)

| | ask (te venden) | bid (te compran) | ancho |
|---|---|---|---|
| **USDT/ARS** | 1.587,9 | 1.585,0 | **0,18%** |
| **BTC/ARS** (fx) | 1.605,0 | 1.580,5 | **1,55%** |

La asimetría es el hallazgo: el bid de BTC está a **−0,2%** del bid de USDT, pero
el ask de BTC está a **+1,1%** del ask de USDT. **La prima está del lado de la
compra, no repartida.**

### Por qué no hay arbitraje de tomador

- Comprar USDT (1.587,9) → spot → vender BTC tomando (1.580,5): **−0,5%**
- Comprar BTC tomando (1.605,0) → spot → vender USDT (1.585,0): **−1,4%**

Cruzar las dos puntas siempre pierde. El ancho no es un spread cobrable: es el
precio de un servicio que alguien tiene que prestar.

---

## 2. La jugada: publicar la venta, fondearse en USDT

```
ARS --(tomo P2P, libro líquido)--> USDT --(spot 0,1%)--> BTC --(PUBLICO)--> ARS
```

Caminando el libro de verdad, con mínimos y máximos por orden (el fix f8ad791):

| ticket ARS | costo fx (fondeo) | órdenes | vendo fx | bruto | **neto** |
|---|---|---|---|---|---|
| 500.000 | 1.589,4 | 2 | 1.606,8 | 1,10% | **0,90%** |
| 1.000.000 | 1.589,8 | 3 | 1.606,8 | 1,07% | **0,87%** |
| 3.000.000 | 1.590,3 | 10 | 1.606,8 | 1,04% | **0,84%** |
| 8.000.000 | 1.590,9 | 20 | 1.606,8 | 1,00% | **0,80%** |

El margen **casi no se degrada con el tamaño**. Lo que sí escala mal es la
fricción: 8 millones de fondeo son **20 órdenes P2P separadas**, con 20
contrapartes y su tiempo.

**Comparación que contesta la pregunta original:** publicar en USDT tiene un
ancho de 0,18% contra un maker de 0,20% → **da negativo**. Publicar en BTC deja
**0,72%–0,92%**. Por eso "cuesta mucho hacerlo en USDT": no es difícil, es que no
está.

---

## 3. Dónde está el 2%: no es BTC, son las alts

Escaneo de todos los activos del libro ARS de Binance:

| activo | prima ask | prima bid | ancho | vol. 20 min (p90) | **cobertura** |
|---|---|---|---|---|---|
| DOGE | **+1,90%** | −1,40% | 3,54% | 1,09% | 1,2x |
| ADA | +1,69% | −1,37% | 3,29% | 1,25% | 0,9x |
| BNB | +1,66% | −0,54% | 2,40% | 0,46% | 2,4x |
| ETH | +1,64% | −0,19% | 2,02% | 0,46% | 2,4x |
| SOL | +1,63% | −0,42% | 2,24% | 0,76% | 2,1x |
| XRP | +1,63% | −0,66% | 2,49% | 1,07% | 1,5x |
| **BTC** | +1,22% | −0,20% | 1,60% | **0,25%** | **2,8x** |
| USDT | 0 | 0 | 0,18% | — | — |
| USDC | −0,10% | −0,20% | 0,28% | — | — |

Dos lecturas:

- **La prima no es de BTC, es de "todo lo que no es stablecoin".** USDC se
  comporta como USDT (0,28%); todo lo demás cotiza +1,2%/+1,9%. Lo que se paga es
  la conveniencia de recibir cripto no-estable contra pesos.
- **La prima alta no es gratis.** `cobertura = neto / cuánto se mueve el activo
  en los 20 minutos que dura una orden`. DOGE paga 1,9% pero se mueve 1,09%:
  cubre 1,2 veces su propio ruido. BTC paga menos y cubre 2,8. **Ajustado por
  riesgo, BTC es el mejor de la tabla y ADA no debería tocarse.**

> Volatilidad medida sobre velas de 1m de OKX, ~5h de ventana en un día calmo.
> En un día movido estos números suben y varias filas dejan de cerrar.

---

## 4. El riesgo que casi me como: el aviso a precio fijo es una opción gratis

Siguiendo cada aviso por su `advNo` durante 19 minutos:

| libro | avisos con ≥3 observaciones | repreciaron | precio fijo |
|---|---|---|---|
| **BTC ask** | 21 | **13 (62%)** | 8 |
| **USDT ask** | 24 | 2 (8%) | 22 |

**Los vendedores de BTC corren avisos flotantes atados al índice; los de USDT,
precio fijo.** No es un detalle de implementación, es la estrategia:

> Si publicás BTC a **precio fijo** y el BTC se mueve, sólo te toman cuando el
> movimiento te juega **en contra**. Estás regalando una opción. Esa es buena
> parte de la razón por la que la prima es 1,2% y no 0,3%.

**Conclusión operativa: el aviso tiene que ser flotante (`priceType=2`, ratio
sobre el índice), no fijo.** Con fijo, el 0,72% medido es optimista y la
selección adversa se lo come.

---

## 5. El volumen: el cuello de botella

Seguimiento por `advNo`, 15 snapshots, 19 minutos, Binance:

| libro | consumo medido | ritmo |
|---|---|---|
| USDT — lado que compran | 10.725 USD | ~34.000 USD/h |
| USDT — lado que venden | 4.627 USD | ~14.700 USD/h |
| BTC — lado que venden (los que **le venden a compradores**) | 458 USD | ~1.455 USD/h |
| **BTC — lado ask (el que yo disputaría)** | **74 USD** | **~235 USD/h** |

- El libro de USDT movió **29 veces** lo del de BTC.
- Peor: dentro de BTC, el flujo está del lado equivocado para esta jugada. **El
  lado ask —donde yo publicaría— movió 74 USD en 19 minutos.**

**Lo que esto implica, sin maquillarlo:** a 235 USD/h y 0,72% neto, aun quedando
primero en el libro el ingreso teórico es de **~1,7 USD/h**. La jugada tiene buen
margen porcentual y **poquísima base sobre la que aplicarlo**.

> ⚠️ **Ventana corta y mal día.** 19 minutos de un **sábado a las 20 ART** es lo
> peor del calendario. No alcanza para el ritmo diario ni semanal. Está marcado
> como pendiente en la sección 8.

### Bybit / OKX / Bitget: no medido

Intenté lo mismo ahí y **descarté el resultado**: en esos venues un mismo
merchant publica varios avisos escalonados (fabricio45 tenía 4 simultáneos) y el
scanner no expone un ID por aviso, así que mi clave los mezclaba y contaba como
"consumo" la diferencia entre avisos distintos. Los 393.752 USD que dio Bybit son
un artefacto. **Volumen de BTC en Bybit/OKX/Bitget: FALTA medir** (requiere
agregar el ID de aviso a los fetchers).

---

## 6. El espejismo de OKX

| | ask fx | prima | avisos vivos | "neto" |
|---|---|---|---|---|
| BTC okx | 1.747,8 | **+10,0%** | **3** | 9,79% |
| ETH okx | 1.751,2 | +10,2% | **2** | 10,00% |
| BTC binance | 1.605,5 | +1,10% | 20 | 0,72% |

OKX no cobra maker (0%), así que la cuenta "da" 9,8%. **No es una oportunidad: es
un libro que nadie disputa.** Tres avisos a un precio que nadie paga no son un
precio de mercado. Es la misma lectura que costó plata el 21/08 con el 15% de
ancho de OKX.

Por eso `core.prima_alt` tiene `MIN_COMPETIDORES = 5` y marca la fila como
`!! VACIO — prima de fantasía, nadie la disputa` en vez de rankearla primero.

---

## 7. Qué hacer con esto

Ordenado por relación resultado/riesgo:

1. **Cobrar la prima con tus clientes OTC, no con el libro.** Es el uso más
   directo del hallazgo: **el precio de mercado minorista del BTC contra pesos es
   +1,2% sobre el USDT**. Cotizarle a un cliente BTC a +1% sobre tu costo de
   fondeo no es caro, es **más barato que Binance**. Y así te ahorrás las dos
   cosas que arruinan la jugada en el libro: el riesgo de que no te tomen y el
   0,20% de maker. Es margen limpio contra una contraparte conocida.
2. **Nunca comprar BTC por el libro P2P.** Si necesitás BTC (para un cliente o
   para posición), armalo por `USDT → spot`: **te ahorra 1,2%**. Y si un cliente
   te trae BTC y quiere pesos, podés pagarle prácticamente la cotización de USDT,
   porque venderlo te cuesta sólo 0,2% más.
3. **Publicar en el libro: sí, pero como complemento y con aviso flotante.** BTC
   o ETH/BNB en Binance, ticket chico, precio flotante. El margen es real
   (0,7%–1,1%); el volumen es el que es.
4. **No tocar ADA/DOGE/XRP** para esto: cobertura ≤1,5x, el ruido se come el
   margen.
5. **Ignorar los porcentajes gordos de OKX/Bitget** salvo que aparezcan avisos y
   contraparte.

---

## 8. Lo que quedó pendiente (FALTA)

- **Maker de BTC/alts en Binance.** Se asumió el 0,20% del USDT. No hay
  comunicado público; la tabla real pide login →
  `binance.com/en/fee/p2pFeeRate`. **Si para BTC fuera distinto, todos los netos
  de este informe se corren.**
- **Volumen con ventana representativa.** Lo medido son 19 minutos de un sábado
  a la noche. Hay que loguear la prima y el consumo por hora y día del semana,
  como ya hace `cli/spread_logger.py` con el spread de USDT.
- **Persistencia de la prima.** `data/spread_log_usdt_ars.csv` sólo tiene USDT:
  **no hay ni un dato histórico de la prima de BTC**. No sé si el +1,2% es
  estable, ni si se abre de noche o los fines de semana.
- **Volumen en Bybit/OKX/Bitget** (sección 5): requiere ID de aviso en los
  fetchers del scanner.
- **Avisos flotantes**: `priceType` viene enmascarado en el endpoint público. Que
  el 62% repreciara es una **inferencia** del seguimiento, no un dato de la API.

---

## Herramienta

```bash
python -m cli.prima_alt                                  # Binance, 7 activos
python -m cli.prima_alt --venues binance bybit okx       # comparar venues
python -m cli.prima_alt --solo-creibles --min-cobertura 2 # sólo lo ejecutable
```

- `core/prima_alt.py` — matemática pura (prima, jugada, ranking, guardia de
  libro vacío). 18 tests en `tests/test_prima_alt.py`.
- `cli/prima_alt.py` — lo corre en vivo. **Sólo lee, no publica nada.**
