---
name: plan-accion-roadmap-2026
description: Plan de accion 2026 Q3-Q4 + roadmap 2027 basado en investigacion de mercado
metadata:
  type: project
---

# Plan de accion SR Certificaciones / SGC — 2026 Q3/Q4

## Contexto
Despues de la investigacion de mercado de competidores CMMS biomedico
(EQ2 HEMS, WebTMA, Nuvolo, MaintainX, UpKeep, Limble, Click Maint,
Oxmaint, Facilio) confirme que:

1. **Modo offline es REQUISITO no diferenciador** — lo tienen TODOS.
   Sin offline no vendes a hospitales medianos o grandes. Es la priori-
   dad ABSOLUTA.
2. **Video adjunto** es destacado por MaintainX y Oxmaint ("photo/video
   proof at bedside"). Vos solo tenes foto.
3. **Tu diferenciador real es la integracion con analizadores**
   (Fluke ESA620, QA-ES II, Impulse 6000D/7000DP, SigmaPace 1000,
   IDA-4 Plus) + IEC 62353 + ISO 17025 + LATAM. NADIE en el mercado
   mid-price tiene esto.
4. **Precio sugerido para LATAM**: USD 15-40/user/mes segun tier.
   Click Maint = $35, UpKeep = $45-75, MaintainX = $21-49, EQ2/Nuvolo = quote.

## Roadmap por prioridad

### TIER 1 - Sin esto no vendes (mes 1-2)
- **#866** Modo offline completo (cambiar ubicacion + reportar falla + crear OT)
  - Fase 1: cambiar ubicacion (~3-4h) -> v5.1.211
  - Fase 2: reportar falla clinical_user (~3-4h) -> v5.1.212
  - Fase 3: crear/editar OT tecnico (~4h) -> v5.1.213
- **#867** Video adjunto al reporte de falla (~6h) -> v5.1.214

### TIER 2 - Diferenciadores (mes 3)
- **#868** Dashboard predictivo simple (AI lite) (~8h) -> v5.1.215
- **#869** Notificaciones push (FCM) (~8h) -> v5.1.216
- **#870** App iOS (~16h + cuenta Apple + Mac) -> v5.2.0

### TIER 3 - Vision 2027
- **#871** IoT sensores temperatura/vibracion (~30-40h)
- **#872** AI predictive maintenance con scikit-learn (~60-80h)
- **#873** Marketplace de protocolos compartidos (~40-60h)

## Decision arrancar
Usuario eligio: **#866 Fase 1 - modo offline para cambiar ubicacion (~3-4h)**.
Patron pequeno que se replica para Fases 2 y 3.

## Que tener listo antes de #866 Fase 1
- sqflite ya esta en pubspec.yaml (verificado)
- connectivity_plus ya esta en pubspec.yaml (verificado)
- Plan tecnico detallado: ver .claude/memory/plan_865_866_qr_detalle_offline.md

## Datos para Google Sheets v5.1.210
- version: 5.1.210
- sha256: f690c05a550615ad6b0e2fa768c5649c3e230885016eba36a4dea1779aafa960
- size: 169474614
- URL: https://github.com/seba24/ESA625_Backend/releases/download/v5.1.210/ESA625_Setup_5.1.210.exe
