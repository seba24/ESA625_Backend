-- Migracion 003 — 2026-06-09
-- Crea la tabla `subscriptions` para el sistema SaaS de modulos de gestion.
--
-- Contexto (#870 Fase 1):
-- Los modulos de gestion del SGC (SE, IB, PG, KB) se venden como
-- suscripciones por periodo (mensual, trimestral, semestral, anual).
-- Esta tabla guarda cada suscripcion activa por usuario.
--
-- Una fila por (user_id, module_id, periodo). Si el usuario renueva,
-- se actualiza la fila existente (extiende expires_at).
--
-- Idempotente: usa IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    module_id VARCHAR(64) NOT NULL,
    period VARCHAR(16) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    amount_paid_usd NUMERIC(10, 2) NOT NULL DEFAULT 0,
    amount_paid_ars NUMERIC(12, 2) NOT NULL DEFAULT 0,
    mp_subscription_id VARCHAR(128),
    auto_renew BOOLEAN NOT NULL DEFAULT TRUE,
    granted_by_admin_id INTEGER REFERENCES users(id),
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indices para consultas frecuentes
CREATE INDEX IF NOT EXISTS idx_sub_user
    ON subscriptions(user_id);

CREATE INDEX IF NOT EXISTS idx_sub_user_module
    ON subscriptions(user_id, module_id);

CREATE INDEX IF NOT EXISTS idx_sub_status_expires
    ON subscriptions(status, expires_at);

-- Restricciones de dominio (valores permitidos)
DO $$
BEGIN
    -- module_id permitido (los 4 modulos de gestion)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'subscriptions_module_id_check'
    ) THEN
        ALTER TABLE subscriptions
            ADD CONSTRAINT subscriptions_module_id_check
            CHECK (module_id IN (
                'service_enterprise',
                'biomedical_engineering',
                'proposal_generator',
                'knowledge_base'
            ));
    END IF;

    -- period permitido
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'subscriptions_period_check'
    ) THEN
        ALTER TABLE subscriptions
            ADD CONSTRAINT subscriptions_period_check
            CHECK (period IN ('monthly', 'quarterly', 'semester', 'annual'));
    END IF;

    -- status permitido
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'subscriptions_status_check'
    ) THEN
        ALTER TABLE subscriptions
            ADD CONSTRAINT subscriptions_status_check
            CHECK (status IN ('active', 'expired', 'cancelled', 'pending'));
    END IF;
END$$;

-- Verificacion opcional:
-- SELECT column_name, data_type, is_nullable, column_default
-- FROM information_schema.columns
-- WHERE table_name = 'subscriptions'
-- ORDER BY ordinal_position;
