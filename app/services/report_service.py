# -*- coding: utf-8 -*-
"""Servicio de gestión de reportes PDF."""

import os
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.user import User
from app.models.report import Report, CreditTransaction

log = logging.getLogger(__name__)

# Directorio para almacenar PDFs subidos
REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "reports_storage")
os.makedirs(REPORTS_DIR, exist_ok=True)


def save_report_pdf(
    db: Session,
    user: User,
    pdf_bytes: bytes,
    module: str,
    protocol_name: str = "",
    client_name: str = "",
    equipment_info: str = "",
) -> Report:
    """
    Guarda un PDF, descuenta 1 crédito y registra la transacción.

    Raises:
        ValueError: Si no hay créditos suficientes.
    """
    if user.credits < 1:
        raise ValueError("Créditos insuficientes. Compre más créditos para generar reportes.")

    # Guardar PDF en disco
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"report_{user.id}_{module}_{timestamp}.pdf"
    filepath = os.path.join(REPORTS_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(pdf_bytes)

    pdf_size = len(pdf_bytes)

    # Descontar crédito
    user.credits -= 1
    new_balance = user.credits

    # Registrar reporte
    report = Report(
        user_id=user.id,
        module=module,
        protocol_name=protocol_name,
        client_name=client_name,
        equipment_info=equipment_info,
        pdf_url=f"/api/reports/{filename}",
        pdf_size=pdf_size,
        credits_charged=1,
    )
    db.add(report)

    # Registrar transacción de crédito
    txn = CreditTransaction(
        user_id=user.id,
        amount=-1,
        balance_after=new_balance,
        description=f"Reporte {module}: {protocol_name or 'sin protocolo'} — {client_name or 'sin cliente'}",
    )
    db.add(txn)

    db.commit()
    db.refresh(report)

    log.info(f"Reporte guardado: {filename} — usuario {user.id} — créditos restantes: {new_balance}")
    return report


def get_report_filepath(filename: str) -> str:
    """Retorna la ruta completa de un PDF almacenado."""
    filepath = os.path.join(REPORTS_DIR, filename)
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Reporte no encontrado: {filename}")
    return filepath
