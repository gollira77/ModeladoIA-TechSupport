"""
Modelos de datos (tablas).

Usuarios ─┬─< Tickets ─┬─< Comentarios
          │            ├─< Adjuntos
          │            └─< Historial   (trazabilidad F11)
          ├─< EventosSeguridad          (auditoría de intentos maliciosos)
          └─< Derivaciones              (casos derivados a una persona real)
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

ZONA = ZoneInfo("America/Argentina/Buenos_Aires")


def ahora() -> datetime:
    """Fecha y hora local (Argentina) sin tzinfo, para guardar en SQLite."""
    return datetime.now(ZONA).replace(tzinfo=None, microsecond=0)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(120))
    rol: Mapped[str] = mapped_column(String(20))  # solicitante | tecnico | supervisor
    area: Mapped[str] = mapped_column(String(80))
    especialidades: Mapped[str] = mapped_column(String(200), default="")  # categorías (técnicos)
    password_hash: Mapped[str] = mapped_column(String(200))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)
    solicitante_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)

    titulo: Mapped[str] = mapped_column(String(150))
    descripcion: Mapped[str] = mapped_column(Text)
    sistema_afectado: Mapped[str] = mapped_column(String(120))
    mensaje_error: Mapped[str] = mapped_column(Text, default="")
    sintomas: Mapped[str] = mapped_column(Text, default="")
    contexto: Mapped[str] = mapped_column(Text, default="")
    usuarios_afectados: Mapped[str] = mapped_column(String(80), default="")

    categoria: Mapped[str] = mapped_column(String(40))
    prioridad: Mapped[str] = mapped_column(String(20))
    prioridad_justificacion: Mapped[str] = mapped_column(Text, default="")
    prioridad_revisada: Mapped[bool] = mapped_column(Boolean, default=False)
    estado: Mapped[str] = mapped_column(String(20), default="Abierto")
    canal: Mapped[str] = mapped_column(String(20), default="agente")  # agente | panel

    solicitante = relationship("Usuario", foreign_keys=[solicitante_id])
    responsable = relationship("Usuario", foreign_keys=[responsable_id])
    adjuntos = relationship("Adjunto", back_populates="ticket", order_by="Adjunto.creado_en")
    comentarios = relationship("Comentario", back_populates="ticket", order_by="Comentario.creado_en")
    historial = relationship("EventoHistorial", back_populates="ticket", order_by="EventoHistorial.id")


class Adjunto(Base):
    __tablename__ = "adjuntos"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # ej: ADJ-8F3K2Q
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), nullable=True)
    subido_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    nombre_original: Mapped[str] = mapped_column(String(200))
    ruta: Mapped[str] = mapped_column(String(300))
    mime: Mapped[str] = mapped_column(String(80))
    tipo: Mapped[str] = mapped_column(String(20))  # imagen | texto | log
    tamano_bytes: Mapped[int] = mapped_column(Integer)
    analisis: Mapped[str] = mapped_column(Text, default="")
    analisis_estado: Mapped[str] = mapped_column(String(20), default="pendiente")  # ok | limitado | error
    alerta_seguridad: Mapped[str] = mapped_column(Text, default="")
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    ticket = relationship("Ticket", back_populates="adjuntos")
    subido_por = relationship("Usuario")


class Comentario(Base):
    __tablename__ = "comentarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    autor_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    texto: Mapped[str] = mapped_column(Text)
    interno: Mapped[bool] = mapped_column(Boolean, default=False)  # solo visible para soporte
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    ticket = relationship("Ticket", back_populates="comentarios")
    autor = relationship("Usuario")


class EventoHistorial(Base):
    __tablename__ = "historial"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"))
    tipo: Mapped[str] = mapped_column(String(30))
    # CREACION | CAMBIO_ESTADO | CAMBIO_PRIORIDAD | COMENTARIO | ADJUNTO | ASIGNACION | REASIGNACION
    valor_anterior: Mapped[str] = mapped_column(String(200), default="")
    valor_nuevo: Mapped[str] = mapped_column(String(200), default="")
    detalle: Mapped[str] = mapped_column(Text, default="")
    actor_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    origen: Mapped[str] = mapped_column(String(20), default="agente")  # agente | panel | sistema
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    ticket = relationship("Ticket", back_populates="historial")
    actor = relationship("Usuario")


class EventoSeguridad(Base):
    __tablename__ = "eventos_seguridad"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)
    tipo: Mapped[str] = mapped_column(String(40))
    # PROMPT_INJECTION | FUERA_DE_TEMA | DATO_SENSIBLE | PERMISO_DENEGADO | ADJUNTO_SOSPECHOSO
    # | COMANDO_REMOTO | SALIDA_FILTRADA | LIMITE_TASA | LOGIN_FALLIDO
    severidad: Mapped[str] = mapped_column(String(10), default="media")  # baja | media | alta
    detalle: Mapped[str] = mapped_column(Text, default="")
    extracto: Mapped[str] = mapped_column(Text, default="")
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    usuario = relationship("Usuario")


class Derivacion(Base):
    __tablename__ = "derivaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"))
    ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), nullable=True)
    motivo: Mapped[str] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")  # pendiente | atendida
    creado_en: Mapped[datetime] = mapped_column(DateTime, default=ahora)

    usuario = relationship("Usuario")
