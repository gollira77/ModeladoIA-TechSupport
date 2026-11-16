"""Pruebas de reglas de negocio: permisos, transiciones, duplicados, historial, resumen, adjuntos."""
import io

import pytest
from PIL import Image

from app.services import adjuntos, resumen, tickets
from app.services.errores import PermisoDenegado, TransicionInvalida, ValidacionError
from tests.conftest import usuario

DATOS = dict(
    titulo="La impresora del piso 2 no imprime",
    descripcion="La impresora HP del piso 2 recibe trabajos pero no imprime nada desde esta mañana.",
    sistema_afectado="Impresora HP LaserJet piso 2",
    categoria="Hardware",
    prioridad="Media",
    justificacion_prioridad="Afecta al área pero hay otra impresora en el piso 3.",
)


def test_crear_ticket_completo_asigna_id_historial_y_responsable(db):
    lucia = usuario(db, "lucia.gomez")
    r = tickets.crear_ticket(db, lucia, DATOS)
    assert r["resultado"] == "creado"
    t = r["ticket"]
    assert t["id"] >= 1054 and t["estado"] == "Abierto" and t["categoria"] == "Hardware"
    assert t["responsable"] == "Jorge Medina"  # especialidad Hardware
    h = tickets.consultar_historial(db, lucia, t["id"])
    assert [e["tipo"] for e in h["eventos"]] == ["CREACION", "ASIGNACION"]


def test_faltan_datos_f04(db):
    with pytest.raises(ValidacionError) as e:
        tickets.crear_ticket(db, usuario(db, "lucia.gomez"), {"titulo": "No anda", "descripcion": "no anda"})
    assert "sistema_afectado" in " ".join(e.value.datos["faltantes"])


def test_duplicado_detectado_y_confirmacion(db):
    lucia = usuario(db, "lucia.gomez")
    datos = dict(
        titulo="VPN FortiClient no conecta",
        descripcion="No puedo conectar la VPN FortiClient, aparece el error -14 al intentar conectar.",
        sistema_afectado="VPN FortiClient", mensaje_error="Credential or SSL VPN configuration is wrong (-14)",
        categoria="Redes y conectividad", prioridad="Media", justificacion_prioridad="Solo yo, puedo trabajar en la oficina.",
    )
    r = tickets.crear_ticket(db, lucia, datos)
    assert r["resultado"] == "posible_duplicado"
    assert r["coincidencias"][0]["id"] == 1043
    assert "creado" not in r["coincidencias"][0]  # ticket ajeno: no se exponen detalles
    r2 = tickets.crear_ticket(db, lucia, datos, confirmar_aunque_duplicado=True)
    assert r2["resultado"] == "creado"


def test_solicitante_no_ve_tickets_ajenos(db):
    lucia = usuario(db, "lucia.gomez")
    with pytest.raises(PermisoDenegado):
        tickets.consultar_ticket(db, lucia, 1043)  # es de Diego
    res = tickets.buscar_tickets(db, lucia, solicitante="diego.sosa")
    assert all(t["solicitante"] == "Lucía Gómez" for t in res["tickets"])


def test_transiciones_y_permisos(db):
    lucia, sergio, paula, vale = (usuario(db, n) for n in ("lucia.gomez", "sergio.luna", "paula.ibarra", "valeria.romero"))
    # 1052 está En progreso, asignado a Sergio
    with pytest.raises(PermisoDenegado):
        tickets.cambiar_estado(db, lucia, 1052, "Resuelto", "lo arreglé yo")
    with pytest.raises(PermisoDenegado):
        tickets.cambiar_estado(db, paula, 1052, "Resuelto", "no es mío")
    with pytest.raises(TransicionInvalida):
        tickets.cambiar_estado(db, sergio, 1052, "Cerrado", "saltando pasos")
    with pytest.raises(ValidacionError):
        tickets.cambiar_estado(db, sergio, 1052, "Resuelto", "")  # falta comentario
    tickets.cambiar_estado(db, sergio, 1052, "Resuelto", "Se borraron cookies del navegador.")
    tickets.cambiar_estado(db, lucia, 1052, "Cerrado", "Confirmo que funciona.")
    with pytest.raises(TransicionInvalida):
        tickets.cambiar_estado(db, vale, 1052, "En progreso", "reabrir")
    h = tickets.consultar_historial(db, lucia, 1052)
    assert [e["nuevo"] for e in h["eventos"] if e["tipo"] == "CAMBIO_ESTADO"][-2:] == ["Resuelto", "Cerrado"]


