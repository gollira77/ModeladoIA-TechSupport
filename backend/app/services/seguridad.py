"""
Capa de seguridad del agente (defensa en profundidad).

El LLM NUNCA es la única barrera. Este módulo implementa controles deterministas
(no dependen del modelo) que se ejecutan ANTES y DESPUÉS de cada llamada al LLM:

  1. analizar_entrada()      -> detecta prompt injection, jailbreaks, pedidos de datos
                                sensibles, temas fuera de alcance y abuso.
  2. sanitizar_adjunto()     -> neutraliza instrucciones escondidas dentro de archivos
                                (prompt injection INDIRECTA) y enmascara secretos de logs.
  3. redactar_salida()       -> enmascara secretos/datos personales en lo que responde
                                el modelo y detecta fuga del prompt del sistema (canario).
  4. LimitadorTasa           -> evita abuso por volumen (flooding).

Todo intento queda registrado en la tabla eventos_seguridad (auditoría).
"""
from __future__ import annotations

import base64
import re
import time
import unicodedata
from collections import defaultdict, deque
from dataclasses import dataclass, field

from app.config import settings

# Token "canario": está escrito dentro de las instrucciones del agente. Si alguna vez
# aparece en una respuesta, significa que el modelo filtró su prompt -> se bloquea.
CANARIO = "TS-CANARIO-7F3A9"

RESPUESTA_INJECTION = (
    "No puedo hacer eso. Soy el asistente de soporte técnico de TechSupport S.A. y mis reglas "
    "de funcionamiento no se pueden modificar ni revelar. Si tenés un problema técnico, contame "
    "qué está pasando y te ayudo a registrarlo."
)
RESPUESTA_SENSIBLE = (
    "No puedo compartir información sensible (contraseñas, credenciales, datos personales, "
    "configuraciones internas ni datos de otros usuarios). Si perdiste el acceso a tu cuenta, "
    "puedo registrar un ticket de 'Accesos y permisos' para que el equipo lo gestione de forma segura."
)
RESPUESTA_FUERA_DE_TEMA = (
    "Solo puedo ayudarte con temas de soporte técnico de TechSupport S.A.: reportar incidencias, "
    "consultar o actualizar tus tickets y ver resúmenes. ¿Tenés algún problema técnico para reportar?"
)
RESPUESTA_LARGO = (
    "El mensaje es demasiado largo. Resumí el problema en pocas líneas y, si tenés registros "
    "extensos, adjuntalos como archivo .log o .txt."
)


# ---------------------------------------------------------------------------
# Normalización: evita evasiones con acentos, mayúsculas, caracteres invisibles,
# leetspeak simple ("1gn0r4") o separadores ("i.g.n.o.r.a").
# ---------------------------------------------------------------------------
_INVISIBLES = re.compile(r"[​-‏⁠-⁤﻿­]")
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})


def normalizar(texto: str) -> str:
    t = _INVISIBLES.sub("", texto or "")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _variantes(texto: str) -> list[str]:
    """Genera variantes del texto para detectar ofuscaciones."""
    base = normalizar(texto)
    variantes = [base, base.translate(_LEET)]
    # "i.g.n.o.r.a" / "i g n o r a" -> "ignora"
    variantes.append(re.sub(r"(?<=\w)[\.\-_*·](?=\w)", "", base))
    variantes.append(re.sub(r"\b(\w) (?=\w\b)", r"\1", base))
    # Contenido codificado en base64 (técnica común de jailbreak)
    for bloque in re.findall(r"[A-Za-z0-9+/]{24,}={0,2}", texto or ""):
        try:
            dec = base64.b64decode(bloque, validate=True).decode("utf-8", "ignore")
            if dec and sum(c.isprintable() for c in dec) / len(dec) > 0.9:
                variantes.append(normalizar(dec))
        except Exception:
            pass
    return variantes


