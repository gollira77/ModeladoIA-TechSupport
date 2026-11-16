"""Registro de eventos de seguridad y derivaciones a personas reales."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Derivacion, EventoSeguridad, Usuario
from app.services.errores import PermisoDenegado

CONTACTO_MESA_AYUDA = {
    "canal": "Mesa de Ayuda TechSupport S.A. (atención humana)",
    "email": "mesadeayuda@techsupport.com.ar",
    "interno": "4500",
    "horario": "Lunes a viernes de 8 a 18 h",
}


def registrar_evento(db: Session, usuario_id: int | None, tipo: str, detalle: str = "", extracto: str = "",
                     severidad: str = "media") -> None:
    db.add(EventoSeguridad(usuario_id=usuario_id, tipo=tipo, detalle=detalle[:500], extracto=(extracto or "")[:300],
                           severidad=severidad))


def crear_derivacion(db: Session, actor: Usuario, motivo: str, ticket_id: int | None = None) -> dict:
    motivo = (motivo or "").strip()[:500] or "Consulta que el asistente no puede responder con la información disponible."
    d = Derivacion(usuario_id=actor.id, motivo=motivo, ticket_id=ticket_id)
    db.add(d)
    db.flush()
    return {
        "resultado": "derivado",
        "numero_derivacion": f"DER-{d.id:04d}",
        "mensaje": "La consulta fue derivada a una persona del equipo de soporte, que se va a contactar.",
        "contacto": CONTACTO_MESA_AYUDA,
    }


def listar_eventos(db: Session, actor: Usuario, limite: int = 100) -> list[dict]:
    if actor.rol != "supervisor":
        raise PermisoDenegado("Solo un supervisor puede ver la auditoría de seguridad.")
    eventos = db.scalars(select(EventoSeguridad).order_by(EventoSeguridad.id.desc()).limit(limite)).all()
    return [
        {"id": e.id, "fecha": e.creado_en.strftime("%d/%m/%Y %H:%M:%S"), "tipo": e.tipo, "severidad": e.severidad,
         "usuario": e.usuario.nombre if e.usuario else "anónimo", "detalle": e.detalle, "extracto": e.extracto}
        for e in eventos
    ]


def listar_derivaciones(db: Session, actor: Usuario) -> list[dict]:
    if actor.rol not in ("tecnico", "supervisor"):
        raise PermisoDenegado("Solo el personal de soporte puede ver las derivaciones.")
    ds = db.scalars(select(Derivacion).order_by(Derivacion.id.desc()).limit(100)).all()
    return [
        {"id": f"DER-{d.id:04d}", "fecha": d.creado_en.strftime("%d/%m/%Y %H:%M"), "usuario": d.usuario.nombre,
         "motivo": d.motivo, "ticket_id": d.ticket_id, "estado": d.estado}
        for d in ds
    ]
