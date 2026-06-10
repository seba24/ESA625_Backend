# -*- coding: utf-8 -*-
"""Modelos de ofertas relampago de creditos.

#871 Fase 2:
- Offer: definicion de una oferta (tipo, config, audiencia, vigencia, limites)
- OfferRedemption: cada vez que un usuario canjea una oferta

Los offer_type son 4:
- 'quantity_discount': cantidad fija con precio especial
  config: {"credits": 10, "price_ars": 70000}
- 'percent_off': % de descuento extra sobre precio normal
  config: {"discount_pct": 30, "min_credits": 1, "max_credits": 100}
- 'bonus': comprar X recibir Y extra de regalo
  config: {"buy_credits": 10, "get_extra_credits": 2}
- 'bundle': combo creditos + suscripcion
  config: {"credits": 50, "free_modules": ["biomedical_engineering"],
           "free_months": 1, "price_ars": 500000}

Los audience_type son 4:
- 'public': todos los usuarios
- 'user_email': un usuario por email (audience_value = email)
- 'user_list': lista CSV de emails (audience_value = "a@x.com,b@y.com")
- 'role': por rol de usuario (audience_value = "admin"|"clinical_user"|...)
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    String,
    Integer,
    DateTime,
    Boolean,
    Numeric,
    Text,
    ForeignKey,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


ALLOWED_OFFER_TYPES = {"quantity_discount", "percent_off", "bonus", "bundle"}
ALLOWED_AUDIENCE_TYPES = {"public", "user_email", "user_list", "role"}
ALLOWED_REDEMPTION_STATUSES = {"pending", "completed", "failed", "refunded"}


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    # Tipo de oferta y su config (JSON serializado, ver schema en offer_service.py)
    offer_type: Mapped[str] = mapped_column(String(32), nullable=False)
    config_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    # Audiencia
    audience_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="public", server_default="public"
    )
    audience_value: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    # Vigencia
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Limites
    max_redemptions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    current_redemptions: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    max_per_user: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    # Estado
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    # Auditoria
    created_by_admin_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    def is_currently_valid(self) -> bool:
        """True si la oferta esta activa, dentro de vigencia y con cupos."""
        if not self.active:
            return False
        now = datetime.now(timezone.utc)
        if self.starts_at > now or self.expires_at <= now:
            return False
        if self.max_redemptions > 0 and self.current_redemptions >= self.max_redemptions:
            return False
        return True

    def remaining_redemptions(self) -> int:
        """Cupos restantes. -1 si es ilimitada (max_redemptions=0)."""
        if self.max_redemptions == 0:
            return -1
        return max(0, self.max_redemptions - self.current_redemptions)


class OfferRedemption(Base):
    __tablename__ = "offer_redemptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    offer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("offers.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    credits_purchased: Mapped[int] = mapped_column(Integer, nullable=False)
    credits_bonus: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    amount_paid_ars: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    mp_payment_id: Mapped[str] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
