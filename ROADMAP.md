# Roadmap — Hotel Munich PMS

> Planificación activa del proyecto.
> Para historia de versiones → ver [CHANGELOG.md](CHANGELOG.md)
> Para instrucciones operativas → ver [CLAUDE.md](CLAUDE.md)

---

## Estado actual

| Item | Estado |
|---|---|
| Versión | v1.10.0-dev (listo para tag v1.10.0 final tras commit/push) |
| Tests | 797 · 83% cobertura (752 baseline + 12 multi-vehicle Phase 2c + 33 multi-currency Phase 2d) |
| KPIs | 9 métricas scoreadas 0-100 (último run: 100/100) |
| Cliente activo | Hospedaje Los Monges (15 habitaciones) |
| Entorno | GCP VM (e2-small) · SQLite WAL · un comando deploy |
| Phases completadas | 1-6 (v1.4-v1.9) + DB Audit Phase 1 (Postgres-readiness) + Phase 2a (Guests + Buildings) + Phase 2a-ext (birth_date + billing_profiles + guest_vehicles, v1.10.0-dev) + Meal Plan UI sweep (PC selector + mobile UX + capacity guard, v1.10.0-dev) + Phase 2b (Type harmonization, v1.10.0-dev) + Phase 2c (Multi-vehicle per reservation, v1.10.0-dev) + **Phase 2d (Multi-currency MVP, v1.10.0-dev)** |
| Próxima migración | `018_*.py` |
| AI tools | 20 (último: `buscar_vehiculo` — Phase 2c extiende el lookup para encontrar quick-add vehicles vía `reservation_vehicles`) |
| Tablas | 30 (suma `accepted_currencies` desde Phase 2d) |

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

## Phase 2b — Type harmonization + retention · ✅ COMPLETADA en v1.10.0-dev

Implementada via migraciones 014 + 015 + script `scripts/cleanup_retention.py` (commit pendiente). Ver entrada Phase 2b en CHANGELOG.md para detalle. Resumen ejecutado:
- ✅ **27 columnas Boolean-as-Integer → Boolean** (cobertura mayor que el "14" estimado originalmente — incluye los 14 `AIAgentPermission.can_*` que se activaron en v1.9.0 + las 13 catalog/config).
- ✅ **5 columnas JSON-in-String → `Column(JSON)`** (`reservations.price_breakdown`, `room_categories.bed_configuration`/`amenities`, `pricing_seasons.applies_to_categories`, `price_calculations.calculation_details`).
- ✅ **`properties.breakfast_included` REMOVED** via SQLite 3.35+ native `DROP COLUMN`. API contract preservado: el field `breakfast_included` en `/settings/property-settings` se deriva de `meals_enabled && mode=='INCLUIDO'`.
- ✅ **8 `property_id` columnas restantes promovidas a FK** real (`room_categories`, `rooms`, `reservations`, `system_settings`, `client_types`, `client_contracts`, `pricing_seasons`, `price_calculations`). Option A — model-only, audit confirmó 0 orphans.
- ✅ **`Property.slug` backfilled + promovido a NOT NULL**.
- ✅ **`checkins.created_at` Date → DateTime** (captura hora de ingreso).
- ✅ **`scripts/cleanup_retention.py`** — idempotente, dry-run capable, configurable. Documentado en CLAUDE.md como periodic maintenance task.
- Tests: 19 nuevos en `test_type_harmonization.py`, total **752 tests**, 0 regresiones.

Próximo slot: `016_*.py`. Ready para tag v1.10.0 final.

## Phase 3+ — PostgreSQL cutover (después de Phase 2b)

- Capa de conexión: `DATABASE_URL` env var, support para `postgresql://...` además de `sqlite:///`.
- Adopción de Alembic (reemplaza `scripts/migrations/NNN_*.py` + `migration_history` table → `alembic/versions/` + `alembic_version`).
- Backup system rewrite — Postgres usa `pg_dump`, no copy de archivo. Reescribir `backup_manager.py`.
- Cutover playbook: dump SQLite → restore en Postgres staging → smoke tests → cutover prod en ventana de mantenimiento.

## Phase 6.5 — Reporting avanzado (post-PostgreSQL)

Suite de reportes financieros y operativos que se benefician de las features de Postgres (`date_trunc`, window functions, GROUP BY con CUBE/ROLLUP, JSONB indexes). Hoy se pueden hacer en SQLite pero las queries serían menos performantes y más verbosas. Implementar después del cutover (Phase 3+ / Postgres).

**Desglose de caja por categoría de ingreso**:
- Habitaciones vs Productos/Consumos vs Desayunos (Plan de comidas surcharge).
- Vistas diaria, semanal, mensual, anual.
- Comparativa year-over-year.
- Source de los datos: `transaccion` + breakdown del `reservation.price_breakdown` (ya es JSONB en Postgres → query-able directo).

