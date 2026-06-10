# -*- coding: utf-8 -*-
"""Endpoints de pagos con MercadoPago."""

import logging
import mercadopago

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.report import CreditTransaction

log = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])

# #871 Fase 1: paquetes calculados al vuelo desde pricing_config.
# El precio base ($/1 credito) y los multiplicadores por cantidad estan
# en la tabla pricing_config, editables desde el panel admin.

# Defaults (fallback si pricing_config no responde)
_DEFAULT_BASE_PRICE_ARS = 10000.0
_DEFAULT_QTY_MULTIPLIERS = {
    1: 1.00,    # 0% off
    5: 0.95,    # 5% off
    10: 0.90,   # 10% off
    25: 0.80,   # 20% off
    50: 0.80,   # 20% off
    100: 0.80,  # 20% off
}


def _read_credit_pricing(db: Session) -> tuple[float, dict]:
    """Lee precio base y multiplicadores de pricing_config.

    Returns (base_price_ars, {cantidad: multiplicador}).
    Si la DB falla, usa defaults.
    """
    try:
        from app.models.pricing_config import PricingConfig
        rows = (
            db.query(PricingConfig)
            .filter(PricingConfig.key.like("credit_%"))
            .all()
        )
        base_price = _DEFAULT_BASE_PRICE_ARS
        multipliers = dict(_DEFAULT_QTY_MULTIPLIERS)
        for r in rows:
            if r.key == "credit_base_price_ars":
                base_price = float(r.value)
            elif r.key.startswith("credit_qty_multiplier:"):
                try:
                    qty = int(r.key.split(":", 1)[1])
                    multipliers[qty] = float(r.value)
                except (ValueError, IndexError):
                    pass
        return base_price, multipliers
    except Exception as e:
        log.warning(f"No se pudo leer pricing_config de DB para creditos, usando defaults: {e}")
        return _DEFAULT_BASE_PRICE_ARS, dict(_DEFAULT_QTY_MULTIPLIERS)


def _calculate_package_price(credits: int, base_price: float, multipliers: dict) -> float:
    """Calcula precio total de un paquete: base * cantidad * multiplicador."""
    mult = multipliers.get(credits, 1.0)  # 1.0 = sin descuento si la cantidad no esta en tabla
    return round(base_price * credits * mult, 2)


def _get_active_packages(db: Session) -> dict:
    """Devuelve {credits: {'price': float, 'description': str}} calculado al vuelo.

    Las cantidades vienen de las claves credit_qty_multiplier:N en pricing_config.
    El precio se calcula como base_price * credits * multiplicador.
    """
    base_price, multipliers = _read_credit_pricing(db)
    packages = {}
    for credits, mult in sorted(multipliers.items()):
        price = _calculate_package_price(credits, base_price, multipliers)
        packages[credits] = {
            "price": price,
            "description": f"{credits} credito" + ("s" if credits != 1 else ""),
        }
    return packages


class CreatePaymentRequest(BaseModel):
    credits: int  # Cantidad de créditos a comprar


class CreatePaymentResponse(BaseModel):
    init_point: str  # URL de checkout MercadoPago
    preference_id: str
    credits: int
    price: float


class PackageResponse(BaseModel):
    credits: int
    price: float
    price_per_credit: float
    description: str


@router.get("/packages", response_model=list[PackageResponse])
def list_packages(db: Session = Depends(get_db)):
    """Listar paquetes de creditos disponibles (lee de DB, fallback a defaults)."""
    packages = _get_active_packages(db)
    return [
        PackageResponse(
            credits=credits,
            price=pkg["price"],
            price_per_credit=round(pkg["price"] / credits, 2),
            description=pkg["description"],
        )
        for credits, pkg in sorted(packages.items())
    ]


