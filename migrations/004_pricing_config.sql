-- Migracion 004 — 2026-06-09
-- Crea la tabla `pricing_config` para precios editables desde el panel admin.
--
-- Contexto (#870 Fase 1 ext):
-- Hasta ahora los precios estaban hardcodeados en app/services/pricing.py.
-- Para poder ajustar precios sin redeploy, los movemos a la DB. El servicio
-- pricing.py lee de esta tabla con cache local de 5 min.
--
-- Esquema clave-valor para flexibilidad:
-- - module_price:<module_id>     => precio mensual USD
-- - period_multiplier:<period>   => multiplicador descuento (1.00, 0.90, 0.83, 0.78)
-- - quantity_multiplier:<n>      => multiplicador por cantidad (1.00, 0.95, 0.90, 0.80)
--
-- Idempotente: usa IF NOT EXISTS + INSERT ON CONFLICT DO NOTHING.

CREATE TABLE IF NOT EXISTS pricing_config (
    key VARCHAR(64) PRIMARY KEY,
    value NUMERIC(10, 4) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_by_admin_id INTEGER REFERENCES users(id)
);

-- Sembrar precios base (los del plan acordado 2026-06-09).
-- Si ya existen, no los pisamos (ON CONFLICT DO NOTHING).
INSERT INTO pricing_config (key, value, description) VALUES
    ('module_price:service_enterprise',     25.00, 'Precio mensual USD - Empresa de Servicio (SE)'),
    ('module_price:biomedical_engineering', 35.00, 'Precio mensual USD - Ingenieria Biomedica (IB)'),
    ('module_price:proposal_generator',     15.00, 'Precio mensual USD - Generador de Propuestas (PG)'),
    ('module_price:knowledge_base',         10.00, 'Precio mensual USD - Base de Conocimiento (KB)'),
    ('period_multiplier:monthly',           1.0000, 'Multiplicador descuento - Mensual (0% off)'),
    ('period_multiplier:quarterly',         0.9000, 'Multiplicador descuento - Trimestral (10% off)'),
    ('period_multiplier:semester',          0.8300, 'Multiplicador descuento - Semestral (17% off)'),
    ('period_multiplier:annual',            0.7800, 'Multiplicador descuento - Anual (22% off)'),
    ('quantity_multiplier:1',               1.0000, 'Multiplicador descuento - 1 modulo (0% off)'),
    ('quantity_multiplier:2',               0.9500, 'Multiplicador descuento - 2 modulos (5% off)'),
    ('quantity_multiplier:3',               0.9000, 'Multiplicador descuento - 3 modulos (10% off)'),
    ('quantity_multiplier:4',               0.8000, 'Multiplicador descuento - 4 modulos (20% off)')
ON CONFLICT (key) DO NOTHING;

-- Verificacion opcional:
-- SELECT key, value, description FROM pricing_config ORDER BY key;
