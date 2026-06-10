-- Migracion 007 - 2026-06-09
-- Sistema de ofertas relampago de creditos (#871 Fase 2)
--
-- Permite al admin crear ofertas de 4 tipos (cantidad fija con precio
-- especial, % off, bonus, bundle con suscripcion), dirigidas a publico
-- general o usuarios especificos, con vigencia y limite de cupos.
--
-- Tabla offers: definicion de cada oferta
-- Tabla offer_redemptions: cada vez que un user canjea una oferta
--
-- Idempotente: usa IF NOT EXISTS.

-- ============================================================
-- Tabla principal de ofertas
-- ============================================================

CREATE TABLE IF NOT EXISTS offers (
    id SERIAL PRIMARY KEY,
    code VARCHAR(32) UNIQUE,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    -- Tipo de oferta y config (JSON serializado en text, ver schema en offer_service.py)
    offer_type VARCHAR(32) NOT NULL,
    config_json TEXT NOT NULL DEFAULT '{}',
    -- Audiencia
    audience_type VARCHAR(32) NOT NULL DEFAULT 'public',
    audience_value TEXT NOT NULL DEFAULT '',
    -- Vigencia
    starts_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    -- Limites
    max_redemptions INTEGER NOT NULL DEFAULT 0,
    current_redemptions INTEGER NOT NULL DEFAULT 0,
    max_per_user INTEGER NOT NULL DEFAULT 1,
    -- Estado
    active BOOLEAN NOT NULL DEFAULT TRUE,
    -- Auditoria
    created_by_admin_id INTEGER REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_offers_active_expires
    ON offers(active, expires_at);
CREATE INDEX IF NOT EXISTS idx_offers_audience
    ON offers(audience_type, audience_value);

-- Restricciones de dominio
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'offers_offer_type_check'
    ) THEN
        ALTER TABLE offers ADD CONSTRAINT offers_offer_type_check
            CHECK (offer_type IN ('quantity_discount', 'percent_off', 'bonus', 'bundle'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'offers_audience_type_check'
    ) THEN
        ALTER TABLE offers ADD CONSTRAINT offers_audience_type_check
            CHECK (audience_type IN ('public', 'user_email', 'user_list', 'role'));
    END IF;
END$$;

-- ============================================================
-- Tabla de canjes (cada vez que un user usa una oferta)
-- ============================================================

CREATE TABLE IF NOT EXISTS offer_redemptions (
    id SERIAL PRIMARY KEY,
    offer_id INTEGER NOT NULL REFERENCES offers(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    credits_purchased INTEGER NOT NULL,
    credits_bonus INTEGER NOT NULL DEFAULT 0,
    amount_paid_ars NUMERIC(12, 2) NOT NULL,
    mp_payment_id VARCHAR(128),
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_redemptions_user
    ON offer_redemptions(user_id);
CREATE INDEX IF NOT EXISTS idx_redemptions_offer
    ON offer_redemptions(offer_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'redemptions_status_check'
    ) THEN
        ALTER TABLE offer_redemptions ADD CONSTRAINT redemptions_status_check
            CHECK (status IN ('pending', 'completed', 'failed', 'refunded'));
    END IF;
END$$;

-- Verificacion opcional:
-- SELECT id, code, name, offer_type, audience_type, expires_at,
--        current_redemptions || '/' || max_redemptions AS uso, active
-- FROM offers
-- ORDER BY created_at DESC;