@router.post("/create", response_model=CreatePaymentResponse)
def create_payment(
    req: CreatePaymentRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Crear preferencia de pago en MercadoPago."""
    if not settings.mercadopago_access_token:
        raise HTTPException(500, "MercadoPago no configurado")

    packages = _get_active_packages(db)
    pkg = packages.get(req.credits)
    if not pkg:
        available = sorted(packages.keys())
        raise HTTPException(400, f"Paquete no valido. Opciones: {available}")

    sdk = mercadopago.SDK(settings.mercadopago_access_token)

    preference_data = {
        "items": [
            {
                "title": f"ESA625 Cloud — {pkg['description']}",
                "quantity": 1,
                "unit_price": float(pkg["price"]),
                "currency_id": "ARS",
            }
        ],
        "payer": {
            "email": user.email,
            "name": user.full_name,
        },
        "back_urls": {
            "success": f"{settings.backend_url}/api/payments/result?status=success",
            "failure": f"{settings.backend_url}/api/payments/result?status=failure",
            "pending": f"{settings.backend_url}/api/payments/result?status=pending",
        },
        "notification_url": f"{settings.backend_url}/api/payments/webhook",
        "auto_return": "approved",
        "binary_mode": True,
        "external_reference": f"user_{user.id}_credits_{req.credits}",
        "metadata": {
            "user_id": user.id,
            "credits": req.credits,
        },
    }

    result = sdk.preference().create(preference_data)

    if result["status"] != 201:
        log.error(f"Error MercadoPago: {result}")
        raise HTTPException(500, "Error al crear preferencia de pago")

    preference = result["response"]

    return CreatePaymentResponse(
        init_point=preference["init_point"],
        preference_id=preference["id"],
        credits=req.credits,
        price=float(pkg["price"]),
    )


@router.post("/webhook")
async def mercadopago_webhook(request: Request, db: Session = Depends(get_db)):
    """Webhook de MercadoPago — notificación de pago."""
    try:
        body = await request.json()
    except Exception:
        return {"status": "ignored"}

    log.info(f"Webhook MP recibido: {body}")

    # Solo procesar pagos aprobados
    if body.get("type") != "payment" or body.get("action") != "payment.created":
        return {"status": "ignored"}

    payment_id = body.get("data", {}).get("id")
    if not payment_id:
        return {"status": "no_payment_id"}

    # Consultar pago en MercadoPago
    if not settings.mercadopago_access_token:
        return {"status": "not_configured"}

    sdk = mercadopago.SDK(settings.mercadopago_access_token)
    payment_info = sdk.payment().get(payment_id)

    if payment_info["status"] != 200:
        log.error(f"Error consultando pago {payment_id}: {payment_info}")
        return {"status": "error"}

    payment = payment_info["response"]

    if payment["status"] != "approved":
        log.info(f"Pago {payment_id} no aprobado: {payment['status']}")
        return {"status": "not_approved"}

    # Extraer user_id y créditos del external_reference
    ext_ref = payment.get("external_reference", "")
    try:
        parts = ext_ref.split("_")
        user_id = int(parts[1])
        credits_amount = int(parts[3])
    except (IndexError, ValueError):
        log.error(f"external_reference inválido: {ext_ref}")
        return {"status": "invalid_reference"}

    # Verificar que no se procesó antes
    existing = (
        db.query(CreditTransaction)
        .filter(CreditTransaction.payment_id == str(payment_id))
        .first()
    )
    if existing:
        log.info(f"Pago {payment_id} ya procesado")
        return {"status": "already_processed"}

    # Acreditar
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        log.error(f"Usuario {user_id} no encontrado")
        return {"status": "user_not_found"}

    user.credits += credits_amount

    txn = CreditTransaction(
        user_id=user.id,
        amount=credits_amount,
        balance_after=user.credits,
        description=f"Compra {credits_amount} créditos — MercadoPago #{payment_id}",
        payment_id=str(payment_id),
    )
    db.add(txn)
    db.commit()

    log.info(f"Acreditados {credits_amount} créditos a user {user_id}. Balance: {user.credits}")
    return {"status": "ok", "credits_added": credits_amount}


@router.get("/result")
def payment_result(status: str):
    """Página de resultado post-pago."""
    messages = {
        "success": "Pago aprobado. Los créditos fueron acreditados a tu cuenta.",
        "failure": "El pago fue rechazado. Intentá nuevamente.",
        "pending": "El pago está pendiente. Los créditos se acreditarán cuando se confirme.",
    }
    return {"status": status, "message": messages.get(status, "Estado desconocido")}
