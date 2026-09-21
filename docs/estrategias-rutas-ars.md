# Las 3 mejores estrategias, calculadas por el buscador de rutas

> Encargo: "buscá las tres estrategias con las que más pueda ganar, sea
> comprando, vendiendo, publicando, cambiando de plataforma; inventá las que
> hagan falta y construí algo que las calcule".
> Datos en vivo del **2026-08-23, ~13:30 ART (domingo)**. Ver también
> `docs/investigacion-prima-btc-alts-ars.md`.

---

## Cómo se buscaron (no se eligieron a mano)

Se armó el **grafo completo** de todo lo que se puede hacer con pesos y se
buscaron todos los ciclos que vuelven a pesos ganando. Ninguna estrategia está
puesta a dedo: salen de la búsqueda.

- **Nodos.** Los pesos son **uno solo** (`ARS`): es plata en el banco, se mueve
  entre venues gratis. La cripto es **un nodo por venue** (`BTC@binance`,
  `USDT@bybit`), porque moverla cuesta fee de red.
- **Aristas.** Por cada activo y venue: comprar tomando, vender tomando,
  publicar compra, publicar venta, convertir en spot contra USDT, y transferir
  entre venues.
- **Ganancia del ciclo** = producto de las tasas netas − 1. El umbral a vencer
  nunca es 0: es la suma de todos los fees del ciclo.

Con 3 venues y 3 activos son **66 operaciones posibles** y salieron **128 ciclos
rentables**. Pero el porcentaje solo no sirve para elegir, y ahí está el hallazgo
principal.

---

## El hallazgo: el porcentaje miente si nadie opera

Ranking por **porcentaje** (lo que uno miraría por instinto):

| # | neto | ruta |
|---|---|---|
| 1 | **2,17%** | ARS → ETH → ARS (publicar las dos puntas) |
| 2 | 1,88% | ARS → BTC → USDT → ETH → ARS |
| 3 | 1,54% | ARS → BTC → ARS (publicar las dos puntas) |

Ranking por **pesos por hora**, después de medir cuánto se consume de verdad en
cada punta del libro (13 muestras, 7,1 minutos, siguiendo cada aviso por su
`advNo`):

| # | ARS/hora | neto | cuello USD/h | te tomen | ruta |
|---|---|---|---|---|---|
| 1 | **26.281** | 1,54% | 1.074 | 2 | ARS → BTC → ARS |
| 2 | **24.690** | 0,82% | 1.901 | **1** | ARS → USDT → BTC → ARS |
| 3 | 22.015 | 0,73% | 1.901 | 2 | ARS → USDT → BTC → ARS |
| … | **0** | **2,17%** | **0** | 2 | ARS → ETH → ARS |

**El ETH pagaba el mejor porcentaje de toda la tabla y rinde cero**, porque en
7 minutos y 34 avisos seguidos **no se movió un solo dólar** en ninguna de sus
dos puntas. Un 2,17% sobre un mercado que no opera es 2,17% de nada.

| punta | avisos | consumo medido | USD/hora |
|---|---|---|---|
| USDT — te venden | 23 | 13.163 USD | 111.236 |
| USDT — te compran | 25 | 1.226 USD | 10.361 |
| BTC — te compran | 21 | 225 USD | 1.901 |
| BTC — te venden | 22 | 127 USD | 1.074 |
| **ETH — las dos** | 34 | **0 USD** | **0** |

---

## Las 3 estrategias

### 1) Doble maker en BTC — 1,54% por vuelta, techo ~26.300 ARS/hora

```
publicás COMPRA de BTC a 121.730.000   (fee maker 0,20%)
publicás VENTA  de BTC a 124.100.000   (fee maker 0,20%)
```

Ponés las dos puntas dentro del ancho del libro y cobrás el medio. No tocás el
mercado de USDT ni el spot: **no pagás fee de red ni de conversión**, sólo dos
makers.

- **A favor:** el mejor porcentaje entre lo que realmente opera, y el ciclo más
  corto (2 patas).
- **En contra:** **necesita que te tomen las DOS puntas**. Si sólo se cierra una,
  quedaste con posición en BTC (o con pesos parados) y el 1,54% se evapora.
  El cuello es la punta compradora, que mueve la mitad que la vendedora.
- **Cómo se arregla el riesgo:** si sólo te toman la venta, **te reponés por la
  ruta sintética** (`USDT → spot`), que cuesta ~1.589 de fx. O sea que la
  estrategia 2 es el paracaídas de la 1. Eso las hace complementarias, no
  alternativas.

### 2) La prima con una sola punta expuesta — 0,82%, techo ~24.700 ARS/hora

