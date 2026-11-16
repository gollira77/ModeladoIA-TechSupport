"""
CONTROLES del agente (callbacks de Google ADK).

ADK permite "enganchar" funciones antes/después de cada llamada al modelo y a cada
herramienta. Las usamos como GUARDRAILS deterministas:

  before_model_callback  -> filtra la ENTRADA (injection, datos sensibles, fuera de tema,
                            usuario bloqueado) y acumula la "evidencia" (lo que dijo el usuario).
  after_model_callback   -> filtra la SALIDA (secretos, emails, fuga del prompt, <think>).
  before_tool_callback   -> controla las HERRAMIENTAS (límite de llamadas por turno,
                            herramientas solo-soporte, saneamiento de argumentos).

Si un callback devuelve algo, ADK usa eso en lugar de llamar al modelo/herramienta.
"""
from __future__ import annotations

import logging
import re
from datetime import timedelta

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.adk.tools import BaseTool, ToolContext
from google.genai import types
from sqlalchemy import func, select

from app.db.database import get_db
from app.db.models import EventoSeguridad, ahora
from app.services.auditoria import registrar_evento
from app.services.seguridad import analizar_entrada, redactar_salida

log = logging.getLogger("guardrails")

MARCA_ADJUNTOS = "<<ADJUNTOS_ANALIZADOS>>"
MAX_HERRAMIENTAS_POR_TURNO = 10
MAX_EVIDENCIA = 20000
HERRAMIENTAS_SOLO_SOPORTE = {"cambiar_prioridad", "asignar_ticket"}
INTENTOS_PARA_BLOQUEO = 3
MINUTOS_BLOQUEO = 15

RESPUESTA_BLOQUEADO = (
    "Por razones de seguridad, el asistente quedó temporalmente bloqueado para tu usuario debido a "
    f"varios intentos de uso indebido. Podrás volver a usarlo en {MINUTOS_BLOQUEO} minutos. Si necesitás "
    "ayuda urgente, comunicate con la Mesa de Ayuda: mesadeayuda@techsupport.com.ar (interno 4500)."
)


def _texto(content: types.Content | None) -> str:
    if not content or not content.parts:
        return ""
    return "\n".join(p.text for p in content.parts if getattr(p, "text", None))


def usuario_bloqueado(usuario_id: int | None) -> bool:
    """Bloqueo temporal si hubo N intentos graves (severidad alta) en la ventana de tiempo."""
    if not usuario_id:
        return False
    with get_db() as db:
        n = db.scalar(
            select(func.count(EventoSeguridad.id)).where(
                EventoSeguridad.usuario_id == usuario_id,
                EventoSeguridad.severidad == "alta",
                EventoSeguridad.creado_en >= ahora() - timedelta(minutes=MINUTOS_BLOQUEO),
            )
        )
    return (n or 0) >= INTENTOS_PARA_BLOQUEO


def evaluar_mensaje_usuario(usuario_id: int | None, texto_usuario: str):
    """
    Evalúa el mensaje escrito por el usuario. Devuelve (respuesta_bloqueo | None, notas_para_modelo).
    Lo usan el callback (adk web) y la API (antes de llamar al agente).
    """
    if usuario_bloqueado(usuario_id):
        return RESPUESTA_BLOQUEADO, []
    r = analizar_entrada(texto_usuario)
    if r.tipo:
        with get_db() as db:
            registrar_evento(db, usuario_id, r.tipo,
                             detalle="Mensaje bloqueado por guardrail de entrada" if r.bloquear
                             else "Advertencia agregada al contexto del modelo",
                             extracto=r.extracto or texto_usuario[:200], severidad=r.severidad)
    if r.bloquear:
        if usuario_bloqueado(usuario_id):
            return RESPUESTA_BLOQUEADO, []
        return r.respuesta, []
    return None, r.notas_para_modelo


def _respuesta(texto: str) -> LlmResponse:
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=texto)]))


