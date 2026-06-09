# -*- coding: utf-8 -*-
"""Modelo de suscripciones para modulos de gestion del SGC.

#870 Fase 1: cada fila representa una suscripcion activa de un usuario
a un modulo de gestion (SE, IB, PG, KB) por un periodo (monthly,
quarterly, semester, annual).

Cuando un usuario renueva o extiende su suscripcion, se actualiza la
fila existente extendiendo `expires_at`. Si compra otro modulo, se
crea una fila nueva.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import String, Integer, DateTime, Boolean, Numeric, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# Valores permitidos (referencia para validacion en routers; la DB tambien los enforca)
ALLOWED_MODULE_IDS = {
    "service_enterprise",
    "biomedical_engineering",
    "proposal_generator",
    "knowledge_base",
}

ALLOWED_PERIODS = {"monthly", "quarterly", "semester", "annual"}

ALLOWED_STATUSES = {"active", "expired", "cancelled", "pending"}


# Duracion de cada periodo en dias (referencia para calcular expires_at)
PERIOD_DAYS = {
    "monthly": 30,
    "quarterly": 90,
    "semester": 180,
    "annual": 365,
}


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    module_id: Mapped[str] = mapped_column(String(64), nullable=False)
    period: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    amount_paid_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0")
    )
    amount_paid_ars: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0")
    )
    mp_subscription_id: Mapped[str] = mapped_column(String(128), nullable=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    granted_by_admin_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def is_currently_active(self) -> bool:
        """True si la suscripcion esta activa y no ha vencido."""
        if self.status != "active":
            return False
        return self.expires_at > datetime.now(timezone.utc)

    def days_left(self) -> int:
        """Dias hasta vencimiento. Negativo si ya vencio. 0 si vence hoy."""
        delta = self.expires_at - datetime.now(timezone.utc)
        return delta.days