```
TOMÁS USDT a 1.586,00          (fee de tomador: centavos)
spot: comprás BTC a 77.375     (fee 0,10%)
publicás VENTA de BTC a 124.100.000   (fee maker 0,20%)
```

Es la jugada de la prima del informe anterior. Rinde la mitad de porcentaje que
la 1, **pero da casi la misma plata por hora** porque su cuello es la punta
vendedora de BTC, que mueve el doble.

- **A favor:** **sólo una pata depende de que te tomen.** Las otras dos las
  ejecutás vos cuando querés. Mucho menos riesgo de quedar a medio camino.
- **En contra:** pagás el spot (0,10%) y dependés de que el libro de USDT esté
  líquido (lo está: 10.000-111.000 USD/hora).
- **Ajustada por riesgo, es la mejor de las tres.** Casi la misma plata que la 1
  con la mitad de la incertidumbre.

### 3) La misma, publicando también la compra de USDT — 0,73%, techo ~22.000 ARS/hora

```
publicás COMPRA de USDT a 1.584,33   (fee maker 0,20%)
spot: comprás BTC a 77.375           (fee 0,10%)
publicás VENTA de BTC a 124.100.000  (fee maker 0,20%)
```

Comprar el USDT publicando en vez de tomando te consigue un precio mejor
(1.584,33 contra 1.586,00), **pero te cobra 0,20% de maker para ganar 0,10% de
precio**: el ancho del USDT (0,18%) no paga su propia comisión.

**Queda tercera y sirve como prueba de por qué el USDT no da margen**: es
exactamente lo que respondía la pregunta original ("¿por qué en USDT no se
puede?"). Sólo conviene si el ancho del USDT se abre por encima del 0,20%.

---

## Lo que el buscador probó y descartó

- **Cross-venue con transferencia** (comprar en un venue, mandar la cripto,
  vender en otro): los 92 ciclos que dieron 10-15% pisaban todos el libro de BTC
  de OKX o Bybit, que tiene 2-8 avisos y **cero consumo medido**. Marcados como
  `VACIO`, no son oportunidad. Es la misma trampa que costó plata el 21/08.
- **La ruta inventada `BTC → USDT → ETH`** (comprar BTC publicando, pasar a ETH
  por spot, vender ETH publicando): 1,88% de neto, muy linda en el papel, y
  **cero por hora** por el mismo motivo que el ETH.
- **Triangular puro cripto-cripto**: ya estaba descartado en
  `docs/investigacion-triangular-rentabilidad-real.md` (se lo llevan los bots por
  latencia). El buscador no encontró ninguno rentable acá tampoco.

---

## Advertencias, sin maquillar

- **Los "ARS/hora" son un TECHO, no una expectativa.** Suponen que capturás
  el 100% del flujo de esa punta, o sea que estás primero en el libro todo el
  tiempo y nadie te undercutea. En la práctica vas a agarrar una fracción.
- **La ventana de flujo es de 7,1 minutos de un domingo a la tarde.** Alcanza
  para separar "opera" de "no opera" —que es la decisión importante y ahí el
  contraste es de 1.900 contra 0— pero **no** para afirmar un caudal diario. Los
  111.236 USD/hora del USDT casi seguro están inflados por un aviso retirado, no
  por ventas. **El logger de la semana (`prima-logger.timer` en el VPS) es lo que
  va a dar el número bueno.**
- **El maker de BTC en Binance no está publicado.** Se asumió el 0,20% del USDT.
  Si para BTC fuera distinto, la estrategia 1 (que lo paga dos veces) se corre el
  doble que las otras. **FALTA verificar** logueado en
  `binance.com/en/fee/p2pFeeRate`.
- **Si publicás en BTC, el aviso va flotante.** A precio fijo sólo te toman
  cuando el movimiento te juega en contra, y eso no está descontado en ninguno de
  estos números.

---

## Herramienta

```bash
python -m cli.rutas                                   # 3 venues, 3 activos
python -m cli.rutas --venues binance --sin-red        # sólo intra-venue
python -m cli.rutas --solo-creibles --max-pasos 5     # más profundo, sin humo
python -m cli.rutas --flujo flujo.json --fx 1590      # rankea por ARS/hora
```

- `core/rutas.py` — grafo, búsqueda de ciclos, perfil de riesgo y cuello de
  botella por flujo. 21 tests en `tests/test_rutas.py`.
- `cli/rutas.py` — arma el grafo en vivo y lo resuelve. **Sólo lee y calcula.**

El `--flujo` toma un JSON `{"BTC_ask": usd_por_hora, "BTC_bid": …}`. Cuando el
logger tenga la semana, ese archivo sale de los datos reales en vez de una
ventana de 7 minutos.
