# Investigación: precio flotante en anuncios P2P, ¿conviene para USDT/ARS?

_Consultado 2026-08-30. Fuentes oficiales de cada exchange + medición propia
sobre el histórico del VPS (6.706 muestras, 08/06 a 30/08 de 2026)._

## Resumen ejecutivo

- **El flotante sigue al ÍNDICE, no a la competencia.** Es la conclusión que
  decide todo: el dolor de "estar modificando el precio a cada rato" es que un
  rival te pisa por un peso, y contra eso el flotante no hace nada. `Sólido`.
- **El USDT/ARS casi no se mueve intradía.** Medido: la mediana de cambio en una
  hora es **0,044%**, y sólo el **11% de las horas** se mueve más de 0,20%. El
  fee de publicar (0,20%) es más grande que la deriva típica de una hora.
  `Sólido` (medición propia).
- **Donde sí sirve: el aviso que queda colgado.** En un día la mediana es
  **0,185%** y el percentil 90, **0,700%**. Un aviso que dejás toda la noche a
  precio fijo se desactualiza de verdad. `Sólido`.
- **Los cuatro exchanges lo tienen**, con la misma fórmula (índice × margen) y
  refrescos distintos: Bybit cada 3 segundos, Binance cada minuto. `Sólido`.
- **Nadie documenta de dónde sale el índice para USDT/ARS.** Ni Binance, ni OKX,
  ni KuCoin. Publicar flotante es atarse a un número cuya fórmula no se puede
  auditar. `Incierto`, y es el riesgo principal.
- **Por API no se puede tocar sin ser Comerciante Verificado.** La doc pública de
  Binance C2C expone UN endpoint (historial de órdenes); crear y actualizar
  avisos es sólo para merchants. `Sólido`.

**Conclusión: el flotante no resuelve el problema que lo motivó.** Lo que lo
resuelve es el repricer automático contra la competencia
(`bot/market_maker.py`, todavía sin construir). El flotante sirve como red de
seguridad para avisos desatendidos, y siempre con tope.

## Hallazgos

### 1. Cómo funciona, exchange por exchange

La fórmula es la misma en los cuatro: **precio del aviso = índice de referencia ×
margen**. Lo que cambia es el refresco y las protecciones.

| | Refresco | Rango del margen | Protección |
|---|---|---|---|
| **Binance** | cada 1 minuto | 80% – 250% | no documentada |
| **Bybit** | cada 3 segundos | no documentado | no documentada |
| **OKX** | no documentado | no documentado | **precio gatillo**: el aviso aparece sólo si el mercado llega a ese nivel |
| **KuCoin** | no documentado | no documentado | **precio máx/mín**: el aviso se **oculta** si el índice se sale del rango |

