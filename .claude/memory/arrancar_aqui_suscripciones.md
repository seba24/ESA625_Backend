---
name: arrancar-aqui-suscripciones
description: ARRANCAR AQUI - Plan #870 Fase 1 listo para implementar - sistema de suscripciones SaaS para modulos de gestion
metadata:
  type: project
---

# ARRANCAR AQUI - #870 Fase 1 sistema de suscripciones

## Como arrancar la sesion

1. Leer este archivo primero
2. Leer `plan_870_suscripciones_modulos_gestion.md` (mismo directorio) - plan completo
3. Empezar con la tarea "Fase 1" detallada abajo

## Contexto rapido

El usuario (Sebastian Lorandi, SR Certificaciones) tiene el SGC (Sistema
de Gestion de Certificaciones) instalado en hospitales/talleres biomedicos
en Argentina. Hoy el sistema cobra creditos por reporte PDF generado en
el cloud (lionfish-app DigitalOcean). Quiere ahora vender los **modulos
de gestion** (SE, IB, PG, KB) por suscripcion mensual/trim/sem/anual.

## Pricing acordado

| Modulo | Precio base USD/mes |
|---|---|
| SE - Empresa de Servicio | 25 |
| IB - Ingenieria Biomedica | 35 |
| PG - Generador de Propuestas | 15 |
| KB - Base de Conocimiento | 10 |

**Descuentos por periodo** (multiplica el precio mensual por el numero de meses):
- Mensual: 0% off (mult 1.0)
- Trimestral: 10% off (mult 0.90)
- Semestral: 17% off (mult 0.83)
- Anual: 22% off (mult 0.78)

**Descuentos acumulativos por cantidad de modulos contratados**:
- 1 modulo: 0%
- 2 modulos: 5% off
- 3 modulos: 10% off
- 4 modulos: 20% off

**Conversion USD->ARS**: oficial BNA al momento del pago.

## Tareas Fase 1 (orden secuencial)

### Tarea 1: Crear migration SQL
- Archivo: `migrations/003_subscriptions.sql`
- Schema completo en `plan_870_suscripciones_modulos_gestion.md` seccion "Tabla nueva subscriptions"
- Aplicar manualmente en Neon console.neon.tech > SQL Editor (no hay alembic)

### Tarea 2: Modelo SQLAlchemy
- Archivo: `app/models/subscription.py`
- Reflejar la tabla con SQLAlchemy ORM
- Agregar import en `app/models/__init__.py`

### Tarea 3: Pricing engine
- Archivo: `app/services/pricing.py`
- Funcion `calculate_price(modules: list[str], period: str) -> dict`
  retorna: `{base_usd, discount_period_pct, discount_quantity_pct, total_usd, total_ars}`
- Tabla de precios hardcodeada arriba (despues se mueve a DB si hace falta)

### Tarea 4: Router de suscripciones
- Archivo: `app/api/routes/subscriptions.py`
- Endpoints:
  - `GET /api/users/me/license/{module_id}` - {licensed, expires_at, days_left}
  - `GET /api/subscriptions/active` - lista activas del user
  - `GET /api/subscriptions/pricing?modules=SE,IB&period=annual` - calcular precio

### Tarea 5: Endpoint admin
- En `app/api/routes/admin.py` agregar:
  - `POST /api/admin/grant-subscription` body `{email, module_id, period, months_count}` - asigna suscripcion sin pasar por MP. Solo admin. Calcula `expires_at = now + months_count * 30 days`.

### Tarea 6: Tool admin local
- Volver al repo del cliente (ESA625_Cloud) y extender `tools/admin_credits.py`
- Comando: `python tools/admin_credits.py grant-subscription <email> <module_id> <period> <months>`
- Ej: `python tools/admin_credits.py grant-subscription slorandi@gmail.com service_enterprise annual 12`

### Tarea 7: Deploy
- `git add . && git commit -m "#870 Fase 1: suscripciones SaaS"`
- `git push origin master`
- Verificar deploy en DigitalOcean panel `lionfish-app`

### Tarea 8: Test smoke
- `curl -X GET https://lionfish-app-58cxz.ondigitalocean.app/api/subscriptions/active -H "Authorization: Bearer <jwt>"`
- Verificar respuesta 200 con lista vacia (todavia no hay suscripciones)
- Usar `tools/admin_credits.py grant-subscription` para asignar una
- Volver a `GET /api/subscriptions/active` y verificar que ahora aparece

## Modulos IDs (importante)

Los module_id usan el formato del registry del cliente (NO el license_prefix):
- `service_enterprise` (prefix SE)
- `biomedical_engineering` (prefix IB)
- `proposal_generator` (prefix PG)
- `knowledge_base` (prefix KB)

## Estimacion
- Fase 1 completa: ~6h
- Despues vienen Fase 2 (cliente valida expires_at, 3h), Fase 3 (MP, 6h), Fase 4 (UI compra, 3h)

## Cuando termines la Fase 1

Avisar al usuario para que:
1. Ejecute la migration en Neon
2. Verifique el deploy en DO
3. Pruebe `grant-subscription` desde el cliente
4. Confirme que `/api/users/me/license/service_enterprise` devuelve `{licensed: true}`

Despues vienen Fase 2 (cambios en el cliente para validar suscripcion).

## Repo del cliente

`c:/Users/sjelo/OneDrive/Documentos/Programacion/Python/ESA625_Cloud`
- Branch activa: `feat/sync-client`
- ULTIMO RELEASE: v5.1.212 (commit 5c82203)
- Ultima sesion: 2026-06-09 - #867 + #869 + #866 Fase 1 mobile

Memorias relevantes del cliente para tener en mente (no necesarias para Fase 1 backend):
- `plan_867_creditos_todos_modulos.md` - sistema actual de creditos por reporte
- `plan_865_866_qr_detalle_offline.md` - APK offline mode

## Variables de entorno backend

En DO App Platform > lionfish-app > Settings > Environment Variables:
- `DATABASE_URL` - Neon Postgres (con channel_binding limpiado)
- `JWT_SECRET_KEY`
- `MERCADOPAGO_ACCESS_TOKEN` (para Fase 3)

## Admin credentials

Para tests:
- email: admin@srcertificaciones.com
- pwd: la que reseteamos en sesion anterior (esta en la memoria del cliente)

## Reglas absolutas del usuario

- Idioma: ESPAÑOL siempre
- Sin emojis salvo pedido explicito
- Referencias a codigo: markdown `[archivo.py:42](ruta)` nunca backticks
- Tablas HORIZONTALES (campos como columnas) nunca verticales
- Commits atomicos con `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`
- NUNCA force push a master
- Resguardar investigaciones ANTES de implementar
- Verificacion antes de implementar - leer el patron antes de cambiar
