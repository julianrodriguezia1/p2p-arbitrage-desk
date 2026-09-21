"""Narración en criollo de las alertas de spread. Toma las alertas ya
computadas (los mismos objetos que van a format_message) y, si hay un
generador LLM disponible, reescribe el mensaje numérico como una call directa
en criollo. Ante cualquier falla, ausencia de generador, salida vacía o con
nomenclatura interna ('ask'/'bid'), devuelve el texto numérico — la alerta
SIEMPRE sale."""
from __future__ import annotations

import re
from typing import Callable

from core.spread_alert import format_message


def _build_prompt(numeric: str) -> str:
    return (
        "Sos el asistente de una mesa de arbitraje P2P USDT/ARS en Argentina. "
        "Abajo hay una o más jugadas de spread con los números EXACTOS ya calculados:\n\n"
        f"{numeric}\n\n"
        "Reescribí cada jugada como una call corta y directa en criollo argentino "
        "para avisarle al trader; no fusiones ni descartes ninguna. NO inventes ni "
        "cambies ningún número, venue ni porcentaje: usá SOLO los que están arriba. "
        "No uses las palabras 'ask' ni 'bid'. Devolvé SOLO el mensaje, sin preámbulo."
    )


def narrate(alerts: list, *, generate: Callable[[str], str] | None = None) -> str:
    """Texto a mandar por Telegram. Con `generate` (LLM) reescribe en criollo;
    sin él o ante cualquier problema, devuelve format_message(alerts)."""
    fallback = format_message(alerts)
    if not fallback or generate is None:
        return fallback
    try:
        text = generate(_build_prompt(fallback))
    except Exception:
        return fallback
    if not text or not text.strip():
        return fallback
    low = text.lower()
    if re.search(r"\b(ask|bid)\b", low):
        return fallback
    return text.strip()


def ada_generate(prompt: str) -> str:
    """Adapter LLM vía claude-agent-sdk (suscripción ADA). Devuelve el texto.
    Puede fallar si la auth headless no está resuelta en el VPS — narrate lo
    captura y cae al fallback numérico."""
    import asyncio

    from claude_agent_sdk import ClaudeAgentOptions, query

    system = (
        "Sos el asistente de una mesa de arbitraje P2P USDT/ARS en Argentina. "
        "Escribís calls cortas, directas y en criollo argentino. Nunca inventás "
        "números ni usás las palabras 'ask'/'bid'."
    )

    async def _run() -> str:
        chunks: list[str] = []
        async for message in query(prompt=prompt, options=ClaudeAgentOptions(system_prompt=system)):
            for block in getattr(message, "content", []) or []:
                text = getattr(block, "text", None)
                if text:
                    chunks.append(text)
        return "\n".join(chunks).strip()

    return asyncio.run(_run())


def default_generate() -> Callable[[str], str] | None:
    """El adapter ADA si config.SPREAD_NARRATE está activo, si no None (fallback)."""
    import config

    return ada_generate if config.SPREAD_NARRATE else None
