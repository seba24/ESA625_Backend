-- Migración 002 — 2026-04-11
-- Agrega columna report_title_template a la tabla companies.
--
-- Contexto: feature de personalización del título del reporte PDF.
-- Cada empresa puede tener un template propio para el encabezado de
-- sus reportes (ej. "VALIDACIÓN TRAZABLE — {module}", "INFORME DE
-- PERFORMANCE — {module}", "Reporte oficial CIAREC", etc.).
--
-- El placeholder {module} se reemplaza en runtime por el nombre del
-- módulo (MARCAPASOS, DESFIBRILADOR, etc.). Si el template no contiene
-- {module}, se usa literal sin reemplazo.
--
-- Es idempotente: usa IF NOT EXISTS, se puede ejecutar varias veces
-- sin daño.

ALTER TABLE companies
    ADD COLUMN IF NOT EXISTS report_title_template VARCHAR(500);

-- Verificación opcional:
-- SELECT column_name, data_type, character_maximum_length, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'companies' AND column_name = 'report_title_template';
