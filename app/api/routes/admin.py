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




class RemoveCreditsRequest(BaseModel):
    email: str
    credits: int
    reason: str = "Ajuste de creditos"


@router.post("/remove-credits", response_model=AddCreditsResponse)
def remove_credits(
    req: RemoveCreditsRequest,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Quitar creditos a un usuario (solo admin)."""
    if req.credits <= 0:
        raise HTTPException(400, "La cantidad debe ser positiva")

    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")

    if user.credits < req.credits:
        raise HTTPException(400, f"El usuario solo tiene {user.credits} creditos")

    user.credits -= req.credits

    txn = CreditTransaction(
        user_id=user.id,
        amount=-req.credits,
        balance_after=user.credits,
        description=f"QUITAR: {req.reason} (admin: {admin.email})",
    )
    db.add(txn)
    db.commit()

    log.info(f"Admin {admin.email} quito {req.credits} creditos a {user.email}. Balance: {user.credits}")

    return AddCreditsResponse(
        user_id=user.id,
        email=user.email,
        credits_added=-req.credits,
        balance=user.credits,
        reason=req.reason,
    )

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


# ----------------------------------------------------------------------
# Reset de password (admin)
# ----------------------------------------------------------------------

class ResetPasswordRequest(BaseModel):
    email: str
    new_password: str


class ResetPasswordResponse(BaseModel):
    user_id: int
    email: str
    message: str


@router.post("/reset-password", response_model=ResetPasswordResponse)
def reset_password(
    req: ResetPasswordRequest,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """
    Resetear la password de un usuario (solo admin).

    Caso de uso: usuario olvidó su password. El admin la resetea manualmente
    vía este endpoint usando tools/admin_credits.py reset-password.

    No requiere email SMTP ni link de recuperación — fix pragmático para el
    bug "no hay recuperación de password" hasta implementar el flujo completo.
    """
    from app.core.security import hash_password

    if len(req.new_password) < 4:
        raise HTTPException(400, "La password debe tener al menos 4 caracteres")

    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")

    user.hashed_password = hash_password(req.new_password)
    db.commit()

    log.info(
        f"Admin {admin.email} reseteó la password de {user.email} "
        f"(user_id={user.id})"
    )

    return ResetPasswordResponse(
        user_id=user.id,
        email=user.email,
        message="Password reseteada exitosamente",
    )


# ----------------------------------------------------------------------
# Suscripciones (#870 Fase 1)
# ----------------------------------------------------------------------

class GrantSubscriptionRequest(BaseModel):
    email: str
    module_id: str
    period: str  # 'monthly' | 'quarterly' | 'semester' | 'annual'
    months: Optional[int] = None  # opcional: si no se pasa, usa la duracion del periodo
    notes: str = "Asignacion manual de admin"


class GrantSubscriptionResponse(BaseModel):
    subscription_id: int
    user_email: str
    module_id: str
    period: str
    started_at: str
    expires_at: str
    days_left: int


@router.post("/grant-subscription", response_model=GrantSubscriptionResponse)
def grant_subscription(
    req: GrantSubscriptionRequest,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Asigna una suscripcion manual a un usuario (solo admin).

    Para demos a clientes, regalos, soporte. NO pasa por Mercado Pago.

    Si el usuario ya tiene una suscripcion activa para ese modulo, EXTIENDE
    su expires_at sumando la duracion del periodo (no crea fila nueva).
    """
    from datetime import datetime, timezone, timedelta
    from app.models.subscription import (
        Subscription,
        ALLOWED_MODULE_IDS,
        ALLOWED_PERIODS,
        PERIOD_DAYS,
    )

    if req.module_id not in ALLOWED_MODULE_IDS:
        raise HTTPException(400, f"module_id invalido. Permitidos: {sorted(ALLOWED_MODULE_IDS)}")
    if req.period not in ALLOWED_PERIODS:
        raise HTTPException(400, f"period invalido. Permitidos: {sorted(ALLOWED_PERIODS)}")

    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")

    # Duracion: por defecto la del periodo, o `months` si se paso explicito
    days_to_add = (
        req.months * 30 if req.months and req.months > 0 else PERIOD_DAYS[req.period]
    )
    now = datetime.now(timezone.utc)

    # Buscar suscripcion activa existente para extenderla
    existing = (
        db.query(Subscription)
        .filter(
            Subscription.user_id == user.id,
            Subscription.module_id == req.module_id,
            Subscription.status == "active",
            Subscription.expires_at > now,
        )
        .order_by(Subscription.expires_at.desc())
        .first()
    )

    if existing:
        # Extender desde el expires_at actual
        existing.expires_at = existing.expires_at + timedelta(days=days_to_add)
        existing.period = req.period
        existing.notes = (existing.notes + f"\n[ext {now.date()}] {req.notes}").strip()
        existing.updated_at = now
        sub = existing
        log.info(
            f"Admin {admin.email} EXTENDIO suscripcion #{sub.id} de {user.email} "
            f"a {req.module_id} hasta {sub.expires_at.isoformat()}"
        )
    else:
        # Crear nueva
        sub = Subscription(
            user_id=user.id,
            module_id=req.module_id,
            period=req.period,
            started_at=now,
            expires_at=now + timedelta(days=days_to_add),
            status="active",
            amount_paid_usd=0,
            amount_paid_ars=0,
            auto_renew=False,
            granted_by_admin_id=admin.id,
            notes=req.notes,
        )
        db.add(sub)
        log.info(
            f"Admin {admin.email} CREO suscripcion de {user.email} "
            f"a {req.module_id} ({req.period}) hasta "
            f"{(now + timedelta(days=days_to_add)).isoformat()}"
        )

    db.commit()
    db.refresh(sub)

    return GrantSubscriptionResponse(
        subscription_id=sub.id,
        user_email=user.email,
        module_id=sub.module_id,
        period=sub.period,
        started_at=sub.started_at.isoformat(),
        expires_at=sub.expires_at.isoformat(),
        days_left=sub.days_left(),
    )


class RevokeSubscriptionRequest(BaseModel):
    email: str
    module_id: str
    reason: str = "Revocada por admin"


@router.post("/revoke-subscription")
def revoke_subscription(
    req: RevokeSubscriptionRequest,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Revoca (cancela) la suscripcion activa de un usuario para un modulo.

    Marca status='cancelled' pero NO borra la fila. El cliente perdera acceso
    inmediatamente (validacion online del expires_at + status).
    """
    from app.models.subscription import Subscription

    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")

    sub = (
        db.query(Subscription)
        .filter(
            Subscription.user_id == user.id,
            Subscription.module_id == req.module_id,
            Subscription.status == "active",
        )
        .order_by(Subscription.expires_at.desc())
        .first()
    )
    if not sub:
        raise HTTPException(404, "No hay suscripcion activa para revocar")

    sub.status = "cancelled"
    sub.notes = (sub.notes + f"\n[REVOCADA por {admin.email}] {req.reason}").strip()
    db.commit()

    log.info(
        f"Admin {admin.email} REVOCO suscripcion #{sub.id} "
        f"de {user.email} a {req.module_id}: {req.reason}"
    )
    return {
        "subscription_id": sub.id,
        "user_email": user.email,
        "module_id": sub.module_id,
        "status": sub.status,
        "message": "Suscripcion revocada",
    }


# ----------------------------------------------------------------------
# Configuracion de precios (#870 Fase 1 ext)
# ----------------------------------------------------------------------

class PricingConfigItem(BaseModel):
    key: str
    value: float
    description: str
    updated_at: Optional[str] = None


class UpdatePricingRequest(BaseModel):
    key: str
    value: float


@router.get("/pricing-config", response_model=List[PricingConfigItem])
def get_pricing_config(
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Lista todas las claves de pricing_config con sus valores y descripciones.

    Para mostrar en la pestaña 'Configuracion de precios' del panel admin.
    Si la tabla esta vacia (DB recien creada sin seed), devuelve lista vacia
    y el admin tiene que aplicar la migracion 004.
    """
    from app.models.pricing_config import PricingConfig

    rows = db.query(PricingConfig).order_by(PricingConfig.key).all()
    return [
        PricingConfigItem(
            key=r.key,
            value=float(r.value),
            description=r.description,
            updated_at=r.updated_at.isoformat() if r.updated_at else None,
        )
        for r in rows
    ]


@router.put("/pricing-config")
def update_pricing_config(
    req: UpdatePricingRequest,
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Actualiza UN valor de pricing_config y invalida el cache del servicio.

    Solo permite editar claves que ya existen (no se pueden crear nuevas
    desde el admin para evitar errores). Si querias agregar una clave nueva,
    se hace via migracion SQL.
    """
    from app.models.pricing_config import PricingConfig
    from app.services.pricing import invalidate_cache as _invalidate_pricing_cache

    if req.value < 0:
        raise HTTPException(400, "El valor debe ser >= 0")

    row = db.query(PricingConfig).filter(PricingConfig.key == req.key).first()
    if not row:
        raise HTTPException(404, f"Clave de pricing no existe: {req.key}. Use migracion SQL para agregarla.")

    old_value = float(row.value)
    row.value = req.value
    row.updated_by_admin_id = admin.id
    db.commit()

    # Invalidar el cache del servicio para que el proximo calculo lea el nuevo valor
    _invalidate_pricing_cache()

    log.info(
        f"Admin {admin.email} actualizo pricing {req.key}: "
        f"{old_value} -> {req.value}"
    )
    return {
        "key": req.key,
        "old_value": old_value,
        "new_value": req.value,
        "message": "Precio actualizado, cache invalidado",
    }


# ----------------------------------------------------------------------
# Paquetes de creditos (#871 Fase 1)
# ----------------------------------------------------------------------
# Eliminados los endpoints CRUD de credit-packages. Los paquetes ahora se
# CALCULAN AL VUELO desde pricing_config (credit_base_price_ars +
# credit_qty_multiplier:<N>). El admin edita esos valores desde la seccion
# 'Configuracion de precios' que ya existe.


@router.get("/list-subscriptions")
def list_all_subscriptions(
    email: Optional[str] = Query(None, description="Filtrar por email de usuario"),
    module_id: Optional[str] = Query(None, description="Filtrar por modulo"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filtrar por status"),
    admin: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Lista todas las suscripciones del sistema (solo admin).

    Para auditoria y soporte. Si se filtra por email, solo las de ese usuario.
    """
    from app.models.subscription import Subscription

    query = db.query(Subscription, User).join(User, Subscription.user_id == User.id)

    if email:
        query = query.filter(User.email == email)
    if module_id:
        query = query.filter(Subscription.module_id == module_id)
    if status_filter:
        query = query.filter(Subscription.status == status_filter)

    rows = query.order_by(Subscription.expires_at.desc()).limit(500).all()

    return [
        {
            "id": s.id,
            "user_email": u.email,
            "module_id": s.module_id,
            "period": s.period,
            "started_at": s.started_at.isoformat(),
            "expires_at": s.expires_at.isoformat(),
            "status": s.status,
            "days_left": s.days_left(),
            "auto_renew": s.auto_renew,
            "amount_paid_usd": float(s.amount_paid_usd),
            "notes": s.notes,
        }
        for s, u in rows
    ]
