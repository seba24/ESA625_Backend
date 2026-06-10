# -*- coding: utf-8 -*-
"""Endpoints de ofertas para el cliente (usuario logueado).

#871 Fase 2:
- GET  /offers/active           lista ofertas vigentes para el user actual
- GET  /offers/{id}             detalle de una oferta (si aplica al user)
- POST /offers/{id}/redeem      crea preferencia MP para canjear

El admin tiene endpoints separados en routes/admin.py.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.offer import Offer
from app.models.user import User
from app.services.offer_service import (
    calculate_offer_price,
    get_active_offers_for_user,
    offer_to_dict,
    register_redemption,
    validate_redemption,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/offers", tags=["offers"])


class RedeemRequest(BaseModel):
    credits: Optional[int] = None  # solo para offer_type='percent_off'


class RedeemResponse(BaseModel):
    redemption_id: int
    offer_id: int
    init_point: Optional[str] = None
    preference_id: Optional[str] = None
    credits: int
    credits_bonus: int
    price_ars: float
    status: str
    message: str


@router.get("/active")
def list_active_offers_for_me(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lista las ofertas activas que aplican al usuario actual."""
    offers = get_active_offers_for_user(db, user)
    return [
        {
            **offer_to_dict(o),
            "pricing_preview": calculate_offer_price(o, db=db),
        }
        for o in offers
    ]


@router.get("/{offer_id}")
def get_offer_detail(
    offer_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Detalle de una oferta. Solo se devuelve si el user puede canjearla."""
    offer = db.query(Offer).filter(Offer.id == offer_id).first()
    if not offer:
        raise HTTPException(404, "Oferta no encontrada")

    err = validate_redemption(db, offer, user)
    if err:
        raise HTTPException(400, err)

    return {
        **offer_to_dict(offer),
        "pricing_preview": calculate_offer_price(offer, db=db),
    }


@router.post("/{offer_id}/redeem", response_model=RedeemResponse)
def redeem_offer(
    offer_id: int,
    req: RedeemRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Canjear una oferta: crea redemption + preferencia MercadoPago.

    El status queda 'pending' hasta que el webhook de MP confirme el pago.
    Si el pago se aprueba, otro endpoint (futuro) suma los creditos al user
    y cambia status a 'completed'.
    """
    offer = db.query(Offer).filter(Offer.id == offer_id).first()
    if not offer:
        raise HTTPException(404, "Oferta no encontrada")

    err = validate_redemption(db, offer, user, requested_credits=req.credits)
    if err:
        raise HTTPException(400, err)

    pricing = calculate_offer_price(offer, base_credits=req.credits, db=db)
    if pricing.get("price_ars", 0) <= 0:
        raise HTTPException(400, "El precio calculado es invalido para esta oferta")

    # Crear el redemption en pending (incrementa cupo global)
    redemption = register_redemption(db, offer, user, requested_credits=req.credits)

    # Crear preferencia MP si esta configurado
    init_point = None
    preference_id = None
    if settings.mercadopago_access_token:
        try:
            import mercadopago
            sdk = mercadopago.SDK(settings.mercadopago_access_token)
            preference_data = {
                "items": [
                    {
                        "title": f"ESA625 Cloud - {offer.name}",
                        "quantity": 1,
                        "unit_price": float(pricing["price_ars"]),
                        "currency_id": "ARS",
                    }
                ],
                "payer": {"email": user.email, "name": user.full_name},
                "back_urls": {
                    "success": f"{settings.backend_url}/api/payments/result?status=success",
                    "failure": f"{settings.backend_url}/api/payments/result?status=failure",
                    "pending": f"{settings.backend_url}/api/payments/result?status=pending",
                },
                "notification_url": f"{settings.backend_url}/api/payments/webhook",
                "auto_return": "approved",
                "binary_mode": True,
                "external_reference": f"redemption_{redemption.id}",
                "metadata": {
                    "redemption_id": redemption.id,
                    "user_id": user.id,
                    "offer_id": offer.id,
                    "credits": pricing.get("credits", 0),
                    "credits_bonus": pricing.get("credits_bonus", 0),
                },
            }
            result = sdk.preference().create(preference_data)
            if result.get("status") == 201:
                preference = result["response"]
                init_point = preference["init_point"]
                preference_id = preference["id"]
            else:
                log.error(f"Error MercadoPago al crear preferencia: {result}")
        except Exception as e:
            log.error(f"Excepcion creando preferencia MP: {e}", exc_info=True)

    return RedeemResponse(
        redemption_id=redemption.id,
        offer_id=offer.id,
        init_point=init_point,
        preference_id=preference_id,
        credits=redemption.credits_purchased,
        credits_bonus=redemption.credits_bonus,
        price_ars=float(redemption.amount_paid_ars),
        status=redemption.status,
        message="Redemption creada. Complete el pago en MercadoPago." if init_point
                else "Redemption creada pero MercadoPago no esta configurado.",
    )
