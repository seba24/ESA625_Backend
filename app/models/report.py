# -*- coding: utf-8 -*-
"""Modelo de reporte generado."""

from datetime import datetime, timezone

from sqlalchemy import String, Integer, DateTime, Text, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(100), nullable=False)  # defibrillator, ventilator, etc.
    protocol_name: Mapped[str] = mapped_column(String(255), default="")
    client_name: Mapped[str] = mapped_column(String(255), default="")
    equipment_info: Mapped[str] = mapped_column(Text, default="")  # JSON con marca/modelo/serie
    result_data: Mapped[str] = mapped_column(Text, default="")  # JSON con resultados
    pdf_url: Mapped[str] = mapped_column(String(500), default="")
    pdf_size: Mapped[int] = mapped_column(Integer, default=0)
    credits_charged: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # positivo=compra, negativo=uso
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(500), default="")
    payment_id: Mapped[str] = mapped_column(String(255), default="")  # ID MercadoPago/Stripe
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
