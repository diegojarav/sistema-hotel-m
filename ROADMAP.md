# Roadmap — Hotel Munich PMS

> Planificación activa del proyecto.
> Para historia de versiones → ver [CHANGELOG.md](CHANGELOG.md)
> Para instrucciones operativas → ver [CLAUDE.md](CLAUDE.md)

---

## Estado actual

| Item | Estado |
|---|---|
| Versión | v1.10.0-dev |
| Tests | 590 · 83% cobertura (606 con KPI+perf) |
| KPIs | 9 métricas scoreadas 0-100 (último run: 100/100) |
| Cliente activo | Hospedaje Los Monges (15 habitaciones) |
| Entorno | GCP VM (e2-small) · SQLite WAL · un comando deploy |
| Phases completadas | 1-6 (v1.4-v1.9) + DB Audit Phase 1 (Postgres-readiness) + Phase 2a (Guests + Buildings, v1.10.0-dev) |
| Próxima migración | `013_*.py` |
| AI tools | 19 (último: `buscar_huesped_historial`) |
| Tablas | 25 (incluye `guests` + `buildings` desde Phase 2a) |

---

## Próximas features (priorizadas)

### Feature 1 — Control granular de herramientas IA por rol · ✅ COMPLETADA en v1.9.0

Implementada en abril 2026 vía migración `008_ai_agent_permissions_activation.py`. Ver entrada v1.9.0 en CHANGELOG.md para detalle completo. Resumen: servicio `AIAgentPermissionService`, middleware `filter_tools_for_role()` en agent.py, 4 endpoints en `/api/v1/admin/ai-permissions/*`, página PC `93_🤖_Permisos_IA.py`, 27 tests.

---

### Feature 2 — SaaS / Multi-hotel

**Por qué**: el sistema está construido con un cliente (`property_id="los-monges"` hardcoded en muchos puntos) pero la arquitectura tiene potencial de escalar a múltiples hoteles. Hay tablas como `Property`, `RoomCategory` y `ClientType` que ya tienen `property_id` como columna, pero el código asume un solo property por seed y por defaults.

**Scope** (alto nivel, requiere diseño detallado antes de implementar):
- Tenant isolation efectivo en todas las queries (auditar uno por uno los `db.query(...).filter(...)` que hoy no filtran por property_id)
- Sistema de access control por hotel (un usuario admin puede pertenecer a varios hoteles, un recepcionista a uno solo)
- Panel de administración multi-tenant separado del PC actual
- Pricing tier para SaaS (free / starter / business)
- Onboarding self-service de hoteles nuevos (signup → seed automático → primer login)
- Migración del cliente actual sin downtime