- Binance: *"Your ad price fluctuates with the market and is refreshed every
  minute"*, fórmula *"Market Reference Price × Floating Price Margin"*, y el
  rango del margen es 80%–250%
  ([glosario P2P](https://www.binance.com/en/support/faq/360041632232),
  [cómo publicar avisos](https://www.binance.com/en/support/faq/how-to-post-p2p-trading-advertisements-via-binance-app-360042084072)).
- Bybit: *"The cost of Floating Price Ads is adjusted according to market
  fluctuations and is updated every three (3) seconds"*
  ([help center](https://www.bybit.com/en/help-center/article/How-to-Post-a-Trade-Ad-on-P2P)).
- OKX: se completa el campo *"% of index"*; un 101,5% es una prima de 1,5% sobre
  el índice. Permite **trigger price** para controlar cuándo el aviso se hace
  visible ([help center](https://okx.com/support/hc/en-us/articles/360045484912--Other-10-Frequently-Asked-Questions-about-P2P-Trading)).
- KuCoin: *"your ad price equals the reference market price multiplied by the
  price premium"*, y **"Your ad will be hidden if the market index price exceeds
  the maximum price or is below the minimum price"**
  ([cómo publicar avisos](https://www.kucoin.com/support/360025469894)).

**La protección de KuCoin y OKX es lo importante**: un flotante sin tope, en un
salto del dólar, te vende barato o te compra caro automáticamente. Con tope, el
aviso se esconde en vez de ejecutarse mal.

### 2. Cuánto se mueve realmente el USDT/ARS

Medición propia sobre `data/spread_vps.csv` del VPS: 6.706 muestras cada ~15
minutos, del 08/06 al 30/08 de 2026. Se mide el cambio absoluto en % del mejor
bid del mercado.

| Ventana | Mediana | p75 | p90 |
|---|---|---|---|
| 15 minutos | 0,010% | 0,042% | 0,102% |
| 1 hora | **0,044%** | 0,102% | 0,206% |
| 4 horas | 0,081% | 0,181% | 0,341% |
| 1 día | **0,185%** | 0,402% | 0,700% |

- En **una hora** el precio se mueve más de 0,20% sólo el **11% de las veces**, y
  más de 0,50% el **2%**.
- La serie tiene **un dato roto** (un print de 2.451, contra un rango real de
  1.496–1.700 en el período) que infla la columna de máximos. Por eso arriba se
  reportan mediana y percentiles, que no se ven afectados, y no el máximo.

**Lectura:** en una hora el mercado se corre menos de lo que cuesta publicar
(0,20% de maker en Binance). El flotante, intradía, te está corrigiendo un ruido
más chico que tu propia comisión. Concuerda con lo ya medido en el proyecto: sólo
el **8%** de los avisos de USDT repreciaron en 19 minutos, contra el 62% de los
de BTC (ver `docs/investigacion-prima-btc-alts-ars.md`).

### 3. El índice para USDT/ARS: nadie lo publica

Ninguna de las cuatro documentaciones dice de dónde sale el "market reference
price" para un par sin mercado spot global. Binance lo nombra en la fórmula pero
no lo define; KuCoin habla de "market index price" sin fuente; OKX dice "índice"
sin más.

Se intentó averiguarlo empíricamente contra la API pública de avisos de Binance:
el objeto del aviso **tiene** los campos `priceType`, `priceFloatingRatio` y
`rateFloatingRatio`, pero vienen en `null` en los 40 avisos del libro de ARS.
**No se puede concluir que nadie use flotante**: el mismo escaneo sobre VES y COP
—mercados donde el flotante es habitual— también dio 40 de 40 en `null`, o sea
que Binance simplemente **no expone ese campo públicamente**. `Incierto`.

### 4. Por API: sólo para Comerciante Verificado

La documentación pública de Binance C2C
([developers.binance.com](https://developers.binance.com/docs/c2c/rest-api))
expone **un solo endpoint**: `GET /sapi/v1/c2c/orderMatch/listUserOrderHistory`,
historial de órdenes, con 6 meses de retención. Crear y actualizar avisos
(`/sapi/v1/c2c/ads/create`, `/sapi/v1/c2c/ads/update`) existe pero **no está en
la doc pública** y aparece sólo en el foro de desarrolladores; un
[tutorial del 22/09/2025](https://dev.to/pydevtop/how-to-update-binance-p2p-ad-price-with-python-complete-step-by-step-tutorial-1p48)
lo usa y advierte: *"only merchants can modify ads through the API"*, con claves
generadas desde la cuenta de comerciante.

O sea: **hasta que no salga el Comerciante Verificado, no hay nada que automatizar
por API.** Ver `docs/spec-market-maker.md` y la memoria del trámite.

## Contradicciones e incógnitas

- **De dónde sale el índice de USDT/ARS.** Sin documentar en los cuatro
  exchanges. Es el hueco que más pesa: el flotante te ata a un número que no
  podés auditar ni replicar. Si el índice se arma con el propio libro P2P, un
  movimiento del libro te arrastra el precio aunque vos no quieras.
- **Rango del margen fuera de Binance.** Sólo Binance publica 80%–250%. Para OKX,
  Bybit y KuCoin no se encontró el límite.
- **Si Binance ofrece tope/gatillo como KuCoin y OKX.** No aparece en su doc. No
  se pudo confirmar ni descartar.
- **Uso real del flotante en el libro de ARS.** No medible con la API pública.

## Recomendación

**1. El flotante no es la solución a tu problema.** Vos querés dejar de repricear
para no perder el puesto frente a los rivales. El flotante sigue al índice: si el
índice no se mueve y un rival te pisa por un peso, el flotante te deja exactamente
donde estabas. Y el índice, medido, casi no se mueve: 0,044% por hora.

**2. Lo que sí lo resuelve es `bot/market_maker.py`**, que repricea contra la
competencia real (el motor de `core/ad_curve.py` ya calcula a qué precio hay que
estar, por tamaño de ticket). Bloqueado hasta el Comerciante Verificado, porque
la API de avisos es sólo para merchants.

**3. Usá flotante para el aviso que dejás desatendido.** Es donde el número
justifica: 0,185% de mediana por día, 0,700% en el percentil 90. Un aviso que
queda toda la noche a precio fijo sí se desactualiza.

**4. Si lo usás, siempre con tope.** KuCoin esconde el aviso fuera del rango y OKX
tiene precio gatillo. Sin tope, un salto del dólar te ejecuta la peor punta
automáticamente. En Binance no está documentado el tope: **verificarlo en la
pantalla antes de dejar un flotante colgado ahí.**

**5. No cambia la regla de BTC.** Para BTC el flotante sigue siendo lo correcto
(62% de los avisos repreciaron en 19 minutos): ahí el índice sí se mueve.

## Fuentes

- [Binance — glosario P2P](https://www.binance.com/en/support/faq/360041632232)
- [Binance — cómo publicar anuncios P2P (app)](https://www.binance.com/en/support/faq/how-to-post-p2p-trading-advertisements-via-binance-app-360042084072)
- [Binance — API C2C (REST)](https://developers.binance.com/docs/c2c/rest-api)
- [Bybit — cómo publicar un aviso P2P](https://www.bybit.com/en/help-center/article/How-to-Post-a-Trade-Ad-on-P2P)
- [OKX — FAQ de P2P](https://okx.com/support/hc/en-us/articles/360045484912--Other-10-Frequently-Asked-Questions-about-P2P-Trading)
- [KuCoin — cómo publicar avisos](https://www.kucoin.com/support/360025469894)
- [Tutorial: actualizar el precio de un aviso P2P de Binance con Python](https://dev.to/pydevtop/how-to-update-binance-p2p-ad-price-with-python-complete-step-by-step-tutorial-1p48) (22/09/2025)
- Medición propia: `data/spread_vps.csv` del VPS (6.706 muestras, 08/06–30/08 de
  2026) y escaneo de `p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search` para
  ARS, VES y COP (30/08/2026).
