"""Parseo de capturas de operaciones P2P usando Claude (Agent SDK / login Max).

La llamada al SDK está aislada en `_ask_claude` para poder mockearla en tests.
El parseo del texto a dict (`_extract_fields`) es puro y testeable.
"""
import json
import tempfile
from pathlib import Path

_MIME_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}

PROMPT = (
    "Mirá la captura de pantalla de una operación P2P de cripto y devolvé "
    "SOLO un objeto JSON (sin texto alrededor) con estas claves: "
    "side ('COMPRA' si el usuario compró cripto / pagó ARS, 'VENTA' si vendió cripto), "
    "date (YYYY-MM-DD), order_id (string), usd_gross (monto de cripto), "
    "commission, price (precio ARS por unidad), total_ars, "
    "exchange_coin (ej 'Binance / USDT'), bank (banco o método de pago). "
    "Usá null en los campos que no puedas leer. No inventes valores."
)


def _extract_fields(raw_text: str) -> dict:
    """Extrae el primer objeto JSON válido del texto de Claude.

    Busca desde la primera '{' y decodifica un único objeto JSON, ignorando
    cualquier texto antes o después (markdown, explicaciones, llaves de más).
    """
    start = raw_text.find("{")
    if start == -1:
        raise ValueError(f"No se encontró JSON en la respuesta: {raw_text!r}")
    try:
        obj, _ = json.JSONDecoder().raw_decode(raw_text[start:])
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON inválido en la respuesta: {raw_text!r}") from exc
    return obj


#: Techo para el fallback a Claude. Sin esto el bot contesta "leyendo la
#: captura…" y no vuelve nunca (visto el 08/09/2026): para el usuario es peor
#: que un error, porque no sabe si seguir esperando.
CLAUDE_TIMEOUT_S: float = 90.0


def _run_sync(coro_factory, timeout: float | None = None):
    """Corre una corutina de forma síncrona, haya o no un event loop andando.

    `asyncio.run()` explota si ya hay un loop en el hilo actual, que es
    exactamente el caso del bot de Telegram: el 2026-09-08 una captura de KuCoin
    se perdió por eso ("asyncio.run() cannot be called from a running event
    loop"). Cuando hay loop, la corutina se corre en un hilo aparte con el suyo.

    Recibe una FÁBRICA y no una corutina para no crearla en el hilo equivocado.
    Corta a los `timeout` segundos con TimeoutError: colgado para siempre es
    peor que un error, porque el usuario no sabe si esperar.
    """
    import asyncio
    import concurrent.futures

    limite = CLAUDE_TIMEOUT_S if timeout is None else timeout

    async def _con_limite():
        return await asyncio.wait_for(coro_factory(), timeout=limite)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_con_limite())
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(lambda: asyncio.run(_con_limite()))
        # +5s de gracia: el que corta es el wait_for de adentro, que además
        # cancela la corutina en vez de dejarla huérfana.
        return fut.result(timeout=limite + 5)


def _ask_claude(prompt: str, image_path: str) -> str:
    """Llama a Claude vía Agent SDK (login Max) y devuelve el texto de la respuesta.

    Se ejecuta el query async de claude-agent-sdk de forma síncrona.
    """
    import asyncio

    from claude_agent_sdk import ClaudeAgentOptions, query

    full_prompt = f"{prompt}\n\nLa imagen está en: {image_path}"

    async def _run() -> str:
        chunks: list[str] = []
        async for message in query(
            prompt=full_prompt,
            options=ClaudeAgentOptions(allowed_tools=["Read"]),
        ):
            for block in getattr(message, "content", []) or []:
                text = getattr(block, "text", None)
                if text:
                    chunks.append(text)
        return "\n".join(chunks)

    return _run_sync(_run)


def parse_screenshot(image_bytes: bytes, mime: str) -> dict:
    """Guarda la imagen a un temporal, la manda a Claude y devuelve los campos."""
    ext = _MIME_EXT.get(mime, ".png")
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name
    try:
        raw = _ask_claude(PROMPT, tmp_path)
        return _extract_fields(raw)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
