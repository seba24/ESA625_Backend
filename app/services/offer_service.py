# -*- coding: utf-8 -*-
"""Servicio de ofertas relampago (#871 Fase 2).

Logica de negocio:
- Filtrar ofertas visibles para un usuario (segun audiencia)
- Validar que una oferta puede ser canjeada por un usuario
- Calcular precio final de una oferta
- Registrar canjes con control de concurrencia
"""

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.offer import (
    Offer,
    OfferRedemption,
    ALLOWED_OFFER_TYPES,
)
from app.models.user import User

log = logging.getLogger(__name__)


def _get_credit_pricing(db: Optional[Session]) -> tuple:
    """Wrapper que importa y llama _read_credit_pricing de payments.py.

    Acepta db None (usa defaults via fallback de payments).
    """
    from app.api.routes.payments import _read_credit_pricing, _DEFAULT_BASE_PRICE_ARS, _DEFAULT_QTY_MULTIPLIERS
    if db is None:
        return _DEFAULT_BASE_PRICE_ARS, dict(_DEFAULT_QTY_MULTIPLIERS)
    return _read_credit_pricing(db)


# ============================================================
# Validacion de config segun offer_type
# ============================================================

def validate_offer_config(offer_type: str, config: Dict) -> Optional[str]:
    """Valida que el config tenga las claves correctas para el offer_type.

    Devuelve None si OK, o un string de error si invalido.
    """
    if offer_type not in ALLOWED_OFFER_TYPES:
        return f"offer_type invalido. Validos: {sorted(ALLOWED_OFFER_TYPES)}"

    if offer_type == "quantity_discount":
        # config: {"credits": int, "price_ars": float}
        if not isinstance(config.get("credits"), int) or config["credits"] < 1:
            return "config.credits debe ser entero >= 1"
        price = config.get("price_ars")
        if not isinstance(price, (int, float)) or price < 0:
            return "config.price_ars debe ser numero >= 0"

    elif offer_type == "percent_off":
        # config: {"discount_pct": float, "min_credits": int, "max_credits": int}
        pct = config.get("discount_pct")
        if not isinstance(pct, (int, float)) or not 0 < pct <= 100:
            return "config.discount_pct debe ser numero entre 0 y 100"
        for opt in ("min_credits", "max_credits"):
            v = config.get(opt, 0)
            if not isinstance(v, int) or v < 0:
                return f"config.{opt} debe ser entero >= 0"

    elif offer_type == "bonus":
        # config: {"buy_credits": int, "get_extra_credits": int}
        for key in ("buy_credits", "get_extra_credits"):
            v = config.get(key)
            if not isinstance(v, int) or v < 1:
                return f"config.{key} debe ser entero >= 1"

    elif offer_type == "bundle":
        # config: {"credits": int, "free_modules": [str], "free_months": int, "price_ars": float}
        if not isinstance(config.get("credits"), int) or config["credits"] < 1:
            return "config.credits debe ser entero >= 1"
        mods = config.get("free_modules", [])
        if not isinstance(mods, list) or not all(isinstance(m, str) for m in mods):
            return "config.free_modules debe ser lista de strings"
        months = config.get("free_months", 0)
        if not isinstance(months, int) or months < 0:
            return "config.free_months debe ser entero >= 0"
        price = config.get("price_ars", 0)
        if not isinstance(price, (int, float)) or price < 0:
            return "config.price_ars debe ser numero >= 0"

    return None


# ============================================================
# Filtros de audiencia
# ============================================================

def get_user_role_name(user: User) -> str:
    """Devuelve un nombre de rol simple para matchear con audience_value.

    Hoy: 'admin' si is_admin=True, sino 'user'. En el futuro se puede expandir
    a 'clinical_user', 'technician', etc. desde el role_manager.
    """
    return "admin" if user.is_admin else "user"


def _offer_applies_to_user(offer: Offer, user: User) -> bool:
    """True si la oferta aplica al usuario segun audience_type/value."""
    if offer.audience_type == "public":
        return True
    if offer.audience_type == "user_email":
        return (offer.audience_value or "").strip().lower() == user.email.lower()
    if offer.audience_type == "user_list":
        emails = [e.strip().lower() for e in (offer.audience_value or "").split(",")]
        return user.email.lower() in emails
    if offer.audience_type == "role":
        return (offer.audience_value or "").strip() == get_user_role_name(user)
    return False


