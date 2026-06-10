---
name: plan-871-ofertas-creditos
description: Plan #871 - sistema completo de ofertas/promos de creditos con segmentacion y notificaciones
metadata:
  type: project
---

# #871 — Sistema completo de ofertas relampago de creditos

## Contexto (2026-06-09)
Usuario pidio: "que los porcentajes los puede cambiar para enviar
ofertas a clientes. Necesito un sistema de envio de ofertas. Compra
relampago x creditos a tanto por credito".

Decision: alcance completo de una (no MVP).

## Estructura de precios (precondicion para #871)

Antes de #871 necesitamos terminar el refactor de creditos que dejo
pendiente:

- Borrar tabla `credit_packages` (precios absolutos)
- Agregar a `pricing_config`:
  - `credit_base_price_ars` = 10000 (precio de 1 credito)
  - `credit_qty_multiplier:1` = 1.00 (0% off)
  - `credit_qty_multiplier:5` = 0.95 (5% off)
  - `credit_qty_multiplier:10` = 0.90 (10% off)
  - `credit_qty_multiplier:25` = 0.80 (20% off)
  - `credit_qty_multiplier:50` = 0.80 (20% off)
  - `credit_qty_multiplier:100` = 0.80 (20% off)
- Refactor `payments.py` para calcular precios al vuelo

Esto va PRIMERO porque las ofertas son DESCUENTOS sobre estos precios base.

## Tipos de oferta (4 tipos)

| Tipo | Descripcion | Ejemplo |
|---|---|---|
| **quantity_discount** | Cantidad fija con precio especial por credito | "10 creditos a $7000/cred" |
| **percent_off** | % de descuento extra sobre precio normal | "30% off en todos los paquetes" |
| **bonus** | Compra X recibi Y extra de regalo | "Comprando 10 te damos 12" |
| **bundle** | Combo de creditos + meses de suscripcion gratis | "50 creditos + 1 mes IB gratis" |

## Segmentacion (4 tipos)

| Tipo | Audiencia | Uso |
|---|---|---|
| **public** | Todos los usuarios | Promo masiva |
| **user_email** | 1 usuario por email | Retencion / nuevo cliente |
| **user_list** | Lista de emails (CSV o filtro) | Segmento custom (ej. inactivos 60+ dias) |
| **role** | Por rol del usuario (admin, clinical_user, etc.) | Promo segun perfil |

## Notificaciones (4 canales)

| Canal | Cuando | Donde |
|---|---|---|
| **Banner SGC desktop** | Al abrir el SGC, oferta activa | QFrame amarillo arriba del sidebar |
| **Email** | Al crear la oferta (uno por destinatario) | SMTP via mailgun o similar |
| **Push mobile** | Cuando se crea oferta | FCM (Firebase Cloud Messaging) |
| **Pestana Ofertas** | Cuando entra a Creditos | Tab dentro del dialog de creditos |

## Arquitectura tecnica

### Backend

**Tabla `offers`** (Neon):
```sql
CREATE TABLE offers (
    id SERIAL PRIMARY KEY,
    code VARCHAR(32) UNIQUE,           -- codigo legible: 'WINTER25'
    name VARCHAR(255) NOT NULL,        -- nombre interno: 'Promo Invierno 2026'
    description TEXT NOT NULL DEFAULT '', -- texto para el cliente
    offer_type VARCHAR(32) NOT NULL,   -- 'quantity_discount'|'percent_off'|'bonus'|'bundle'
    audience_type VARCHAR(32) NOT NULL,-- 'public'|'user_email'|'user_list'|'role'
    audience_value TEXT NOT NULL DEFAULT '', -- email / CSV emails / nombre rol
    -- Configuracion segun offer_type (JSONB)
    config JSONB NOT NULL DEFAULT '{}',
    -- Vigencia
    starts_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    -- Limites
    max_redemptions INTEGER NOT NULL DEFAULT 0, -- 0 = sin limite
    current_redemptions INTEGER NOT NULL DEFAULT 0,
    max_per_user INTEGER NOT NULL DEFAULT 1,    -- cuantas veces puede usar 1 user
    -- Estado
    active BOOLEAN NOT NULL DEFAULT TRUE,
    -- Auditoria
    created_by_admin_id INTEGER REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_offers_active_expires ON offers(active, expires_at);
CREATE INDEX idx_offers_audience ON offers(audience_type, audience_value);
```

**Tabla `offer_redemptions`** (canjes):
```sql
CREATE TABLE offer_redemptions (
    id SERIAL PRIMARY KEY,
    offer_id INTEGER NOT NULL REFERENCES offers(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    credits_purchased INTEGER NOT NULL,
    credits_bonus INTEGER NOT NULL DEFAULT 0,
    amount_paid_ars NUMERIC(12, 2) NOT NULL,
    mp_payment_id VARCHAR(128),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_redemptions_user ON offer_redemptions(user_id);
CREATE INDEX idx_redemptions_offer ON offer_redemptions(offer_id);
```

**Schema config JSONB por tipo:**

- `quantity_discount`: `{"credits": 10, "price_ars": 70000, "price_per_credit_ars": 7000}`
- `percent_off`: `{"discount_pct": 30, "min_credits": 0, "max_credits": 0}` (0 = sin limite)
- `bonus`: `{"buy_credits": 10, "get_extra_credits": 2}`
- `bundle`: `{"credits": 50, "free_modules": ["biomedical_engineering"], "free_months": 1, "price_ars": 500000}`

**Endpoints:**

