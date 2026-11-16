"""
Detección de tickets duplicados (criterio 10) con búsqueda HÍBRIDA:

  score = 0.5 * similitud_semántica (embeddings en Chroma)
        + 0.5 * similitud_léxica   (palabras en común + mismo sistema + mismo código de error)

Si Ollama no está disponible para generar embeddings, se usa solo la parte léxica
(el sistema sigue funcionando, con menor precisión).
"""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Ticket
from app.services.seguridad import normalizar

ESTADOS_ACTIVOS = ["Abierto", "En revisión", "En progreso", "Pendiente"]

STOPWORDS = set(
    """a al algo algun alguna algunas alguno algunos ante antes asi aun bien cada como con contra cual
    cuando de del desde donde dos el ella ellas ellos en entre era es esa ese eso esta estan estoy este esto
    fue ha hay la las le les lo los me mi mis muy nada ni no nos o otra otro para pero poco por porque que
    se sea ser si sin sobre son su sus tambien tengo tiene todo todos tu un una uno unos y ya yo hoy anda
    funciona problema error favor hola buenas buen dia gracias necesito ayuda puedo puede me sale""".split()
)
RX_CODIGO = re.compile(r"\b(?=[a-z0-9_\-x\.]*\d)[a-z0-9_\-\.]{3,}\b")


def tokens(texto: str) -> set[str]:
    palabras = re.findall(r"[a-z0-9_\-\.]{3,}", normalizar(texto))
    return {p.strip(".-") for p in palabras if p not in STOPWORDS}


def codigos_error(texto: str) -> set[str]:
    """Códigos tipo 0x80070005, ORA-12541, 500, ERR_CONNECTION_REFUSED."""
    t = normalizar(texto)
    codigos = {c for c in RX_CODIGO.findall(t) if not re.fullmatch(r"\d{1,2}", c)}
    codigos |= set(re.findall(r"\berr_[a-z_]+\b", t))
    # Fechas/horas no son códigos
    return {c for c in codigos if not re.fullmatch(r"\d{1,4}([\-/\.:]\d{1,4}){1,2}", c)}


def similitud_lexica(a: dict, b: dict) -> float:
    ta = tokens(" ".join([a.get("titulo", ""), a.get("descripcion", ""), a.get("mensaje_error", "")]))
    tb = tokens(" ".join([b.get("titulo", ""), b.get("descripcion", ""), b.get("mensaje_error", "")]))
    if not ta or not tb:
        return 0.0
    jaccard = len(ta & tb) / len(ta | tb)
    score = jaccard * 1.6
    sa, sb = normalizar(a.get("sistema_afectado", "")), normalizar(b.get("sistema_afectado", ""))
    if sa and sb and (sa == sb or sa in sb or sb in sa):
        score += 0.25
    ca = codigos_error(a.get("mensaje_error", "") + " " + a.get("descripcion", ""))
    cb = codigos_error(b.get("mensaje_error", "") + " " + b.get("descripcion", ""))
    if ca & cb:
        score += 0.3
    return round(min(score, 1.0), 3)


def buscar_posibles_duplicados(db: Session, datos: dict, limite: int = 3) -> list[dict]:
    """Devuelve tickets ACTIVOS parecidos al que se quiere crear, ordenados por score."""
    from app.rag import vector_store  # import diferido (evita ciclos)

    activos = db.scalars(select(Ticket).where(Ticket.estado.in_(ESTADOS_ACTIVOS))).all()
    if not activos:
        return []

    consulta = " ".join(
        [datos.get("titulo", ""), datos.get("sistema_afectado", ""), datos.get("mensaje_error", ""),
         datos.get("descripcion", "")]
    )
    semanticos = vector_store.similitud_tickets(consulta, k=8, solo_activos=True)  # {id: score} o None

    candidatos = []
    for t in activos:
        lex = similitud_lexica(
            datos,
            {"titulo": t.titulo, "descripcion": t.descripcion, "mensaje_error": t.mensaje_error,
             "sistema_afectado": t.sistema_afectado},
        )
        if semanticos is None:
            score, metodo = lex, "léxico"
        else:
            score, metodo = 0.5 * semanticos.get(t.id, 0.0) + 0.5 * lex, "híbrido"
        if score >= settings.UMBRAL_DUPLICADO:
            candidatos.append((round(score, 2), metodo, t))

    candidatos.sort(key=lambda x: x[0], reverse=True)
    return [
        {"ticket": t, "similitud": s, "metodo": m}
        for s, m, t in candidatos[:limite]
    ]
