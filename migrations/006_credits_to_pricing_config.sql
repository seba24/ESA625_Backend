-- Migracion 006 - 2026-06-09
-- Refactor de creditos: pasar de tabla credit_packages (precios absolutos)
-- a pricing_config (precio base + multiplicadores por cantidad).
--
-- Contexto (#871 Fase 1):
-- El usuario pidio que el sistema de creditos use la MISMA logica que
-- las suscripciones: un solo precio base editable + multiplicadores por
-- cantidad. Si cambias el precio base de 1 credito, todos los paquetes
-- recalculan automaticamente.
--
-- Cambios:
-- 1. Elimina tabla credit_packages (ya no se usa)
-- 2. Agrega a pricing_config:
--    - credit_base_price_ars: precio de 1 credito en pesos argentinos
--    - credit_qty_multiplier:<N>: descuento para paquete de N creditos
--
-- Idempotente: usa IF EXISTS / ON CONFLICT DO NOTHING.

-- 1. Eliminar tabla credit_packages (ya no se usa - reemplazada por pricing_config)
DROP TABLE IF EXISTS credit_packages;

-- 2. Sembrar nuevas claves en pricing_config
-- Precio base: 10000 ARS por 1 credito (el equivalente al precio actual de 1 credito)
-- Multiplicadores por cantidad coherentes con los % acordados:
--   1=0% off, 5=5% off, 10=10% off, 25=20% off, 50=20% off, 100=20% off
INSERT INTO pricing_config (key, value, description) VALUES
    ('credit_base_price_ars',     10000.00, 'Precio base de 1 credito en ARS'),
    ('credit_qty_multiplier:1',    1.0000, 'Multiplicador para paquete 1 credito (0% off)'),
    ('credit_qty_multiplier:5',    0.9500, 'Multiplicador para paquete 5 creditos (5% off)'),
    ('credit_qty_multiplier:10',   0.9000, 'Multiplicador para paquete 10 creditos (10% off)'),
    ('credit_qty_multiplier:25',   0.8000, 'Multiplicador para paquete 25 creditos (20% off)'),
    ('credit_qty_multiplier:50',   0.8000, 'Multiplicador para paquete 50 creditos (20% off)'),
    ('credit_qty_multiplier:100',  0.8000, 'Multiplicador para paquete 100 creditos (20% off)')
ON CONFLICT (key) DO NOTHING;

-- Verificacion opcional:
-- SELECT key, value, description FROM pricing_config
-- WHERE key LIKE 'credit_%' ORDER BY key;
--
-- Calculo esperado con precio base $10000:
--   1 cred:   10000 * 1 * 1.00 = $10,000  ($10,000/cred)
--   5 cred:   10000 * 5 * 0.95 = $47,500  ($9,500/cred)
--   10 cred:  10000 * 10 * 0.90 = $90,000  ($9,000/cred)
--   25 cred:  10000 * 25 * 0.80 = $200,000 ($8,000/cred)
--   50 cred:  10000 * 50 * 0.80 = $400,000 ($8,000/cred)
--   100 cred: 10000 * 100 * 0.80 = $800,000 ($8,000/cred)
