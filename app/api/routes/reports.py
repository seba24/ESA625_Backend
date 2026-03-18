# -*- coding: utf-8 -*-
"""Endpoints de reportes."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.report import Report
from app.schemas.reports import ReportUploadResponse, ReportListResponse
from app.services.report_service import save_report_pdf, get_report_filepath

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/upload", response_model=ReportUploadResponse)
async def upload_report(
    pdf: UploadFile = File(...),
    module: str = Form(...),
    protocol_name: str = Form(""),
    client_name: str = Form(""),
    equipment_info: str = Form(""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Subir un reporte PDF generado por el desktop.
    Descuenta 1 crédito del usuario.
    """
    # Validar que es un PDF
    if not pdf.filename or not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo debe ser un PDF",
        )

    # Leer contenido
    pdf_bytes = await pdf.read()
    if len(pdf_bytes) < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo PDF está vacío o corrupto",
        )

    # Límite 50MB
    if len(pdf_bytes) > 50 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo excede el límite de 50MB",
        )

    try:
        report = save_report_pdf(
            db=db,
            user=user,
            pdf_bytes=pdf_bytes,
            module=module,
            protocol_name=protocol_name,
            client_name=client_name,
            equipment_info=equipment_info,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(e),
        )

    return ReportUploadResponse(
        id=report.id,
        module=report.module,
        pdf_url=report.pdf_url,
        credits_remaining=user.credits,
        message="Reporte guardado exitosamente",
    )


@router.get("/", response_model=List[ReportListResponse])
def list_reports(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 50,
):
    """Listar reportes generados por el usuario."""
    reports = (
        db.query(Report)
        .filter(Report.user_id == user.id)
        .order_by(Report.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        ReportListResponse(
            id=r.id,
            module=r.module,
            protocol_name=r.protocol_name,
            client_name=r.client_name,
            equipment_info=r.equipment_info,
            credits_charged=r.credits_charged,
            created_at=r.created_at.isoformat(),
        )
        for r in reports
    ]


@router.get("/{filename}")
def download_report(
    filename: str,
    user: User = Depends(get_current_user),
):
    """Descargar un PDF de reporte."""
    # Verificar que el filename pertenece al usuario
    if not filename.startswith(f"report_{user.id}_"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permiso para acceder a este reporte",
        )
    try:
        filepath = get_report_filepath(filename)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Reporte no encontrado",
        )
    return FileResponse(
        filepath,
        media_type="application/pdf",
        filename=filename,
    )
