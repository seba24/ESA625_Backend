# -*- coding: utf-8 -*-
"""Motor de pricing para suscripciones SaaS de modulos de gestion.

#870 Fase 1: calcula precios finales aplicando descuentos por periodo y
descuentos acumulativos por cantidad de modulos contratados.

Pricing acordado (2026-06-09 con sjelo):
- SE (service_enterprise):     $25 USD/mes
- IB (biomedical_engineering): $35 USD/mes
- PG (proposal_generator):     $15 USD/mes
- KB (knowledge_base):         $10 USD/mes

Descuentos por periodo (sobre el precio mensual * cantidad de meses):
- Mensual:    0% off (mult 1.00)
- Trimestral: 10% off (mult 0.90)
- Semestral:  17% off (mult 0.83)
- Anual:      22% off (mult 0.78)

Descuentos acumulativos por cantidad de modulos:
- 1 modulo:  0% off
- 2 modulos: 5% off
- 3 modulos: 10% off
- 4 modulos: 20% off

Conversion USD -> ARS: cotizacion USD oficial BNA al momento del calculo.
"""

import logging
import time
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


# Display name de cada modulo (NO se edita desde admin, es identidad del modulo).
MODULE_DISPLAY_NAMES: Dict[str, str] = {
    "service_enterprise":     "Empresa de Servicio (SE)",
    "biomedical_engineering": "Ingenieria Biomedica (IB)",
    "proposal_generator":     "Generador de Propuestas (PG)",
    "knowledge_base":         "Base de Conocimiento (KB)",
}

# Meses de cada periodo (NO se edita - es identidad del periodo).
PERIOD_MONTHS: Dict[str, int] = {
    "monthly":   1,
    "quarterly": 3,
    "semester":  6,
    "annual":    12,
}


# ============================================================
# Defaults: usados como fallback si la DB no responde y como
# valores iniciales si la tabla pricing_config esta vacia.
# La fuente de verdad es la DB (tabla pricing_config).
# ============================================================

_DEFAULT_MODULE_PRICES_USD: Dict[str, Decimal] = {
    "service_enterprise":     Decimal("25"),
    "biomedical_engineering": Decimal("35"),
    "proposal_generator":     Decimal("15"),
    "knowledge_base":         Decimal("10"),
}

_DEFAULT_PERIOD_MULTIPLIERS: Dict[str, Decimal] = {
    "monthly":   Decimal("1.00"),
    "quarterly": Decimal("0.90"),
    "semester":  Decimal("0.83"),
    "annual":    Decimal("0.78"),
}

_DEFAULT_QUANTITY_MULTIPLIERS: Dict[int, Decimal] = {
    1: Decimal("1.00"),
    2: Decimal("0.95"),
    3: Decimal("0.90"),
    4: Decimal("0.80"),
}


# ============================================================
# Cache en memoria de los valores leidos de DB.
# TTL: 5 minutos. Cuando un admin actualiza un precio, se invalida
# explicitamente via invalidate_cache().
# ============================================================

_CACHE_TTL_SECONDS = 300
_cache_loaded_at: float = 0.0
_cache_module_prices: Dict[str, Decimal] = {}
_cache_period_mults: Dict[str, Decimal] = {}
_cache_quantity_mults: Dict[int, Decimal] = {}


def invalidate_cache() -> None:
    """Forzar recarga desde DB en el proximo calculo. Llamar desde el
    endpoint admin tras actualizar un precio."""
    global _cache_loaded_at
    _cache_loaded_at = 0.0
    log.info("Cache de pricing invalidado")


