# -*- coding: utf-8 -*-
"""ESA625 Backend — FastAPI application."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import logging
import traceback

from app.core.config import settings
from app.api.routes import auth, credits, reports, payments, admin

log = logging.getLogger(__name__)

app = FastAPI(
    title="ESA625 Backend",
    description="Backend para generación de reportes PDF y gestión de créditos",
    version=settings.app_version,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rutas
app.include_router(auth.router, prefix="/api")
app.include_router(credits.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(payments.router, prefix="/api")
app.include_router(admin.router, prefix="/api")


@app.on_event("startup")
def on_startup():
    """Crear tablas al arrancar (si hay DB disponible)."""
    try:
        from app.core.database import engine, Base
        Base.metadata.create_all(bind=engine)
        log.info("Base de datos inicializada")
    except Exception as e:
        log.warning(f"No se pudo conectar a la DB: {e} — arrancando sin DB")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Capturar errores no manejados y devolver detalle."""
    log.error(f"Error no manejado: {exc}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "type": type(exc).__name__},
    )


@app.get("/api/health")
def health_check():
    """Health check para DigitalOcean."""
    db_type = "postgresql" if settings.database_url.startswith("postgresql") else "sqlite"
    return {
        "status": "ok",
        "version": settings.app_version,
        "env": settings.app_env,
        "db": db_type,
    }