**Analytics de desayunos**:
- % de habitaciones con desayuno vs sin desayuno por noche.
- Promedio de pax desayuno por día / mes.
- Tendencia por temporada (alta vs baja).
- Planificación de compra de insumos basada en pax forecast (cross-reference con calendario de reservas futuras).
- Source: `KitchenReportService.get_daily_report` extendido + `pricing_seasons` para detectar temporada.

**Reporting de productos**:
- Ranking top N productos más vendidos (ya existe `ProductService.get_top_selling`, falta la vista PC con CSV export + filtros de fecha).
- Ingresos por categoría (BEBIDA, SNACK, SERVICIO, MINIBAR, OTRO) — diario/mensual/anual.
- Tendencias mensuales / estacionales.
- Productos con stock bajo recurrente (para optimizar `stock_minimum`).

**KPIs hoteleros operativos** (RevPAR / ADR forecast):
- Revenue Per Available Room (`RevPAR`) — revenue total / room_nights disponibles.
- Average Daily Rate (`ADR`) — revenue de habitaciones / room_nights vendidas.
- Forecast 30/60/90 días basado en reservas futuras + histórico de pickup.
- Heatmap de demanda por día de la semana / mes.

**UI**:
- Nueva página PC `92_📊_Reportes_Avanzados.py` con tabs (Caja / Cocina / Productos / KPIs).
- CSV + PDF export por cada tab.
- Charts con `st.line_chart` / `st.bar_chart` (no dependencia extra).
- Filtros de fecha persistentes en `st.session_state`.

**Dependencia**: Postgres (las queries en SQLite serían 10x más verbosas con CTEs).

## Backlog (sin prioridad asignada)

Ideas documentadas para no perderlas. **No tienen estimación ni fecha.**

- **OCR de chapas en la entrada** (Phase 2a-ext follow-up — premium feature): cámara IP en la entrada del hotel lee la chapa de cualquier vehículo que llega. El sistema:
  1. Recibe la chapa via webhook/API del proveedor de OCR (e.g. OpenALPR, AWS Rekognition, Plate Recognizer).
  2. Llama `GuestVehicleService.search_by_plate(property_id, plate)`.
  3. Si hay match con reserva activa o próxima → push notification a recepción: "Llegando: [Apellido, Nombre], reserva #[id], habitación [X], check-in [fecha]".
  4. Si no hay match → log en panel "Vehículos no identificados" para que recepción pueda asociar manualmente al check-in que se haga después.
  - Dependencias: hardware (cámara con visión IP en la entrada), proveedor de OCR (≈ USD 0.001-0.01 por lectura según volumen), webhook receptor en el backend.
  - Tabla `guest_vehicles` ya está lista (Phase 2a-ext) con el index `idx_vehicle_property_plate` para hacer el lookup en O(log n).
- **Saludo de cumpleaños automático** (Phase 2a-ext follow-up): scheduled job diario que:
  1. Query: guests donde `MONTH(birth_date) = MONTH(today) AND DAY(birth_date) = DAY(today) AND is_active = true`.
  2. Para cada uno: si tiene reserva activa, mandar email + WhatsApp con saludo personalizado.
  3. Opcional: auto-aplicar un descuento o consumo complementario (caja de bombones, copa de vino) vía `ConsumoService`.
  - Tabla ya tiene `birth_date` en `guests` (Phase 2a-ext). Falta el job + plantilla de mensaje + integración con WhatsApp Business API.
- **De-dup / merge tool de huéspedes** (Phase 2a follow-up): UI admin para detectar candidatos (nombre similar, mismo phone, etc.) y mergear dos rows en uno. Reasigna `reservations.guest_id` y `checkins.guest_id` al canónico, soft-deletea el otro. Útil porque la entrada manual + auto-creación generan duplicados con tiempo.
- **Mostrar meal plan en mobile reservation detail** (Meal Plan UI sweep follow-up — flageado durante visual verification de v1.10.0-dev): el endpoint `/api/v1/reservations/{id}` ya devuelve `meal_plan_id`, `meal_plan_code`, `meal_plan_name` y `breakfast_guests`, pero `frontend_mobile/app/dashboard/calendar/[id]/page.tsx` no los renderiza. Operadores en mobile no pueden ver si una reserva incluye desayuno. Cross-platform parity gap: el PC `tab_reserva.py` sí pre-fillea esta info en modo edit. Agregar mini-sección "🍽️ Plan de comidas" entre Huésped y Folio. Conditional al `getMealsConfig().meals_enabled`. Reusa el patrón de gating del nuevo-reserva form (líneas 531-575).
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