# ============================================================
# Listar ofertas activas para un usuario
# ============================================================

def get_active_offers_for_user(db: Session, user: User) -> List[Offer]:
    """Devuelve ofertas activas, vigentes, con cupos, que aplican al usuario.

    Tambien filtra las que el usuario ya canjeo max_per_user veces.
    """
    now = datetime.now(timezone.utc)
    candidates = (
        db.query(Offer)
        .filter(
            Offer.active.is_(True),
            Offer.starts_at <= now,
            Offer.expires_at > now,
        )
        .order_by(Offer.expires_at.asc())
        .all()
    )

    result = []
    for offer in candidates:
        # Filtrar por audiencia
        if not _offer_applies_to_user(offer, user):
            continue
        # Filtrar por cupos globales
        if offer.max_redemptions > 0 and offer.current_redemptions >= offer.max_redemptions:
            continue
        # Filtrar por cupos por usuario
        user_redemptions = (
            db.query(OfferRedemption)
            .filter(
                OfferRedemption.offer_id == offer.id,
                OfferRedemption.user_id == user.id,
                OfferRedemption.status.in_(["pending", "completed"]),
            )
            .count()
        )
        if user_redemptions >= offer.max_per_user:
            continue
        result.append(offer)
    return result


# ============================================================
# Calcular precio segun offer_type
# ============================================================

def calculate_offer_price(
    offer: Offer,
    base_credits: Optional[int] = None,
    db: Optional[Session] = None,
) -> Dict:
    """Calcula el precio final de una oferta.

    Args:
        offer: la oferta
        base_credits: solo necesario para 'percent_off' (cuantos creditos
            quiere comprar el user con descuento)
        db: necesaria para 'percent_off' y 'bonus' (necesitan leer precio
            base desde pricing_config). Si None, usa defaults.

    Returns dict con: credits, credits_bonus, price_ars, description.
    """
    try:
        config = json.loads(offer.config_json or "{}")
    except json.JSONDecodeError:
        config = {}

    if offer.offer_type == "quantity_discount":
        credits = config.get("credits", 0)
        price = float(config.get("price_ars", 0))
        return {
            "credits": credits,
            "credits_bonus": 0,
            "price_ars": price,
            "price_per_credit_ars": round(price / credits, 2) if credits > 0 else 0,
            "description": f"{credits} creditos a ${price:,.0f} (${round(price/credits, 0):,.0f}/cred)" if credits > 0 else "",
        }

    if offer.offer_type == "percent_off":
        if base_credits is None or base_credits < 1:
            return {
                "credits": 0,
                "credits_bonus": 0,
                "price_ars": 0,
                "description": "Necesita indicar cantidad de creditos a comprar",
            }
        pct = float(config.get("discount_pct", 0))
        min_c = config.get("min_credits", 0)
        max_c = config.get("max_credits", 0)
        if base_credits < min_c or (max_c > 0 and base_credits > max_c):
            return {
                "credits": 0,
                "credits_bonus": 0,
                "price_ars": 0,
                "description": f"Cantidad fuera de rango ({min_c}-{max_c if max_c else 'inf'})",
            }
        # Necesitamos el precio base para aplicar el % off
        base_price, multipliers = _get_credit_pricing(db)
        mult = multipliers.get(base_credits, 1.0)
        normal_price = base_price * base_credits * mult
        final_price = normal_price * (1 - pct / 100)
        return {
            "credits": base_credits,
            "credits_bonus": 0,
            "price_ars": round(final_price, 2),
            "price_per_credit_ars": round(final_price / base_credits, 2),
            "description": f"{base_credits} creditos con {pct}% off extra = ${final_price:,.0f}",
        }

    if offer.offer_type == "bonus":
        buy = config.get("buy_credits", 0)
        extra = config.get("get_extra_credits", 0)
        base_price, multipliers = _get_credit_pricing(db)
        mult = multipliers.get(buy, 1.0)
        price = base_price * buy * mult
        return {
            "credits": buy,
            "credits_bonus": extra,
            "price_ars": round(price, 2),
            "total_credits": buy + extra,
            "description": f"Compra {buy} creditos y recibi {extra} extra (total {buy + extra})",
        }

    if offer.offer_type == "bundle":
        credits = config.get("credits", 0)
        modules = config.get("free_modules", [])
        months = config.get("free_months", 0)
        price = float(config.get("price_ars", 0))
        return {
            "credits": credits,
            "credits_bonus": 0,
            "price_ars": price,
            "free_modules": modules,
            "free_months": months,
            "description": f"{credits} creditos + {months} mes(es) gratis de {', '.join(modules) if modules else 'modulos'}",
        }

    return {"credits": 0, "credits_bonus": 0, "price_ars": 0, "description": "Tipo desconocido"}


