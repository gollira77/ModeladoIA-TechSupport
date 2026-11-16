"""
RAG con LangChain + Chroma + nomic-embed-text (igual que en el material de la materia).

Colecciones:
  - "conocimiento": catálogo de categorías, prioridades, estados, políticas y soluciones
                     conocidas (archivos data/conocimiento/*.md).
  - "tickets":      un documento por ticket. Se usa para detectar duplicados y para
                     encontrar incidencias históricas similares.

Si Ollama no responde, las funciones devuelven None / hacen fallback léxico para
que la aplicación siga funcionando (degradación controlada).
"""
from __future__ import annotations

import logging
import math
import re
import time
from functools import lru_cache
from pathlib import Path

import httpx

from app.config import settings

log = logging.getLogger("rag")

COLECCION_CONOCIMIENTO = "conocimiento"
COLECCION_TICKETS = "tickets"
DIR_CONOCIMIENTO = settings.DATA_DIR / "conocimiento"

_estado_ollama = {"ok": None, "chequeado": 0.0}


def ollama_disponible() -> bool:
    """Chequea (con caché de 30 s) si Ollama responde y tiene el modelo de embeddings."""
    if time.time() - _estado_ollama["chequeado"] < 30 and _estado_ollama["ok"] is not None:
        return _estado_ollama["ok"]
    ok = False
    try:
        r = httpx.get(f"{settings.OLLAMA_API_BASE}/api/tags", timeout=1.5)
        modelos = [m.get("name", "") for m in r.json().get("models", [])]
        ok = any(m.startswith(settings.MODELO_EMBEDDINGS) for m in modelos)
        if not ok:
            log.warning("Ollama responde pero falta el modelo %s (ollama pull %s)",
                        settings.MODELO_EMBEDDINGS, settings.MODELO_EMBEDDINGS)
    except Exception:
        ok = False
    _estado_ollama.update(ok=ok, chequeado=time.time())
    return ok


@lru_cache(maxsize=4)
def _store(nombre: str):
    from langchain_chroma import Chroma
    from langchain_ollama import OllamaEmbeddings

    return Chroma(
        collection_name=nombre,
        embedding_function=OllamaEmbeddings(model=settings.MODELO_EMBEDDINGS,
                                            base_url=settings.OLLAMA_API_BASE),
        persist_directory=settings.VECTOR_DIR,
        collection_metadata={"hnsw:space": "cosine"},  # similitud del coseno
    )


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------
def texto_ticket(t) -> str:
    return (
        f"Título: {t.titulo}\nSistema afectado: {t.sistema_afectado}\n"
        f"Mensaje de error: {t.mensaje_error}\nSíntomas: {t.sintomas}\nDescripción: {t.descripcion}"
    )


def indexar_ticket(t) -> bool:
    """Inserta o actualiza (upsert) el ticket en la colección vectorial."""
    if not ollama_disponible():
        return False
    try:
        from langchain_core.documents import Document

        doc = Document(
            page_content=texto_ticket(t),
            metadata={"ticket_id": t.id, "estado": t.estado, "categoria": t.categoria,
                      "prioridad": t.prioridad, "solicitante_id": t.solicitante_id},
        )
        _store(COLECCION_TICKETS).add_documents([doc], ids=[str(t.id)])
        return True
    except Exception as e:  # nunca romper el flujo por el índice
        log.warning("No se pudo indexar el ticket %s: %s", t.id, e)
        return False


def similitud_tickets(consulta: str, k: int = 8, solo_activos: bool = True) -> dict[int, float] | None:
    """{ticket_id: similitud 0..1}. None si el RAG semántico no está disponible."""
    if not ollama_disponible():
        return None
    try:
        filtro = {"estado": {"$in": ["Abierto", "En revisión", "En progreso", "Pendiente"]}} if solo_activos else None
        res = _store(COLECCION_TICKETS).similarity_search_with_score(consulta, k=k, filter=filtro)
        # distancia coseno (0 = idéntico) -> similitud
        return {int(d.metadata["ticket_id"]): max(0.0, 1 - float(dist)) for d, dist in res}
    except Exception as e:
        log.warning("Búsqueda semántica de tickets falló: %s", e)
        return None


# ---------------------------------------------------------------------------
# Base de conocimiento
# ---------------------------------------------------------------------------
def _chunks_conocimiento():
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_core.documents import Document

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=900, chunk_overlap=150, separators=["\n## ", "\n### ", "\n\n", "\n", " "]
    )
    docs = []
    for archivo in sorted(Path(DIR_CONOCIMIENTO).glob("*.md")):
        texto = archivo.read_text(encoding="utf-8")
        titulo = texto.splitlines()[0].lstrip("# ").strip() if texto else archivo.stem
        for i, chunk in enumerate(splitter.split_text(texto)):
            seccion = next((l.lstrip("# ").strip() for l in chunk.splitlines() if l.startswith("#")), titulo)
            docs.append(Document(page_content=chunk,
                                 metadata={"fuente": archivo.name, "titulo": titulo, "seccion": seccion, "chunk": i}))
    return docs


def indexar_conocimiento() -> int:
    """Re-indexa toda la base de conocimiento (se corre con scripts/indexar.py)."""
    docs = _chunks_conocimiento()
    store = _store(COLECCION_CONOCIMIENTO)
    try:
        store.delete_collection()
    except Exception:
        pass
    _store.cache_clear()
    store = _store(COLECCION_CONOCIMIENTO)
    store.add_documents(docs, ids=[f"{d.metadata['fuente']}#{d.metadata['chunk']}" for d in docs])
    return len(docs)


@lru_cache(maxsize=1)
def _indice_lexico():
    docs = _chunks_conocimiento()
    from app.services.duplicados import tokens

    return [(d, tokens(d.page_content)) for d in docs]


def _busqueda_lexica(consulta: str, k: int) -> list[dict]:
    from app.services.duplicados import tokens

    q = tokens(consulta)
    if not q:
        return []
    indice = _indice_lexico()
    n = len(indice)
    df = {t: sum(1 for _, toks in indice if t in toks) for t in q}
    resultados = []
    for doc, toks in indice:
        score = sum(math.log(1 + n / (1 + df[t])) for t in q if t in toks)
        if score > 0:
            resultados.append((score, doc))
    resultados.sort(key=lambda x: x[0], reverse=True)
    maximo = resultados[0][0] if resultados else 1
    return [
        {"fuente": d.metadata["fuente"], "seccion": d.metadata["seccion"],
         "contenido": d.page_content, "relevancia": round(s / maximo, 2), "metodo": "léxico"}
        for s, d in resultados[:k]
    ]


def buscar_conocimiento(consulta: str, k: int = 4, umbral: float = 0.35) -> list[dict]:
    """Recupera fragmentos relevantes con su fuente (para citar y no inventar)."""
    if ollama_disponible():
        try:
            res = _store(COLECCION_CONOCIMIENTO).similarity_search_with_score(consulta, k=k)
            salida = []
            for d, dist in res:
                rel = round(max(0.0, 1 - float(dist)), 2)
                if rel >= umbral:
                    salida.append({"fuente": d.metadata.get("fuente"), "seccion": d.metadata.get("seccion"),
                                   "contenido": d.page_content, "relevancia": rel, "metodo": "semántico"})
            if salida:
                return salida
        except Exception as e:
            log.warning("Búsqueda semántica en conocimiento falló, uso léxica: %s", e)
    return _busqueda_lexica(consulta, k)


def limpiar_texto(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip()
