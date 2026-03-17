# -*- coding: utf-8 -*-
"""Endpoints de reportes — placeholder para Fase 3."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.report import Report, CreditTransaction

router = APIRouter(prefix="/reports", tags=["reports"])


class ReportListResponse(BaseModel):
    id: int
    module: str
    protocol_name: str
    client_name: str
    credits_charged: int
    created_at: str

    model_config = {"from_attributes": True}


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
            credits_charged=r.credits_charged,
            created_at=r.created_at.isoformat(),
        )
        for r in reports
    ]


# TODO Fase 3: POST /generate — recibe JSON de resultados, genera PDF, descuenta crédito