# ---------------------------------------------------------------------------
# Patrones (sobre texto normalizado: sin acentos y en minúsculas)
# ---------------------------------------------------------------------------
PATRONES_INJECTION = [
    # "ignorá tus instrucciones", "olvidate de todas las reglas anteriores"
    r"\b(ignora|ignore|olvida|olvidate|descarta|omiti|saltea|disregard|forget)\b.{0,20}\b(tus|todas|todas las|las anteriores|las previas|your|all|previous|prior|above)\b.{0,25}\b(instrucciones|reglas|indicaciones|restricciones|prompt|instructions|rules|directivas|guidelines)",
    r"\b(ignora|ignore|olvida|olvidate|forget)\b.{0,15}\b(lo anterior|todo lo anterior|lo que te dijeron|everything above|the above)\b",
    r"\b(a partir de ahora|desde ahora|from now on)\b.{0,40}\b(eres|sos|seras|vas a ser|actua|actuaras|you are|act as|responde)",
    r"\b(actua|actuar|comportate|hace de cuenta|finge|fingi|simula|pretend|act as|roleplay|juego de rol)\b.{0,25}\b(como|que sos|que eres|as)\b.{0,30}\b(admin|administrador|root|supervisor|desarrollador|developer|otro asistente|otro modelo|otra ia|sin (reglas|restricciones|filtros)|dan|hacker|chatgpt)",
    r"\b(modo|mode)\s*(desarrollador|developer|dios|god|dan|sin restricciones|sin filtros|jailbreak|unrestricted)\b",
    r"\bjailbreak|\bdo anything now\b|\bdan mode\b|\bprompt injection\b",
    r"\b(muestra|mostra|mostrame|muestrame|revela|revelame|repeti|repite|imprime|dime|decime|copia|cual es|cuales son|filtra|exporta|print|show|reveal|repeat|output)\b.{0,40}\b(system prompt|prompt del sistema|prompt de sistema|prompt inicial|tu prompt|instrucciones internas|instrucciones iniciales|instrucciones del sistema|instrucciones originales|instrucciones ocultas|tus instrucciones|tus reglas|configuracion interna|initial prompt|your instructions|system instructions|your rules)",
    r"(</?\s*(system|sistema|instructions?)\s*>|\[/?inst\]|<\|im_start\|>|<\|im_end\|>|<\|system\|>|###\s*(system|sistema)\s*(prompt)?\s*$)",
    r"^\s*(system|sistema)\s*(prompt|instructions?)?\s*:\s*(eres|sos|you are|tu nuevo|your new|ignora|ignore|a partir)",
    r"\b(nuevas|new)\s+(instrucciones|instructions|reglas|rules)\b.{0,10}(para vos|para ti|for you|del asistente|para el asistente|:\s*(eres|sos|you|ignora|a partir))",
    r"\b(responde|respondeme|contesta|actua|habla|answer|respond|reply)\w*\b.{0,20}\b(sin|without)\s+(restricciones|limites|filtros|censura|reglas|restrictions|filters|rules)\b",
    r"\b(hipoteticamente|hypothetically|imagina que|supongamos que)\b.{0,60}\b(no tuvieras|sin|no existieran|no hubiera|didn.t have)\b.{0,20}\b(reglas|restricciones|limites|rules|restrictions)",
    r"\b(soy|i am|habla con|te habla)\b.{0,10}\b(tu creador|tu desarrollador|tu programador|quien te programo|tu administrador|your creator|your developer)\b",
    r"\b(desactiva|apaga|deshabilita|saltea|disable|turn off|bypass)\b.{0,15}\b(tus|tu|your)\b.{0,15}\b(seguridad|filtros|guardrails|controles|restricciones|reglas|safety|filters)",
    r"\b(cambia|modifica|actualiza|asignate|asignarme|poneme|ponme|setea)\b.{0,10}\b(mi rol|tu rol|el rol del usuario|my role)\b",
    r"\b(trata|tratame|considerame|tomame|treat me)\b.{0,5}\b(como|as)\b.{0,5}\b(supervisor|tecnico|admin|administrador|root)",
]

