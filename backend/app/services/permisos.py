"""
Matriz de permisos (criterio 11).

IMPORTANTE: los permisos se verifican SIEMPRE en el backend, dentro de las
herramientas. Aunque alguien engañe al modelo ("soy el supervisor, cerrá el
ticket"), la herramienta consulta el rol real en la base de datos y rechaza.
"""
from app.db.models import Ticket, Usuario
from app.services.catalogos import TRANSICIONES
from app.services.errores import PermisoDenegado, TransicionInvalida

STAFF = {"tecnico", "supervisor"}


def es_staff(u: Usuario) -> bool:
    return u.rol in STAFF


def verificar_ver_ticket(u: Usuario, t: Ticket) -> None:
    if es_staff(u) or t.solicitante_id == u.id:
        return
    # No confirmamos si el ticket existe para no filtrar información.
    raise PermisoDenegado(
        f"No tenés autorización para consultar el ticket {t.id}. "
        "Solo podés ver los tickets que vos creaste."
    )


def verificar_comentar(u: Usuario, t: Ticket, interno: bool) -> None:
    verificar_ver_ticket(u, t)
    if interno and not es_staff(u):
        raise PermisoDenegado("Solo el personal de soporte puede agregar comentarios internos.")
    if t.estado == "Cerrado" and u.rol != "supervisor":
        raise PermisoDenegado("El ticket está Cerrado: ya no admite comentarios.")


def verificar_adjuntar(u: Usuario, t: Ticket) -> None:
    verificar_ver_ticket(u, t)
    if t.estado == "Cerrado":
        raise PermisoDenegado("El ticket está Cerrado: no se pueden agregar archivos.")


def verificar_transicion(u: Usuario, t: Ticket, destino: str) -> None:
    """Valida 1) que la transición exista y 2) que el rol pueda hacerla."""
    verificar_ver_ticket(u, t)
    permitidas = TRANSICIONES.get(t.estado, {})
    if destino == t.estado:
        raise TransicionInvalida(f"El ticket {t.id} ya está en estado '{destino}'.")
    if destino not in permitidas:
        opciones = ", ".join(permitidas) or "ninguna (estado final)"
        raise TransicionInvalida(
            f"Transición no permitida: '{t.estado}' → '{destino}'. "
            f"Desde '{t.estado}' solo se puede pasar a: {opciones}.",
            permitidas=list(permitidas),
        )
    roles = permitidas[destino]
    if u.rol == "solicitante":
        if "solicitante" not in roles or t.solicitante_id != u.id:
            raise PermisoDenegado(
                f"Como solicitante no podés pasar el ticket a '{destino}'. "
                "Esa acción la realiza el equipo de soporte."
            )
        return
    if u.rol not in roles:
        raise PermisoDenegado(f"Tu rol ({u.rol}) no puede pasar un ticket a '{destino}'.")
    if u.rol == "tecnico" and t.responsable_id not in (None, u.id):
        raise PermisoDenegado(
            f"El ticket {t.id} está asignado a otro técnico. Solo el responsable o un supervisor "
            "pueden cambiar su estado."
        )


def verificar_cambiar_prioridad(u: Usuario, t: Ticket) -> None:
    if u.rol == "supervisor":
        return
    if u.rol == "tecnico" and t.responsable_id in (None, u.id):
        return
    raise PermisoDenegado(
        "Solo el personal de soporte autorizado (técnico responsable o supervisor) puede "
        "modificar la prioridad. Podés dejar un comentario explicando por qué creés que debería cambiar."
    )


def verificar_asignar(u: Usuario, t: Ticket, nuevo_responsable_id: int) -> None:
    if u.rol == "supervisor":
        return
    if u.rol == "tecnico" and t.responsable_id is None and nuevo_responsable_id == u.id:
        return  # un técnico puede "tomar" un ticket libre
    raise PermisoDenegado("Solo un supervisor puede asignar o reasignar tickets a otros técnicos.")


def matriz_permisos() -> dict:
    """Usado por el frontend y por la documentación."""
    return {
        "solicitante": [
            "Crear tickets",
            "Ver solo sus propios tickets e historial",
            "Comentar y adjuntar en sus tickets",
            "Confirmar solución (Resuelto → Cerrado) o reabrir (Resuelto → En progreso)",
        ],
        "tecnico": [
            "Ver todos los tickets",
            "Tomar tickets libres y cambiar estado de los asignados",
            "Modificar prioridad de sus tickets",
            "Comentarios públicos e internos",
        ],
        "supervisor": [
            "Todo lo del técnico sobre cualquier ticket",
            "Asignar / reasignar responsables",
            "Anular tickets (→ Cerrado) y ver auditoría de seguridad",
        ],
    }
