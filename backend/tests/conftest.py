"""
Configuración de pruebas: base de datos temporal y Ollama "apagado" (para probar
el comportamiento de degradación sin depender del modelo).
"""
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="techsupport_test_"))
os.environ["DB_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["SESIONES_DB_URL"] = f"sqlite+aiosqlite:///{_TMP / 'sesiones.db'}"
os.environ["VECTOR_DIR"] = str(_TMP / "vector")
os.environ["UPLOADS_DIR"] = str(_TMP / "uploads")
os.environ["OLLAMA_API_BASE"] = "http://127.0.0.1:9"  # puerto cerrado: fuerza modo sin Ollama
os.environ["MENSAJES_POR_MINUTO"] = "1000"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def base_limpia():
    from scripts import seed

    seed.main()
    yield


@pytest.fixture
def db():
    from app.db.database import get_db

    with get_db() as s:
        yield s


def usuario(db, username):
    from sqlalchemy import select

    from app.db.models import Usuario

    return db.scalar(select(Usuario).where(Usuario.username == username))
