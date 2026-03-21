# -*- coding: utf-8 -*-
"""Endpoints de reportes."""

import io
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.report import Report, CreditTransaction
from app.schemas.reports import ReportUploadResponse, ReportListResponse
from app.services.report_service import save_report_pdf, get_report_filepath

log = logging.getLogger(__name__)

# Mapeo módulo → generador
REPORT_GENERATORS = {
    "ventilator": "app.services.reports.ventilator_report.VentilatorReportGenerator",
    "defibrillator": "app.services.reports.defibrillator_report.DefibrillatorReportGenerator",
    "electrosurgery": "app.services.reports.electrosurgery_report.ESUReportGenerator",
    "ecg_performance": "app.services.reports.ecg_performance_report.ECGPerformanceReportGenerator",
    "pacemaker": "app.services.reports.pacemaker_report.PacemakerReportGenerator",
    "multiparameter_monitor": "app.services.reports.multiparameter_report.MPReportGenerator",
    "infusion_pump": "app.services.reports.infusion_pump_report.InfusionPumpReportGenerator",
    "patient_simulation": "app.services.reports.patient_simulation_report.PatientSimulationReportGenerator",
    "electrical_safety": "app.services.reports.electrical_safety_report.ElectricalSafetyReportGenerator",
}

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


class GenerateReportRequest(BaseModel):
    module: str
    results: Dict[str, Any]
    client: Dict[str, Any] = {}
    equipment: Dict[str, Any] = {}
    protocol: Dict[str, Any] = {}
    analyzer: Dict[str, Any] = {}
    company: Dict[str, Any] = {}


@router.post("/generate")
def generate_report(
    req: GenerateReportRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generar PDF en el servidor a partir de datos JSON.
    Descuenta 1 crédito. Devuelve el PDF como descarga.
    """
    # Verificar créditos
    if user.credits < 1:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Sin créditos disponibles",
        )

    # Verificar módulo soportado
    generator_path = REPORT_GENERATORS.get(req.module)
    if not generator_path:
        supported = list(REPORT_GENERATORS.keys())
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Módulo no soportado. Disponibles: {supported}",
        )

    # Importar generador dinámicamente
    try:
        module_path, class_name = generator_path.rsplit(".", 1)
        import importlib
        mod = importlib.import_module(module_path)
        GeneratorClass = getattr(mod, class_name)
    except Exception as e:
        log.error(f"Error importando generador {generator_path}: {e}")
        raise HTTPException(500, f"Error cargando generador: {e}")

    # Preparar datos
    results_data = {
        "results": req.results,
        "client": req.client,
        "equipment": req.equipment,
        "protocol": req.protocol,
        "analyzer": req.analyzer,
    }

    # Setear datos de empresa si vienen
    generator = GeneratorClass()
    if req.company:
        generator.company_name = req.company.get("name", "")
        generator.company_address = req.company.get("address", "")
        generator.company_phone = req.company.get("phone", "")
        generator.company_email = req.company.get("email", "")
        generator.company_website = req.company.get("website", "")
        generator.technician_name = req.company.get("technician", "")

    # Generar PDF en memoria
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result_path = generator.generate_report(results_data, output_path=tmp_path)
        if not result_path or not os.path.exists(result_path):
            raise HTTPException(500, "Error generando PDF")

        with open(result_path, "rb") as f:
            pdf_bytes = f.read()
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    # Descontar crédito
    user.credits -= 1
    txn = CreditTransaction(
        user_id=user.id,
        amount=-1,
        balance_after=user.credits,
        description=f"Reporte {req.module} generado en servidor",
    )
    db.add(txn)

    # Guardar registro
    report = Report(
        user_id=user.id,
        module=req.module,
        protocol_name=req.protocol.get("name", ""),
        client_name=req.client.get("institucion", req.client.get("name", "")),
        equipment_info=str(req.equipment),
        pdf_size=len(pdf_bytes),
        credits_charged=1,
    )
    db.add(report)
    db.commit()

    log.info(f"PDF generado para user {user.id}, módulo {req.module}, "
             f"créditos restantes: {user.credits}")

    # Devolver PDF como descarga
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="reporte_{req.module}.pdf"',
            "X-Credits-Remaining": str(user.credits),
        },
    )
