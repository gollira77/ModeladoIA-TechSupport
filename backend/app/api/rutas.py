"""Endpoints REST del panel web + chat con el agente (SSE)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.auth import crear_token, usuario_actual, usuario_publico, verificar_password
from app.config import settings
from app.db.database import get_db
from app.db.models import Usuario
from app.services import adjuntos as svc_adjuntos
from app.services import auditoria, permisos, resumen, tickets
from app.services.catalogos import CATEGORIAS, ESTADOS, PRIORIDADES, TRANSICIONES
from app.services.errores import ErrorNegocio
from app.services.seguridad import LimitadorTasa, limitador_chat

router = APIRouter(prefix="/api")
limitador_login = LimitadorTasa(maximo=8, ventana_seg=60)


def _err(e: ErrorNegocio):
    codigos = {"no_encontrado": 404, "permiso_denegado": 403, "validacion": 422, "transicion_invalida": 409}
    return HTTPException(codigos.get(e.codigo, 400), detail={"mensaje": e.mensaje, **e.datos})


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class LoginIn(BaseModel):
    username: str = Field(max_length=50)
    password: str = Field(max_length=100)


@router.post("/auth/login")
def login(datos: LoginIn, request: Request):
    clave_limite = hash((datos.username.lower(), request.client.host if request.client else ""))
    if not limitador_login.permitir(clave_limite):
        raise HTTPException(429, detail={"mensaje": "Demasiados intentos. Esperá un minuto."})
    with get_db() as db:
        u = db.scalar(select(Usuario).where(Usuario.username == datos.username.strip().lower()))
        if not u or not u.activo or not verificar_password(datos.password, u.password_hash):
            auditoria.registrar_evento(db, u.id if u else None, "LOGIN_FALLIDO",
                                       f"Usuario: {datos.username[:50]}", severidad="baja")
            raise HTTPException(401, detail={"mensaje": "Usuario o contraseña incorrectos."})
        return {"token": crear_token(u), "usuario": usuario_publico(u)}


@router.get("/auth/me")
def me(u: Usuario = Depends(usuario_actual)):
    return {**usuario_publico(u), "permisos": permisos.matriz_permisos()[u.rol]}


@router.get("/usuarios/demo")
def usuarios_demo():
    """Usuarios ficticios para el login de la demo (sin datos sensibles)."""
    with get_db() as db:
        us = db.scalars(select(Usuario).where(Usuario.activo.is_(True)).order_by(Usuario.id)).all()
        return [{"username": u.username, "nombre": u.nombre, "rol": u.rol, "area": u.area} for u in us]


# ---------------------------------------------------------------------------
# Catálogos y salud
# ---------------------------------------------------------------------------
@router.get("/catalogos")
def catalogos():
    return {
        "categorias": CATEGORIAS, "prioridades": PRIORIDADES, "estados": ESTADOS,
        "transiciones": {k: {d: sorted(r) for d, r in v.items()} for k, v in TRANSICIONES.items()},
        "permisos": permisos.matriz_permisos(),
    }


@router.get("/salud")
def salud():
    import httpx

    from app.rag.vector_store import ollama_disponible

    modelos = []
    try:
        r = httpx.get(f"{settings.OLLAMA_API_BASE}/api/tags", timeout=2)
        modelos = [m["name"] for m in r.json().get("models", [])]
        ollama = True
    except Exception:
        ollama = False
    agente = settings.MODELO_AGENTE.split("/", 1)[-1]

    def presente(nombre: str) -> bool:
        return any(m == nombre or m == f"{nombre}:latest" or m.startswith(nombre + ":") for m in modelos)

    return {
        "ollama": ollama,
        "modelo_agente": {"nombre": agente, "disponible": presente(agente)},
        "modelo_vision": {"nombre": settings.MODELO_VISION, "disponible": presente(settings.MODELO_VISION)},
        "modelo_embeddings": {"nombre": settings.MODELO_EMBEDDINGS, "disponible": ollama_disponible()},
    }


@router.get("/tecnicos")
def tecnicos(u: Usuario = Depends(usuario_actual)):
    if not permisos.es_staff(u):
        raise HTTPException(403, detail={"mensaje": "Solo personal de soporte."})
    with get_db() as db:
        ts = db.scalars(select(Usuario).where(Usuario.rol.in_(["tecnico", "supervisor"]), Usuario.activo.is_(True))).all()
        return [{"username": t.username, "nombre": t.nombre, "rol": t.rol, "especialidades": t.especialidades.split("|")}
                for t in ts]


# ---------------------------------------------------------------------------
# Chat con el agente (Server-Sent Events)
# ---------------------------------------------------------------------------
class ChatIn(BaseModel):
    mensaje: str = Field(default="", max_length=8000)
    session_id: str | None = Field(default=None, max_length=100)
    adjuntos_ids: list[str] = Field(default_factory=list, max_length=5)


@router.post("/chat")
async def chat(datos: ChatIn, u: Usuario = Depends(usuario_actual)):
    from app.agent.runtime import ejecutar_turno

    if not limitador_chat.permitir(u.id):
        with get_db() as db:
            auditoria.registrar_evento(db, u.id, "LIMITE_TASA", "Exceso de mensajes por minuto", severidad="media")
        raise HTTPException(429, detail={"mensaje": "Estás enviando demasiados mensajes. Esperá un momento."})
    if not datos.mensaje.strip() and not datos.adjuntos_ids:
        raise HTTPException(422, detail={"mensaje": "El mensaje está vacío."})

    with get_db() as db:
        adjs = []
        for aid in datos.adjuntos_ids:
            try:
                a = svc_adjuntos.obtener_adjunto(db, u, aid)
            except ErrorNegocio as e:
                raise _err(e)
            if a.subido_por_id != u.id:
                raise HTTPException(403, detail={"mensaje": "Solo podés enviar tus propios adjuntos."})
            adjs.append(a)

    async def stream():
        async for evento in ejecutar_turno(u, datos.session_id, datos.mensaje, adjs):
            yield f"data: {json.dumps(evento, ensure_ascii=False, default=str)}\n\n"
        yield "data: {\"tipo\": \"fin\"}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/chat/sesiones/{session_id}")
async def historial_chat(session_id: str, u: Usuario = Depends(usuario_actual)):
    from app.agent.runtime import mensajes_de_sesion

    return {"session_id": session_id, "mensajes": await mensajes_de_sesion(u, session_id)}


# ---------------------------------------------------------------------------
# Adjuntos
# ---------------------------------------------------------------------------
@router.post("/adjuntos")
async def subir_adjunto(archivo: UploadFile = File(...), u: Usuario = Depends(usuario_actual)):
    contenido = await archivo.read(settings.MAX_ARCHIVO_MB * 1024 * 1024 + 1)
    import anyio

    def _procesar():
        with get_db() as db:
            a = svc_adjuntos.subir_y_analizar(db, u, archivo.filename or "archivo", contenido)
            return {"id": a.id, "nombre": a.nombre_original, "tipo": a.tipo, "tamano": a.tamano_bytes,
                    "analisis_estado": a.analisis_estado, "analisis": a.analisis, "alerta_seguridad": a.alerta_seguridad}

    try:
        return await anyio.to_thread.run_sync(_procesar)  # el análisis de visión puede tardar
    except ErrorNegocio as e:
        raise _err(e)


@router.get("/adjuntos/{adjunto_id}/archivo")
def descargar_adjunto(adjunto_id: str, u: Usuario = Depends(usuario_actual)):
    with get_db() as db:
        try:
            a = svc_adjuntos.obtener_adjunto(db, u, adjunto_id)
        except ErrorNegocio as e:
            raise _err(e)
        return FileResponse(a.ruta, media_type=a.mime, filename=a.nombre_original)


@router.get("/adjuntos/{adjunto_id}")
def ver_adjunto(adjunto_id: str, u: Usuario = Depends(usuario_actual)):
    with get_db() as db:
        try:
            return svc_adjuntos.adjunto_para_agente(svc_adjuntos.obtener_adjunto(db, u, adjunto_id))
        except ErrorNegocio as e:
            raise _err(e)


# ---------------------------------------------------------------------------
# Tickets (panel) — usan EXACTAMENTE los mismos servicios que el agente
# ---------------------------------------------------------------------------
def _op(u: Usuario, fn):
    try:
        with get_db() as db:
            actor = tickets.obtener_usuario(db, u.id)
            return fn(db, actor)
    except ErrorNegocio as e:
        if e.codigo == "permiso_denegado":
            with get_db() as db:
                auditoria.registrar_evento(db, u.id, "PERMISO_DENEGADO", f"Panel: {e.mensaje}")
        raise _err(e)


@router.get("/tickets")
def listar(estado: str = "", categoria: str = "", prioridad: str = "", texto: str = "", solo_mios: bool = False,
           solo_activos: bool = False, u: Usuario = Depends(usuario_actual)):
    return _op(u, lambda db, a: tickets.buscar_tickets(db, a, estado or None, categoria or None, prioridad or None,
                                                       None, texto or None, solo_mios, solo_activos, limite=500))


@router.get("/tickets/{ticket_id}")
def detalle(ticket_id: int, u: Usuario = Depends(usuario_actual)):
    return _op(u, lambda db, a: tickets.consultar_ticket(db, a, ticket_id))


@router.get("/tickets/{ticket_id}/historial")
def historial(ticket_id: int, u: Usuario = Depends(usuario_actual)):
    return _op(u, lambda db, a: tickets.consultar_historial(db, a, ticket_id))


class EstadoIn(BaseModel):
    estado: str
    comentario: str = Field(default="", max_length=2000)


@router.post("/tickets/{ticket_id}/estado")
def cambiar_estado(ticket_id: int, datos: EstadoIn, u: Usuario = Depends(usuario_actual)):
    return _op(u, lambda db, a: tickets.cambiar_estado(db, a, ticket_id, datos.estado, datos.comentario, origen="panel"))


class PrioridadIn(BaseModel):
    prioridad: str
    motivo: str = Field(max_length=500)


@router.post("/tickets/{ticket_id}/prioridad")
def cambiar_prioridad(ticket_id: int, datos: PrioridadIn, u: Usuario = Depends(usuario_actual)):
    return _op(u, lambda db, a: tickets.cambiar_prioridad(db, a, ticket_id, datos.prioridad, datos.motivo, origen="panel"))


class AsignarIn(BaseModel):
    tecnico: str = Field(max_length=80)


@router.post("/tickets/{ticket_id}/asignar")
def asignar(ticket_id: int, datos: AsignarIn, u: Usuario = Depends(usuario_actual)):
    return _op(u, lambda db, a: tickets.asignar_ticket(db, a, ticket_id, datos.tecnico, origen="panel"))


class ComentarioIn(BaseModel):
    texto: str = Field(max_length=2000)
    interno: bool = False


@router.post("/tickets/{ticket_id}/comentarios")
def comentar(ticket_id: int, datos: ComentarioIn, u: Usuario = Depends(usuario_actual)):
    return _op(u, lambda db, a: tickets.agregar_comentario(db, a, ticket_id, datos.texto, datos.interno, origen="panel"))


class AdjuntarIn(BaseModel):
    adjunto_id: str = Field(max_length=20)


@router.post("/tickets/{ticket_id}/adjuntos")
def adjuntar(ticket_id: int, datos: AdjuntarIn, u: Usuario = Depends(usuario_actual)):
    return _op(u, lambda db, a: tickets.adjuntar_archivo(db, a, ticket_id, datos.adjunto_id, origen="panel"))


@router.get("/resumen")
def obtener_resumen(periodo_dias: int = 0, u: Usuario = Depends(usuario_actual)):
    return _op(u, lambda db, a: resumen.generar_resumen(db, a, periodo_dias or None))


# ---------------------------------------------------------------------------
# Seguridad
# ---------------------------------------------------------------------------
@router.get("/seguridad/eventos")
def eventos_seguridad(u: Usuario = Depends(usuario_actual)):
    return _op(u, lambda db, a: auditoria.listar_eventos(db, a))


@router.get("/derivaciones")
def derivaciones(u: Usuario = Depends(usuario_actual)):
    return _op(u, lambda db, a: auditoria.listar_derivaciones(db, a))
