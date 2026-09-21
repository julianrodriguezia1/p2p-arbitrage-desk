# Investigación: El Dorado P2P (eldorado.io) — ¿es confiable para vender USDT?

**Fecha:** 2026-07-03 · **Contexto:** apareció como venue "paga más caro" (~1602 ARS) al vender USDT en el dashboard de arbitraje. El usuario sospecha que es peligroso. Objetivo: saber si es seguro operar antes de mandar fondos.

---

## Resumen ejecutivo

- **NO es una estafa ni un fly-by-night.** Es una fintech real, con nombre y apellido de fundadores, respaldada por fondos cripto de primer nivel (Coinbase Ventures, Multicoin Capital, **Paradigm**), ~1.000.000 de usuarios y **registro PSAV en la CNV argentina (N° 63)**. Está *más* regulada en Argentina que la mayoría de los P2P globales. **[Sólido]**
- **Tu instinto no está del todo errado**, pero por otra razón: es una plataforma **más chica y más joven que Binance**, con **menos liquidez**, **menos historial arbitrando disputas** y un **lío regulatorio serio en Venezuela** (allanamiento al CEO en junio 2025). Riesgo ≠ estafa. **[Sólido]**
- **El modelo P2P es idéntico al de Binance:** escrow custodial automático, la cripto se traba hasta que vos confirmás que cobraste. No hay auto-liberación. Tu regla de "nunca liberar sin plata en el banco" aplica igual. **[Sólido]**
- **Reputación mixta pero no alarmante:** Google Play **4,5★ con ~50.000 reseñas** (muestra masiva, positiva) vs Trustpilot **2,7★ con ~63 reseñas** (muestra chica, sesgada a quejas de disputas P2P). Las quejas graves son de **estafas de contraparte** (comprador/vendedor), no de robo de la plataforma. **[Probable]**
- **El precio alto (~1600) viene con un spread ANCHO (~2,5% bid/ask), típico de mercado premium/remesa, no de P2P líquido.** En la misma foto de CriptoYa: eldoradop2p ask 1585 / bid 1546 (~2,5%) vs Binance/OKX/Bybit P2P ~0,3-0,8%. Se parece a un CEX local (Buenbit/SatoshiTango), no a Binance. El "paga más caro" es real pero hay que ver profundidad. **[Sólido]**
- **SÍ retira a ARS de verdad** (CVU/CBU, Mercado Pago, Lemon, Belo, Brubank, Ualá, BBVA, Prex) y está en CriptoYa como `eldoradop2p`. Fee de plataforma **0,25% al que publica** (maker); el taker paga poco/nada. **[Sólido]**
- **Veredicto:** operable **con cautela y en montos chicos** (KYC completo + 2FA + tratarlo como cualquier P2P). No para mandar todo el volumen sin probar primero.

---

## Hallazgos por tema

### 1. Empresa, fundadores e historia — **[Sólido]**