def _load_from_db() -> None:
    """Cargar pricing config desde la DB. Si falla, usar defaults."""
    global _cache_loaded_at, _cache_module_prices, _cache_period_mults, _cache_quantity_mults

    # Defaults primero para garantizar valores si la DB falla parcialmente
    module_prices = dict(_DEFAULT_MODULE_PRICES_USD)
    period_mults = dict(_DEFAULT_PERIOD_MULTIPLIERS)
    quantity_mults = dict(_DEFAULT_QUANTITY_MULTIPLIERS)

    try:
        from app.core.database import SessionLocal
        from app.models.pricing_config import PricingConfig
        db = SessionLocal()
        try:
            rows = db.query(PricingConfig).all()
            for row in rows:
                key = row.key
                val = Decimal(str(row.value))
                if key.startswith("module_price:"):
                    module_id = key.split(":", 1)[1]
                    if module_id in MODULE_DISPLAY_NAMES:
                        module_prices[module_id] = val
                elif key.startswith("period_multiplier:"):
                    period = key.split(":", 1)[1]
                    if period in PERIOD_MONTHS:
                        period_mults[period] = val
                elif key.startswith("quantity_multiplier:"):
                    qty_str = key.split(":", 1)[1]
                    try:
                        qty = int(qty_str)
                        quantity_mults[qty] = val
                    except ValueError:
                        log.warning(f"quantity_multiplier con qty invalido: {qty_str}")
        finally:
            db.close()
    except Exception as e:
        log.warning(f"No se pudo leer pricing_config de DB, usando defaults: {e}")

    _cache_module_prices = module_prices
    _cache_period_mults = period_mults
    _cache_quantity_mults = quantity_mults
    _cache_loaded_at = time.monotonic()


def _ensure_cache() -> None:
    """Garantiza que el cache este cargado y dentro del TTL."""
    age = time.monotonic() - _cache_loaded_at
    if _cache_loaded_at == 0.0 or age > _CACHE_TTL_SECONDS:
        _load_from_db()


def get_module_prices() -> Dict[str, Decimal]:
    """Precios mensuales USD de cada modulo (desde DB con cache)."""
    _ensure_cache()
    return dict(_cache_module_prices)


def get_period_multipliers() -> Dict[str, Decimal]:
    """Multiplicadores de descuento por periodo (desde DB con cache)."""
    _ensure_cache()
    return dict(_cache_period_mults)


def get_quantity_multipliers() -> Dict[int, Decimal]:
    """Multiplicadores de descuento por cantidad de modulos (desde DB con cache)."""
    _ensure_cache()
    return dict(_cache_quantity_mults)


# Aliases de compatibilidad con el codigo previo (lectura solo).
# IMPORTANTE: estos NO se mutan en runtime - los modulos que los lean
# llamaran a las funciones get_*() y obtendran valores vivos.
MODULE_PRICES_USD = _DEFAULT_MODULE_PRICES_USD  # placeholder; usar get_module_prices()
PERIOD_MULTIPLIERS = _DEFAULT_PERIOD_MULTIPLIERS  # placeholder; usar get_period_multipliers()
QUANTITY_MULTIPLIERS = _DEFAULT_QUANTITY_MULTIPLIERS  # placeholder; usar get_quantity_multipliers()


