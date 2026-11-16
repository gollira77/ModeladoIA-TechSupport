"""
Carga los datos FICTICIOS de prueba: usuarios y tickets históricos (con su historial).

    cd backend
    python -m scripts.seed            # crea la base (borra la anterior)

Contraseña de todos los usuarios de demo: demo123
"""
import json
import random
import shutil
from datetime import timedelta

from app.config import settings
from app.db.database import Base, engine, get_db
from app.db.models import Comentario, EventoHistorial, Ticket, Usuario, ahora
from app.api.auth import hash_password

SEMILLA = settings.DATA_DIR / "semilla"
PASSWORD_DEMO = "demo123"


def main():
    random.seed(7)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    # Limpia adjuntos subidos en pruebas anteriores
    if settings.UPLOADS_DIR.exists():
        shutil.rmtree(settings.UPLOADS_DIR)
    settings.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    usuarios = json.loads((SEMILLA / "usuarios.json").read_text(encoding="utf-8"))
    tickets = json.loads((SEMILLA / "tickets_historicos.json").read_text(encoding="utf-8"))

    with get_db() as db:
        por_username = {}
        for u in usuarios:
            obj = Usuario(password_hash=hash_password(PASSWORD_DEMO), **u)
            db.add(obj)
            por_username[u["username"]] = obj
        db.flush()

        for t in tickets:
            momento = ahora() - timedelta(days=t["dias_atras"], hours=random.randint(1, 6))
            solicitante = por_username[t["solicitante"]]
            responsable = por_username.get(t["responsable"]) if t["responsable"] else None
            ticket = Ticket(
                id=t["id"], creado_en=momento, actualizado_en=momento, solicitante_id=solicitante.id,
                responsable_id=responsable.id if responsable else None, titulo=t["titulo"],
                descripcion=t["descripcion"], sistema_afectado=t["sistema"], mensaje_error=t["error"],
                categoria=t["categoria"], prioridad=t["prioridad"], prioridad_justificacion=t["justificacion"],
                prioridad_revisada=bool(t["camino"]), estado="Abierto", canal="agente",
            )
            db.add(ticket)
            db.flush()

            def evento(tipo, actor, anterior="", nuevo="", detalle="", origen="agente"):
                nonlocal momento
                db.add(EventoHistorial(ticket_id=ticket.id, tipo=tipo, valor_anterior=anterior, valor_nuevo=nuevo,
                                       detalle=detalle, actor_id=actor.id, origen=origen, creado_en=momento))

            evento("CREACION", solicitante, nuevo="Abierto",
                   detalle=f"Ticket creado. Categoría: {t['categoria']}. Prioridad propuesta: {t['prioridad']}")
            if responsable:
                momento += timedelta(minutes=random.randint(2, 20))
                evento("ASIGNACION", solicitante, nuevo=responsable.nombre,
                       detalle=f"Asignación automática por especialidad '{t['categoria']}'.", origen="sistema")
            estado = "Abierto"
            for nuevo, actor_u, comentario in t["camino"]:
                momento += timedelta(hours=random.randint(1, 20) if t["dias_atras"] > 1 else random.randint(1, 3) / 4)
                actor = por_username[actor_u]
                evento("CAMBIO_ESTADO", actor, estado, nuevo, comentario, origen="panel")
                if comentario:
                    db.add(Comentario(ticket_id=ticket.id, autor_id=actor.id, texto=f"[{estado} → {nuevo}] {comentario}",
                                      creado_en=momento))
                estado = nuevo
            ticket.estado = estado
            ticket.actualizado_en = momento

        # Un comentario interno de ejemplo (solo lo ve soporte)
        db.add(Comentario(ticket_id=1042, autor_id=por_username["sergio.luna"].id, interno=True,
                          texto="Se observan intentos de login desde una IP externa. Se notificó a Seguridad."))

    print(f"✔ {len(usuarios)} usuarios y {len(tickets)} tickets históricos cargados. Contraseña demo: {PASSWORD_DEMO}")
    print("  Siguiente paso: python -m scripts.indexar   (requiere Ollama con nomic-embed-text)")


if __name__ == "__main__":
    main()
