"""
Configuración central de la aplicación.

Todos los valores se leen desde variables de entorno (archivo .env) para poder
cambiar de modelo, de rutas o de límites SIN tocar el código.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # carpeta backend/
load_dotenv(BASE_DIR / ".env")


def _bool(nombre: str, defecto: bool) -> bool:
    return os.getenv(nombre, str(defecto)).strip().lower() in {"1", "true", "si", "sí", "yes"}


class Settings:
    # --- Ollama / modelos -------------------------------------------------
    OLLAMA_API_BASE: str = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
    # Modelo que razona y usa herramientas (el que cuantizamos nosotros).
    MODELO_AGENTE: str = os.getenv("MODELO_AGENTE", "ollama_chat/qwen3.5:4b_K_M")
    # Modelo con capacidad "vision" para leer capturas y fotos.
    MODELO_VISION: str = os.getenv("MODELO_VISION", "qwen3.5:4b")
    # Modelo de embeddings para el RAG.
    MODELO_EMBEDDINGS: str = os.getenv("MODELO_EMBEDDINGS", "nomic-embed-text")
    TEMPERATURA: float = float(os.getenv("TEMPERATURA", "0.1"))
    # Qwen3.5 es un modelo de razonamiento: apagamos el "thinking" para que sea más rápido.
    DESACTIVAR_THINKING: bool = _bool("DESACTIVAR_THINKING", True)

    # --- Rutas --------------------------------------------------------------
    DATA_DIR: Path = BASE_DIR / "data"
    DB_URL: str = os.getenv("DB_URL", f"sqlite:///{BASE_DIR / 'data' / 'techsupport.db'}")
    SESIONES_DB_URL: str = os.getenv(
        "SESIONES_DB_URL", f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'sesiones_agente.db'}"
    )
    VECTOR_DIR: str = os.getenv("VECTOR_DIR", str(BASE_DIR / "data" / "vector_store"))
    UPLOADS_DIR: Path = Path(os.getenv("UPLOADS_DIR", str(BASE_DIR / "data" / "uploads")))

    # --- Seguridad ----------------------------------------------------------
    JWT_SECRET: str = os.getenv("JWT_SECRET", "cambiar-este-secreto-en-produccion")
    JWT_EXPIRA_MINUTOS: int = int(os.getenv("JWT_EXPIRA_MINUTOS", "480"))
    MAX_MENSAJE_CARACTERES: int = int(os.getenv("MAX_MENSAJE_CARACTERES", "4000"))
    MAX_ARCHIVO_MB: int = int(os.getenv("MAX_ARCHIVO_MB", "8"))
    MENSAJES_POR_MINUTO: int = int(os.getenv("MENSAJES_POR_MINUTO", "12"))
    # Usuario usado SOLO cuando se prueba con `adk web` (no hay login allí).
    ADK_WEB_USUARIO_DEMO: str = os.getenv("ADK_WEB_USUARIO_DEMO", "")

    # --- RAG / duplicados ---------------------------------------------------
    UMBRAL_DUPLICADO: float = float(os.getenv("UMBRAL_DUPLICADO", "0.55"))
    CORS_ORIGINS: list[str] = os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")


settings = Settings()
settings.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("OLLAMA_API_BASE", settings.OLLAMA_API_BASE)
