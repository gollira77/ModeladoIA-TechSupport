"""
Procesamiento MULTIMODAL de adjuntos (F02, criterio 2 y 3).

Cada modalidad se convierte en TEXTO ESTRUCTURADO antes de llegar al agente:

  imagen / captura  ->  modelo con visión en Ollama (OCR + descripción + error visible)
                        fallback: OCR con Tesseract (si está instalado)
  .txt / .log       ->  parser determinista: niveles, errores, códigos, rango de fechas

Luego TODO el texto extraído pasa por seguridad.sanitizar_adjunto():
  - se eliminan instrucciones escondidas (prompt injection indirecta)
  - se enmascaran contraseñas, tokens y claves que aparezcan en logs

Si algo no se puede interpretar, el análisis queda en estado "limitado" o "error"
y el agente está obligado a informarlo (restricción de la consigna).
"""
from __future__ import annotations

import io
import logging
import re
import secrets
import string
from collections import Counter
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Adjunto, Usuario
from app.services.errores import NoEncontrado, PermisoDenegado, ValidacionError
from app.services.seguridad import sanitizar_adjunto

log = logging.getLogger("adjuntos")

EXT_IMAGEN = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
EXT_TEXTO = {".txt": "texto", ".log": "log"}
MAX_LINEAS_EXTRACTO = 40

PROMPT_VISION = """Sos un analista de soporte técnico. Analizá la imagen y respondé EXACTAMENTE con este formato,
en español, sin agregar nada más. Si un dato no se ve, escribí "no visible". NO inventes.

TIPO: <captura de pantalla | foto de equipo | foto de documento | no relacionada con soporte técnico>
LEGIBILIDAD: <alta | media | baja | ilegible>
SISTEMA_O_DISPOSITIVO: <aplicación, sistema operativo o equipo que se ve>
MENSAJE_DE_ERROR: <texto literal del error, si hay>
TEXTO_VISIBLE: <otro texto relevante que se lea>
DESCRIPCION: <qué se observa, en 1 a 3 oraciones: daños físicos, luces, ventanas, etc.>"""


def _nuevo_id() -> str:
    alfabeto = string.ascii_uppercase + string.digits
    return "ADJ-" + "".join(secrets.choice(alfabeto) for _ in range(6))


# ---------------------------------------------------------------------------
# Validación de archivos (seguridad de subida)
# ---------------------------------------------------------------------------
def validar_archivo(nombre: str, contenido: bytes) -> tuple[str, str, str]:
    """Devuelve (tipo, extension, mime). Lanza ValidacionError si no es aceptable."""
    nombre_limpio = Path(nombre or "archivo").name
    ext = Path(nombre_limpio).suffix.lower()
    if len(contenido) == 0:
        raise ValidacionError("El archivo está vacío.")
    if len(contenido) > settings.MAX_ARCHIVO_MB * 1024 * 1024:
        raise ValidacionError(f"El archivo supera el máximo de {settings.MAX_ARCHIVO_MB} MB.")

    if ext in EXT_IMAGEN:
        try:
            with Image.open(io.BytesIO(contenido)) as img:
                img.verify()  # comprueba que realmente sea una imagen (no un .exe renombrado)
                formato = (img.format or "png").lower()
        except (UnidentifiedImageError, Exception):
            raise ValidacionError("El archivo no es una imagen válida.")
        return "imagen", ext, f"image/{'jpeg' if formato == 'jpg' else formato}"

    if ext in EXT_TEXTO:
        if b"\x00" in contenido[:4096]:
            raise ValidacionError("El archivo parece binario, no un texto/log.")
        texto = _decodificar(contenido)
        imprimibles = sum(c.isprintable() or c in "\n\r\t" for c in texto[:5000])
        if texto and imprimibles / min(len(texto), 5000) < 0.9:
            raise ValidacionError("El archivo no parece un texto legible.")
        return EXT_TEXTO[ext], ext, "text/plain"

    raise ValidacionError(
        f"Formato '{ext or 'desconocido'}' no admitido. Se aceptan imágenes (PNG, JPG, WEBP, BMP, GIF) "
        "y archivos de texto .txt o .log."
    )


def _decodificar(contenido: bytes) -> str:
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return contenido.decode(enc)
        except UnicodeDecodeError:
            continue
    return contenido.decode("utf-8", "ignore")


