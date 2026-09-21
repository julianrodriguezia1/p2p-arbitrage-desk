# Investigación: ¿API pública del orderbook P2P de Lemon? (para publicar avisos ahí)

_Consultado 2026-08-29. Fuentes primarias abiertas, cruzadas cuando se pudo._

## Resumen ejecutivo

- **NO existe API pública del orderbook P2P de Lemon.** No hay portal de
  desarrolladores, ni endpoint documentado, ni wrapper de terceros. `Sólido`.
- **CriptoYa NO sirve profundidad de ningún exchange.** Su schema tiene sólo
  `ask`, `totalAsk`, `bid`, `totalBid`, `time`. No hay volumen, ni cantidad de
  avisos, ni límites por orden. `Sólido` (spec OpenAPI propia de CriptoYa).
- **Comisiones del P2P de Lemon: 1% al que PUBLICA, 1,5% al que TOMA.** `Sólido`
  (centro de ayuda oficial + dos medios). Confirma el 1% que dijo el usuario.
- **El 1,5% que CriptoYa le carga a `lemoncashp2p` es el fee de TOMADOR.** La
  aritmética da exacto (1603,69 × 1,015 = 1627,745). O sea que el `totalAsk`/
  `totalBid` de CriptoYa es **correcto si tomás** y **castiga 0,5% de más por
  punta si publicás**. `Sólido`.
- **De dónde saca CriptoYa el precio de `lemoncashp2p`: no se pudo confirmar.**
  No lo documentan. `Incierto`.

**Conclusión: no se puede armar un fetcher de profundidad para Lemon P2P.** Queda
la opción de modelarlo como venue P2P con el precio suelto de CriptoYa, marcado
como no verificado en profundidad.

## Hallazgos

### 1. No hay API pública de Lemon Cash