PATRONES_SENSIBLE = [
    # Pedidos directos de credenciales/secretos (mencionar "olvidé mi contraseña" NO se bloquea)
    r"\b(dame|dime|decime|pasame|pasa|pasas|me das|me decis|me pasas|podes pasarme|podes darme|mostrame|mostra|muestra|muestrame|enviame|mandame|compartime|comparti|revelame|listame|exporta|exportame|cual es|cuales son|sabes)\b.{0,30}\b(contrasena|contrasenas|password|passwords|clave|claves|credencial|credenciales|tokens?|api ?keys?|secretos|hashes|pin)\b",
    r"\b(api ?key|secret ?key|jwt secret|private key|clave privada|cadena de conexion|connection string)\b",
    r"\b(lista|listado|listame|exporta|exportame|dump|volcado|pasame|dame|mostrame)\b.{0,25}\b(de )?(todos los |todas las |los |las )?(usuarios|empleados|clientes|correos|emails|mails|telefonos|dni|datos personales|legajos)\b",
    r"\b(dame|decime|dime|pasame|cual es|cuales son|mostrame|quiero saber|necesito saber)\b.{0,25}\b(datos personales|direccion|domicilio|telefono|celular|dni|cuil|sueldo|salario|legajo|mail|email|correo)\b.{0,10}\b(de|del)\b",
    r"\b(select\s+.{0,40}\bfrom\b|drop\s+table|delete\s+from|union\s+select|insert\s+into|;\s*--|'\s*or\s*'?1'?\s*=\s*'?1)",
    r"\b(tickets?|incidencias?|casos?)\b.{0,30}\b(de otro usuario|de otros usuarios|de otra persona|de todos los usuarios|ajenos|de mis companeros|de otro empleado)\b",
    r"\b(cuales son|dame|decime|listame|lista|mostrame|pasame)\b.{0,25}\b(vulnerabilidades|exploits?|puertos abiertos|ips? internas?|topologia de red|reglas del firewall|servidores internos|usuarios administradores)\b",
]

PATRONES_FUERA_DE_TEMA = [
    r"\b(escribi|escribime|escribe|redacta|redactame|crea|creame|compone|componeme|inventa|inventame|genera|haceme)\b.{0,20}\b(un|una)?\s*(poema|cuento|historia|cancion|chiste|ensayo|novela|carta de amor|rap|monografia|trabajo practico)\b",
    r"\b(receta|recetas|cocinar|horoscopo|signo zodiacal|tarot)\b",
    r"\b(quien gano|resultado del partido|futbol|mundial de|messi|la seleccion)\b",
    r"\b(cual es la capital de|cuantos habitantes|quien fue el|quien descubrio|quien invento)\b",
    r"\b(que opinas|tu opinion|que pensas)\b.{0,30}\b(politica|presidente|gobierno|partido|elecciones|religion|aborto|milei|peron)\b",
    r"\b(resolve|resolveme|resuelve|resolver)\b.{0,20}\b(ecuacion|integral|derivada|ejercicio|examen|parcial|tarea)\b",
    r"\b(traducime|traduceme|traduci esto|traduce esto|translate this)\b",
    r"\b(escribi|escribime|haceme|hace|crea|creame|genera|generame|programame|codea|codeame)\b.{0,15}\b(un |una )?(programa|codigo|script|funcion|app|pagina web|bot)\b.{0,25}\b(en|in)\b\s+(python|javascript|java|c\+\+|php|rust|golang|html)\b",
    r"\b(como|ensename|enseñame|haceme|crea|creame|genera|escribi|programa|ayudame a)\b.{0,20}\b(hackear|crackear|robar|clonar una tarjeta|un keylogger|un ransomware|un malware|un virus|hacer phishing|un ddos|bypassear|saltear la autenticacion|vulnerar|sacar la contrasena)\b",
    r"\b(contame un chiste|sos humano|tenes sentimientos|estas vivo|cual es tu modelo|que modelo sos|que modelo usas|quien te entreno|en que llm)\b",
]

PATRONES_COMANDO = [
    r"\b(ejecuta|ejecutalo|corre|correlo|lanza|run|execute)\b.{0,25}\b(este|el|un|estos|los|this)?\s*(comando|comandos|script|scripts|command|powershell|bash|cmd|\.bat|\.ps1)\b",
    r"\b(conectate|accede|ingresa|entra|logueate)\b.{0,20}\b(a|en)\b.{0,15}\b(mi (pc|equipo|computadora|maquina|notebook)|al servidor|por ssh|por rdp|remotamente)\b",
    r"(rm -rf|format c:|del /f|shutdown -|mkfs|dd if=|sudo |chmod 777|net user )",
    r"\b(podes|puedes|podrias)\b.{0,10}\b(reiniciar|apagar|formatear|reinstalar|borrar|modificar)\b.{0,20}\b(mi|el|la)\b.{0,10}\b(pc|equipo|servidor|computadora|notebook|router)\b",
]

