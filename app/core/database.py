# -*- coding: utf-8 -*-
"""Conexión y sesión de base de datos."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings

connect_args = {}
db_url = settings.database_url

if db_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False
elif db_url.startswith("postgresql"):
    # Limpiar parámetros no soportados por psycopg2
    import re
    db_url = re.sub(r'[&?]channel_binding=[^&]*', '', db_url)

engine = create_engine(
    db_url, pool_pre_ping=True, connect_args=connect_args
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependency que provee una sesión de DB por request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
