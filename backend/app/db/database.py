"""Conexión a SQLite con SQLAlchemy."""
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(
    settings.DB_URL,
    connect_args={"check_same_thread": False} if settings.DB_URL.startswith("sqlite") else {},
)


@event.listens_for(engine, "connect")
def _activar_foreign_keys(dbapi_conn, _):
    if settings.DB_URL.startswith("sqlite"):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


@contextmanager
def get_db():
    """Abre una sesión de base de datos y la cierra siempre (commit/rollback)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def crear_tablas():
    from app.db import models  # noqa: F401  (registra los modelos)

    Base.metadata.create_all(bind=engine)