- Fundada por **cuatro venezolanos**: **Guillermo Goncalvez Espiga** (CEO, hoy en Colombia; MIT Technology Review "Innovadores menores de 35" 2024), **Juan Carlos Andreu** (CTO, Portugal), **Alessandro Cecere** (CMO, Brasil) y **Carlos Fontes** (Portugal).
- El equipo viene de minería cripto en Venezuela desde ~2013. **Fundación formal 2018-2019**, lanzamiento público de la app **diciembre 2020**, expansión a toda LATAM **enero 2023**. La motivación (huir de la hiperinflación venezolana) está bien documentada.
- **Sede actual: Bogotá, Colombia.** Fuentes: [Forbes Colombia (may-2024)](https://forbes.co/2024/05/23/emprendedores/el-dorado-atrae-us3-millones-para-su-billetera-de-pagos-con-criptomonedas), [Chainwire (ene-2025)](https://chainwire.org/2025/01/21/stablecoin-powered-superapp-el-dorado-crosses-500000-users/), [Bitcoin.com](https://news.bitcoin.com/el-dorado-ceo-venezuela-highlights-stablecoins-use-case-as-a-tool-for-resilience/).

> ⚠️ **No confundir con `eldorado.gg`** (marketplace de cuentas de videojuegos, empresas GWD Processing FZCO / Halfway House OÜ) ni con la **"Eldorado ransomware"** (grupo de cibercrimen). Son cosas totalmente distintas. Varias reseñas negativas de "compra de cuentas / el soporte apoya al vendedor" que aparecen en Google **son del sitio de gaming, no del cripto.**

### 2. Estructura legal y regulación — **[Sólido]**

| Entidad | Jurisdicción | Rol |
|---|---|---|
| **El Dorado Trade SAS** | Bogotá, Colombia | Operadora principal (miembro Colombia Fintech) |
| **El Dorado Labs S.R.L.** | CABA, Argentina (CUIT 30-71856888-5) | **PSAV registrado en CNV N° 63 (5-ago-2024)** |
| EL DORADO MT LLC | Florida, EE.UU. | Rol no especificado |

- **Registro PSAV en la CNV (RG 994/2024): N° 63 (5-ago-2024).** Es un plus real — muchos venues que pingeás no tienen registro formal en Argentina. **Caveat honesto:** el N° 63 sale del propio [About Us](https://eldorado.io/en/about-us)/T&C y del CUIT verificado en [Dateas](https://www.dateas.com/en-us/empresa/el-dorado-labs-srl-30718568885), pero un agente consultó el registro público de la CNV y la tabla figuraba vacía (posible problema de render o desactualización). Autoatribución muy probable, no confirmada al 100% en el registro oficial en vivo. **[Probable]**
- **Ley aplicable en los T&C: República de Panamá** (foro de disputas = tribunales de Panamá). Si algo sale mal, reclamás bajo derecho panameño, no argentino — es más incómodo. **[Sólido]**
- Los T&C permiten **retener fondos indefinidamente** si banean la cuenta por "sospecha de fraude", hasta que resuelva una "autoridad competente". Cláusula estándar pero amplia — riesgo real si hay un falso positivo AML. **[Sólido]**
- Certificaciones ISO 27001/27017/27018/27701 (autodeclaradas, seguridad de la info, **no** licencias financieras).

### 3. Cómo opera el P2P (escrow / custodia) — **[Sólido]**

- **Custodial durante la operación con escrow automático**, igual que Binance P2P:
  1. El vendedor publica su oferta (los USDT ya están en su wallet interno de El Dorado).
  2. Cuando alguien acepta, **la plataforma traba automáticamente los USDT del vendedor** en escrow.
  3. El comprador paga ARS **fuera de la plataforma** (Mercado Pago / transferencia).
  4. El vendedor **confirma manualmente** que cobró → recién ahí se liberan los USDT.
  5. **No hay liberación por temporizador ni automática.** Requiere tu confirmación activa.
- **Disputas:** las arbitra un equipo humano de El Dorado. Apelás dentro de 3 días hábiles, juntan evidencia hasta 48 hs, verificación hasta 10 días hábiles. Si el comprador no pagó → la cripto vuelve al vendedor; si vos no liberás habiendo cobrado → la liberan al comprador. **[Sólido / SLA exacto Incierto]**
- **Producto aparte:** hay un wallet *self-custodial* (Safe/Gnosis, USDM sobre Arbitrum) que **no es** el P2P operativo — no lo mezcles.
- Fuentes: [blog "Depósitos en garantía"](https://eldorado.io/es/blog/que-son-depositos-en-garantia/), [guía P2P oficial](https://eldorado.io/en/blog/welcome-to-el-dorado-p2p), [Safe Foundation](https://safefoundation.org/blog/el-dorado-integrates-safe-for-its-stablecoin-self-custodial-wallet).

**Métodos de pago ARS (Sólido, FAQ oficial):** CVU/CBU, Mercado Pago, Lemon Cash, Belo, Brubank, Ualá, Reba, BBVA, Banco del Sol, Prex. O sea: **sí cobrás pesos en tu banco/billetera** (te transfiere la contraparte). Par USDT/ARS directo.

**Fees (Sólido, blog oficial + anuncio en X oct-2024):** maker (el que publica) **0,25%** por orden; taker poco/nada; depósito USDT gratis; retiro USDT <200 = 0,99 USDT + red, ≥200 = 0,5% + red. Más caro que OKX/Bybit/KuCoin (0%), más barato que Lemon (1%).

**Para ser merchant/publicar anuncios:** KYC Nivel 2 + 5 operaciones completadas + 7 días de cuenta, mínimo 1 USDT por aviso, **sin depósito congelado** (a diferencia de KuCoin, que pide 200-500 USDT trabados — dato relevante para tu [[project_kucoin_merchant]]). No hay API pública de merchant documentada → no se puede automatizar el posteo de anuncios. **[Sólido / API Incierto]**

**Implicancia para vos:** el riesgo de "auto-liberar por comprobante" no existe (la plata queda trabada hasta tu OK). Tu regla innegociable aplica idéntica.

### 4. Seguridad y KYC — **[Sólido]**

- **2FA: solo TOTP** (Google Authenticator / Authy). No hay SMS ni email OTP. [faq oficial](https://faq.eldorado.io/en/articles/12356332-how-to-enable-two-factor-authentication-2fa-on-your-account).
- **Dispositivos autorizados** (máx. 3), con **bloqueo de 48 hs** al entrar desde IP/dispositivo nuevo (no podés crear órdenes ni retirar en ese lapso). [blog Authorized Devices](https://eldorado.io/en/blog/authorized-devices-el-dorado).
- **KYC en 4 niveles vía SumSub:** Nivel 2 (DNI + selfie) = **10.000 USDT/mes**; Nivel 3 (declaración financiera) = 250.000/mes; Nivel 4 = 1.000.000/mes. DNI argentino aceptado. [KYC levels](https://eldorado.io/en/blog/kyc-levels-el-dorado).
- **Sin evidencia de hackeo/brecha de eldorado.io.** (La "Eldorado ransomware" es otra cosa sin relación.) **[Sólido]**

### 5. Reputación y opiniones de usuarios — **[Probable]**

| Fuente | Rating | Muestra | Lectura |
|---|---|---|---|
| **Google Play** | **4,5★** | **~49.900 reseñas** / 1M+ descargas | Muestra masiva, sentimiento **positivo**. App cripto más bajada en Venezuela 2024. |
| **Trustpilot** | **2,7★** | ~63 reseñas | Muestra chica, sesgada a quejas (60% 5★ / 30% 1★, la empresa no responde). |
| **App Store (iOS)** | **4,9★** | ~1.500 | Volumen bajo para 1M usuarios (sesgo de selección). |

- **Un caso puntual leído directo en App Store (12-may-2025, "Joalllll"):** *"tenía dinero en la cuenta y cuando pedí la devolución me bloquearon la cuenta"* — bloqueo al pedir retiro. Caso aislado, no un patrón, pero es la red flag más seria del lado vendedor y engancha con la cláusula de retención de los T&C.

- **Quejas recurrentes (Trustpilot 1★):** estafas de **contraparte** (te estafa el otro usuario), soporte que en disputas "toma partido", falta de reembolso. **Ojo:** parte de estas quejas están contaminadas por confusión con eldorado.gg (gaming).
- **Elogios recurrentes:** servicio rápido, buena atención, "vale la pena aunque el precio sea un poco más alto".
- **No pude abrir Trustpilot ni un hilo de Reddit directamente** (403 / sin resultados) — el 2,7★/63 viene de snippets consistentes en dos búsquedas, por eso lo marco **Probable** y no Sólido.

### 6. Tracción y respaldo — **[Sólido]**

- **500.000 usuarios** (ene-2025, Chainwire) → **1M+** hoy. ARR $2,7M, 12× de crecimiento en 2024, 5M+ transacciones.
- **Fondeo ~$12,4M** en tres rondas: pre-seed ~$450k (**Berkeley SkyDeck**, no Y Combinator), **Seed $3M** (jun-2024, **Multicoin Capital** lead + **Coinbase Ventures**), **Serie A $9M** (jun-2026, **Paradigm** lead + Coinbase Ventures + Verda). [CoinDesk (jun-2024)](https://www.coindesk.com/business/2024/06/04/multicoin-coinbase-ventures-invest-in-latin-american-stablecoin-powered-superapp-el-dorado).
- Que **Paradigm** (uno de los mejores fondos cripto del mundo: Uniswap, dYdX) lidere la Serie A es una señal fuerte de que no es humo.

---

## La señal de alarma real: Venezuela (junio 2025) — **[Sólido]**

- El **31-may-2025 El Dorado cerró operaciones en Venezuela** y en **junio 2025 la Policía Nacional Bolivariana allanó propiedades del CEO Goncalvez**; 25+ personas detenidas en el mismo operativo. Se enmarca en la **persecución del régimen de Maduro al mercado del dólar paralelo** (el precio de El Dorado se usaba como referencia del paralelo). Fuentes: Efecto Cocuyo, El Nacional, CriptoNoticias (jun-2025).
- **Lectura correcta:** es **persecución política**, no una causa por estafa/fraude. Paradójicamente muestra que la plataforma era económicamente relevante. **No afecta directamente tus fondos en Argentina**, pero sí dice que la empresa opera en terreno geopolítico caliente y que un gobierno puede forzarle un cierre con plazos de retiro. Es riesgo de gobernanza, no de robo.

---

## Contradicciones e incógnitas

- **Trustpilot 2,7★/63:** no pude abrir la página (403); número tomado de snippets. Además mezcla reseñas con eldorado.gg. → **Probable.**
- **Reddit:** no encontré hilos sustanciales en español sobre experiencias reales en Argentina. Vacío honesto — no significa "todo bien", significa poca discusión pública.
- **Fees P2P exactos para maker/taker en Argentina:** no publicados en el landing; se ven dentro de la app. → **Incierto.**
- **Año de fundación:** las fuentes oscilan 2017/2018/2019 según si cuentan la etapa de minería, la constitución de la SAS o el lanzamiento. → converge en **2018-2019**.

---

## Recomendación para tu operatoria

1. **Es seguro *probarlo*, no es una estafa.** Empezá con **montos chicos** (una operación testigo), KYC Nivel 2 + **2FA TOTP activado**, y tratalo como cualquier P2P: **no des por cobrado hasta que el ARS impacte en tu banco.**
2. **Verificá que el precio de ~1600 sea profundidad real, no un fantasma.** Al ser P2P *publicás y esperás*: mirá cuánto stock hay a ese precio y si los anuncios tienen reputación. El premium de El Dorado es real (mercado remesa/paralelo) pero la liquidez es más fina que Binance/KuCoin.
3. **Ojo con el bloqueo de 48 hs** al entrar desde un dispositivo/IP nuevo: si vas a operar rápido, logueate y autorizá el dispositivo **antes**, no en el momento.
4. **No está en tu whitelist de arbitraje** (`CRIPTOYA_ARBITRAGE_WHITELIST`) — hoy solo se pingea como referencia (`eldoradop2p`). Si después de probar te convence, es decisión tuya sumarlo; cumple los criterios (retiro ARS + registro CNV), pero yo lo dejaría como **venue secundario de baja exposición** hasta tener tu propia experiencia de disputa/retiro.
5. **Riesgo de gobernanza a monitorear:** la empresa tuvo un cierre forzado en Venezuela. No mantengas saldos grandes parkeados ahí; entrás, vendés, retirás a tu CBU, salís.

---

## Fuentes

- [El Dorado — About Us](https://eldorado.io/en/about-us) · [Homepage](https://eldorado.io) — consultado 2026-07-03
- [Forbes Colombia — ronda seed, may-2024](https://forbes.co/2024/05/23/emprendedores/el-dorado-atrae-us3-millones-para-su-billetera-de-pagos-con-criptomonedas)
- [CoinDesk — Multicoin/Coinbase invierten, jun-2024](https://www.coindesk.com/business/2024/06/04/multicoin-coinbase-ventures-invest-in-latin-american-stablecoin-powered-superapp-el-dorado)
- [Chainwire — 500k usuarios, ene-2025](https://chainwire.org/2025/01/21/stablecoin-powered-superapp-el-dorado-crosses-500000-users/)
- [Blog — Depósitos en garantía / escrow](https://eldorado.io/es/blog/que-son-depositos-en-garantia/)
- [Blog — Guía P2P](https://eldorado.io/en/blog/welcome-to-el-dorado-p2p) · [KYC levels](https://eldorado.io/en/blog/kyc-levels-el-dorado) · [Dispositivos autorizados](https://eldorado.io/en/blog/authorized-devices-el-dorado)
- [FAQ — 2FA](https://faq.eldorado.io/en/articles/12356332-how-to-enable-two-factor-authentication-2fa-on-your-account)
- [Safe Foundation — wallet self-custodial](https://safefoundation.org/blog/el-dorado-integrates-safe-for-its-stablecoin-self-custodial-wallet)
- [Trustpilot — eldorado.io](https://www.trustpilot.com/review/eldorado.io) (2,7★, no accesible directo, vía snippets)
- [Google Play — El Dorado](https://play.google.com/store/apps/details?id=io.eldorado.app) (4,5★)
- [Colombia Fintech — El Dorado Trade](https://colombiafintech.co/miembros/el-dorado-trade/) · [Dateas — El Dorado Labs SRL](https://www.dateas.com/en-us/empresa/el-dorado-labs-srl-30718568885)
- Venezuela (jun-2025): Efecto Cocuyo, El Nacional, CriptoNoticias (persecución dólar paralelo / cierre)
- CriptoYa API `eldoradop2p/usdt/ars` — verificado 2026-07-03 (ask 1585 / totalAsk 1600,69 / bid 1546 / totalBid 1530,94)
