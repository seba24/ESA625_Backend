# -*- coding: utf-8 -*-
"""Modelo de empresa."""

from datetime import datetime, timezone

from cryptography.fernet import Fernet
from sqlalchemy import String, Integer, Float, DateTime, Text, LargeBinary, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _generate_fernet_key() -> str:
    """Genera una clave Fernet única para cifrado de protocolos."""
    return Fernet.generate_key().decode('ascii')


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(String(500), default="")
    phone: Mapped[str] = mapped_column(String(100), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    website: Mapped[str] = mapped_column(String(255), default="")
    technician: Mapped[str] = mapped_column(String(255), default="")
    logo: Mapped[bytes] = mapped_column(LargeBinary, nullable=True)
    logo_x: Mapped[float] = mapped_column(Float, default=0.0)
    logo_y: Mapped[float] = mapped_column(Float, default=0.0)
    logo_width: Mapped[float] = mapped_column(Float, default=0.0)
    logo_height: Mapped[float] = mapped_column(Float, default=0.0)
    signature: Mapped[bytes] = mapped_column(LargeBinary, nullable=True)
    signature_x: Mapped[float] = mapped_column(Float, default=0.0)
    signature_y: Mapped[float] = mapped_column(Float, default=0.0)
    signature_width: Mapped[float] = mapped_column(Float, default=0.0)
    signature_height: Mapped[float] = mapped_column(Float, default=0.0)
    protocol_key: Mapped[str] = mapped_column(String(255), default=_generate_fernet_key)
    # Template del título de reportes PDF. Soporta {module} como placeholder
    # que se reemplaza en runtime por el nombre del módulo (MARCAPASOS,
    # DESFIBRILADOR, etc.). Si está vacío, se usa el default del generator.
    report_title_template: Mapped[str] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
