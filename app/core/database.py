# -*- coding: utf-8 -*-
"""Conexión y sesión de base de datos."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.database_url, pool_pre_ping=True, connect_args=connect_args
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