# ---------------------------------------------------------------------------
# ENTRADA
# ---------------------------------------------------------------------------
def guardrail_entrada(callback_context: CallbackContext, llm_request: LlmRequest) -> LlmResponse | None:
    estado = callback_context.state
    if estado.get("temp:entrada_revisada"):
        return None  # ya se revisó este mensaje (el modelo se llama varias veces por turno)
    estado["temp:entrada_revisada"] = True

    completo = _texto(callback_context.user_content)
    texto_usuario = completo.split(MARCA_ADJUNTOS)[0]

    # Evidencia: todo lo que el usuario informó (texto + adjuntos analizados). Se usa para
    # verificar que el agente no invente mensajes de error al crear tickets.
    estado["evidencia"] = (estado.get("evidencia", "") + "\n" + completo)[-MAX_EVIDENCIA:]

    if estado.get("canal") == "web":
        return None  # la API web ya evaluó este mensaje ANTES de enviarlo al agente

    bloqueo, notas = evaluar_mensaje_usuario(estado.get("usuario_id"), texto_usuario)
    if bloqueo:
        return _respuesta(bloqueo)
    if notas and llm_request.contents:
        llm_request.contents[-1].parts.append(
            types.Part(text="\n[NOTA DEL SISTEMA DE SEGURIDAD] " + " ".join(notas))
        )
    return None


# ---------------------------------------------------------------------------
# SALIDA
# ---------------------------------------------------------------------------
_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)


def guardrail_salida(callback_context: CallbackContext, llm_response: LlmResponse) -> LlmResponse | None:
    if not llm_response.content or not llm_response.content.parts:
        return None
    cambiado = False
    permitidos = {callback_context.state.get("usuario_email", "").lower()} - {""}
    for parte in llm_response.content.parts:
        if not getattr(parte, "text", None) or getattr(parte, "thought", False):
            continue
        original = parte.text
        limpio = _THINK.sub("", original).strip() if "<think>" in original.lower() else original
        limpio, hallazgos = redactar_salida(limpio, permitidos)
        if hallazgos:
            with get_db() as db:
                registrar_evento(db, callback_context.state.get("usuario_id"), "SALIDA_FILTRADA",
                                 detalle="Se enmascaró contenido en la respuesta: " + ", ".join(sorted(set(hallazgos))),
                                 severidad="alta" if "FUGA_PROMPT" in hallazgos else "baja")
        if limpio != original:
            parte.text = limpio
            cambiado = True
    return llm_response if cambiado else None


# ---------------------------------------------------------------------------
# HERRAMIENTAS
# ---------------------------------------------------------------------------
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def guardrail_herramientas(tool: BaseTool, args: dict, tool_context: ToolContext) -> dict | None:
    estado = tool_context.state
    n = int(estado.get("temp:llamadas_herramientas", 0)) + 1
    estado["temp:llamadas_herramientas"] = n
    if n > MAX_HERRAMIENTAS_POR_TURNO:
        return {"resultado": "error", "tipo": "limite_operaciones",
                "mensaje": "Se alcanzó el máximo de operaciones para este mensaje. Respondé con lo que ya tenés."}

    if tool.name in HERRAMIENTAS_SOLO_SOPORTE and estado.get("usuario_rol") == "solicitante":
        with get_db() as db:
            registrar_evento(db, estado.get("usuario_id"), "PERMISO_DENEGADO",
                             f"Solicitante intentó usar {tool.name}", severidad="media")
        return {"resultado": "error", "tipo": "permiso_denegado",
                "mensaje": "Esta operación es exclusiva del personal de soporte. El usuario puede dejar un comentario "
                           "en su ticket explicando lo que necesita."}

    # Saneamiento de argumentos: sin caracteres de control y con largo máximo.
    for k, v in list(args.items()):
        if isinstance(v, str):
            args[k] = _CONTROL.sub("", v)[:4000]
    log.info("Herramienta %s (usuario %s) args=%s", tool.name, estado.get("usuario_id"),
             {k: (v[:60] if isinstance(v, str) else v) for k, v in args.items()})
    return None