# ---------------------------------------------------------------------------
# Análisis de texto / logs
# ---------------------------------------------------------------------------
RX_NIVEL = re.compile(r"\b(FATAL|CRITICAL|CRIT|ERROR|ERR|SEVERE|WARN|WARNING|EXCEPTION|TRACEBACK|FAILED|FAILURE|DENIED|TIMEOUT|TIMED OUT)\b", re.I)
RX_FECHA = re.compile(r"\b(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?|\d{2}/\d{2}/\d{4}[ ,]+\d{2}:\d{2}(:\d{2})?)")
RX_CODIGO = re.compile(r"\b(0x[0-9A-Fa-f]{6,8}|[A-Z]{2,5}-\d{3,5}|ERR_[A-Z_]+|HTTP\s?[45]\d\d|\b[45]\d\d\s(?:Internal|Bad|Service|Gateway|Not|Forbidden|Unauthorized)[\w ]*|errno\s?\d+|code[=: ]\s?-?\d+|Event ID[: ]\s?\d+)", re.I)
NIVELES_GRAVES = {"FATAL", "CRITICAL", "CRIT", "ERROR", "ERR", "SEVERE", "EXCEPTION", "TRACEBACK", "FAILED",
                  "FAILURE", "DENIED", "TIMEOUT", "TIMED OUT"}


def analizar_texto(texto: str, tipo: str) -> tuple[str, str]:
    lineas = [l.rstrip() for l in texto.splitlines()]
    no_vacias = [l for l in lineas if l.strip()]
    if not no_vacias:
        return "El archivo no contiene texto.", "limitado"

    niveles = Counter()
    relevantes = []
    for i, l in enumerate(lineas, 1):
        m = RX_NIVEL.findall(l)
        if m:
            for n in m:
                niveles[n.upper().replace("WARNING", "WARN").replace("CRIT", "CRITICAL").replace("CRITICALICAL", "CRITICAL")] += 1
            if any(n.upper() in NIVELES_GRAVES for n in m) or "WARN" in l.upper():
                relevantes.append(f"L{i}: {l.strip()[:300]}")
    fechas = RX_FECHA.findall(texto)
    codigos = Counter(c.strip() for c in RX_CODIGO.findall(texto))

    # Mensajes de error únicos (sin la marca de tiempo) para ver qué se repite
    def _sin_fecha(l: str) -> str:
        return RX_FECHA.sub("", l.split(": ", 1)[-1] if ": " in l else l).strip()[:160]

    errores_unicos = Counter(_sin_fecha(l.split(": ", 1)[1]) for l in relevantes if ": " in l)

    partes = [
        f"Tipo: archivo {'de registro (LOG)' if tipo == 'log' else 'de texto (TXT)'} con {len(no_vacias)} líneas.",
    ]
    if fechas:
        partes.append(f"Rango temporal: {fechas[0][0]} → {fechas[-1][0]}.")
    if niveles:
        partes.append("Niveles detectados: " + ", ".join(f"{k}×{v}" for k, v in niveles.most_common()) + ".")
    if codigos:
        partes.append("Códigos de error: " + ", ".join(f"{k} (×{v})" for k, v in codigos.most_common(8)) + ".")
    if errores_unicos:
        partes.append("Mensajes más repetidos:\n" + "\n".join(f"  - ({v}×) {k}" for k, v in errores_unicos.most_common(5)))

    if relevantes:
        extracto = relevantes[:MAX_LINEAS_EXTRACTO]
        partes.append("Líneas relevantes (errores/advertencias):\n" + "\n".join(extracto))
        if len(relevantes) > MAX_LINEAS_EXTRACTO:
            partes.append(f"(... {len(relevantes) - MAX_LINEAS_EXTRACTO} líneas relevantes más omitidas)")
        estado = "ok"
    else:
        # Texto libre (ej: el usuario describe el problema en un .txt)
        partes.append("No se detectaron líneas de error con formato de log. Contenido (primeras líneas):\n"
                      + "\n".join(l[:300] for l in no_vacias[:25]))
        estado = "ok" if tipo == "texto" else "limitado"
    return "\n".join(partes), estado


# ---------------------------------------------------------------------------
# Análisis de imágenes
# ---------------------------------------------------------------------------
def _reducir_imagen(contenido: bytes, lado_max: int = 1280) -> bytes:
    """Achica la imagen para que el modelo de visión consuma menos memoria (recursos limitados)."""
    with Image.open(io.BytesIO(contenido)) as img:
        img = img.convert("RGB")
        img.thumbnail((lado_max, lado_max))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


