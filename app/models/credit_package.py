# -*- coding: utf-8 -*-
"""Modelo de paquetes de creditos editables desde el panel admin."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Integer, Numeric, Text, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CreditPackage(Base):
    __tablename__ = "credit_packages"

    credits: Mapped[int] = mapped_column(Integer, primary_key=True)
    price_ars: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_by_admin_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
