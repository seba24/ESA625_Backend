---
name: plan-870-suscripciones-modulos-gestion
description: Plan #870 - sistema de suscripciones mensuales/trim/sem/anuales para modulos de gestion (SE/IB/PG/KB)
metadata:
  type: project
---

# #870 — Sistema de suscripciones para modulos de gestion

## Contexto del pedido (2026-06-09)
Usuario: "quiero vender las licencias de los soft de gestion, podriamos
hacer pagos mensuales trimestrales semestrales y anuales".

Hoy el sistema cobra creditos por reporte PDF (cloud) y los modulos
estan registrados con prefixes pero NO hay validacion de suscripcion.

## Modelo de pricing acordado

### Analizadores
- App + modulos analizadores: **gratis** (instalacion sin costo)
- Cobro por reporte PDF: 1 credito por reporte (#867 funcionando)

### Modulos de gestion (suscripcion)
- **SE** Empresa de Servicio: $25 USD/mes
- **IB** Ingenieria Biomedica: $35 USD/mes
- **PG** Generador de Propuestas: $15 USD/mes
- **KB** Base de Conocimiento: $10 USD/mes
- Total combo (los 4): $85 USD/mes sin descuento

### Descuentos por periodo
- Mensual: 0% off
- Trimestral: 10% off
- Semestral: 17% off
- Anual: 22% off

### Descuentos acumulativos por cantidad de modulos
- 1 modulo: 0%
- 2 modulos: 5% off sobre total
- 3 modulos: 10% off
- 4 modulos: 20% off

### Ejemplos de precio final (USD)
- 1 modulo (IB) mensual: $35
- 1 modulo (IB) anual: $35 * 12 * 0.78 = $327.60
- 4 modulos combo mensual: $85 * 0.80 = $68
- 4 modulos combo anual: $85 * 12 * 0.78 * 0.80 = $636.48
- 2 modulos (SE+IB) trimestral: ($25+$35)*3*0.90*0.95 = $153.90

### Migracion
No hay clientes externos con licencias perpetuas. Todos los usuarios actuales
son internos de SR Certificaciones. Modelo nuevo se aplica desde dia 1.

## Arquitectura tecnica

### Backend (lionfish-app DigitalOcean)

**Tabla nueva: `subscriptions`**
```sql
CREATE TABLE subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) NOT NULL,
    module_id TEXT NOT NULL,  -- 'service_enterprise' / 'biomedical_engineering' / 'proposal_generator' / 'knowledge_base'
    period TEXT NOT NULL,     -- 'monthly' / 'quarterly' / 'semester' / 'annual'
    started_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    status TEXT NOT NULL,     -- 'active' / 'expired' / 'cancelled'
    amount_paid_usd NUMERIC(10,2) NOT NULL,
    mp_subscription_id TEXT,  -- ID en Mercado Pago para autorenovacion
    auto_renew BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_sub_user ON subscriptions(user_id);
CREATE INDEX idx_sub_status_expires ON subscriptions(status, expires_at);
```

**Endpoints nuevos:**
- `GET /api/subscriptions/active` — lista las suscripciones activas del user
- `GET /api/subscriptions/pricing` — devuelve la tabla de precios calculada (incluye descuentos por cantidad de modulos seleccionados y periodo)
- `POST /api/subscriptions/checkout` — body: {modules: [...], period: 'annual'}. Calcula precio final + descuentos. Devuelve URL de Mercado Pago.
- `POST /api/subscriptions/webhook/mercadopago` — recibe notificacion de pago aceptado o renovado. Crea/actualiza fila en subscriptions.
- `POST /api/subscriptions/{id}/cancel` — desactiva auto_renew. La suscripcion sigue activa hasta expires_at.
- `GET /api/users/me/license/{module_id}` — devuelve {licensed: bool, expires_at: timestamp, days_left: int} para que el cliente lo cachee localmente.

**Cron job (DigitalOcean Function o pg_cron):**
- Cada hora: marcar como `status='expired'` las que pasaron `expires_at`
- Cada dia: enviar email "tu suscripcion vence en 7 dias" si auto_renew=False

### Cliente (sgc/components/common/license_online.py)

**Cambios al `OnlineLicenseManager`:**
- Agregar campo `expires_at` al cache de licencia
- `is_module_activated_or_offline(module_id)` valida que `expires_at > now()`
- Cache TTL bajo (15 min) para reaccionar a expiraciones del backend
- Si expiro: dialog modal "Suscripcion vencida" con boton "Renovar" que abre MP

**Cambios al settings_dialog_qt.py (pestaña Suscripciones nueva):**
- Listado de modulos disponibles con checkbox + radio button de periodo
- Calculo de precio en vivo (call al endpoint /api/subscriptions/pricing)
- Boton "Pagar" que abre Mercado Pago en navegador
- Listado de suscripciones activas con fecha de vencimiento y boton "Cancelar autorenovacion"

### Mercado Pago integracion

MP soporta **suscripciones recurrentes** con el flujo:
1. Cliente crea `PreApprovalPlan` (plan recurrente) en MP
2. Cliente firma autorizacion (autorenovacion automatica)
3. MP llama webhook con cada cobro mensual/trimestral/anual
4. Nuestro webhook actualiza `subscriptions.expires_at`

SDK Python disponible: `mercadopago` package. Tenemos el access token configurado.

## Plan de implementacion (Fases)

### Fase 1 — Backend mínimo viable (~6h)
- Tabla `subscriptions` + migracion
- Endpoint `GET /api/users/me/license/{module_id}` (consultar)
- Endpoint `POST /api/admin/grant-subscription` (asignar manual desde admin_credits.py)
- Endpoint `GET /api/subscriptions/active`
- Sin MP integration todavia - manual grant con admin_credits.py

### Fase 2 — Cliente: validacion de suscripcion (~3h)
- `OnlineLicenseManager` valida `expires_at`
- Dialog modal "Suscripcion vencida" al expirar
- Cache local con TTL 15 min
- Settings_dialog: pestaña Suscripciones con lista de activas

### Fase 3 — Backend: integracion Mercado Pago (~6h)
- Endpoint `POST /api/subscriptions/checkout` que calcula precio + crea preferencia MP
- Endpoint `POST /api/subscriptions/webhook/mercadopago` que actualiza DB
- Cron job para marcar expired

### Fase 4 — Cliente: UI de compra (~3h)
- Settings_dialog Suscripciones: selector de modulos + periodo + calculo en vivo
- Boton "Pagar" abre MP en navegador
- Despues del pago, actualizar saldo / suscripciones

### Fase 5 — Operacion (~2h)
- Admin tool: `python tools/admin_credits.py grant-subscription <email> <module> <period>`
- Reportes mensuales de MRR (monthly recurring revenue)

**Total estimado: ~20 horas distribuidas en 3 releases**

## Riesgos

- **Mercado Pago suscripciones**: tiene limitaciones de API y aprobacion manual de cuenta. Verificar antes que la cuenta este habilitada para PreApprovalPlan.
- **Conversion de moneda**: MP cobra en ARS, los precios son en USD. Necesitamos definir el tipo de cambio (oficial / blue / cripto).
- **Clientes que no renuevan**: hay que tener flujo claro de "cuando expira que pasa". Idea: 7 dias de grace period (sigue funcionando con banner "renovar"), despues bloquea.
- **Backups y reembolsos**: politica de reembolso (NO en mensual, prorrateo en anual?)
- **Soporte tecnico**: incluido o extra? Plan basico vs premium?

## Decisiones pendientes
- Conversion USD->ARS (oficial al momento del pago?)
- Grace period de 7 dias incluido o solo aviso?
- Politica de reembolsos?
- Trial gratis 14 dias?
