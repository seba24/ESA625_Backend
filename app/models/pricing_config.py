# -*- coding: utf-8 -*-
"""Modelo para configuracion de precios editables desde el panel admin.

#870 Fase 1 ext: tabla clave-valor para precios + multiplicadores.
Permite ajustar precios sin redeploy. El servicio pricing.py lee de esta
tabla con cache de 5 min (TTL razonable para precios que no cambian seguido).

Keys soportadas:
- `module_price:<module_id>`     => precio mensual USD
- `period_multiplier:<period>`   => multiplicador descuento periodo
- `quantity_multiplier:<n>`      => multiplicador descuento cantidad
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import String, DateTime, Integer, Numeric, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PricingConfig(Base):
    __tablename__ = "pricing_config"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    updated_by_admin_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