**Dependencia**: decisión de negocio primero (¿hay clientes #2/#3 confirmados?). Migration trigger documentado: cliente #3 o >20 usuarios concurrentes simultáneos requiere también migración SQLite → PostgreSQL.

**Complejidad estimada**: alta (impacto transversal, múltiples migraciones de datos, riesgo regresivo)

---

### Feature 3 — RoomStatusLog · ✅ COMPLETADA en v1.9.0

Implementada en abril 2026 vía migración `007_room_status_log.py`. Ver entrada v1.9.0 en CHANGELOG.md para detalle completo. Resumen: modelo `RoomStatusLog`, insert automático en `PATCH /rooms/{id}/status`, endpoint `GET /rooms/{id}/status-log`, expander en PC Admin, 10 tests.

---

## Decisiones técnicas pendientes

Items identificados en la auditoría del 2026-04-21. No son features ni bugs — son decisiones abiertas que requieren análisis antes de actuar.

### D1 — `scripts/migrate_monges.py` · ✅ CLOSED 2026-04-22

Resolución: Opción C ejecutada. Script eliminado (`git rm scripts/migrate_monges.py`). Las 2 referencias en `seed_monges.py:750` y `Admin_Habitaciones.py:741` actualizadas para apuntar al flujo canónico (`run_migrations.py` + `seed_monges.py`). Phantom table `room_status_log` no estaba presente en dev DB; la migración 007 incluye drop+recreate idempotente para entornos donde sí existiera. Cero regresiones en tests.

---

### D2 — Qué hacer con `verify_mobile_api.py` y `verify_parking.py` · ✅ CLOSED 2026-04-22

**Resolución**: Opción A ejecutada. Movidos a `scripts/` — confirmado como scripts manuales de verificación, no tests automatizados.
- `git mv backend/tests/verify_mobile_api.py scripts/verify_mobile_api.py`
- `git mv backend/tests/verify_parking.py scripts/verify_parking.py`
- Fix sys.path en `verify_parking.py` (apunta a `../backend/` ahora).
- Cero referencias en código (sólo CHANGELOG/ROADMAP las mencionan).
- Tests post-move: 539 passed, 0 failed (los archivos nunca fueron colectados por pytest).

---

### D3 — TODO de `RoomStatusLog` · ✅ CLOSED 2026-04-22

Resolución: implementado vía Feature 3 en v1.9.0. Migración 007, modelo `RoomStatusLog`, endpoint `GET /rooms/{id}/status-log`, expander en PC Admin, 10 tests. Ver CHANGELOG.md v1.9.0 para detalles.

---

## Phase 2b — Type harmonization + retention (próxima, requerida antes del tag v1.10.0)

Continuación de la auditoría DB. **No agrega features**, prepara el cutover a Postgres y limpia debt acumulado:
- **Boolean-as-Integer fixes** — 14 columnas declaradas como `Column(Integer, default=0/1)` que conceptualmente son booleanas. Migrar a `Column(Boolean)` con table-rebuild dance bajo SQLite (la conversión es no-op en Postgres).
- **JSON-as-String fixes** — 4 columnas con comentario `# JSON` que guardan strings: `reservations.price_breakdown`, `room_categories.amenities`, `pricing_seasons.applies_to_categories`, `price_calculations.calculation_details`. Migrar a `Column(JSON)` (en Postgres se vuelve `JSONB`).
- **Drop `Property.breakfast_included`** — deprecated desde v1.7. Reemplazado por `meals_enabled` + `meal_inclusion_mode`. Slot disponible: `013_*.py`.
- **Promover los 9 `property_id` String restantes a FK reales** — hoy 12/24 tablas tienen `property_id` pero solo 3 lo declaran como FK. La promoción es model-only (Phase 1 Option A). Audit pendiente de orphan rows antes.
- **Backfill `Property.slug` NULL → property.id** y promover a `NOT NULL` (UNIQUE ya declarado en Phase 2a).
- **Retención automática para tablas append-only** — `price_calculations` y `session_logs` crecen sin límite. Job semanal que elimina rows >365 días. Configurable via `system_settings`.

## Phase 3+ — PostgreSQL cutover (después de Phase 2b)

- Capa de conexión: `DATABASE_URL` env var, support para `postgresql://...` además de `sqlite:///`.
- Adopción de Alembic (reemplaza `scripts/migrations/NNN_*.py` + `migration_history` table → `alembic/versions/` + `alembic_version`).
- Backup system rewrite — Postgres usa `pg_dump`, no copy de archivo. Reescribir `backup_manager.py`.
- Cutover playbook: dump SQLite → restore en Postgres staging → smoke tests → cutover prod en ventana de mantenimiento.

## Backlog (sin prioridad asignada)

Ideas documentadas para no perderlas. **No tienen estimación ni fecha.**

- **De-dup / merge tool de huéspedes** (Phase 2a follow-up): UI admin para detectar candidatos (nombre similar, mismo phone, etc.) y mergear dos rows en uno. Reasigna `reservations.guest_id` y `checkins.guest_id` al canónico, soft-deletea el otro. Útil porque la entrada manual + auto-creación generan duplicados con tiempo.
- **Sistema de plantillas de email** — continuación de Phase 5. Templates configurables para pre-checkin reminder (X días antes), post-checkout thank-you, recordatorio de pago pendiente. Requiere extender `email_body_template` a múltiples templates por evento.
- **OTA API nativa** — integración directa con Booking.com / Expedia / Airbnb API en lugar de iCal. Elimina el delay de 15 min de polling pero requiere certificación con cada OTA, costos y mantenimiento de credenciales.
- **Notificaciones push mobile** — alertas en el frontend mobile para nueva reserva entrante por OTA, stock bajo, sync failure de un feed iCal. Requiere service worker + suscripción FCM o similar.
- **Portal de huéspedes** — acceso web público (sin login del staff) para que el huésped vea su reserva, modifique datos, haga checkin online y descargue su propio PDF. Implica auth separada (token por reserva) y endpoints públicos.
- **Reportes avanzados / Revenue Management** — dashboard de KPIs de negocio (RevPAR, ADR, ocupación forecast), recomendaciones automáticas de pricing dinámico según demanda histórica, comparativa year-over-year.
- **Subir cobertura de tests 75% → 80%** (TEST-01 del backlog histórico). Las áreas con menor cobertura hoy son los servicios de reportes y las rutas administrativas.
- **PERF-12 — capa de cache Redis** entre el agente IA y los servicios pesados (`get_revenue_summary`, `get_occupancy_for_month`). Hoy los cálculos se hacen on-demand cada vez que el agente los pide.
- **Limpieza de back-compat de status legacy** — los filtros de reserva todavía aceptan ambos sets (`["RESERVADA", "Confirmada", ...]`). Una vez confirmado que no quedan reservas con valores legacy en la DB, simplificar.

---

## Visión a mediano plazo

El producto fue diseñado para un caso de uso específico (hotel pequeño-mediano paraguayo, ~15 habitaciones, operación familiar) y ese sigue siendo el sweet spot. La arquitectura — SQLite, hybrid monolith con Streamlit + Next.js, deploy en VM única de GCP — encaja exactamente con esa escala y mantiene los costos operativos bajos (un VM e2-small alcanza para todo el stack).

La dirección natural es **estabilizar al cliente actual** mientras se prepara el sistema para escalar horizontalmente cuando aparezca el cliente #2. Eso significa: mantener la cobertura de tests, mantener los KPIs en 100/100, y completar las features de tenant isolation antes de aceptar un segundo hotel. El umbral técnico documentado para migrar SQLite → PostgreSQL es cliente #3 o >20 usuarios concurrentes simultáneos.

El **agente IA conversacional** es uno de los diferenciadores fuertes — 18 herramientas en español que cubren todas las consultas operativas habituales, sin que el operador necesite memorizar dónde está cada reporte en el menú. La activación de `AIAgentPermission` (Feature 1) lo lleva al siguiente nivel: agente personalizado por rol, con políticas de acceso granulares. Esto es especialmente valioso si el sistema escala a SaaS y diferentes hoteles quieren limitar qué información expone el agente a cada tipo de empleado.

A más corto plazo, la prioridad operativa es cerrar las **decisiones técnicas pendientes (D1/D2/D3)** para limpiar el repo de ambigüedades, y ejecutar los deploys pendientes de v1.7.0 + v1.8.0 cuando el cliente lo apruebe (ambas versiones están listas, validadas con tests, y no rompen nada existente).
