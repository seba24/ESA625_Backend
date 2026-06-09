# -*- coding: utf-8 -*-
"""Endpoints para suscripciones SaaS de modulos de gestion.

#870 Fase 1: endpoints minimos para que el cliente desktop pueda:
- Consultar el estado de su licencia para un modulo especifico
- Listar sus suscripciones activas
- Calcular el precio de un combo de modulos + periodo (preview)

La compra real (con Mercado Pago) se hace en Fase 3.
La asignacion manual la hace el admin con `/admin/grant-subscription`.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.subscription import (
    Subscription,
    ALLOWED_MODULE_IDS,
    ALLOWED_PERIODS,
)
from app.models.user import User
from app.services.pricing import (
    calculate_price,
    fetch_usd_oficial_bna,
    get_module_catalog,
    get_period_catalog,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


# ========== Schemas ==========


class LicenseStatus(BaseModel):
    """Estado de licencia de un modulo para el usuario actual."""
    module_id: str
    licensed: bool
    expires_at: Optional[str] = None  # ISO 8601 UTC
    days_left: Optional[int] = None
    period: Optional[str] = None
    status: Optional[str] = None


class SubscriptionItem(BaseModel):
    """Item de la lista de suscripciones activas."""
    id: int
    module_id: str
    period: str
    started_at: str
    expires_at: str
    status: str
    auto_renew: bool
    days_left: int
    amount_paid_usd: float
    amount_paid_ars: float


class PricingModuleItem(BaseModel):
    id: str
    name: str
    price_usd_monthly: float


class PricingResponse(BaseModel):
    """Respuesta del calculo de precios."""
    modules: List[PricingModuleItem]
    period: str
    months: int
    base_total_usd: float
    period_discount_pct: int
    quantity_discount_pct: int
    total_usd: float
    total_ars: float
    usd_to_ars_rate: Optional[float] = None
    savings_usd: float
    savings_pct: int


class CatalogResponse(BaseModel):
    """Catalogo completo de modulos y periodos disponibles."""
    modules: List[dict]
    periods: List[dict]
    usd_to_ars_rate: Optional[float] = None


# ========== Helpers ==========


def _get_active_subscription_for_module(
    db: Session, user_id: int, module_id: str
) -> Optional[Subscription]:
    """Busca la suscripcion activa mas reciente del usuario para un modulo.

    Si hay varias filas (renovaciones), devuelve la de expires_at mas lejano.
    """
    now = datetime.now(timezone.utc)
    return (
        db.query(Subscription)
        .filter(
            Subscription.user_id == user_id,
            Subscription.module_id == module_id,
            Subscription.status == "active",
            Subscription.expires_at > now,
        )
        .order_by(Subscription.expires_at.desc())
        .first()
    )


# ========== Endpoints ==========


@router.get("/license/{module_id}", response_model=LicenseStatus)
def get_license_status(
    module_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Estado de licencia del usuario actual para un modulo especifico.

    Usado por el cliente desktop (OnlineLicenseManager) para validar si
    el usuario puede usar el modulo. Cachear localmente con TTL bajo
    (15 min) para reaccionar a cambios.
    """
    if module_id not in ALLOWED_MODULE_IDS:
        raise HTTPException(400, f"Modulo desconocido: {module_id}")

    sub = _get_active_subscription_for_module(db, user.id, module_id)
    if sub is None:
        return LicenseStatus(module_id=module_id, licensed=False)

    return LicenseStatus(
        module_id=module_id,
        licensed=True,
        expires_at=sub.expires_at.isoformat(),
        days_left=sub.days_left(),
        period=sub.period,
        status=sub.status,
    )


@router.get("/active", response_model=List[SubscriptionItem])
def list_active_subscriptions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lista todas las suscripciones del usuario actual (activas, expiradas, canceladas).

    Para mostrar en la pestaña 'Suscripciones' del cliente desktop.
    """
    subs = (
        db.query(Subscription)
        .filter(Subscription.user_id == user.id)
        .order_by(Subscription.expires_at.desc())
        .all()
    )
    return [
        SubscriptionItem(
            id=s.id,
            module_id=s.module_id,
            period=s.period,
            started_at=s.started_at.isoformat(),
            expires_at=s.expires_at.isoformat(),
            status=s.status,
            auto_renew=s.auto_renew,
            days_left=s.days_left(),
            amount_paid_usd=float(s.amount_paid_usd),
            amount_paid_ars=float(s.amount_paid_ars),
        )
        for s in subs
    ]


@router.get("/pricing", response_model=PricingResponse)
def get_pricing(
    modules: str = Query(
        ...,
        description="Lista CSV de module_id, ej: service_enterprise,biomedical_engineering",
    ),
    period: str = Query(..., description="monthly | quarterly | semester | annual"),
    user: User = Depends(get_current_user),
):
    """Calcula el precio de un combo de modulos + periodo.

    Usa cotizacion USD oficial BNA en tiempo real para conversion a ARS.
    """
    module_list = [m.strip() for m in modules.split(",") if m.strip()]
    if not module_list:
        raise HTTPException(400, "Debe pasar al menos un modulo")
    if period not in ALLOWED_PERIODS:
        raise HTTPException(400, f"Periodo invalido: {period}")

    usd_rate = fetch_usd_oficial_bna()
    try:
        result = calculate_price(module_list, period, usd_rate)
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Convertir Decimals a float para el response
    return PricingResponse(
        modules=[
            PricingModuleItem(
                id=m["id"],
                name=m["name"],
                price_usd_monthly=float(m["price_usd_monthly"]),
            )
            for m in result["modules"]
        ],
        period=result["period"],
        months=result["months"],
        base_total_usd=float(result["base_total_usd"]),
        period_discount_pct=result["period_discount_pct"],
        quantity_discount_pct=result["quantity_discount_pct"],
        total_usd=float(result["total_usd"]),
        total_ars=float(result["total_ars"]),
        usd_to_ars_rate=float(usd_rate) if usd_rate else None,
        savings_usd=float(result["savings_usd"]),
        savings_pct=result["savings_pct"],
    )


@router.get("/catalog", response_model=CatalogResponse)
def get_catalog(
    user: User = Depends(get_current_user),
):
    """Catalogo de modulos y periodos disponibles.

    Para llenar los selectores del UI del cliente. Incluye cotizacion
    USD->ARS actual.
    """
    usd_rate = fetch_usd_oficial_bna()
    return CatalogResponse(
        modules=[
            {**m, "price_usd_monthly": float(m["price_usd_monthly"])}
            for m in get_module_catalog()
        ],
        periods=get_period_catalog(),
        usd_to_ars_rate=float(usd_rate) if usd_rate else None,
    )