# Secretos que se enmascaran en adjuntos y respuestas
PATRONES_SECRETOS = [
    (re.compile(r"(?i)\b(password|passwd|pwd|contrase[ñn]a|clave|secret|token|api[_-]?key)\b(\s*[:=]\s*|\s+)(\S{3,})"),
     lambda m: f"{m.group(1)}{m.group(2)}[REDACTADO]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}\b"), lambda m: "[TOKEN_REDACTADO]"),
    (re.compile(r"\b(sk|pk|rk)-[A-Za-z0-9]{16,}\b"), lambda m: "[API_KEY_REDACTADA]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), lambda m: "[API_KEY_REDACTADA]"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
     lambda m: "[CLAVE_PRIVADA_REDACTADA]"),
    (re.compile(r"\b(?:\d[ -]?){13,16}\b"), lambda m: "[NUMERO_REDACTADO]" if _luhn(m.group(0)) else m.group(0)),
    (re.compile(r"(?i)\b(mongodb|postgres(?:ql)?|mysql|redis|amqp)://[^\s]+"), lambda m: f"{m.group(1)}://[REDACTADO]"),
]
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
EMAILS_PUBLICOS = {"soporte@techsupport.com.ar", "mesadeayuda@techsupport.com.ar"}


def _luhn(numero: str) -> bool:
    digitos = [int(c) for c in numero if c.isdigit()]
    if len(digitos) < 13:
        return False
    total = 0
    for i, d in enumerate(reversed(digitos)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _coincide(patrones: list[str], variantes: list[str]) -> str | None:
    for p in patrones:
        rx = re.compile(p, re.IGNORECASE | re.MULTILINE)
        for v in variantes:
            m = rx.search(v)
            if m:
                return m.group(0)[:120]
    return None


@dataclass
class ResultadoGuardrail:
    bloquear: bool = False
    tipo: str = ""
    severidad: str = "baja"
    respuesta: str = ""
    extracto: str = ""
    notas_para_modelo: list[str] = field(default_factory=list)


def analizar_entrada(texto: str) -> ResultadoGuardrail:
    """Primera barrera: se ejecuta antes de que el mensaje llegue al LLM."""
    if not texto or not texto.strip():
        return ResultadoGuardrail()
    if len(texto) > settings.MAX_MENSAJE_CARACTERES:
        return ResultadoGuardrail(True, "MENSAJE_EXCESIVO", "baja", RESPUESTA_LARGO, texto[:80])

    variantes = _variantes(texto)

    if m := _coincide(PATRONES_INJECTION, variantes):
        return ResultadoGuardrail(True, "PROMPT_INJECTION", "alta", RESPUESTA_INJECTION, m)
    if m := _coincide(PATRONES_SENSIBLE, variantes):
        return ResultadoGuardrail(True, "DATO_SENSIBLE", "alta", RESPUESTA_SENSIBLE, m)
    if m := _coincide(PATRONES_FUERA_DE_TEMA, variantes):
        return ResultadoGuardrail(True, "FUERA_DE_TEMA", "baja", RESPUESTA_FUERA_DE_TEMA, m)

    resultado = ResultadoGuardrail()
    if m := _coincide(PATRONES_COMANDO, variantes):
        # No se bloquea: puede ser un pedido legítimo ("necesito que reinicien el servidor").
        # Se le recuerda al modelo su restricción y se registra el evento.
        resultado.tipo = "COMANDO_REMOTO"
        resultado.extracto = m
        resultado.notas_para_modelo.append(
            "El usuario pide ejecutar comandos o actuar sobre un equipo. NO podés hacerlo ni dar "
            "instrucciones para ejecutar comandos peligrosos. Ofrecé registrar un ticket para que un "
            "técnico lo atienda."
        )
    return resultado


def enmascarar_secretos(texto: str) -> tuple[str, int]:
    """Enmascara contraseñas, tokens, claves, tarjetas, cadenas de conexión."""
    cantidad = 0
    for rx, reemplazo in PATRONES_SECRETOS:
        texto, n = rx.subn(reemplazo, texto)
        cantidad += n
    return texto, cantidad


# Patrones extra SOLO para contenido de adjuntos: en un log o captura nadie le habla al asistente.
PATRONES_ADJUNTO = [
    r"\b(para el|al|nota para el|mensaje para el|importante para el)\s+(asistente|agente|bot|modelo|ia|chatbot)\b",
    r"\b(note to|message for|instructions? for)\s+(the\s+)?(ai|assistant|agent|model|bot)\b",
    r"\b(ahora sos|ahora eres|sos ahora|eres ahora|now you are|you are now)\b",
    r"\b(cerra|cierra|elimina|borra|asigna|cambia|modifica|aproba|escala|delete|close)\b.{0,15}\b(todos|todas|los demas|las demas|all)\b.{0,10}\b(los |las )?(tickets|incidencias|casos|usuarios)\b",
    r"\b(asigna|asignale|pone|ponele|marca)\b.{0,20}\bprioridad\b.{0,10}\b(critica|alta)\b",
]


def sanitizar_adjunto(texto: str) -> tuple[str, str]:
    """
    Limpia el contenido extraído de un archivo/imagen ANTES de mostrárselo al modelo.
    Devuelve (texto_limpio, alerta). La alerta queda guardada en el adjunto.
    """
    lineas = (texto or "").splitlines()
    patrones = PATRONES_INJECTION + PATRONES_ADJUNTO
    sospechosas = {i for i, l in enumerate(lineas) if _coincide(patrones, _variantes(l))}
    if sospechosas:
        # Si hay una instrucción oculta, también se revisan pedidos de datos sensibles en el resto del archivo
        sospechosas |= {i for i, l in enumerate(lineas) if _coincide(PATRONES_SENSIBLE, _variantes(l))}
        # y las líneas inmediatamente siguientes que continúan la orden (texto sin formato de log)
        for i in sorted(sospechosas):
            j = i + 1
            while j < len(lineas) and lineas[j].strip() and not RX_LINEA_LOG.match(lineas[j]) and j - i <= 3:
                sospechosas.add(j)
                j += 1
    alertas = ["instrucciones ocultas (prompt injection indirecta)"] if sospechosas else []
    limpias = [
        "[LÍNEA REMOVIDA POR SEGURIDAD: contenía instrucciones dirigidas al asistente]" if i in sospechosas else l
        for i, l in enumerate(lineas)
    ]
    limpio, n = enmascarar_secretos("\n".join(limpias))
    if n:
        alertas.append(f"{n} dato(s) sensible(s) enmascarado(s)")
    return limpio, "; ".join(alertas)


RX_LINEA_LOG = re.compile(r"^\s*(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}|L\d+:|\[|\(|TIPO:|LEGIBILIDAD:|SISTEMA_|MENSAJE_|TEXTO_|DESCRIPCION:)")


def redactar_salida(texto: str, emails_permitidos: set[str] | None = None) -> tuple[str, list[str]]:
    """Última barrera: se aplica a TODO lo que el modelo responde."""
    hallazgos = []
    if CANARIO.lower() in (texto or "").lower() or "reglas_internas_agente" in (texto or "").lower():
        return RESPUESTA_INJECTION, ["FUGA_PROMPT"]
    texto, n = enmascarar_secretos(texto or "")
    if n:
        hallazgos.append("SECRETO")
    permitidos = EMAILS_PUBLICOS | (emails_permitidos or set())

    def _email(m):
        if m.group(0).lower() in permitidos:
            return m.group(0)
        hallazgos.append("EMAIL")
        return "[email protegido]"

    texto = EMAIL.sub(_email, texto)
    return texto, hallazgos


class LimitadorTasa:
    """Ventana deslizante en memoria: N mensajes por minuto por usuario."""

    def __init__(self, maximo: int, ventana_seg: int = 60):
        self.maximo = maximo
        self.ventana = ventana_seg
        self._registro: dict[int, deque] = defaultdict(deque)

    def permitir(self, usuario_id: int) -> bool:
        ahora = time.monotonic()
        cola = self._registro[usuario_id]
        while cola and ahora - cola[0] > self.ventana:
            cola.popleft()
        if len(cola) >= self.maximo:
            return False
        cola.append(ahora)
        return True


limitador_chat = LimitadorTasa(settings.MENSAJES_POR_MINUTO)
