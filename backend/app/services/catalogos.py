"""
Reglas de negocio de TechSupport S.A. expresadas como DATOS.

Esto es lo que el agente NO puede cambiar: el LLM propone, pero el código decide.
Los mismos textos están en data/conocimiento/*.md para que el RAG los pueda consultar.
"""

CATEGORIAS = [
    "Hardware",
    "Software",
    "Redes y conectividad",
    "Sistemas y aplicaciones",
    "Accesos y permisos",
    "Infraestructura",
    "Otros",
]

PRIORIDADES = ["Baja", "Media", "Alta", "Crítica"]

ESTADOS = ["Abierto", "En revisión", "En progreso", "Pendiente", "Resuelto", "Cerrado"]

ROLES = ["solicitante", "tecnico", "supervisor"]

# Transiciones permitidas:  estado_actual -> {estado_destino: roles que pueden hacerla}
# "solicitante" significa "el solicitante DUEÑO del ticket".
TRANSICIONES: dict[str, dict[str, set[str]]] = {
    "Abierto": {
        "En revisión": {"tecnico", "supervisor"},
        "Cerrado": {"supervisor"},  # anulación (ej. duplicado confirmado)
    },
    "En revisión": {
        "En progreso": {"tecnico", "supervisor"},
        "Pendiente": {"tecnico", "supervisor"},
        "Cerrado": {"supervisor"},
    },
    "En progreso": {
        "Pendiente": {"tecnico", "supervisor"},
        "Resuelto": {"tecnico", "supervisor"},
    },
    "Pendiente": {
        "En progreso": {"tecnico", "supervisor"},
        "En revisión": {"tecnico", "supervisor"},
        "Cerrado": {"supervisor"},
    },
    "Resuelto": {
        "Cerrado": {"solicitante", "tecnico", "supervisor"},  # el solicitante confirma la solución
        "En progreso": {"solicitante", "tecnico", "supervisor"},  # reapertura: "no se solucionó"
    },
    "Cerrado": {},  # estado final
}

# Sinónimos para que el agente (o el usuario) pueda escribir los valores con libertad.
_SINONIMOS_ESTADO = {
    "abierto": "Abierto", "nuevo": "Abierto",
    "en revision": "En revisión", "en revisión": "En revisión", "revision": "En revisión", "revisión": "En revisión",
    "en progreso": "En progreso", "progreso": "En progreso", "en curso": "En progreso",
    "pendiente": "Pendiente", "en espera": "Pendiente",
    "resuelto": "Resuelto", "solucionado": "Resuelto",
    "cerrado": "Cerrado", "finalizado": "Cerrado",
}
_SINONIMOS_PRIORIDAD = {
    "baja": "Baja", "low": "Baja",
    "media": "Media", "medium": "Media", "normal": "Media",
    "alta": "Alta", "high": "Alta", "urgente": "Alta",
    "critica": "Crítica", "crítica": "Crítica", "critical": "Crítica",
}
_SINONIMOS_CATEGORIA = {
    "hardware": "Hardware",
    "software": "Software",
    "redes": "Redes y conectividad", "red": "Redes y conectividad", "conectividad": "Redes y conectividad",
    "redes y conectividad": "Redes y conectividad",
    "sistemas": "Sistemas y aplicaciones", "aplicaciones": "Sistemas y aplicaciones",
    "sistemas y aplicaciones": "Sistemas y aplicaciones",
    "accesos": "Accesos y permisos", "permisos": "Accesos y permisos", "accesos y permisos": "Accesos y permisos",
    "infraestructura": "Infraestructura",
    "otros": "Otros", "otro": "Otros",
}


def _norm(v: str | None) -> str:
    return (v or "").strip().lower()


def normalizar_estado(v: str | None) -> str | None:
    return _SINONIMOS_ESTADO.get(_norm(v))


def normalizar_prioridad(v: str | None) -> str | None:
    return _SINONIMOS_PRIORIDAD.get(_norm(v))


def normalizar_categoria(v: str | None) -> str | None:
    return _SINONIMOS_CATEGORIA.get(_norm(v))


def transiciones_desde(estado: str) -> list[str]:
    return list(TRANSICIONES.get(estado, {}).keys())
