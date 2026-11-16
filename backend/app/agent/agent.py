"""
Definición del agente con Google ADK + LiteLLM + Ollama.

Componentes de un agente (según "Fundamentos de Agentes de IA"):
  - Modelo de IA      -> LiteLlm("ollama_chat/<modelo cuantizado>")
  - Instrucciones     -> construir_instrucciones (rol, objetivo, reglas, restricciones)
  - Herramientas      -> TODAS_LAS_HERRAMIENTAS (13 tools)
  - Contexto          -> RAG (consultar_base_conocimiento) + adjuntos analizados
  - Estado / memoria  -> sesión de ADK (historial de la conversación + datos del usuario)
  - Controles         -> callbacks (guardrails) + permisos en los servicios
"""
import os

from app.config import settings

os.environ["OLLAMA_API_BASE"] = settings.OLLAMA_API_BASE  # requerido por LiteLLM

from google.adk.agents.llm_agent import Agent  # noqa: E402
from google.adk.models.lite_llm import LiteLlm  # noqa: E402
from google.genai import types  # noqa: E402

from app.agent.callbacks import guardrail_entrada, guardrail_herramientas, guardrail_salida  # noqa: E402
from app.agent.instrucciones import construir_instrucciones  # noqa: E402
from app.agent.tools import TODAS_LAS_HERRAMIENTAS  # noqa: E402


def crear_modelo(nombre: str | None = None):
    kwargs = {}
    if settings.DESACTIVAR_THINKING:
        kwargs["reasoning_effort"] = "none"  # LiteLLM lo traduce a think=false en Ollama
    return LiteLlm(model=nombre or settings.MODELO_AGENTE, **kwargs)


def crear_agente(modelo=None) -> Agent:
    return Agent(
        name="techsupport_agent",
        model=modelo or crear_modelo(),
        description="Asistente de la Mesa de Ayuda de TechSupport S.A. para gestionar tickets de soporte técnico.",
        instruction=construir_instrucciones,
        tools=TODAS_LAS_HERRAMIENTAS,
        generate_content_config=types.GenerateContentConfig(
            temperature=settings.TEMPERATURA,  # baja = respuestas deterministas, menos alucinación
            max_output_tokens=1500,
        ),
        before_model_callback=guardrail_entrada,
        after_model_callback=guardrail_salida,
        before_tool_callback=guardrail_herramientas,
    )


root_agent = crear_agente()
