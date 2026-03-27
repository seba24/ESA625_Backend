# -*- coding: utf-8 -*-
"""Endpoints de empresa — CRUD + logo/firma."""

import base64
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.company import Company

log = logging.getLogger(__name__)

router = APIRouter(prefix="/company", tags=["company"])


class CompanyCreate(BaseModel):
    name: str
    address: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    technician: str = ""
    logo_base64: Optional[str] = None
    logo_x: float = 0.0
    logo_y: float = 0.0
    logo_width: float = 0.0
    logo_height: float = 0.0
    signature_base64: Optional[str] = None
    signature_x: float = 0.0
    signature_y: float = 0.0
    signature_width: float = 0.0
    signature_height: float = 0.0


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    technician: Optional[str] = None
    logo_base64: Optional[str] = None
    logo_x: Optional[float] = None
    logo_y: Optional[float] = None
    logo_width: Optional[float] = None
    logo_height: Optional[float] = None
    signature_base64: Optional[str] = None
    signature_x: Optional[float] = None
    signature_y: Optional[float] = None
    signature_width: Optional[float] = None
    signature_height: Optional[float] = None


class CompanyResponse(BaseModel):
    id: int
    name: str
    address: str
    phone: str
    email: str
    website: str
    technician: str
    has_logo: bool
    logo_x: float
    logo_y: float
    logo_width: float
    logo_height: float
    has_signature: bool
    signature_x: float
    signature_y: float
    signature_width: float
    signature_height: float
    created_at: str

    model_config = {"from_attributes": True}


def _to_response(c: Company) -> CompanyResponse:
    return CompanyResponse(
        id=c.id, name=c.name, address=c.address, phone=c.phone,
        email=c.email, website=c.website, technician=c.technician,
        has_logo=c.logo is not None,
        logo_x=c.logo_x, logo_y=c.logo_y,
        logo_width=c.logo_width, logo_height=c.logo_height,
        has_signature=c.signature is not None,
        signature_x=c.signature_x, signature_y=c.signature_y,
        signature_width=c.signature_width, signature_height=c.signature_height,
        created_at=c.created_at.isoformat(),
    )


@router.get("/", response_model=List[CompanyResponse])
def list_companies(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Listar empresas del usuario."""
    companies = db.query(Company).filter(Company.user_id == user.id).all()
    return [_to_response(c) for c in companies]


@router.post("/", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
def create_company(
    req: CompanyCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Crear empresa."""
    logo_bytes = base64.b64decode(req.logo_base64) if req.logo_base64 else None
    sig_bytes = base64.b64decode(req.signature_base64) if req.signature_base64 else None

    company = Company(
        user_id=user.id,
        name=req.name,
        address=req.address,
        phone=req.phone,
        email=req.email,
        website=req.website,
        technician=req.technician,
        logo=logo_bytes,
        logo_x=req.logo_x, logo_y=req.logo_y,
        logo_width=req.logo_width, logo_height=req.logo_height,
        signature=sig_bytes,
        signature_x=req.signature_x, signature_y=req.signature_y,
        signature_width=req.signature_width, signature_height=req.signature_height,
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    log.info(f"Empresa creada: {company.name} (id={company.id}) por user={user.id}")
    return _to_response(company)


@router.put("/{company_id}", response_model=CompanyResponse)
def update_company(
    company_id: int,
    req: CompanyUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Actualizar empresa."""
    company = db.query(Company).filter(
        Company.id == company_id, Company.user_id == user.id
    ).first()
    if not company:
        raise HTTPException(404, "Empresa no encontrada")

    if req.name is not None:
        company.name = req.name
    if req.address is not None:
        company.address = req.address
    if req.phone is not None:
        company.phone = req.phone
    if req.email is not None:
        company.email = req.email
    if req.website is not None:
        company.website = req.website
    if req.technician is not None:
        company.technician = req.technician
    if req.logo_base64 is not None:
        company.logo = base64.b64decode(req.logo_base64) if req.logo_base64 else None
    if req.logo_x is not None:
        company.logo_x = req.logo_x
    if req.logo_y is not None:
        company.logo_y = req.logo_y
    if req.logo_width is not None:
        company.logo_width = req.logo_width
    if req.logo_height is not None:
        company.logo_height = req.logo_height
    if req.signature_base64 is not None:
        company.signature = base64.b64decode(req.signature_base64) if req.signature_base64 else None
    if req.signature_x is not None:
        company.signature_x = req.signature_x
    if req.signature_y is not None:
        company.signature_y = req.signature_y
    if req.signature_width is not None:
        company.signature_width = req.signature_width
    if req.signature_height is not None:
        company.signature_height = req.signature_height

    db.commit()
    db.refresh(company)
    return _to_response(company)


@router.delete("/{company_id}")
def delete_company(
    company_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Eliminar empresa."""
    company = db.query(Company).filter(
        Company.id == company_id, Company.user_id == user.id
    ).first()
    if not company:
        raise HTTPException(404, "Empresa no encontrada")

    db.delete(company)
    db.commit()
    return {"message": f"Empresa '{company.name}' eliminada"}


@router.get("/{company_id}/logo")
def get_logo(
    company_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Obtener logo de empresa como base64."""
    company = db.query(Company).filter(
        Company.id == company_id, Company.user_id == user.id
    ).first()
    if not company or not company.logo:
        raise HTTPException(404, "Logo no encontrado")

    return {"logo_base64": base64.b64encode(company.logo).decode('ascii')}


@router.get("/{company_id}/signature")
def get_signature(
    company_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Obtener firma de empresa como base64."""
    company = db.query(Company).filter(
        Company.id == company_id, Company.user_id == user.id
    ).first()
    if not company or not company.signature:
        raise HTTPException(404, "Firma no encontrada")

    return {"signature_base64": base64.b64encode(company.signature).decode('ascii')}


@router.get("/{company_id}/protocol-key")
def get_protocol_key(
    company_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Obtener clave de cifrado de protocolos de la empresa."""
    company = db.query(Company).filter(
        Company.id == company_id, Company.user_id == user.id
    ).first()
    if not company:
        raise HTTPException(404, "Empresa no encontrada")

    return {"protocol_key": company.protocol_key, "company_id": company.id, "company_name": company.name}