def _vision_ollama(contenido: bytes) -> str | None:
    try:
        import ollama

        cliente = ollama.Client(host=settings.OLLAMA_API_BASE, timeout=180)
        resp = cliente.chat(
            model=settings.MODELO_VISION,
            messages=[{"role": "user", "content": PROMPT_VISION, "images": [_reducir_imagen(contenido)]}],
            options={"temperature": 0},
            think=False,
        )
        texto = (resp["message"]["content"] or "").strip()
        return texto or None
    except Exception as e:
        log.warning("Modelo de visión no disponible (%s): %s", settings.MODELO_VISION, e)
        return None


def _ocr_tesseract(contenido: bytes) -> str | None:
    try:
        import pytesseract

        with Image.open(io.BytesIO(contenido)) as img:
            texto = pytesseract.image_to_string(img.convert("L"), lang="spa+eng")
        return texto.strip() or None
    except Exception:
        return None


def analizar_imagen(contenido: bytes) -> tuple[str, str]:
    salida = _vision_ollama(contenido)
    if salida:
        legib = re.search(r"LEGIBILIDAD:\s*(\w+)", salida, re.I)
        tipo = re.search(r"TIPO:\s*(.+)", salida, re.I)
        estado = "ok"
        avisos = []
        if legib and legib.group(1).lower() in ("baja", "ilegible"):
            estado = "limitado"
            avisos.append("La imagen tiene baja legibilidad: parte de la información puede no ser exacta.")
        if tipo and "no relacionada" in tipo.group(1).lower():
            estado = "limitado"
            avisos.append("La imagen no parece relacionada con un problema técnico.")
        return (salida + ("\nAVISOS: " + " ".join(avisos) if avisos else "")), estado

    ocr = _ocr_tesseract(contenido)
    if ocr:
        return (
            "LIMITACIÓN: el modelo de visión no está disponible; solo se pudo extraer el texto con OCR "
            "(sin interpretación visual del contenido).\nTEXTO_OCR:\n" + ocr[:3000],
            "limitado",
        )
    return (
        "LIMITACIÓN: no se pudo interpretar la imagen (modelo de visión no disponible y sin texto reconocible). "
        "Hay que pedirle al usuario que describa lo que muestra la imagen o que copie el mensaje de error.",
        "error",
    )


# ---------------------------------------------------------------------------
# API del servicio
# ---------------------------------------------------------------------------
def subir_y_analizar(db: Session, actor: Usuario, nombre: str, contenido: bytes) -> Adjunto:
    tipo, ext, mime = validar_archivo(nombre, contenido)
    adj_id = _nuevo_id()
    ruta = settings.UPLOADS_DIR / f"{adj_id}{ext}"  # nombre generado: evita path traversal
    ruta.write_bytes(contenido)

    alertas_crudo = ""
    if tipo == "imagen":
        analisis, estado = analizar_imagen(contenido)
    else:
        crudo = _decodificar(contenido)
        analisis, estado = analizar_texto(crudo, tipo)
        _, alertas_crudo = sanitizar_adjunto(crudo)  # revisa TODO el archivo, no solo las líneas de error

    analisis_limpio, alerta = sanitizar_adjunto(analisis)
    alerta = "; ".join(dict.fromkeys(x for x in (alerta + "; " + alertas_crudo).split("; ") if x))
    a = Adjunto(
        id=adj_id, subido_por_id=actor.id, nombre_original=Path(nombre).name[:200], ruta=str(ruta), mime=mime,
        tipo=tipo, tamano_bytes=len(contenido), analisis=analisis_limpio, analisis_estado=estado,
        alerta_seguridad=alerta,
    )
    db.add(a)
    db.flush()
    if alerta and "prompt injection" in alerta:
        from app.services.auditoria import registrar_evento

        registrar_evento(db, actor.id, "ADJUNTO_SOSPECHOSO", f"{adj_id} {a.nombre_original}: {alerta}",
                         severidad="alta")
    return a


def obtener_adjunto(db: Session, actor: Usuario, adjunto_id: str) -> Adjunto:
    from app.services import permisos

    a = db.get(Adjunto, (adjunto_id or "").strip().upper())
    if not a:
        raise NoEncontrado(f"No existe el adjunto {adjunto_id}.")
    if a.subido_por_id == actor.id or permisos.es_staff(actor):
        return a
    if a.ticket and a.ticket.solicitante_id == actor.id:
        return a
    raise PermisoDenegado("No tenés autorización para ver ese adjunto.")


def adjunto_para_agente(a: Adjunto) -> dict:
    return {
        "adjunto_id": a.id,
        "nombre": a.nombre_original,
        "tipo": a.tipo,
        "estado_analisis": a.analisis_estado,
        "alerta_seguridad": a.alerta_seguridad or "ninguna",
        "ticket_asociado": a.ticket_id,
        "contenido_extraido": a.analisis,
    }
