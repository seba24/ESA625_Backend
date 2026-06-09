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
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


# Precio base mensual por modulo en USD
MODULE_PRICES_USD: Dict[str, Decimal] = {
    "service_enterprise":     Decimal("25"),
    "biomedical_engineering": Decimal("35"),
    "proposal_generator":     Decimal("15"),
    "knowledge_base":         Decimal("10"),
}

# Display name de cada modulo para mostrar al cliente
MODULE_DISPLAY_NAMES: Dict[str, str] = {
    "service_enterprise":     "Empresa de Servicio (SE)",
    "biomedical_engineering": "Ingenieria Biomedica (IB)",
    "proposal_generator":     "Generador de Propuestas (PG)",
    "knowledge_base":         "Base de Conocimiento (KB)",
}

# Meses de cada periodo
PERIOD_MONTHS: Dict[str, int] = {
    "monthly":   1,
    "quarterly": 3,
    "semester":  6,
    "annual":    12,
}

# Multiplicador de descuento por periodo (sobre el total mensual * meses)
PERIOD_MULTIPLIERS: Dict[str, Decimal] = {
    "monthly":   Decimal("1.00"),
    "quarterly": Decimal("0.90"),
    "semester":  Decimal("0.83"),
    "annual":    Decimal("0.78"),
}

# Multiplicador de descuento por cantidad de modulos
QUANTITY_MULTIPLIERS: Dict[int, Decimal] = {
    1: Decimal("1.00"),
    2: Decimal("0.95"),
    3: Decimal("0.90"),
    4: Decimal("0.80"),
}


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

    # Validar y deduplicar (manteniendo orden)
    seen = set()
    unique_modules = []
    for m in modules:
        if m not in MODULE_PRICES_USD:
            raise ValueError(f"Modulo desconocido: {m}")
        if m not in seen:
            seen.add(m)
            unique_modules.append(m)

    if period not in PERIOD_MONTHS:
        raise ValueError(f"Periodo desconocido: {period}")

    months = PERIOD_MONTHS[period]
    period_mult = PERIOD_MULTIPLIERS[period]

    qty = len(unique_modules)
    qty_mult = QUANTITY_MULTIPLIERS.get(qty, Decimal("1.00"))

    # Precio base = suma de precios mensuales * meses
    monthly_sum = sum((MODULE_PRICES_USD[m] for m in unique_modules), Decimal("0"))
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
                "price_usd_monthly": _round_money(MODULE_PRICES_USD[m]),
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
    return [
        {
            "id": module_id,
            "name": MODULE_DISPLAY_NAMES[module_id],
            "price_usd_monthly": _round_money(price),
        }
        for module_id, price in MODULE_PRICES_USD.items()
    ]


def get_period_catalog() -> List[Dict]:
    """Lista los periodos disponibles con su descuento.

    Para mostrar al cliente como selector.
    """
    return [
        {
            "id": period_id,
            "months": months,
            "discount_pct": int((Decimal("1") - PERIOD_MULTIPLIERS[period_id]) * 100),
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