def test_prioridad_solo_soporte(db):
    lucia, sergio = usuario(db, "lucia.gomez"), usuario(db, "sergio.luna")
    with pytest.raises(PermisoDenegado):
        tickets.cambiar_prioridad(db, lucia, 1052, "Crítica", "es urgente para mí")
    r = tickets.cambiar_prioridad(db, sergio, 1052, "Alta", "Afecta a la demo con cliente de mañana")
    assert r["prioridad_nueva"] == "Alta"


def test_reasignacion_solo_supervisor(db):
    jorge, vale = usuario(db, "jorge.medina"), usuario(db, "valeria.romero")
    with pytest.raises(PermisoDenegado):
        tickets.asignar_ticket(db, jorge, 1052, "jorge.medina")
    r = tickets.asignar_ticket(db, vale, 1052, "Jorge")
    assert r["responsable_nuevo"] == "Jorge Medina"
    h = tickets.consultar_historial(db, vale, 1052)
    assert h["eventos"][-1]["tipo"] == "REASIGNACION"


def test_comentario_interno_oculto_al_solicitante(db):
    carla, sergio = usuario(db, "carla.ruiz"), usuario(db, "sergio.luna")
    with pytest.raises(PermisoDenegado):
        tickets.agregar_comentario(db, carla, 1042, "nota", interno=True)
    t = tickets.consultar_ticket(db, carla, 1042)
    assert not any("IP externa" in c["texto"] for c in t["comentarios"])
    t2 = tickets.consultar_ticket(db, sergio, 1042)
    assert any("IP externa" in c["texto"] for c in t2["comentarios"])


def test_resumen_por_rol(db):
    lucia, vale = usuario(db, "lucia.gomez"), usuario(db, "valeria.romero")
    global_ = resumen.generar_resumen(db, vale)
    propio = resumen.generar_resumen(db, lucia)
    assert global_["total"] == 24 and sum(global_["por_estado"].values()) == 24
    assert propio["total"] < global_["total"] and propio["activos_sin_asignar"] is None
    assert any(t["prioridad"] == "Crítica" for t in global_["urgentes_activos"])


def test_busqueda_criticas_pendientes(db):
    r = tickets.buscar_tickets(db, usuario(db, "valeria.romero"), estado="pendiente", prioridad="critica")
    assert {t["id"] for t in r["tickets"]} == {1046, 1048}


def _png() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (40, 20), "white").save(b, format="PNG")
    return b.getvalue()


def test_adjuntos_validacion_y_analisis(db):
    lucia = usuario(db, "lucia.gomez")
    with pytest.raises(ValidacionError):
        adjuntos.subir_y_analizar(db, lucia, "virus.exe", b"MZ\x90\x00")
    with pytest.raises(ValidacionError):
        adjuntos.subir_y_analizar(db, lucia, "foto.png", b"esto no es una imagen")
    log = (b"2026-11-05 08:00:01 INFO inicio\n2026-11-05 08:00:05 ERROR ORA-12541: TNS:no listener\n"
           b"2026-11-05 08:01:05 ERROR ORA-12541: TNS:no listener\npassword=secreta123\n")
    a = adjuntos.subir_y_analizar(db, lucia, "app.log", log)
    assert a.tipo == "log" and a.analisis_estado == "ok"
    assert "ORA-12541" in a.analisis and "secreta123" not in a.analisis
    img = adjuntos.subir_y_analizar(db, lucia, "captura.png", _png())
    # Sin Ollama ni texto legible: debe declarar la limitación (no inventar)
    assert img.analisis_estado in ("limitado", "error") and "LIMITACIÓN" in img.analisis
    r = tickets.crear_ticket(db, lucia, {**DATOS, "titulo": "Error ORA-12541 en el sistema de ventas",
                                         "sistema_afectado": "Sistema de ventas", "categoria": "Sistemas y aplicaciones"},
                             adjuntos_ids=[a.id])
    assert r["ticket"]["adjuntos"][0]["id"] == a.id
    with pytest.raises(PermisoDenegado):
        adjuntos.obtener_adjunto(db, usuario(db, "diego.sosa"), a.id)