```
# Cliente (autenticado)
GET  /api/offers/active                    listar ofertas activas para mi user
POST /api/offers/{id}/redeem               canjear oferta (crea preferencia MP)

# Admin
GET    /api/admin/offers                   listar todas (incluye expiradas)
POST   /api/admin/offers                   crear oferta
PUT    /api/admin/offers/{id}              actualizar
DELETE /api/admin/offers/{id}              borrar (soft delete - active=False)
POST   /api/admin/offers/{id}/notify       reenviar notificaciones
GET    /api/admin/offers/{id}/redemptions  ver canjes de una oferta
```

**Servicio `offer_service.py`:**
- `get_active_offers_for_user(user)` filtra por audience + vigencia + limites
- `calculate_offer_price(offer, credits)` calcula precio final segun tipo
- `redeem_offer(user, offer, credits)` crea redemption + preferencia MP
- `notify_offer(offer)` envia banners + emails + push

**Notificacion async:**
- Email: usar `services/email_service.py` con SMTP (sendgrid free tier 100/dia, o gmail SMTP)
- Push mobile: FCM con `firebase-admin` SDK + token registrado por device
- Banner SGC: cliente hace polling cada 5 min a `GET /api/offers/active` y muestra si hay nuevas

### Cliente desktop (SGC)

**Banner de ofertas:**
- En `main_window_qt.py` agregar QFrame amarillo arriba (entre toolbar y sidebar)
- Cargar `/api/offers/active` al startup + cada 5 min
- Mostrar oferta MAS URGENTE (la que vence mas cerca)
- Click abre `OffersDialog` con lista completa

**OffersDialog (nuevo):**
- `sgc/components/gui/dialogs/offers_dialog_qt.py`
- Lista ofertas activas como cards
- Cada card: titulo + descripcion + precio + countdown + boton "Aprovechar"
- Click "Aprovechar" abre `/api/offers/{id}/redeem` -> URL MP en navegador

**Pestana "Ofertas" en CreditsTab:**
- En `settings_dialog_qt.py` pestaña Creditos, sub-tab "Ofertas vigentes"
- Mismo contenido que OffersDialog pero embebido

### Cliente mobile (Flutter APK)

**Push notification:**
- Firebase Messaging registrado en cada device
- Cuando admin crea oferta, FCM dispara notification
- Tap abre pantalla "Ofertas" con detalle

**Pantalla Ofertas:**
- `mobile_app/lib/screens/offers_screen.dart`
- Lista cards similar al desktop
- Boton "Comprar" abre URL MP en browser externo

### Panel admin web

**Seccion "Ofertas":**
- Lista todas las ofertas con filtros (activas / expiradas / por tipo)
- Boton "Crear oferta" abre modal con:
  - Tipo (4 dropdowns muestran campos especificos)
  - Segmentacion (selector + input segun tipo)
  - Vigencia (date pickers)
  - Limites
  - Notificaciones (checkboxes: email / push / banner)
- Tabla de canjes por oferta (link "Ver canjes" en cada fila)

## Plan de implementacion (5 fases)

### Fase 1 (precondicion) - Refactor precios creditos a pricing_config (~2h)
- Migration 006: borrar credit_packages + agregar credit_* a pricing_config
- Refactor payments.py para calcular al vuelo
- Eliminar modelo CreditPackage + endpoints CRUD
- Panel admin: editar credit_base_price y credit_qty_multiplier desde Configuracion de precios

### Fase 2 - Backend ofertas core (~5h)
- Migration 007: tablas offers + offer_redemptions
- Modelo SQLAlchemy
- Servicio offer_service.py con los 4 tipos
- Endpoints admin (CRUD) + cliente (list + redeem)
- Tool admin local: `admin_credits.py create-offer ...`

### Fase 3 - Notificaciones (~6h)
- Email: services/email_service.py con SendGrid (free tier) o SMTP
- Push: firebase-admin SDK + endpoint /api/devices/register-token para mobile
- Banner cliente: endpoint listo, cliente hace polling

### Fase 4 - Cliente desktop (~4h)
- Banner amarillo en main_window_qt
- OffersDialog (lista + countdown + boton comprar)
- Pestaña Ofertas en CreditsTab

### Fase 5 - Cliente mobile + Panel admin web (~5h)
- Mobile: OffersScreen + push notifications
- Panel admin web: seccion completa con CRUD y ver canjes

## Riesgos

- **Push notifications**: requiere FCM setup + cuenta Firebase + cert iOS si en el futuro hay iOS. Setup tarda ~2h extra solo para Firebase project.
- **Email**: SendGrid free tier solo 100 emails/dia. Si tenes 200 usuarios, una promo masiva no alcanza. Alternativa: gmail SMTP (limit 500/dia pero requiere "less secure apps").
- **Concurrencia**: si 2 usuarios canjean la oferta numero 99 de 100 simultaneamente, necesitamos lock. Usar `SELECT ... FOR UPDATE` en redeem_offer.
- **Polling cada 5 min**: aumenta carga del backend. Alternativa: WebSocket. Por ahora polling es OK.

## Decisiones pendientes
- Proveedor de email (SendGrid vs gmail SMTP vs mailgun)
- Si setup Firebase ahora o dejar push para fase 6
- Si las ofertas SE COMBINAN con descuentos base (oferta 10% off + precio 25cred ya con 20% off) o son EXCLUSIVAS
- Politica de devolucion si oferta sale mal y cliente reclama

## Estimacion total
- Fase 1: 2h
- Fase 2: 5h
- Fase 3: 6h
- Fase 4: 4h
- Fase 5: 5h
- **Total: ~22h en 4-5 releases**
