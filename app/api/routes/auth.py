# -*- coding: utf-8 -*-
"""Endpoints de autenticación."""

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.core.deps import get_current_user
from app.models.user import User
from app.models.login_attempt import LoginAttempt
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse

log = logging.getLogger(__name__)

# Configuración de bloqueo
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

router = APIRouter(prefix="/auth", tags=["auth"])


def _get_client_ip(request: Request) -> str:
    """Obtener IP real del cliente."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_locked_out(email: str, db: Session) -> bool:
    """Verificar si el email está bloqueado por intentos fallidos."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=LOCKOUT_MINUTES)
    failed_count = db.query(func.count(LoginAttempt.id)).filter(
        LoginAttempt.email == email,
        LoginAttempt.success == False,
        LoginAttempt.created_at >= cutoff,
    ).scalar()
    return failed_count >= MAX_FAILED_ATTEMPTS


def _record_attempt(db: Session, email: str, ip: str, user_agent: str,
                    success: bool, reason: str = ""):
    """Registrar intento de login."""
    attempt = LoginAttempt(
        email=email,
        ip_address=ip,
        user_agent=user_agent,
        success=success,
        failure_reason=reason,
    )
    db.add(attempt)
    db.commit()


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Autenticar usuario y devolver token JWT."""
    ip = _get_client_ip(request)
    ua = request.headers.get("User-Agent", "")[:500]

    # Verificar bloqueo
    if _is_locked_out(req.email, db):
        _record_attempt(db, req.email, ip, ua, False, "bloqueado")
        log.warning(f"Login bloqueado para {req.email} desde {ip}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Demasiados intentos fallidos. Reintente en {LOCKOUT_MINUTES} minutos.",
        )

    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.hashed_password):
        reason = "usuario no existe" if not user else "contraseña incorrecta"
        _record_attempt(db, req.email, ip, ua, False, reason)
        log.warning(f"Login fallido para {req.email} desde {ip}: {reason}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
        )
    if not user.is_active:
        _record_attempt(db, req.email, ip, ua, False, "cuenta desactivada")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta desactivada",
        )

    # Login exitoso
    _record_attempt(db, req.email, ip, ua, True)

    # Actualizar machine_id si se envía
    if req.machine_id and user.machine_id != req.machine_id:
        user.machine_id = req.machine_id
        db.commit()

    token = create_access_token({"sub": str(user.id), "email": user.email})
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        full_name=user.full_name,
        credits=user.credits,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """Registrar nuevo usuario."""
    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El email ya está registrado",
        )
    user = User(
        email=req.email,
        hashed_password=hash_password(req.password),
        full_name=req.full_name,
        company=req.company,
        machine_id=req.machine_id,
        credits=3,  # 3 reportes gratis de bienvenida
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": str(user.id), "email": user.email})
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        full_name=user.full_name,
        credits=user.credits,
    )


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)):
    """Obtener datos del usuario actual."""
    return user