def _round_money(value: Decimal) -> Decimal:
    """Redondea a 2 decimales con redondeo HALF_UP (estilo financiero)."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_price(
    modules: List[str],
    period: str,
    usd_to_ars_rate: Optional[Decimal] = None,
) -> Dict:
    """Calcula el precio final de un combo de modulos para un periodo.

    Args:
        modules: lista de module_id (ej. ['service_enterprise', 'biomedical_engineering'])
        period: 'monthly' | 'quarterly' | 'semester' | 'annual'
        usd_to_ars_rate: cotizacion para convertir total USD a ARS. Si es
            None, no se calcula total_ars (devuelve 0).

    Returns:
        dict con desglose completo del calculo:
        {
            'modules': [{'id', 'name', 'price_usd_monthly'}, ...],
            'period': 'annual',
            'months': 12,
            'base_total_usd': Decimal,            # suma de precios mensuales * meses, sin descuentos
            'period_multiplier': Decimal,         # 0.78 para anual
            'period_discount_pct': int,           # 22
            'quantity_multiplier': Decimal,       # 0.80 para 4 modulos
            'quantity_discount_pct': int,         # 20
            'total_usd': Decimal,                 # base * period_mult * quantity_mult
            'total_ars': Decimal,                 # total_usd * cotizacion
            'usd_to_ars_rate': Decimal | None,
            'savings_usd': Decimal,               # base - total
            'savings_pct': int,                   # porcentaje total de descuento
        }

    Raises:
        ValueError: si modules tiene IDs invalidos / duplicados, period es invalido,
            o no se eligio al menos 1 modulo.
    """
    if not modules:
        raise ValueError("Debe seleccionar al menos 1 modulo")

    # Leer precios y multiplicadores desde DB (con cache)
    module_prices = get_module_prices()
    period_mults = get_period_multipliers()
    quantity_mults = get_quantity_multipliers()

    # Validar y deduplicar (manteniendo orden)
    seen = set()
    unique_modules = []
    for m in modules:
        if m not in module_prices:
            raise ValueError(f"Modulo desconocido: {m}")
        if m not in seen:
            seen.add(m)
            unique_modules.append(m)

    if period not in PERIOD_MONTHS:
        raise ValueError(f"Periodo desconocido: {period}")

    months = PERIOD_MONTHS[period]
    period_mult = period_mults.get(period, Decimal("1.00"))

    qty = len(unique_modules)
    qty_mult = quantity_mults.get(qty, Decimal("1.00"))

    # Precio base = suma de precios mensuales * meses
    monthly_sum = sum((module_prices[m] for m in unique_modules), Decimal("0"))
    base_total_usd = monthly_sum * Decimal(months)

    # Aplicar descuentos
    total_usd = base_total_usd * period_mult * qty_mult
    total_usd = _round_money(total_usd)
    base_total_usd = _round_money(base_total_usd)

    savings_usd = _round_money(base_total_usd - total_usd)
    savings_pct = (
        int((savings_usd / base_total_usd * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if base_total_usd > 0
        else 0
    )

    # Total en ARS (si se paso cotizacion)
    total_ars = Decimal("0")
    if usd_to_ars_rate is not None and usd_to_ars_rate > 0:
        total_ars = _round_money(total_usd * Decimal(str(usd_to_ars_rate)))

    return {
        "modules": [
            {
                "id": m,
                "name": MODULE_DISPLAY_NAMES[m],
                "price_usd_monthly": _round_money(module_prices[m]),
            }
            for m in unique_modules
        ],
        "period": period,
        "months": months,
        "base_total_usd": base_total_usd,
        "period_multiplier": period_mult,
        "period_discount_pct": int((Decimal("1") - period_mult) * 100),
        "quantity_multiplier": qty_mult,
        "quantity_discount_pct": int((Decimal("1") - qty_mult) * 100),
        "total_usd": total_usd,
        "total_ars": total_ars,
        "usd_to_ars_rate": usd_to_ars_rate,
        "savings_usd": savings_usd,
        "savings_pct": savings_pct,
    }


def get_module_catalog() -> List[Dict]:
    """Lista los modulos disponibles con sus precios mensuales base.

    Para mostrar al cliente como catalogo antes de elegir.
    """
    prices = get_module_prices()
    return [
        {
            "id": module_id,
            "name": MODULE_DISPLAY_NAMES[module_id],
            "price_usd_monthly": _round_money(prices.get(module_id, Decimal("0"))),
        }
        for module_id in MODULE_DISPLAY_NAMES
    ]


def get_period_catalog() -> List[Dict]:
    """Lista los periodos disponibles con su descuento.

    Para mostrar al cliente como selector.
    """
    mults = get_period_multipliers()
    return [
        {
            "id": period_id,
            "months": months,
            "discount_pct": int((Decimal("1") - mults.get(period_id, Decimal("1"))) * 100),
        }
        for period_id, months in PERIOD_MONTHS.items()
    ]


def fetch_usd_oficial_bna() -> Optional[Decimal]:
    """Obtiene la cotizacion USD oficial del BNA (Banco Nacion).

    Usa la API gratuita de dolarapi.com que consolida los valores
    publicados por BNA.

    Returns:
        Cotizacion vendedor en ARS por 1 USD, o None si la API falla.
        El cliente puede decidir si bloquear el checkout o usar fallback.
    """
    import urllib.request
    import json
    import ssl

    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(
            "https://dolarapi.com/v1/dolares/oficial",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
            data = json.loads(resp.read())
            venta = data.get("venta")
            if venta:
                return Decimal(str(venta))
    except Exception as e:
        log.warning(f"No se pudo obtener cotizacion USD BNA: {e}")
    return None
