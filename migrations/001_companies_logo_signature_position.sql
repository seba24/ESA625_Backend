-- Migración 001 — 2026-04-11
-- Agrega columnas de posición de logo/firma y protocol_key a la tabla companies.
--
-- Contexto: el modelo SQLAlchemy app/models/company.py se actualizó en los
-- commits 671c776 ("Posicion logo/firma en Company") y d576963 ("protocol_key
-- a Company"), pero la base Postgres en producción nunca recibió la migración.
-- Esto rompe los INSERT desde POST /api/company/ con:
--    column "logo_x" of relation "companies" does not exist
--
-- Es idempotente: usa IF NOT EXISTS, se puede ejecutar varias veces sin daño.

ALTER TABLE companies ADD COLUMN IF NOT EXISTS logo_x          FLOAT NOT NULL DEFAULT 0.0;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS logo_y          FLOAT NOT NULL DEFAULT 0.0;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS logo_width      FLOAT NOT NULL DEFAULT 0.0;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS logo_height     FLOAT NOT NULL DEFAULT 0.0;

ALTER TABLE companies ADD COLUMN IF NOT EXISTS signature_x     FLOAT NOT NULL DEFAULT 0.0;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS signature_y     FLOAT NOT NULL DEFAULT 0.0;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS signature_width FLOAT NOT NULL DEFAULT 0.0;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS signature_height FLOAT NOT NULL DEFAULT 0.0;

-- protocol_key: String(255) con default vía Python (Fernet.generate_key()).
-- En la DB lo dejamos NULLABLE para no romper filas existentes; el modelo
-- llena el default al crear nuevas filas. Si querés backfill de las existentes,
-- ver el bloque opcional al final.
ALTER TABLE companies ADD COLUMN IF NOT EXISTS protocol_key VARCHAR(255);

-- Verificación: listar columnas finales de la tabla
-- (descomentá si querés ver el resultado)
-- SELECT column_name, data_type, is_nullable, column_default
-- FROM information_schema.columns
-- WHERE table_name = 'companies'
-- ORDER BY ordinal_position;

-- ─────────────────────────────────────────────────────────────────────
-- BLOQUE OPCIONAL: backfill de protocol_key para empresas pre-existentes
-- (solo si necesitás que las empresas viejas también tengan clave Fernet)
-- ─────────────────────────────────────────────────────────────────────
-- UPDATE companies
-- SET protocol_key = encode(gen_random_bytes(32), 'base64')
-- WHERE protocol_key IS NULL;
