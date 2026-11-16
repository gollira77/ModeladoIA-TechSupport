"""Autenticación simple con JWT (usuarios ficticios para la demo)."""
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.db.database import get_db
from app.db.models import Usuario

_bearer = HTTPBearer(auto_error=False)
ITERACIONES = 120_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERACIONES)
    return f"pbkdf2${salt.hex()}${h.hex()}"


def verificar_password(password: str, guardado: str) -> bool:
    try:
        _, salt_hex, h_hex = guardado.split("$")
        h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), ITERACIONES)
        return hmac.compare_digest(h.hex(), h_hex)
    except Exception:
        return False


def crear_token(u: Usuario) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRA_MINUTOS)
    return jwt.encode({"sub": str(u.id), "rol": u.rol, "exp": exp}, settings.JWT_SECRET, algorithm="HS256")


def usuario_actual(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Usuario:
    if not cred:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta el token de acceso.")
    try:
        datos = jwt.decode(cred.credentials, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión inválida o vencida. Volvé a iniciar sesión.")
    with get_db() as db:
        u = db.get(Usuario, int(datos["sub"]))
        if not u or not u.activo:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario inactivo.")
        return u


def usuario_publico(u: Usuario) -> dict:
    return {"id": u.id, "username": u.username, "nombre": u.nombre, "rol": u.rol, "area": u.area}
