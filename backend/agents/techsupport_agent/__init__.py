"""
Paquete para probar el agente con la interfaz de ADK:

    cd backend
    adk web agents

(En adk web no hay login: el usuario de prueba se define con ADK_WEB_USUARIO_DEMO en .env)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # carpeta backend/

from . import agent  # noqa: E402,F401
