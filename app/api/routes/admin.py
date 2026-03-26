# -*- coding: utf-8 -*-
"""Endpoints de administración — solo para admin."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from app.core.database import get_db
from app.core.deps import get_admin_user
from app.models.user import User
from app.models.report import CreditTransaction
from app.models.login_attempt import LoginAttempt

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


ADMIN_BOOTSTRAP_KEY = "SR-CERT-ADMIN-2026"


class BootstrapRequest(BaseModel):
    email: str
    bootstrap_key: str


@router.post("/bootstrap")
def bootstrap_admin(
    req: BootstrapRequest,
    db: Session = Depends(get_db),
):
    """Hacer admin al primer usuario. Solo funciona con clave de bootstrap."""
    if req.bootstrap_key != ADMIN_BOOTSTRAP_KEY:
        raise HTTPException(403, "Clave de bootstrap incorrecta")

    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")

    user.is_admin = True
    user.credits += 100  # Créditos iniciales de admin
    db.commit()

    return {"message": f"{req.email} es admin con 100 créditos", "user_id": user.id}


class AddCreditsRequest(BaseModel):
    user_id: Optional[int] = None
    email: Optional[str] = None
    credits: int
    reason: str = "Créditos de demostración"


class AddCreditsResponse(BaseModel):
    user_id: int
    email: str
    credits_added: int
    balance: int
    reason: str


class UserListResponse(BaseModel):
    id: int
    email: str
    full_name: str
    company: str
    credits: int
    is_admin: bool
    is_active: bool
    created_at: str

    model_config = {"from_attributes": True}


@router.post("/add-credits", response_model=AddCreditsResponse)
def add_credits(
    req: AddCreditsRequest,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Agregar créditos a un usuario (solo admin)."""
    if req.credits <= 0:
        raise HTTPException(400, "La cantidad de créditos debe ser positiva")

    # Buscar usuario por ID o email
    user = None
    if req.user_id:
        user = db.query(User).filter(User.id == req.user_id).first()
    elif req.email:
        user = db.query(User).filter(User.email == req.email).first()

    if not user:
        raise HTTPException(404, "Usuario no encontrado")

    user.credits += req.credits

    txn = CreditTransaction(
        user_id=user.id,
        amount=req.credits,
        balance_after=user.credits,
        description=f"{req.reason} (admin: {admin.email})",
    )
    db.add(txn)
    db.commit()

    log.info(f"Admin {admin.email} agregó {req.credits} créditos a {user.email}. Balance: {user.credits}")

    return AddCreditsResponse(
        user_id=user.id,
        email=user.email,
        credits_added=req.credits,
        balance=user.credits,
        reason=req.reason,
    )


@router.get("/users", response_model=List[UserListResponse])
def list_users(
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Listar todos los usuarios (solo admin)."""
    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        UserListResponse(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            company=u.company,
            credits=u.credits,
            is_admin=u.is_admin,
            is_active=u.is_active,
            created_at=u.created_at.isoformat(),
        )
        for u in users
    ]


@router.post("/make-admin")
def make_admin(
    email: str,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Hacer admin a un usuario (solo admin)."""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")
    user.is_admin = True
    db.commit()
    return {"message": f"{email} ahora es admin", "user_id": user.id}


class LoginAttemptResponse(BaseModel):
    id: int
    email: str
    ip_address: str
    user_agent: str
    success: bool
    failure_reason: str
    created_at: str

    model_config = {"from_attributes": True}


@router.get("/login-attempts", response_model=List[LoginAttemptResponse])
def get_login_attempts(
    email: Optional[str] = Query(None, description="Filtrar por email"),
    failed_only: bool = Query(False, description="Solo intentos fallidos"),
    limit: int = Query(100, ge=1, le=1000),
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Ver intentos de login (solo admin)."""
    query = db.query(LoginAttempt).order_by(LoginAttempt.created_at.desc())

    if email:
        query = query.filter(LoginAttempt.email == email)
    if failed_only:
        query = query.filter(LoginAttempt.success == False)

    attempts = query.limit(limit).all()
    return [
        LoginAttemptResponse(
            id=a.id,
            email=a.email,
            ip_address=a.ip_address,
            user_agent=a.user_agent,
            success=a.success,
            failure_reason=a.failure_reason,
            created_at=a.created_at.isoformat(),
        )
        for a in attempts
    ]
