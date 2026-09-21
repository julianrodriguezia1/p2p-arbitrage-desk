# P2P Arbitrage Desk — contexto del proyecto

> Se carga en cada sesión: mantenerlo **corto y cierto**. El detalle vive en
> `docs/`; acá van sólo las reglas innegociables, el mapa del
> repo y lo que falta.

## Skills del proyecto (`.claude/skills/`)

- **actualizar-movimientos** — cuando el usuario pide "actualizar/cargar los
  movimientos", "las operaciones de hoy" o "sincronizar Binance": correr
  `cli/sync_binance.py` (preview con `n`, luego `--today`/`--date` y `s`).
  Ver `.claude/skills/actualizar-movimientos/SKILL.md`.

- **preparar-anuncio** — cuando el usuario pide "prepará un anuncio", "a qué
  precio publico/vendo/compro": correr `cli/prepare_ad.py` (sugiere precio
  competitivo + por margen, no publica). Ver
  `.claude/skills/preparar-anuncio/SKILL.md`.

- **cargar-captura** — cuando el usuario manda una captura/foto de una operación
  P2P (Lemon/Bitget/Binance) para cargar: parsear, confirmar (ojo maña Lemon del
  monto redondo) y cargar con `cli/add_movement`. Pensado para que mande el screen
  por Telegram y se cargue. Ver `.claude/skills/cargar-captura/SKILL.md`.

- **cotizar-cliente** — cuando un cliente manda PESOS y hay que cotizarle cripto:
  "cotizar BTC para Daniel", "a cuánto le vendo 500 mil en USDT". Corre
  `cli/cotizar_cliente.py` y devuelve 3 renglones (qué comprar, a cuánto
  cotizarle, cuánto se gana). BTC siempre por ARS→USDT→spot. No carga la op.
  Ver `.claude/skills/cotizar-cliente/SKILL.md`.

- **estrategia-spread** — cuando el usuario pide "la estrategia", "¿qué hago?",
  "¿qué me conviene?", "dónde gano más spread" o tipea `/estrategia` / `/hago`:
  pega a `GET /api/estrategia` del VPS y da la mejor jugada ahora (neta de comisiones
  + fee de red) con hasta 2 alternativas. Ver `.claude/skills/estrategia-spread/SKILL.md`.

- **optimizar-jugadas** — el escalón de arriba: cuando pide "buscá oportunidades",
  "optimizá la estrategia", "armame una estrategia", "dónde gano más con volumen"
  o tipea `/jugadas` / `/optimizar`. Compara TODAS las rutas y rankea por **plata
  por hora, no por porcentaje** (un 2% sobre un libro que no opera rinde cero),
  filtrando los libros sin volumen. Ver `.claude/skills/optimizar-jugadas/SKILL.md`.

## Agentes del proyecto (`.claude/agents/`)

- **matematico** — auditar cualquier cuenta del repo (spreads, fees, VWAP,
  promedios, volúmenes) o buscar estrategias cuantificadas para las metas de
  Binance P2P. Recalcula por otro camino y reporta ✔/✘/FALTA.

---

## 0. Contexto del proyecto

Sistema modular en Python para un trader de arbitraje USDT/BTC contra ARS en
Argentina que opera P2P en Binance, OKX, Bybit y otros venues. Agiliza toda la
operatoria: precios ejecutables, jugadas netas de comisiones, carga de
operaciones, alertas y bot de Telegram.

**Regla de negocio innegociable (la más importante):**
- Para arbitraje SOLO se usan exchanges con orderbook real y retiro a ARS.
- **Whitelist:** Binance, OKX, Bybit, Lemon, Belo, Ripio, Buenbit, Satoshitango,
  CryptoMKT, LetsBit, Fiwind, CocosCrypto, TiendaCrypto, PlusCrypto, Bitso, Decrypto,
  KuCoin (P2P, aprobado 2026-07-01: zero-fee, orderbook real, retiro a ARS vía P2P).
- **Blacklist (NUNCA como destino de arbitraje, aunque aparezcan en CriptoYa):**
  DolarApp, Takenos, GrabrFi, Airtm, Wallbit, AstroPay, P2PMe. Son cuentas
  USD/remesa, no operatoria cripto/ARS.

**Regla de seguridad innegociable:**
- NUNCA liberar cripto solo con un comprobante/captura. Liberar únicamente
  cuando el dinero impactó de verdad en la cuenta bancaria. Ninguna
  automatización debe saltarse este paso.

**Regla de alertas a Telegram (2026-08-28):** nada por debajo de **0,5% neto**.
El piso es `SPREAD_ALERT_MIN_PCT` en `config.py` y se aplica en
`cli/spread_alert.py` sobre TODOS los umbrales, para que un `.env` viejo del VPS
no cuele avisos más chicos.

**Regla de BTC (medida 2026-08-22/23, ver `docs/investigacion-prima-btc-alts-ars.md`):**

El BTC contra pesos está torcido **de un solo lado**: es caro para COMPRAR y
normal para VENDER. Todo lo que sigue sale de traducir los precios a *fx
implícito* = `precio_ARS / precio_USD_del_activo`, que es lo único que hace
comparable un BTC de 124 millones con un USDT de 1.588.

