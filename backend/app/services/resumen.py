"""F12: resúmenes agrupados por estado, categoría y prioridad."""
from collections import Counter
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Ticket, Usuario, ahora
from app.services import permisos
from app.services.catalogos import CATEGORIAS, ESTADOS, PRIORIDADES, normalizar_categoria
from app.services.tickets import ticket_resumido

ACTIVOS = {"Abierto", "En revisión", "En progreso", "Pendiente"}


def generar_resumen(db: Session, actor: Usuario, periodo_dias: int | None = None, categoria: str | None = None) -> dict:
    q = select(Ticket)
    alcance = "todos los tickets"
    if not permisos.es_staff(actor):
        q = q.where(Ticket.solicitante_id == actor.id)
        alcance = f"tickets de {actor.nombre}"
    if periodo_dias:
        dias = max(1, min(int(periodo_dias), 365))
        q = q.where(Ticket.creado_en >= ahora() - timedelta(days=dias))
        alcance += f" de los últimos {dias} días"
    if categoria and normalizar_categoria(categoria):
        q = q.where(Ticket.categoria == normalizar_categoria(categoria))
        alcance += f" (categoría {normalizar_categoria(categoria)})"
    tickets = db.scalars(q).all()

    por_estado = Counter(t.estado for t in tickets)
    por_categoria = Counter(t.categoria for t in tickets)
    por_prioridad = Counter(t.prioridad for t in tickets)
    activos = [t for t in tickets if t.estado in ACTIVOS]
    criticos = [t for t in activos if t.prioridad in ("Crítica", "Alta")]
    criticos.sort(key=lambda t: (0 if t.prioridad == "Crítica" else 1, t.creado_en))

    cruce = {
        c: {p: sum(1 for t in tickets if t.categoria == c and t.prioridad == p) for p in PRIORIDADES}
        for c in CATEGORIAS if por_categoria.get(c)
    }
    sin_asignar = sum(1 for t in activos if t.responsable_id is None)
    prioridad_sin_revisar = sum(1 for t in activos if not t.prioridad_revisada)

    return {
        "alcance": alcance,
        "generado": ahora().strftime("%d/%m/%Y %H:%M"),
        "total": len(tickets),
        "activos": len(activos),
        "por_estado": {e: por_estado.get(e, 0) for e in ESTADOS},
        "por_categoria": {c: por_categoria.get(c, 0) for c in CATEGORIAS},
        "por_prioridad": {p: por_prioridad.get(p, 0) for p in PRIORIDADES},
        "categoria_x_prioridad": cruce,
        "activos_sin_asignar": sin_asignar if permisos.es_staff(actor) else None,
        "prioridades_pendientes_de_revision": prioridad_sin_revisar if permisos.es_staff(actor) else None,
        "urgentes_activos": [ticket_resumido(t) for t in criticos[:10]],
    }
