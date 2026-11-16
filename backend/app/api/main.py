"""
Punto de entrada de la API.

    cd backend
    uvicorn app.api.main:app --reload --port 8000
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db.database import crear_tablas
from app.api.rutas import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("LiteLLM").setLevel(logging.WARNING)

@asynccontextmanager
async def lifespan(_: FastAPI):
    crear_tablas()
    yield


app = FastAPI(title="TechSupport S.A. — Agente de tickets", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True,
    allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def cabeceras_seguridad(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@app.exception_handler(RequestValidationError)
async def validacion(_: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": {"mensaje": "Datos inválidos en la solicitud."}})


@app.exception_handler(Exception)
async def error_generico(_: Request, exc: Exception):
    logging.getLogger("api").exception("Error no controlado")
    # Nunca exponer trazas internas al cliente
    return JSONResponse(status_code=500, content={"detail": {"mensaje": "Error interno del servidor."}})


app.include_router(router)
