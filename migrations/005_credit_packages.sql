-- Migracion 005 — 2026-06-09
-- Crea la tabla `credit_packages` para paquetes de creditos editables desde
-- el panel admin.
--
-- Contexto (#870):
-- Los paquetes de creditos estaban hardcodeados en app/api/routes/payments.py.
-- Para poder editar precios y agregar/quitar paquetes sin redeploy, los
-- movemos a la DB. El servicio credits_pricing.py lee con cache de 5 min.
--
-- Esquema:
-- - credits         => cantidad de creditos (clave primaria, ej. 1, 5, 10, 25, 50, 100)
-- - price_ars       => precio total en pesos argentinos
-- - description     => texto para mostrar al cliente
-- - active          => si esta visible al usuario (admin puede deshabilitar)
-- - sort_order      => orden de aparicion en la UI
--
-- Idempotente: usa IF NOT EXISTS + INSERT ON CONFLICT DO NOTHING.

CREATE TABLE IF NOT EXISTS credit_packages (
    credits INTEGER PRIMARY KEY,
    price_ars NUMERIC(12, 2) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_by_admin_id INTEGER REFERENCES users(id)
);

-- Sembrar paquetes (los 4 actuales + 2 nuevos).
-- Si ya existen, NO los pisamos.
INSERT INTO credit_packages (credits, price_ars, description, sort_order) VALUES
    (1,    10000.00,  '1 credito',     10),
    (5,    45000.00,  '5 creditos',    20),
    (10,   80000.00,  '10 creditos',   30),
    (25,   175000.00, '25 creditos',   40),
    (50,   325000.00, '50 creditos',   50),
    (100,  600000.00, '100 creditos',  60)
ON CONFLICT (credits) DO NOTHING;

-- Verificacion opcional:
-- SELECT credits, price_ars, ROUND(price_ars/credits, 2) AS por_credito,
--        description, active, sort_order
-- FROM credit_packages
-- ORDER BY sort_order;