# ============================================================
# Validar y canjear oferta
# ============================================================

def validate_redemption(
    db: Session, offer: Offer, user: User, requested_credits: Optional[int] = None
) -> Optional[str]:
    """Valida que el usuario puede canjear la oferta. Devuelve error o None.

    NO modifica nada. La modificacion se hace en register_redemption().
    """
    if not offer.is_currently_valid():
        return "La oferta no esta vigente o se agotaron los cupos"
    if not _offer_applies_to_user(offer, user):
        return "Esta oferta no aplica a tu cuenta"

    user_redemptions = (
        db.query(OfferRedemption)
        .filter(
            OfferRedemption.offer_id == offer.id,
            OfferRedemption.user_id == user.id,
            OfferRedemption.status.in_(["pending", "completed"]),
        )
        .count()
    )
    if user_redemptions >= offer.max_per_user:
        return f"Ya canjeaste esta oferta el maximo de veces ({offer.max_per_user})"

    if offer.offer_type == "percent_off" and not requested_credits:
        return "Para esta oferta hay que indicar cantidad de creditos a comprar"

    return None


def register_redemption(
    db: Session,
    offer: Offer,
    user: User,
    requested_credits: Optional[int] = None,
    mp_payment_id: Optional[str] = None,
) -> OfferRedemption:
    """Registra un canje en estado 'pending'.

    El canje pasa a 'completed' cuando MercadoPago confirma el pago via webhook.
    Incrementa offer.current_redemptions atomicamente.
    """
    pricing = calculate_offer_price(offer, requested_credits, db=db)

    redemption = OfferRedemption(
        offer_id=offer.id,
        user_id=user.id,
        credits_purchased=pricing.get("credits", 0),
        credits_bonus=pricing.get("credits_bonus", 0),
        amount_paid_ars=Decimal(str(pricing.get("price_ars", 0))),
        mp_payment_id=mp_payment_id,
        status="pending",
    )
    db.add(redemption)

    # Incrementar contador global (control de cupos)
    offer.current_redemptions = (offer.current_redemptions or 0) + 1
    db.commit()
    db.refresh(redemption)

    log.info(
        f"Canje registrado #{redemption.id}: user {user.email} canjea "
        f"oferta #{offer.id} ({offer.offer_type}), creditos={redemption.credits_purchased}"
    )
    return redemption


# ============================================================
# Serializacion para respuestas API
# ============================================================

def offer_to_dict(offer: Offer, include_admin_fields: bool = False) -> Dict:
    """Convierte una Offer a dict para JSON response."""
    try:
        config = json.loads(offer.config_json or "{}")
    except json.JSONDecodeError:
        config = {}

    result = {
        "id": offer.id,
        "code": offer.code,
        "name": offer.name,
        "description": offer.description,
        "offer_type": offer.offer_type,
        "config": config,
        "starts_at": offer.starts_at.isoformat() if offer.starts_at else None,
        "expires_at": offer.expires_at.isoformat() if offer.expires_at else None,
        "remaining_redemptions": offer.remaining_redemptions(),
        "max_per_user": offer.max_per_user,
    }
    if include_admin_fields:
        result.update({
            "audience_type": offer.audience_type,
            "audience_value": offer.audience_value,
            "max_redemptions": offer.max_redemptions,
            "current_redemptions": offer.current_redemptions,
            "active": offer.active,
            "created_at": offer.created_at.isoformat() if offer.created_at else None,
        })
    return result