Lo único que Lemon publica para desarrolladores es el **Mini-App SDK**
([lemon.me/build](https://lemon.me/build)), y sus métodos son de billetera, no de
mercado: autenticación por SIWE, depósito, retiro y ejecución de contratos. **No
expone precios, ni P2P, ni orderbook.** La página pública del mercado
([lemon.me/en/invertir-pesos](https://lemon.me/en/invertir-pesos)) es marketing:
tiene una calculadora estática, no cotizaciones en vivo.

El P2P vive dentro de la app autenticada: se entra por la pestaña "Mercado" →
banner "Ir a P2P"
([wiki.lemon.me](https://wiki.lemon.me/es-ar/lemon-cash-app/como-funciona-el-p2p-de-lemon-intercambia-crypto-directamente-con-otros-usuarios/)).

### 2. El host de API existe pero está cerrado

`api.lemoncash.com.ar` responde, pero devuelve **HTTP 400 con el cuerpo "Fixed
response content" a todas las rutas probadas** (`/p2p`, `/p2p/orders`,
`/p2p/offers`, `/p2p/ads`, `/p2p/orderbook`, `/p2p/publications`, `/health`,
`/docs`, `/openapi.json`). Es la respuesta por defecto de un WAF/gateway: no hay
superficie pública. `api.lemon.me` y `backend.lemon.me` ni siquiera resuelven.

Búsquedas en GitHub (`gh search code lemoncashp2p`, repos de scrapers de Lemon) no
devolvieron nada. Los resultados de "lemon API" son de **lemon.markets**, una
plataforma alemana de acciones, sin relación.

### 3. CriptoYa no da profundidad, y su "total" es el precio del tomador

Del OpenAPI oficial de CriptoYa
([enzonotario/criptoya-api-docs](https://github.com/enzonotario/criptoya-api-docs),
`openapi-argentina.json`), el objeto `Cotizacion` tiene exactamente cinco campos:

| Campo | Definición textual de CriptoYa |
|---|---|
| `ask` | "Precio de compra reportado por el exchange, **sin sumar comisiones**" |
| `totalAsk` | "Precio de compra final **incluyendo las comisiones de transferencia y trade**" |
| `bid` | "Precio de venta reportado por el exchange, **sin restar comisiones**" |
| `totalBid` | "Precio de venta final incluyendo las comisiones de transferencia y trade" |
| `time` | timestamp |

**No hay ningún campo de profundidad, volumen, cantidad de avisos ni límites por
orden.** Por eso ningún venue que venga sólo de CriptoYa puede pasar el filtro de
`venue_liquido`: no hay nada que medir.

Medición propia del 2026-08-29 sobre `criptoya.com/api/lemoncashp2p/usdt/ars/1000`:

```
ask 1603,6897   totalAsk 1627,745    → 1627,745 / 1603,6897 = 1,0150
bid 1595,5054   totalBid 1571,5728   → 1571,5728 / 1595,5054 = 0,9850
```

Exactamente **1,5% por punta** = el fee de tomador de Lemon.

### 4. Comisiones del P2P de Lemon

Centro de ayuda oficial, artículo actualizado el **17/01/2024**
([help.lemon.me](https://help.lemon.me/es/articles/8490732-cuales-son-y-como-funcionan-las-comisiones-para-p2p)):

- Publicar: *"cuando creás una publicación, y esta es aceptada por otro usuario,
  vas a pagar una comisión del **1%**"*.
- Tomar: *"Al momento de elegir una publicación de otro usuario, vas a pagar una
  comisión del **1.5%**"*.
- Publicar en sí no cuesta nada; sólo se cobra si alguien acepta.
- El artículo aclara que *"Los porcentajes de comisión pueden llegar a cambiar en
  un futuro de acuerdo a las condiciones del mercado"* → conviene reverificarlo
  cada tanto.

Cruzado con la cobertura del lanzamiento (mismos números: 1% publicador / 1,5%
tomador, mínimo 5 USDT):
[Cointelegraph](https://es.cointelegraph.com/news/lemon-adds-a-p2p-marketplace-to-its-platform),
[Forbes Argentina](https://www.forbesargentina.com/negocios/nuevo-mercado-p2p-crypto-argentina-como-funciona-cuales-son-sus-beneficios-n42387),
[blog de Lemon](https://lemon.me/en/blog/p2p-lemon).

El artículo **no menciona costo de retiro de pesos**; el usuario confirmó
(2026-08-29) que sacar los pesos de Lemon no le cuesta nada.

## Contradicciones e incógnitas

- **De dónde saca CriptoYa el precio de `lemoncashp2p`.** No está documentado y no
  hay repo público del backend. Puede ser un acuerdo con Lemon, un endpoint
  privado o scraping. `Incierto`. Consecuencia práctica: no sé si ese ask/bid es
  el mejor aviso del libro, un promedio, o un aviso de 5 USDT.
- **Qué "comisiones de transferencia" mete CriptoYa además del trade.** Para
  Lemon la cuenta cierra con 1,5% solo de trade, así que ahí no agrega
  transferencia — pero eso es inferencia mía de la aritmética, no un dato de
  ellos.

## Recomendación

Cae la opción de fetcher propio: **no hay orderbook público que leer.** Queda:

1. Modelar `lemoncashp2p` como venue **P2P** (hoy entra como CEX, así que el
   motor nunca le ofrece publicar), usando el **`ask`/`bid` crudo** de CriptoYa,
   no el `total*` — porque el `total*` ya trae clavado el 1,5% de tomador y
   nosotros queremos publicar.
2. Cobrarle el fee **por modo**: `maker_pct` 1,0 y `taker_pct` 1,5 en
   `config.FEE_P2P_BY_MODE`. Con eso la ruta aparece sola cuando el gap lo pague.
3. **Marcar la jugada como "sin profundidad verificada"**, porque no hay forma de
   saber si atrás de ese precio hay stock. Es el mismo riesgo que costó plata el
   21/08 y no se puede eliminar por API: se verifica entrando a la app.

Umbral medido el 2026-08-29: comprar publicando en Binance a 1592,52 y vender
publicando en Lemon a 1604,00 da +0,72% bruto y **−0,58% neto** (0,2% maker
Binance + 1,0% maker Lemon + 0,1% de red). Lemon necesita estar en **~1613** para
empatar.

## Fuentes

- [help.lemon.me — comisiones del P2P](https://help.lemon.me/es/articles/8490732-cuales-son-y-como-funcionan-las-comisiones-para-p2p) (act. 17/01/2024)
- [wiki.lemon.me — cómo funciona el P2P](https://wiki.lemon.me/es-ar/lemon-cash-app/como-funciona-el-p2p-de-lemon-intercambia-crypto-directamente-con-otros-usuarios/)
- [lemon.me/build — Mini-App SDK](https://lemon.me/build)
- [lemon.me/en/invertir-pesos](https://lemon.me/en/invertir-pesos)
- [lemon.me/en/blog/p2p-lemon](https://lemon.me/en/blog/p2p-lemon)
- [Cointelegraph — Lemon añade mercado P2P](https://es.cointelegraph.com/news/lemon-adds-a-p2p-marketplace-to-its-platform)
- [Forbes Argentina — nuevo mercado P2P](https://www.forbesargentina.com/negocios/nuevo-mercado-p2p-crypto-argentina-como-funciona-cuales-son-sus-beneficios-n42387)
- [OpenAPI de CriptoYa (enzonotario/criptoya-api-docs)](https://github.com/enzonotario/criptoya-api-docs)
- [docs.criptoya.com](https://docs.criptoya.com/)
- Medición propia contra `criptoya.com/api/lemoncashp2p/usdt/ars/1000` y sondeo de
  `api.lemoncash.com.ar` (2026-08-29).
