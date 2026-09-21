"""Configuración no-secreta del p2p-desk."""
import os
from decimal import Decimal
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

SHEET_ID: str = os.getenv("SHEET_ID", "")
GOOGLE_SERVICE_ACCOUNT_JSON: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
TRADES_DB_PATH: Path = Path(os.getenv("TRADES_DB_PATH", "./data/trades.db"))
SPREAD_LOG_PATH: Path = Path(os.getenv("SPREAD_LOG_PATH", "./data/spread_log_usdt_ars.csv"))
CAPTACION_DOCS_DIR: Path = Path(os.getenv("CAPTACION_DOCS_DIR", "./core/captacion_docs"))
VPS_API_URL: str = os.getenv("VPS_API_URL", "")
BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")
BYBIT_API_KEY: str = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET: str = os.getenv("BYBIT_API_SECRET", "")

# --- Visión para capturas por Telegram (NVIDIA, OpenAI-compatible) ---
NVIDIA_API_KEY: str = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL: str = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
# Modelos de visión GRATUITOS para leer capturas, en orden de preferencia. Se
# prueban en cadena y sólo si todos fallan se gasta una lectura de Claude.
# Bake-off 2026-09-03 (6 corridas por modelo, con y sin marca visible):
#   kimi-k3                6/6, 35-64s   <- estable, va primero
#   nemotron-3-nano-omni   4/6, 18-38s   <- más rápido pero tira 503 y JSON roto
#   llama-3.2-90b-vision   0/6           <- erraba la fecha e inventaba el exchange
#   nemotron-nano-12b-v2-vl               <- RETIRADO 2026-08-26, la API da 410
NVIDIA_VISION_MODELS: list[str] = [
    m.strip() for m in os.getenv(
        "NVIDIA_VISION_MODELS",
        "moonshotai/kimi-k3,nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    ).split(",") if m.strip()
]
NVIDIA_VISION_MODEL: str = os.getenv("NVIDIA_VISION_MODEL", NVIDIA_VISION_MODELS[0])
# Modelo de texto para el orquestador de Telegram (rutea el texto libre a una
# acción). Default = el mismo VL (también responde solo-texto).
NVIDIA_TEXT_MODEL: str = os.getenv("NVIDIA_TEXT_MODEL", NVIDIA_VISION_MODEL)

# --- Puente de sync (compañero <-> bot) ---
SYNC_BRIDGE_TOKEN: str = os.getenv("SYNC_BRIDGE_TOKEN", "")
SYNC_BRIDGE_PORT: int = int(os.getenv("SYNC_BRIDGE_PORT", "8765"))
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
# Narración LLM de las alertas de spread (ADA). Default OFF: se prende en el VPS
# cuando la auth headless de claude-agent-sdk esté resuelta. Con OFF sale el
# texto numérico (fallback), la alerta funciona igual.
SPREAD_NARRATE: bool = os.getenv("SPREAD_NARRATE", "0") == "1"
DASHBOARD_URL: str = os.getenv("DASHBOARD_URL", "http://127.0.0.1:8002")
SYNC_BRIDGE_URL: str = os.getenv("SYNC_BRIDGE_URL", "")  # http://<tailscale-ip-PC>:8765/sync
SYNC_AGENT_TOKEN: str = os.getenv("SYNC_AGENT_TOKEN", "")  # agente on-demand <-> VPS
AGENTE_EXE_PATH: Path = Path(os.getenv("AGENTE_EXE_PATH", "./dist/agente-arbitrador.exe"))

# --- Comerciante Verificado de Binance P2P ---
# Requisitos que pasó el usuario el 2026-08-28 (Argentina, estimativos). NO
# verificados contra la página oficial de Binance: si cambian, se tocan acá.
# Sólo están los 3 que se pueden medir con trades.db; el resto (antigüedad, 98%
# de finalización, KYC, depósito de garantía, tiempo de liberación) ya los tiene.
MERCHANT_OPS_30D: int = int(os.getenv("MERCHANT_OPS_30D", "400"))
MERCHANT_VOL_30D_BTC: float = float(os.getenv("MERCHANT_VOL_30D_BTC", "0.5"))
MERCHANT_VOL_HIST_BTC: float = float(os.getenv("MERCHANT_VOL_HIST_BTC", "1.0"))
MERCHANT_VENTANA_DIAS: int = int(os.getenv("MERCHANT_VENTANA_DIAS", "30"))

# --- Alertas de spread a Telegram (no-secreto) ---
# Piso duro pedido el 2026-08-28: por debajo de esto NO se avisa nada, sin
# importar lo que diga cada umbral individual. Existe porque los umbrales viven
# en el .env del VPS y uno viejo de 0,2% seguiria colando avisos que no sirven.
SPREAD_ALERT_MIN_PCT: float = float(os.getenv("SPREAD_ALERT_MIN_PCT", "0.5"))
SPREAD_ALERT_CROSS_PCT: float = float(os.getenv("SPREAD_ALERT_CROSS_PCT", "0.5"))
SPREAD_ALERT_INTRA_PCT: float = float(os.getenv("SPREAD_ALERT_INTRA_PCT", "1.0"))
SPREAD_ALERT_COSTO_PCT: float = float(os.getenv("SPREAD_ALERT_COSTO_PCT", "1.5"))
SPREAD_ALERT_HYSTERESIS_PCT: float = float(os.getenv("SPREAD_ALERT_HYSTERESIS_PCT", "0.1"))
SPREAD_ALERT_STATE_PATH: Path = Path(
    os.getenv("SPREAD_ALERT_STATE_PATH", "./data/spread_alert_state.json")
)

# --- Alerta cross-venue con modo publicar (ver plan 2026-07-02) ---
SPREAD_ALERT_MEDIA_PCT: float = float(os.getenv("SPREAD_ALERT_MEDIA_PCT", "0.5"))
SPREAD_ALERT_MM_PCT: float = float(os.getenv("SPREAD_ALERT_MM_PCT", "0.5"))
SPREAD_ALERT_INSTANT_PCT: float = float(os.getenv("SPREAD_ALERT_INSTANT_PCT", "0.5"))
# Fee % por venue (un solo lugar para tocar). Default 0.0 para claves ausentes.
# Binance cobra 0,20% (aprox conservadora, no distingue maker/taker); el resto
# de los P2P core son zero-fee; los CEX locales tienen el spread en el precio.
FEE_PCT_BY_VENUE: dict[str, float] = {
    "binancep2p": 0.2,
    "binance": 0.2,
    "bybitp2p": 0.0,
    "kucoinp2p": 0.0,
    "okexp2p": 0.0,
    "bitgetp2p": 0.0,
}

# Fee P2P separado por MODO. El de arriba (un solo número por venue) le cobra lo
# mismo al que publica y al que toma, y eso es falso: en Binance publicar cuesta
# 0,20% y tomar un aviso ya publicado cuesta un flat de centavos. Con el spread
# de USDT en ~0,2%, esa diferencia decide si publicar conviene o no.
#
# Fuentes (verificadas 2026-08-21, comunicados oficiales de Binance):
# - maker ARS 0,20% desde 2023-10-02:
#   binance.com/en/support/announcement/detail/cb2e0f8b48ea4858ac735940eda6d14d
# - taker flat 0,05 USDT desde 2024-03-19:
#   binance.com/en/support/announcement/detail/cde0427260394f17b7d0d69c56b8657f
# - taker flat 0,06-0,08 USDT desde 2025-09-22 (se toma 0,08, el peor caso):
#   binance.com/en/support/announcement/detail/70c92ace9acb45529cd4541195248c91
# El flat de tomador está anunciado SOLO para pares USDT. Para BTC no hay
# comunicado público y la tabla real pide login: se asume 0 y queda FALTA
# VERIFICAR en binance.com/en/fee/p2pFeeRate con la cuenta abierta.
# Comisión de trading del spot, para la ruta sintética ARS→USDT→BTC. Binance
# cobra 0,1% y no figura en la captura de la operación (ver memoria
# reference_binance_spot_fee).
SPOT_FEE_PCT: float = float(os.getenv("SPOT_FEE_PCT", "0.1"))

FEE_P2P_BY_MODE: dict[str, dict[str, float]] = {
    # 0,07 MEDIDO en la cuenta propia el 22/08/2026: dos órdenes de USDT del
    # mismo día (273,53 y 499,00) cobraron 0,07 las dos → es flat, no %. Antes
    # figuraba 0,08, que salía del rango anunciado (0,06-0,08) y no de un dato
    # real. Publicar (0,20%) está medido en 11 órdenes propias.
    "binancep2p": {"maker_pct": 0.20, "taker_pct": 0.0, "taker_flat_quote": 0.07},
    "okexp2p": {"maker_pct": 0.0, "taker_pct": 0.0, "taker_flat_quote": 0.0},
    "bybitp2p": {"maker_pct": 0.0, "taker_pct": 0.0, "taker_flat_quote": 0.0},
    "bitgetp2p": {"maker_pct": 0.0, "taker_pct": 0.0, "taker_flat_quote": 0.0},
    "kucoinp2p": {"maker_pct": 0.0, "taker_pct": 0.0, "taker_flat_quote": 0.0},
    # Lemon P2P: VERIFICADO 2026-08-29 en help.lemon.me (art. 8490732, act.
    # 17/01/2024) y cruzado con Cointelegraph/Forbes. Mínimo 5 USDT. Ellos avisan
    # que puede cambiar: reverificar cada tanto.
    "lemoncashp2p": {"maker_pct": 1.0, "taker_pct": 1.5, "taker_flat_quote": 0.0},
}
# Dónde puedo CREAR anuncios hoy. No es un fee ni una preferencia: el exchange
# lo tiene detrás de requisitos (órdenes, contrapartes únicas, tasa de
# finalización, volumen). Ausente = habilitado. Tomar avisos ajenos NO tiene
# requisitos, así que sólo se apaga el lado de publicar.
#
# Estado confirmado por el usuario 2026-08-29: puede publicar compra Y venta en
# Binance, OKX, Bybit y KuCoin. El único bloqueado es Bitget (captura "Unable to
# create ad": 2/5 órdenes, 0/5 usuarios únicos, 67%/80% de finalización,
# 413,63/500 USDT). Revisar cuando destrabe Bitget.
P2P_PUEDE_PUBLICAR_COMPRA: dict[str, bool] = {"bitgetp2p": False}
P2P_PUEDE_PUBLICAR_VENTA: dict[str, bool] = {"bitgetp2p": False}

# Venues que SON libros P2P (se puede publicar un aviso) pero no exponen el
# orderbook, así que el precio sale de CriptoYa. Se los arma con el ask/bid
# CRUDO, no con totalAsk/totalBid: el "total" de CriptoYa ya trae clavado el fee
# de TOMADOR (para Lemon, 1,5% exacto), y castigaría de más una jugada de
# publicar. Como no hay profundidad, la liquidez queda no medible: la jugada sale
# marcada "sin profundidad verificada" y hay que confirmarla en la app.
# Ver docs/investigacion-lemon-api-p2p.md.
P2P_SIN_PROFUNDIDAD: set[str] = {"lemoncashp2p"}

# El flat del tomador está anunciado solo para estos activos.
TAKER_FLAT_ASSETS: tuple[str, ...] = ("USDT",)

# --- Cotizador al cliente (bot: "cotizar BTC") ---
# Margen por defecto sobre el precio EJECUTABLE. Es un default, no un piso: si el
# margen no cubre el costo de darse vuelta, el cotizador avisa en vez de negarse.
COTIZA_MARGEN_PCT: float = float(os.getenv("COTIZA_MARGEN_PCT", "0.5"))

# --- Estrategia de spread on-demand (/estrategia, /hago) ---
# Haircut de fee de red (%) que se descuenta a las jugadas CROSS-venue (mover USDT
# de un venue a otro). En market-making intra-venue no aplica.
STRATEGY_NETWORK_FEE_PCT: float = float(os.getenv("STRATEGY_NETWORK_FEE_PCT", "0.1"))

# Fee de retiro de USDT, en USDT. Es un FLAT por transferencia, no un %: leído de
# /sapi/v1/capital/config/getall con la cuenta propia el 2026-09-08. El 0,1% de
# arriba castiga las rutas cross-venue hasta 100x de mas en tickets grandes.
# BSC es 150 veces mas barata que TRC20: mover por ahi cuando la contraparte la acepte.
FEE_RED_USDT_FLAT: dict[str, float] = {
    "BSC": 0.01,
    "MATIC": 0.07,
    "ARBITRUM": 0.1,
    "ETH": 0.3,
    "TRX": 1.5,
}
FEE_RED_USDT_DEFAULT: str = os.getenv("FEE_RED_USDT_DEFAULT", "BSC")

# Fee de retiro de USDT segun DE DONDE sale la plata, en USDT. El dict de arriba
# es el de Binance (su API); estos los aporto el usuario el 2026-09-12:
#   · KuCoin -> Binance por BNB Smart Chain: 0,40 USDT (dato suyo, firme)
#   · Bybit: GRATIS. El usuario lo confirmo el 2026-09-12 ("estoy seguro, hay una
#     manera de sacarlo gratis ahi"). Se modela 0 porque es la red que va a usar.
#     FALTA anotar POR QUE RED es gratis: si sale por otra, el numero cambia.
# Es un FLAT por transferencia, no por operacion: se hacen muchas compras chicas
# y se pasa una sola tanda. Por eso el motor lo divide por el tamano de la tanda.
# Tus apodos en los libros P2P, separados por coma (env MIS_NICKS_P2P). Se sacan
# del libro antes de calcular la punta: si no, el vigilante de avisos se mide
# contra tu propio aviso y nunca suena.
MIS_NICKS_P2P: tuple[str, ...] = tuple(
    n.strip() for n in os.getenv("MIS_NICKS_P2P", "").split(",") if n.strip())

# Marca que aparece en la placa de cotización al cliente y en el bot.
BRAND_NAME: str = os.getenv("BRAND_NAME", "MI CAMBIO")

FEE_RED_RETIRO_USDT: dict[str, float] = {
    "binancep2p": FEE_RED_USDT_FLAT["BSC"],
    "kucoinp2p": 0.40,
    "bybitp2p": 0.0,
}

# Comisión de red del retiro de BTC, en BTC. Sale de lo que RECIBE el cliente:
# el 03/09/2026 se retiraron 0,00509 y le entraron 0,00507. Se usa para cotizar
# sobre lo que le llega y no sobre lo que sale de la cuenta.
BTC_NETWORK_FEE: float = float(os.getenv("BTC_NETWORK_FEE", "0.00002"))
# Un venue fuera de la whitelist operable dispara el aviso solo si supera al mejor
# operable por al menos este margen (%).
STRATEGY_OUTSIDE_MARGIN_PCT: float = float(os.getenv("STRATEGY_OUTSIDE_MARGIN_PCT", "0.5"))

# Pricing del asistente de publicación (no-secreto)
TICK_ARS: Decimal = Decimal(os.getenv("TICK_ARS", "1"))
MIN_MARGIN_PCT: Decimal = Decimal(os.getenv("MIN_MARGIN_PCT", "1.0"))
# Circuit breaker: precios fuera de este rango se descartan (dato roto).
PRICE_FLOOR_ARS: Decimal = Decimal(os.getenv("PRICE_FLOOR_ARS", "500"))
PRICE_CEIL_ARS: Decimal = Decimal(os.getenv("PRICE_CEIL_ARS", "5000"))
# Defaults del anuncio
DEFAULT_AD_MIN_ARS: Decimal = Decimal(os.getenv("DEFAULT_AD_MIN_ARS", "30000"))
DEFAULT_AD_MAX_ARS: Decimal = Decimal(os.getenv("DEFAULT_AD_MAX_ARS", "150000"))
DEFAULT_METHODS: list[str] = [
    m.strip()
    for m in os.getenv("DEFAULT_METHODS", "LemonCash,MercadoPago,Uala").split(",")
    if m.strip()
]

# CriptoYa: exchanges aprobados (claves tal como las nombra CriptoYa).
# OJO: las claves deben coincidir EXACTO con como CriptoYa nombra al exchange,
# si no, el filtro las ignora en silencio (ej: "bitso" no existe, es "bitsoalpha";
# CryptoMKT es "cryptomktpro" para USDT y "cryptomkt" para USDC).
CRIPTOYA_WHITELIST: set[str] = {
    # locales / ya operados
    "binancep2p", "okexp2p", "lemoncash", "lemoncashp2p", "belo", "ripio",
    "ripioexchange", "buenbit", "satoshitango", "letsbit", "fiwind",
    "cocoscrypto", "tiendacrypto", "pluscrypto", "decrypto",
    "bitsoalpha", "cryptomktpro", "cryptomkt", "saldo",
    # core de arbitraje
    "bybit", "bybitp2p", "bitgetp2p",
    # P2P globales con ARS (suman liquidez al mejor bid/ask)
    "kucoinp2p", "mexc", "mexcp2p", "huobip2p", "bingxp2p", "coinexp2p",
    "weexp2p", "eldoradop2p",
    # convertidores/remesa que igual cotizan ARS (spread interno amplio)
    "peanut", "vibrant", "vitawallet",
    "astropay", "wallbit", "airtm", "dolarapp", "p2pme", "takenos", "grabrfi",
    # referencia spot
    "binance",
}
# Decisión del usuario (2026-06-08): pinguear TODO lo que cotice ARS/USDT|USDC.
# EXCEPCIÓN (2026-06-19): exchanges que publican PRECIOS FANTASMA — ask/bid
# irreales que no se concretan y falsean el mejor bid/ask del spread. WEEX y
# MEXC daban fantasmas casi siempre (ganaban ~la mitad de las muestras), así que
# se excluyen del cálculo de todo (historial, oportunidades, anuncios).
CRIPTOYA_BLACKLIST: set[str] = {"weexp2p", "mexcp2p", "mexc"}
# La whitelist efectiva nunca incluye exchanges blacklisteados.
CRIPTOYA_WHITELIST -= CRIPTOYA_BLACKLIST
CRIPTOYA_VOLUME: float = float(os.getenv("CRIPTOYA_VOLUME", "1000"))
# Volumen de referencia por activo. El de CriptoYa está pensado en USDT: pedir
# 1000 BTC no es un ticket, es una barbaridad, y algún venue puede filtrarlo.
# 0,01 BTC ≈ el mismo tamaño de orden en dólares que 1000 USDT.
CRIPTOYA_VOLUME_BY_ASSET: dict[str, float] = {"BTC": 0.01}
# Activos que el spread/cotizador sabe leer. Nada fuera de acá se consulta.
SPREAD_ASSETS: tuple[str, ...] = ("USDT", "BTC")

# Whitelist de ARBITRAJE (CEX->P2P): SOLO exchanges reales con retiro a ARS.
# OJO: NO es CRIPTOYA_WHITELIST (esa incluye billeteras de remesa para pinguear).
# Las de remesa (DolarApp/Takenos/Airtm/AstroPay/Wallbit/P2PMe/GrabrFi/Peanut/
# Vibrant/VitaWallet) NUNCA son destino de arbitraje (regla innegociable).
CRIPTOYA_ARBITRAGE_WHITELIST: set[str] = {
    "binance", "binancep2p", "okexp2p", "bybit", "bybitp2p", "bitgetp2p",
    "saldo", "lemoncash", "lemoncashp2p", "belo", "ripio", "ripioexchange",
    "buenbit", "satoshitango", "letsbit", "cryptomktpro", "cryptomkt",
    "fiwind", "cocoscrypto", "tiendacrypto", "pluscrypto", "bitsoalpha",
    "decrypto", "kucoinp2p",
}
# Venues que casi nunca operan (pedido 2026-09-16: "en KuCoin nunca hay mucho
# movimiento"). Siguen en la whitelist y se miden, pero en Jugadas NUNCA
# encabezan: sólo salen como alternativa marcada "poco volumen".
VENUES_SECUNDARIOS: frozenset[str] = frozenset({"kucoinp2p"})

# Billeteras de remesa/convertidores (cuentas USD): se pueden comprar USDT ahí,
# solo las etiquetamos como "remesa" para informar de qué tipo es el venue.
REMESA_VENUES: set[str] = {
    "astropay", "wallbit", "airtm", "dolarapp", "p2pme", "takenos", "grabrfi",
    "peanut", "vibrant", "vitawallet",
}
MAX_QUOTE_AGE_MIN: int = int(os.getenv("MAX_QUOTE_AGE_MIN", "30"))
SPREAD_ALERT_CEXP2P_PCT: float = float(os.getenv("SPREAD_ALERT_CEXP2P_PCT", "1.0"))

# --- Dólar / Análisis Técnico (no-secreto) ---
DOLLAR_TA_MA_SHORT: int = int(os.getenv("DOLLAR_TA_MA_SHORT", "50"))
DOLLAR_TA_MA_LONG: int = int(os.getenv("DOLLAR_TA_MA_LONG", "200"))
DOLLAR_TA_RSI_PERIOD: int = int(os.getenv("DOLLAR_TA_RSI_PERIOD", "14"))
DOLLAR_TA_DEV_THRESHOLD: Decimal = Decimal(os.getenv("DOLLAR_TA_DEV_THRESHOLD", "3"))
DOLLAR_TA_RSI_LOW: Decimal = Decimal(os.getenv("DOLLAR_TA_RSI_LOW", "35"))
DOLLAR_TA_RSI_HIGH: Decimal = Decimal(os.getenv("DOLLAR_TA_RSI_HIGH", "65"))
DOLLAR_TA_DEFAULT_WINDOW: int = int(os.getenv("DOLLAR_TA_DEFAULT_WINDOW", "200"))
