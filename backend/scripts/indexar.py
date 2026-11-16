"""
Indexación RAG (fase 1 del RAG: preparar los documentos).

  1. Lee data/conocimiento/*.md            -> colección "conocimiento"
  2. Lee todos los tickets de la base       -> colección "tickets"

    cd backend
    python -m scripts.indexar

Requiere Ollama corriendo con:  ollama pull nomic-embed-text
"""
from sqlalchemy import select

from app.db.database import get_db
from app.db.models import Ticket
from app.rag import vector_store


def main():
    if not vector_store.ollama_disponible():
        print("✘ Ollama no responde o falta el modelo de embeddings. Ejecutá: ollama pull nomic-embed-text")
        print("  (La app funciona igual con búsqueda léxica, pero sin búsqueda semántica.)")
        return
    n = vector_store.indexar_conocimiento()
    print(f"✔ Base de conocimiento: {n} fragmentos indexados")
    with get_db() as db:
        tickets = db.scalars(select(Ticket)).all()
        ok = sum(vector_store.indexar_ticket(t) for t in tickets)
    print(f"✔ Tickets indexados: {ok}/{len(tickets)}")

    pruebas = ["¿qué prioridad corresponde si se cae la facturación?", "VPN error -14"]
    for p in pruebas:
        r = vector_store.buscar_conocimiento(p, k=1)
        if r:
            print(f"  Prueba '{p}' -> {r[0]['fuente']} / {r[0]['seccion']} (relevancia {r[0]['relevancia']})")


if __name__ == "__main__":
    main()
