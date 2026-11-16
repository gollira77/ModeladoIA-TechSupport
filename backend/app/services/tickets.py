"""
Servicio de tickets: TODA la lógica de negocio vive acá.

Lo usan dos "clientes":
  - las herramientas del agente (app/agent/tools.py)
  - el panel web (app/api/routes_tickets.py)

Así las reglas (permisos, transiciones, historial) se aplican igual sin importar
si el cambio lo pidió una persona desde el panel o el agente desde el chat.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Adjunto, Comentario, EventoHistorial, Ticket, Usuario, ahora
from app.rag import vector_store
from app.services import permisos
from app.services.catalogos import (
    CATEGORIAS, ESTADOS, PRIORIDADES, TRANSICIONES, normalizar_categoria, normalizar_estado,
    normalizar_prioridad,
)
from app.services.duplicados import buscar_posibles_duplicados
from app.services.errores import NoEncontrado, ValidacionError

FMT = "%d/%m/%Y %H:%M"
ESTADOS_QUE_EXIGEN_COMENTARIO = {"Pendiente", "Resuelto", "Cerrado"}


def _f(d: datetime | None) -> str:
    return d.strftime(FMT) if d else ""


# ---------------------------------------------------------------------------
# Serialización (qué datos ve cada rol)
# ---------------------------------------------------------------------------
def ticket_resumido(t: Ticket) -> dict:
    return {
        "id": t.id,
        "titulo": t.titulo,
        "estado": t.estado,
        "prioridad": t.prioridad,
        "categoria": t.categoria,
        "creado": _f(t.creado_en),
        "solicitante": t.solicitante.nombre if t.solicitante else "",
        "responsable": t.responsable.nombre if t.responsable else "Sin asignar",
    }


def ticket_detallado(t: Ticket, actor: Usuario) -> dict:
    staff = permisos.es_staff(actor)
    comentarios = [c for c in t.comentarios if staff or not c.interno]
    return {
        **ticket_resumido(t),
        "actualizado": _f(t.actualizado_en),
        "descripcion": t.descripcion,
        "sistema_afectado": t.sistema_afectado,
        "mensaje_error": t.mensaje_error,
        "sintomas": t.sintomas,
        "contexto": t.contexto,
        "usuarios_afectados": t.usuarios_afectados,
        "prioridad_justificacion": t.prioridad_justificacion,
        "prioridad_revisada_por_soporte": t.prioridad_revisada,
        "canal": t.canal,
        "solicitante_area": t.solicitante.area if t.solicitante else "",
        "transiciones_posibles": _transiciones_para(actor, t),
        "adjuntos": [
            {"id": a.id, "nombre": a.nombre_original, "tipo": a.tipo, "analisis_estado": a.analisis_estado}
            for a in t.adjuntos
        ],
        "comentarios": [
            {"autor": c.autor.nombre, "rol": c.autor.rol, "fecha": _f(c.creado_en), "texto": c.texto,
             **({"interno": c.interno} if staff else {})}
            for c in comentarios
        ],
    }


def _transiciones_para(actor: Usuario, t: Ticket) -> list[str]:
    """Solo las transiciones que ESTE usuario puede hacer (el frontend no muestra botones inútiles)."""
    posibles = []
    for destino in TRANSICIONES.get(t.estado, {}):
        try:
            permisos.verificar_transicion(actor, t, destino)
            posibles.append(destino)
        except Exception:
            pass
    return posibles


def evento_dict(e: EventoHistorial) -> dict:
    return {
        "fecha": _f(e.creado_en),
        "tipo": e.tipo,
        "anterior": e.valor_anterior,
        "nuevo": e.valor_nuevo,
        "detalle": e.detalle,
        "responsable_del_cambio": f"{e.actor.nombre} ({e.actor.rol})" if e.actor else "",
        "origen": e.origen,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def obtener_usuario(db: Session, usuario_id: int) -> Usuario:
    u = db.get(Usuario, usuario_id)
    if not u or not u.activo:
        raise NoEncontrado("Usuario inexistente o inactivo.")
    return u


def _obtener_ticket(db: Session, ticket_id) -> Ticket:
    try:
        tid = int(str(ticket_id).strip().lstrip("#").replace("TCK-", "").replace("tck-", ""))
    except (TypeError, ValueError):
        raise ValidacionError(f"'{ticket_id}' no es un número de ticket válido. Ejemplo: 1052.")
    t = db.get(Ticket, tid)
    if not t:
        raise NoEncontrado(f"No existe el ticket {tid}.")
    return t


def _registrar(db: Session, t: Ticket, actor: Usuario, tipo: str, anterior="", nuevo="", detalle="",
               origen="agente") -> None:
    """F11: TODO cambio deja un evento con fecha, actor y origen."""
    db.add(EventoHistorial(ticket_id=t.id, tipo=tipo, valor_anterior=str(anterior or ""),
                           valor_nuevo=str(nuevo or ""), detalle=detalle, actor_id=actor.id, origen=origen))
    t.actualizado_en = ahora()


def _elegir_responsable(db: Session, categoria: str) -> Usuario | None:
    """Asignación automática: técnico con esa especialidad y menos tickets activos."""
    tecnicos = db.scalars(select(Usuario).where(Usuario.rol == "tecnico", Usuario.activo.is_(True))).all()
    aptos = [t for t in tecnicos if categoria in (t.especialidades or "").split("|")]
    if not aptos:
        return None

    def carga(u: Usuario) -> int:
        return db.scalar(
            select(func.count(Ticket.id)).where(
                Ticket.responsable_id == u.id, Ticket.estado.in_(["Abierto", "En revisión", "En progreso", "Pendiente"])
            )
        ) or 0

    return min(aptos, key=lambda u: (carga(u), u.id))


# ---------------------------------------------------------------------------
# F04 + F05 + F06 + F07 + criterio 10 : crear ticket
# ---------------------------------------------------------------------------
def validar_datos_ticket(datos: dict) -> list[str]:
    """Devuelve la lista de datos que FALTAN para poder crear el ticket (F04)."""
    faltan = []
    if len((datos.get("titulo") or "").strip()) < 5:
        faltan.append("titulo (resumen corto del problema)")
    if len((datos.get("descripcion") or "").strip()) < 20:
        faltan.append("descripcion (qué pasa, desde cuándo, qué estaba haciendo)")
    if len((datos.get("sistema_afectado") or "").strip()) < 2:
        faltan.append("sistema_afectado (equipo, aplicación o servicio con el problema)")
    if not normalizar_categoria(datos.get("categoria")):
        faltan.append(f"categoria válida ({', '.join(CATEGORIAS)})")
    if not normalizar_prioridad(datos.get("prioridad")):
        faltan.append(f"prioridad válida ({', '.join(PRIORIDADES)})")
    if len((datos.get("justificacion_prioridad") or "").strip()) < 10:
        faltan.append("justificacion_prioridad (impacto y urgencia)")
    return faltan


def crear_ticket(db: Session, actor: Usuario, datos: dict, adjuntos_ids: list[str] | None = None,
                 confirmar_aunque_duplicado: bool = False, origen: str = "agente") -> dict:
    faltan = validar_datos_ticket(datos)
    if faltan:
        raise ValidacionError("Faltan datos para crear el ticket.", faltantes=faltan)

    # Los adjuntos deben ser del usuario, existir y estar analizados ANTES de usarse.
    adjuntos: list[Adjunto] = []
    for aid in adjuntos_ids or []:
        a = db.get(Adjunto, str(aid).strip().upper())
        if not a or a.subido_por_id != actor.id:
            raise ValidacionError(f"El adjunto {aid} no existe o no fue subido por vos.")
        if a.ticket_id is not None:
            raise ValidacionError(f"El adjunto {aid} ya está asociado al ticket {a.ticket_id}.")
        if a.analisis_estado == "pendiente":
            raise ValidacionError(f"El adjunto {aid} todavía no fue analizado.")
        adjuntos.append(a)

    # Criterio 10: no crear duplicados sin confirmación explícita del usuario.
    if not confirmar_aunque_duplicado:
        posibles = buscar_posibles_duplicados(db, datos)
        if posibles:
            coincidencias = []
            for p in posibles:
                t = p["ticket"]
                propio = t.solicitante_id == actor.id or permisos.es_staff(actor)
                coincidencias.append({
                    "id": t.id, "titulo": t.titulo, "estado": t.estado, "categoria": t.categoria,
                    "similitud": p["similitud"], "metodo": p["metodo"],
                    "es_tuyo": t.solicitante_id == actor.id,
                    **({"creado": _f(t.creado_en), "sistema_afectado": t.sistema_afectado} if propio else {}),
                })
            return {
                "resultado": "posible_duplicado",
                "mensaje": "NO se creó el ticket: hay incidencias activas similares. Mostrale las coincidencias "
                           "al usuario y preguntale si es el mismo problema. Solo si confirma que es DISTINTO, "
                           "volvé a llamar con confirmar_aunque_duplicado=true.",
                "coincidencias": coincidencias,
            }

    categoria = normalizar_categoria(datos["categoria"])
    t = Ticket(
        solicitante_id=actor.id,
        titulo=datos["titulo"].strip()[:150],
        descripcion=datos["descripcion"].strip(),
        sistema_afectado=datos["sistema_afectado"].strip()[:120],
        mensaje_error=(datos.get("mensaje_error") or "").strip(),
        sintomas=(datos.get("sintomas") or "").strip(),
        contexto=(datos.get("contexto") or "").strip(),
        usuarios_afectados=(datos.get("usuarios_afectados") or "").strip()[:80],
        categoria=categoria,
        prioridad=normalizar_prioridad(datos["prioridad"]),
        prioridad_justificacion=datos["justificacion_prioridad"].strip(),
        estado="Abierto",
        canal=origen,
    )
    db.add(t)
    db.flush()  # obtiene el ID único

    _registrar(db, t, actor, "CREACION", nuevo="Abierto",
               detalle=f"Ticket creado. Categoría: {t.categoria}. Prioridad propuesta: {t.prioridad} "
                       f"({t.prioridad_justificacion})", origen=origen)
    for a in adjuntos:
        a.ticket_id = t.id
        _registrar(db, t, actor, "ADJUNTO", nuevo=a.nombre_original, detalle=f"{a.id} ({a.tipo})", origen=origen)

    responsable = _elegir_responsable(db, categoria)
    if responsable:
        t.responsable_id = responsable.id
        _registrar(db, t, actor, "ASIGNACION", nuevo=responsable.nombre,
                   detalle=f"Asignación automática por especialidad '{categoria}' y menor carga.", origen="sistema")
    db.flush()
    db.refresh(t)
    vector_store.indexar_ticket(t)
    return {"resultado": "creado", "ticket": ticket_detallado(t, actor)}


# ---------------------------------------------------------------------------
# F09 : consultas
# ---------------------------------------------------------------------------
def consultar_ticket(db: Session, actor: Usuario, ticket_id) -> dict:
    t = _obtener_ticket(db, ticket_id)
    permisos.verificar_ver_ticket(actor, t)
    return ticket_detallado(t, actor)


def buscar_tickets(db: Session, actor: Usuario, estado: str | None = None, categoria: str | None = None,
                   prioridad: str | None = None, solicitante: str | None = None, texto: str | None = None,
                   solo_mios: bool = False, solo_activos: bool = False, limite: int = 20) -> dict:
    q = select(Ticket)
    filtros_aplicados = {}

    if actor.rol == "solicitante" or solo_mios:
        # Un solicitante SOLO puede ver lo suyo, diga lo que diga el mensaje.
        if actor.rol == "tecnico" and solo_mios:
            q = q.where(Ticket.responsable_id == actor.id)
            filtros_aplicados["responsable"] = actor.nombre
        else:
            q = q.where(Ticket.solicitante_id == actor.id)
            filtros_aplicados["solicitante"] = actor.nombre
    elif solicitante:
        u = db.scalar(select(Usuario).where(or_(Usuario.username == solicitante.strip().lower(),
                                                Usuario.nombre.ilike(f"%{solicitante.strip()}%"))))
        if not u:
            return {"total": 0, "tickets": [], "filtros": {"solicitante": solicitante},
                    "mensaje": f"No encontré un usuario que coincida con '{solicitante}'."}
        q = q.where(Ticket.solicitante_id == u.id)
        filtros_aplicados["solicitante"] = u.nombre

    if estado:
        e = normalizar_estado(estado)
        if not e:
            raise ValidacionError(f"Estado '{estado}' inválido. Opciones: {', '.join(ESTADOS)}.")
        q = q.where(Ticket.estado == e)
        filtros_aplicados["estado"] = e
    elif solo_activos:
        q = q.where(Ticket.estado.in_(["Abierto", "En revisión", "En progreso", "Pendiente"]))
        filtros_aplicados["estado"] = "activos (no resueltos ni cerrados)"
    if categoria:
        c = normalizar_categoria(categoria)
        if not c:
            raise ValidacionError(f"Categoría '{categoria}' inválida. Opciones: {', '.join(CATEGORIAS)}.")
        q = q.where(Ticket.categoria == c)
        filtros_aplicados["categoria"] = c
    if prioridad:
        p = normalizar_prioridad(prioridad)
        if not p:
            raise ValidacionError(f"Prioridad '{prioridad}' inválida. Opciones: {', '.join(PRIORIDADES)}.")
        q = q.where(Ticket.prioridad == p)
        filtros_aplicados["prioridad"] = p
    if texto and texto.strip():
        patron = f"%{texto.strip()[:60]}%"
        q = q.where(or_(Ticket.titulo.ilike(patron), Ticket.descripcion.ilike(patron),
                        Ticket.sistema_afectado.ilike(patron), Ticket.mensaje_error.ilike(patron)))
        filtros_aplicados["texto"] = texto.strip()[:60]

    limite = max(1, min(int(limite or 20), 500))
    orden_prioridad = {"Crítica": 0, "Alta": 1, "Media": 2, "Baja": 3}
    tickets = db.scalars(q.order_by(Ticket.creado_en.desc())).all()
    tickets.sort(key=lambda t: (orden_prioridad.get(t.prioridad, 9), -t.id))
    return {
        "total": len(tickets),
        "mostrando": min(len(tickets), limite),
        "filtros": filtros_aplicados,
        "tickets": [ticket_resumido(t) for t in tickets[:limite]],
    }


# ---------------------------------------------------------------------------
# F08 + F10 : estados, prioridad, asignación, comentarios, adjuntos
# ---------------------------------------------------------------------------
def cambiar_estado(db: Session, actor: Usuario, ticket_id, nuevo_estado: str, comentario: str = "",
                   origen: str = "agente") -> dict:
    t = _obtener_ticket(db, ticket_id)
    destino = normalizar_estado(nuevo_estado)
    if not destino:
        raise ValidacionError(f"Estado '{nuevo_estado}' inválido. Opciones: {', '.join(ESTADOS)}.")
    permisos.verificar_transicion(actor, t, destino)
    if destino in ESTADOS_QUE_EXIGEN_COMENTARIO and len((comentario or "").strip()) < 5:
        raise ValidacionError(
            f"Para pasar a '{destino}' hay que indicar un motivo o detalle (comentario).",
            faltantes=["comentario"],
        )
    if t.estado == "Resuelto" and destino == "En progreso" and len((comentario or "").strip()) < 5:
        raise ValidacionError("Para reabrir el ticket indicá por qué no quedó solucionado.", faltantes=["comentario"])

    anterior = t.estado
    # Si un técnico toma un ticket sin responsable, queda asignado a él.
    if actor.rol == "tecnico" and t.responsable_id is None:
        t.responsable_id = actor.id
        _registrar(db, t, actor, "ASIGNACION", nuevo=actor.nombre, detalle="El técnico tomó el ticket.", origen=origen)
    t.estado = destino
    _registrar(db, t, actor, "CAMBIO_ESTADO", anterior, destino, detalle=(comentario or "").strip(), origen=origen)
    if comentario and comentario.strip():
        db.add(Comentario(ticket_id=t.id, autor_id=actor.id, texto=f"[{anterior} → {destino}] {comentario.strip()}"))
    db.flush()
    db.refresh(t)
    vector_store.indexar_ticket(t)
    return {"resultado": "actualizado", "ticket_id": t.id, "estado_anterior": anterior, "estado_nuevo": destino,
            "proximas_transiciones": list(TRANSICIONES.get(destino, {}).keys())}


def cambiar_prioridad(db: Session, actor: Usuario, ticket_id, nueva_prioridad: str, motivo: str,
                      origen: str = "agente") -> dict:
    t = _obtener_ticket(db, ticket_id)
    permisos.verificar_ver_ticket(actor, t)
    permisos.verificar_cambiar_prioridad(actor, t)
    p = normalizar_prioridad(nueva_prioridad)
    if not p:
        raise ValidacionError(f"Prioridad '{nueva_prioridad}' inválida. Opciones: {', '.join(PRIORIDADES)}.")
    if len((motivo or "").strip()) < 5:
        raise ValidacionError("Indicá el motivo del cambio de prioridad.", faltantes=["motivo"])
    if t.estado == "Cerrado":
        raise ValidacionError("No se puede modificar la prioridad de un ticket Cerrado.")
    anterior = t.prioridad
    t.prioridad = p
    t.prioridad_revisada = True
    _registrar(db, t, actor, "CAMBIO_PRIORIDAD", anterior, p, detalle=motivo.strip(), origen=origen)
    db.flush()
    return {"resultado": "actualizado", "ticket_id": t.id, "prioridad_anterior": anterior, "prioridad_nueva": p}


def asignar_ticket(db: Session, actor: Usuario, ticket_id, tecnico: str, origen: str = "agente") -> dict:
    t = _obtener_ticket(db, ticket_id)
    permisos.verificar_ver_ticket(actor, t)
    clave = (tecnico or "").strip()
    if clave.lower() in {"yo", "mi", "a mi", "me"}:
        u = actor
    else:
        u = db.scalar(select(Usuario).where(
            Usuario.rol.in_(["tecnico", "supervisor"]), Usuario.activo.is_(True),
            or_(Usuario.username == clave.lower(), Usuario.nombre.ilike(f"%{clave}%"))))
    if not u or u.rol not in ("tecnico", "supervisor"):
        raise NoEncontrado(f"No encontré un técnico que coincida con '{tecnico}'.")
    permisos.verificar_asignar(actor, t, u.id)
    if t.estado == "Cerrado":
        raise ValidacionError("No se puede reasignar un ticket Cerrado.")
    anterior = t.responsable.nombre if t.responsable else ""
    if t.responsable_id == u.id:
        raise ValidacionError(f"El ticket ya está asignado a {u.nombre}.")
    t.responsable_id = u.id
    _registrar(db, t, actor, "REASIGNACION" if anterior else "ASIGNACION", anterior, u.nombre, origen=origen)
    db.flush()
    return {"resultado": "asignado", "ticket_id": t.id, "responsable_anterior": anterior or "Sin asignar",
            "responsable_nuevo": u.nombre}


def agregar_comentario(db: Session, actor: Usuario, ticket_id, texto: str, interno: bool = False,
                       origen: str = "agente") -> dict:
    t = _obtener_ticket(db, ticket_id)
    permisos.verificar_comentar(actor, t, interno)
    texto = (texto or "").strip()
    if len(texto) < 3:
        raise ValidacionError("El comentario está vacío.")
    if len(texto) > 2000:
        raise ValidacionError("El comentario es demasiado largo (máx. 2000 caracteres).")
    c = Comentario(ticket_id=t.id, autor_id=actor.id, texto=texto, interno=bool(interno))
    db.add(c)
    _registrar(db, t, actor, "COMENTARIO", nuevo="interno" if interno else "público", detalle=texto[:300],
               origen=origen)
    db.flush()
    return {"resultado": "comentario_agregado", "ticket_id": t.id, "interno": bool(interno)}


def adjuntar_archivo(db: Session, actor: Usuario, ticket_id, adjunto_id: str, origen: str = "agente") -> dict:
    t = _obtener_ticket(db, ticket_id)
    permisos.verificar_adjuntar(actor, t)
    a = db.get(Adjunto, (adjunto_id or "").strip().upper())
    if not a or a.subido_por_id != actor.id:
        raise NoEncontrado(f"El adjunto {adjunto_id} no existe o no fue subido por vos.")
    if a.ticket_id == t.id:
        raise ValidacionError(f"El adjunto {a.id} ya está en el ticket {t.id}.")
    if a.ticket_id is not None:
        raise ValidacionError(f"El adjunto {a.id} ya pertenece al ticket {a.ticket_id}.")
    a.ticket_id = t.id
    _registrar(db, t, actor, "ADJUNTO", nuevo=a.nombre_original,
               detalle=f"{a.id} ({a.tipo}). Análisis: {a.analisis_estado}", origen=origen)
    db.flush()
    return {"resultado": "adjuntado", "ticket_id": t.id, "adjunto": a.id, "nombre": a.nombre_original,
            "analisis_estado": a.analisis_estado}


# ---------------------------------------------------------------------------
# F11 : historial
# ---------------------------------------------------------------------------
def consultar_historial(db: Session, actor: Usuario, ticket_id) -> dict:
    t = _obtener_ticket(db, ticket_id)
    permisos.verificar_ver_ticket(actor, t)
    eventos = t.historial
    if not permisos.es_staff(actor):
        # Los comentarios internos no se muestran al solicitante, tampoco en el historial.
        internos = {"interno"}
        eventos = [e for e in eventos if not (e.tipo == "COMENTARIO" and e.valor_nuevo in internos)]
    return {"ticket_id": t.id, "titulo": t.titulo, "estado_actual": t.estado, "eventos": [evento_dict(e) for e in eventos]}