- **NUNCA comprar BTC por el libro P2P.** Se arma siempre por
  `ARS → USDT (P2P) → BTC (spot, 0,1%)`. Medido: comprar BTC directo salía
  1.602,66 de fx contra 1.589,09 por la ruta sintética = **13.573 ARS de ahorro
  cada 1.000 USD (0,85%; el día anterior 1,2%)**.
- **Vender BTC por el libro P2P sí está bien**: rinde igual que vender USDT
  (1.582,46 vs 1.582,02 de fx). O sea que si un cliente trae BTC y quiere pesos,
  **se le puede pagar casi la cotización del USDT** — no corresponde
  descontarle "porque es BTC".
- **El ancho del libro de BTC (1,55% vs 0,18% del USDT) NO es un spread
  cobrable**: cruzar las dos puntas pierde 0,5%-1,4%. Es una *prima de
  conveniencia del lado de la compra* y se cobra publicando la venta, no
  tomando.
- Si se publica en BTC, **el aviso va FLOTANTE** (ratio sobre el índice), nunca
  a precio fijo: a precio fijo sólo te toman cuando el movimiento te juega en
  contra. El 62% de los avisos de BTC repreciaron en 19 min contra el 8% en
  USDT.
- Herramientas: `python -m cli.prima_alt` (foto en vivo) y
  `python -m cli.prima_report` (serie histórica del logger del VPS).

---

## 1. Mapa del repo (lo que EXISTE, verificado 2026-08-24)

```
config.py          whitelist/blacklist, fees por venue y por modo, umbrales
p2p_scanner.py     fetchers P2P públicos (binance/okx/bybit/bitget/kucoin) + Ad
core/              motores puros, sin red, con tests:
  criptoya         CEX locales · spot · dolar_ref · dollar_ta
  p2p_depth        precio ejecutable por profundidad (VWAP con mín/máx por orden)
  arb_matrix       las 3 jugadas (media/mm/instant) tomar-vs-publicar
  strategy         ranking + venue_liquido (descarta libros sin volumen)
  prima_alt        prima de lo no-stablecoin vs USDT
  merchant         progreso hacia el Comerciante Verificado de Binance P2P
  rutas            grafo completo: TODOS los ciclos ARS→…→ARS, por plata/hora
  trades_db        clients_db · movements · sheet_writer (planilla + SQLite)
  capture_parser   screenshot_parser · orchestrator (bot que entiende criollo)
cli/               entradas de línea de comando (sync, spread, prima, rutas)
webapp/server.py   FastAPI del dashboard; sirve el HTML y las /api/*
bot/               Telegram (comandos, cotizar, capturas, ops de cliente)
companion/         app de bandeja: fetch residencial y push al VPS (evita el 451)
deploy/            units de systemd + READMEs de deploy
templates/         speeches de captación y plantillas de campaña
docs/              investigaciones con los números crudos
```

**El VPS es la fuente única.** Dashboard 24/7, los syncs privados de
Binance/Bybit corren en la PC (desde un VPS dan 451) y pushean. Ver `deploy/`.

---

## 2. Lo único grande que FALTA: `bot/market_maker.py`

Market-making por API oficial de merchant (nunca automatizando la web).
Spec completa y salvaguardas: `docs/spec-market-maker.md`. Leerla antes de
tocar el tema.

---

## 3. Stack y convenciones

- Python 3.11+, type hints en todo. `requests` para HTTP, `sqlite3` de stdlib.
- Secrets SIEMPRE en `.env` (gitignored). Firmas HMAC-SHA256, cada exchange
  tiene su esquema.
- **TDD**: test que falla primero. La suite entera tiene que quedar verde
  (`python -m pytest -q`).
- Los motores de `core/` son **puros y sin red**: la red vive en los `cli/`,
  `webapp/` y los fetchers. Por eso se pueden testear sin mocks de HTTP.
- Nunca afirmar una comisión de memoria: está en `config.py`.

---

## 4. Ahorro de tokens

Reglas de ahorro de tokens, recortadas a lo medido y sin repetir
las reglas de respuesta que ya están en el `CLAUDE.md` global.

**Leer**
- Sólo el rango de líneas que hace falta. `grep`/`rg` antes de abrir un archivo
  entero. Apuntar al archivo (`@core/arb_matrix.py`), no "buscá en el repo".
- No releer un archivo recién editado para verificar: la herramienta ya habría
  fallado.

**Escribir**
- Editar lo que cambia; no reescribir el archivo entero por tres líneas.

**Comandos**
- Filtrar en el comando, no después: `| head`, `| grep ERROR`, `-q`.
  `python -m pytest -q`, no `-v`, salvo que se esté depurando un test puntual.
- Si se filtra de más se corren más comandos y se pierde lo ganado.

**Sesión**
- `/clear` entre tareas sin relación: es gratis, compactar es caro.
- Fijar modelo y esfuerzo al arrancar y no cambiarlos: cada cambio invalida la
  caché y recomputa el pedido entero.

**Subagentes**
- Sólo cuando la tarea quema muchos tokens para devolver pocos (correr la
  suite, leer logs del VPS, explorar código). Ahorran contexto, no dinero.
- Nunca para tareas cortas: un subagente gastó ~8.700 tokens en un commit que
  el agente principal hace con ~200.

**Mantenimiento**
- Cada línea de este archivo se paga en cada mensaje. Si se agrega una regla,
  sacar otra. Regla que no se puede atar a un número medido, se saca.

