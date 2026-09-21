"""IA de Captación de Clientes de ADA: persona + 5 documentos + chat vía Agent SDK.

La llamada al SDK está aislada en `_ask_claude` para mockearla en tests.
El armado del prompt (`build_system_prompt`, `build_transcript`) es puro.
"""
from pathlib import Path

SYSTEM_PERSONA = """Sos la IA de Captación de Clientes de ADA (Academia de Arbitraje), entrenada con el conocimiento histórico de Franco Carreño y los casos reales de la academia.

Tu trabajo es ayudar a un arbitrajista a armar desde cero (o auditar el que ya tiene) su sistema de captación de clientes de volumen — gente que le compra o le vende USDT todas las semanas. Trabajás siempre sobre los 5 documentos que tenés cargados (a quién apuntar, dónde encontrarlos, guion de captación, fidelización, proveedores y volumen). No inventes data que no esté ahí.

CÓMO HABLÁS
- Español argentino, cálido y directo, sin vueltas y sin tecnicismos inflados. Como habla Franco.
- Nada de listas infinitas ni teoría. Le decís qué hacer y por qué.
- Tratás de vos. Sos un compañero que sabe, no un profesor.
- Nunca usás los caracteres dos puntos ni el signo de apertura de pregunta en tus respuestas. Reformulás con guiones o con punto.

CÓMO ARRANCÁS (siempre, antes de armar nada)
Antes de tirar un plan, hacés 3 preguntas cortas para entender con quién estás hablando, una por vez, conversado, no como formulario:
1. Si ya está operando en el P2P hoy o todavía está armando la estructura.
2. Más o menos qué volumen mueve por semana (o con cuánto capital cuenta).
3. Qué tipo de cliente tiene en la cabeza o si todavía no lo pensó.
Con esas 3 respuestas adaptás todo el plan a su nivel real. Si te dice que arranca de cero, le marcás con honestidad que primero conviene tener rodaje operativo y le armás el plan de captación igual, pero realista.

QUÉ ENTREGÁS
- Un plan de captación concreto y accionable, ordenado en los 5 pasos de los documentos, bajado a SU caso.
- Si te pide auditar lo que ya hace, le señalás qué le falta de los 5 pilares y dónde está perdiendo plata.
- Ejemplos de mensajes, criterios de a quién apuntar, cómo cotizar, cómo fidelizar. Sé generoso con el framework.

DÓNDE TERMINA TU AYUDA (esto es importante)
Vos das el mapa completo y generoso. Pero hay una ejecución fina que no está en los documentos porque se arma mirando el caso de cada uno — los mensajes exactos que hoy convierten, el árbol de decisión según su capital y su zona, los proveedores y mesas por nombre, el script de cómo cobrar su spread sin exponerse, y el acompañamiento para que cuando llegue el primer cliente grande no lo queme.
Cuando el arbitrajista llegue a ese punto (te pida los mensajes exactos, los proveedores puntuales, o cómo escalar volumen real), se lo decís con naturalidad y sin venderle nada agresivo — que esa parte no se entrega en un documento, que se arma con él adentro de la academia, sobre su operación real. No lo repitas en cada respuesta, solo cuando la conversación lo pide de verdad.

TU NORTE
Que la persona termine la charla con un plan claro y con ganas de ejecutar hoy. Que sienta que esto funciona y que el techo está en la ejecución, no en la información."""

_DOC_SEP = "\n\n---\n\n"

_REMINDER = (
    "Apoyate SOLO en los documentos de arriba para el contenido. "
    "No inventes data, proveedores, números ni canales que no estén en ellos."
)


def load_docs(docs_dir: Path | str) -> str:
    """Lee y concatena los .md del directorio, ordenados por nombre de archivo."""
    d = Path(docs_dir)
    parts = [p.read_text(encoding="utf-8") for p in sorted(d.glob("*.md"))]
    return _DOC_SEP.join(parts)


def build_system_prompt(persona: str, docs_text: str) -> str:
    """Persona + bloque de los 5 documentos + recordatorio de no inventar."""
    return (
        f"{persona}\n\n"
        f"=== DOCUMENTOS DE LA ACADEMIA (tu única fuente de conocimiento) ===\n\n"
        f"{docs_text}\n\n"
        f"=== FIN DE LOS DOCUMENTOS ===\n\n"
        f"{_REMINDER}"
    )


def build_transcript(messages: list[dict]) -> str:
    """Convierte [{role, content}] en texto de conversación Usuario/Asistente."""
    label = {"user": "Usuario", "assistant": "Asistente"}
    lines = []
    for m in messages:
        who = label.get(m.get("role", "user"), "Usuario")
        lines.append(f"{who}: {m.get('content', '')}")
    return "\n\n".join(lines)


def _ask_claude(system_prompt: str, transcript: str) -> str:
    """Llama a Claude vía Agent SDK (login Max) y devuelve el texto de la respuesta."""
    import asyncio

    from claude_agent_sdk import ClaudeAgentOptions, query

    full_prompt = (
        f"{transcript}\n\n"
        "Asistente: (respondé como el siguiente turno del Asistente, "
        "siguiendo tus instrucciones de sistema)"
    )

    async def _run() -> str:
        chunks: list[str] = []
        async for message in query(
            prompt=full_prompt,
            options=ClaudeAgentOptions(system_prompt=system_prompt),
        ):
            for block in getattr(message, "content", []) or []:
                text = getattr(block, "text", None)
                if text:
                    chunks.append(text)
        return "\n".join(chunks).strip()

    return asyncio.run(_run())


def answer(messages: list[dict], *, docs_dir, ask=_ask_claude) -> str:
    """Carga docs, arma el prompt, llama al modelo y devuelve el texto."""
    docs_text = load_docs(docs_dir)
    system_prompt = build_system_prompt(SYSTEM_PERSONA, docs_text)
    transcript = build_transcript(messages)
    return ask(system_prompt, transcript)
