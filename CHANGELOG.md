# Changelog — Hotel Munich PMS

> Registro histórico del proyecto. Inmutable hacia el pasado.
> Para instrucciones operativas → ver `CLAUDE.md`
> Para próximos pasos → ver `ROADMAP.md`

## Convención de versiones

- **MAJOR**: cambio de stack o arquitectura que rompe compatibilidad
- **MINOR**: nueva feature completa (una Phase = una versión minor)
- **PATCH**: bugfix, ajuste, migración de datos sin nueva funcionalidad

---

## [v1.8.0] — abril 2026 · Phase 5 — Email Sending

### Qué se agregó
- Envío del PDF de confirmación de reserva por email al huésped, configurable desde la UI del hotel.
- Configuración SMTP por hotel (host, port, user, password, from_name, from_email, toggle enabled, body template) editable por Admin desde `09_🔧_Configuracion.py`.
- AI tool 18 `estado_email_reserva(query)` para que el agente conversacional pueda responder "¿se envió el correo a la reserva X?".
- Tab "📧 Historial de Emails" en `97_📄_Documentos_Hotel.py` con filtros por fecha y estado, exportable a CSV.
- Botón "📧 Enviar por correo" en detalle de reserva (PC modo edición + mobile detail) con modal `EnviarEmailModal` y feedback inline (toast verde/rojo + caption "Último envío: ...").

### Qué se modificó
- `services/__init__.py` exporta `EmailService` y `EmailError`.
- `api/main.py` registra el nuevo router `/api/v1/email`.
- `api/v1/endpoints/settings.py` extendido con 3 endpoints `/email/*`.
- `api/v1/endpoints/ai_tools.py` suma `estado_email_reserva` al `TOOLS_LIST`.
- `services/settings_service.py` extendido con `get_smtp_config(include_password)` y `set_smtp_config(...)` (encripta/desencripta automáticamente).
- `api/core/security.py` suma helpers `encrypt_secret`/`decrypt_secret` con Fernet derivado de `SECRET_KEY` via PBKDF2HMAC-SHA256 (200k iterations, salt fijo).

### Base de datos
- Tabla nueva `email_log` (id, reserva_id FK, recipient_email, subject, status ENVIADO|FALLIDO|PENDIENTE, error_message, sent_at, sent_by FK users, created_at) — append-only, con índices en reserva_id, status, sent_at.
- Tabla `system_settings` reutilizada para SMTP config (key/value): `smtp_host`, `smtp_port`, `smtp_username`, `smtp_password_encrypted`, `smtp_from_name`, `smtp_from_email`, `smtp_enabled`, `email_body_template`.
- Migración aplicada: `006_email_log.py`.

### Tests
- 29 tests nuevos en `test_email.py` (encryption roundtrip, render_body, rate_limit, prepare_send validations, send_async mocked SMTP, endpoints integration, RBAC).
- Total backend: 539 tests, 83% coverage. KPI 100/100, perf benchmarks dentro de thresholds.

### Decisión técnica destacada
- **Encripción simétrica del SMTP password en DB**: se evaluó guardar las credenciales en `.env` (modelo single-tenant simple) vs encriptarlas en DB (admin las edita desde UI). Se eligió encriptar con Fernet derivado de `SECRET_KEY` para permitir edición por UI sin SSH. Trade-off aceptado: rotar `SECRET_KEY` invalida los passwords almacenados (admin debe re-ingresar).
- **Rate limit cuenta solo `ENVIADO` exitosos** (no PENDIENTE ni FALLIDO): permite al admin debuggear SMTP sin auto-bloqueo de la reserva.
- **PDF se regenera siempre** antes de enviar (no se reusa cache): evita enviar datos obsoletos si la reserva fue editada después de la primera generación.

---

## [v1.7.0] — abril 2026 · Phase 4 — Meal Plan Configuration & Kitchen Reports

### Qué se agregó
- Configuración opcional de servicio de comidas por hotel: hoteles que no sirven comida no ven NADA de meal plans (zero-regression gate).
- 3 modos cuando habilitado: `INCLUIDO` (incluido en tarifa), `OPCIONAL_PERSONA` (recargo por persona), `OPCIONAL_HABITACION` (recargo por habitación).
- Página nueva PC `94_👨‍🍳_Cocina.py` (date picker, métricas, tabla, CSV + PDF export).
- Página nueva mobile `/dashboard/meals` (read-only, toggle Hoy/Mañana).
- Rol nuevo `cocina` (read-only, solo accede a `/api/v1/reportes/cocina*`).
- AI tool 17 `reporte_cocina(fecha)`.

### Base de datos
- Tabla nueva `meal_plans` (catalog: code, name, surcharges, applies_to_mode, is_system, sort_order). Unique `(property_id, code)`.
- `properties` extendida con `meals_enabled` (default 0) + `meal_inclusion_mode` (nullable). Legacy `breakfast_included` mantenido para back-compat.
- `reservations` extendida con `meal_plan_id` (FK nullable) + `breakfast_guests` (Integer nullable).
- Migración aplicada: `005_meal_plans.py` (incluye backfill `breakfast_included=1 → meals_enabled=1, mode=INCLUIDO` + seed `SOLO_HABITACION` para todas las properties).

### Tests
- 44 tests nuevos (`test_meal_config.py`, `test_meal_plan_crud.py`, `test_meal_plan_pricing.py`, `test_kitchen_report.py`, `test_cocina_role.py`).
- Total backend al cierre: 510 tests.

### Decisión técnica destacada
- **Zero-regression gate**: hoteles que no sirven comida no deben ver ningún cambio en su UI. Cada componente mobile que muestra meal info debe verificar `getMealsConfig().meals_enabled` antes de renderizar.
- **Lógica de fecha del reporte de cocina = night-of-(D-1)**: un huésped que hace check-in el día D NO desayuna ese día, pero el que hace check-out el día D SÍ desayunó esa mañana. La query lo encoda; no re-implementar.
- **System plans no son borrables**: `MealPlanService.soft_delete` lanza error si `is_system=1`. Para ocultar uno, set `is_active=0` via update.

---

## [v1.6.0] — abril 2026 · Phase 3 — Room Charges & Product Inventory

### Qué se agregó
- Catálogo de productos vendibles a habitación (BEBIDA / SNACK / SERVICIO / MINIBAR / OTRO) con stock tracking y stock mínimo.
- Sistema de consumos (cargos a la habitación) — inmutables, con snapshot de precio y nombre del producto al momento del cargo.
- Folio del Huésped: PDF auto-generado al pasar reserva a `COMPLETADA` con todos los cargos itemizados, pagos y saldo. Guardado en `hotel/Cuentas/`.
- Página nueva PC `95_📦_Inventario.py` con 4 tabs (Productos, Stock y ajustes, Stock bajo, Más vendidos).
- Modal mobile `RegistrarConsumoModal` con selector grouped-by-category + qty stepper + warnings de stock bajo.
- Alertas Discord automáticas cuando un producto llega a stock mínimo o por debajo.
- AI tools 15 (`consultar_inventario`) y 16 (`consumos_habitacion`).

### Base de datos
- Tabla nueva `producto` (catálogo).
- Tabla nueva `consumo` (line items por reserva, voided-only).
- Tabla nueva `ajuste_inventario` (audit trail de cambios de stock: COMPRA / MERMA / AJUSTE).
- Migración aplicada: `003_inventario_v3.py`.

### Tests
- 54 tests nuevos (`test_product_service.py`, `test_consumo_service.py`, `test_consumo_api.py`).

### Decisión técnica destacada
- **Snapshot de precio al momento del cargo**: si el precio del producto cambia o el producto se renombra, los consumos históricos preservan el dato original. Permite auditoría correcta sin migrar registros viejos.
- **Recálculo automático de status de reserva** después de cada consumo: si un nuevo consumo crea saldo pendiente, una reserva CONFIRMADA puede degradarse a SEÑADA.

---

## [v1.5.0] — abril 2026 · Phase 2 — Channel Manager v2

### Qué se agregó
- Soporte de 5 fuentes iCal: Booking.com, Airbnb, Vrbo, Expedia, Custom (cualquier .ics URL).
- Detección automática de cancelaciones desde feeds OTA: cuando un UID desaparece, la reserva se marca `needs_review=True` y se dispara alerta Discord (operador decide acknowledge o confirmar cancelación).
- Detección de conflictos de overbooking entre OTAs (logged + counted, pero la reserva OTA se crea porque OTA es autoritativa).
- Health monitoring por feed: badges 🟢/🟡/🔴/⚪ en UI, `consecutive_failures` con escalado a Discord ≥3.
- Audit trail `ical_sync_log` (per-attempt: counts, error_message, duration_ms).
- Rate limiting en endpoints públicos `.ics` (60/min per IP por habitación, 30/min para `all.ics`).
- Página mobile `/dashboard/channels` (read-only) + tile en dashboard.

### Base de datos
- `ical_feeds` extendida con `last_sync_status`, `last_sync_error`, `consecutive_failures`, `last_sync_attempted_at`.
- Tabla nueva `ical_sync_log` (pruned a últimas 100 por feed).
- `reservations` extendida con `ota_booking_id`, `needs_review`, `review_reason`.
- Migración aplicada: `002_ical_v2.py`.

### Tests
- 43 tests nuevos (`test_ical_v2_api.py`, `test_ical_cancellation_sync.py`, `test_ical_conflicts.py`, `test_ical_error_tracking.py`, `test_ical_sync_log.py`).

### Decisión técnica destacada
- **Cancelaciones OTA: flag for review, no auto-cancel**. Cuando un UID desaparece del feed puede ser cancelación real o glitch transitorio. El sistema marca la reserva para revisión y deja la decisión final al operador. Si el UID reaparece en sync siguiente, el flag se auto-clearea.

---

## [v1.4.0] — abril 2026 · Phase 1 — Cash Register & Transactions

### Qué se agregó
- Sistema de caja (cash register): apertura/cierre de sesión por usuario, reconciliación declarado vs esperado.
- Transacciones inmutables (EFECTIVO / TRANSFERENCIA / POS) con referencia bancaria/voucher. Solo se pueden anular (con razón obligatoria), nunca modificar.
- Ciclo de vida de reservas auto-derivado de pagos: 5 estados (RESERVADA → SEÑADA → CONFIRMADA → COMPLETADA / CANCELADA) calculados de la suma de pagos vs total.
- Reportes financieros: ingresos del día por método, lista de transferencias para conciliación bancaria (con CSV export), resumen por período.
- Página PC `96_💰_Caja.py` (Sesión Actual / Historial / Reportes).
- Página mobile `/dashboard/caja` + componente `RegistrarPagoModal` en detalle de reserva.
- AI tools 13 (`consultar_caja`) y 14 (`resumen_ingresos_por_metodo`).

### Qué se modificó
- Reservation status pasó de 4 valores legacy a 5 valores nuevos manteniendo back-compat (filtros usan listas `.in_()` con ambos sets).

### Base de datos
- Tabla nueva `caja_sesion` (opening_balance, closing_balance_declared/expected, difference, status ABIERTA|CERRADA).
- Tabla nueva `transaccion` (immutable, voided field, FK a reserva + caja_sesion).
- Migración aplicada: `001_caja_transacciones.py` (también renombra valores legacy + crea transacciones TRANSFERENCIA sintéticas para CONFIRMADA históricas).

### Tests
- 56 tests nuevos (`test_caja_service.py`, `test_caja_api.py`, `test_transaccion_service.py`).

### Decisión técnica destacada
- **Status de reserva derivado, no asignado**: el status se recalcula desde transacciones en cada cambio (`TransaccionService._recalcular_status_reserva`). Elimina la posibilidad de status inconsistente con los pagos.
- **EFECTIVO requiere caja abierta** (TRANSFERENCIA y POS no): garantiza que todo el dinero físico que entra al hotel queda asociado a una sesión que se cierra con reconciliación.

---

## [v1.3.0] — abril 2026 (baseline pre-phases)

### Qué se agregó
- Migración `004_contact_email_backfill.py` — agrega columna `contact_email` a `reservations` y `checkins`. Necesaria porque el dev DB y el VM DB divergieron schema.
- Manual season override: optional `season_id` en `PriceCalculationRequest` para forzar temporada (útil en eventos puntuales como conciertos).
- Endpoint `GET /pricing/seasons` + `SeasonSelector` mobile + `st.selectbox` PC.

### Qué se modificó
- README + CLAUDE.md publicados como v1.3.0 (último update 2026-04-06).

### Base de datos
- Migración `004_contact_email_backfill.py` aplicada.

### Tests
- ~313 tests al cierre (pre-Phase 1).

### Decisión técnica destacada
- **Sistema canónico de migraciones numeradas**: introducción de `scripts/migrations/NNN_*.py` con `run_migrations.py` runner que tracking en tabla `migration_history`. Reemplaza el patrón ad-hoc de `migrate_*.py` legacy en `scripts/` (esos quedan solo como seed-only).

---

## [v1.0.0 → v1.2.0] — enero a marzo 2026 (fundación)

### v1.0.0 — Núcleo del PMS (enero 30, 2026)
- Database (SQLAlchemy), Backend (FastAPI), Frontend PC (Streamlit), Frontend Mobile (Next.js).
- Auth JWT + bcrypt.
- CRUD básico de reservas, huéspedes, habitaciones, check-ins.
- Sistema de pricing con client types, seasons, contracts (enero 31).

### v1.1.0 — Hardening de seguridad y arquitectura (febrero 2026)
- **Seguridad**: CORS whitelist, RBAC con `require_role()`, JWT revocation, error sanitization, security headers middleware, rate limiting (slowapi).
- **Arquitectura**: split de god files (`services.py` 1379 LOC → 8 módulos; `app.py` 1400 LOC → orchestrator 116 LOC + components/helpers; mobile `page.tsx` 750 LOC → orchestrator 286 LOC + 4 componentes).
- **Performance**: N+1 query fix (PERF-001), date bounds (PERF-002), 6 índices DB (PERF-006), pagination (PERF-004), occupancy SQL optimization (PERF-003), shared `requests.Session` para PC (PERF-10), removed `time.sleep()` (PERF-11), Gemini timeout 30s + límite 5MB (PERF-08-10).
- **Bugfixes mayores**: BUG-PRICING-01/02 (currency field, db param), BUG-SESSION-01 (scoped_session concurrency en FastAPI), BUG-CORS-01 (middleware ordering), BUG-OVERBOOKING-01 (date-range overlap check), BUG-ROOMNAME-01/02 (UIs muestran `internal_code`).
- **iCal sync**: import/export `.ics` con Booking/Airbnb, auto-sync background cada 15 min via FastAPI lifespan.
- **Theme migration**: dark glassmorphism → light theme (white bg + black text) en 13 archivos mobile + 2 PC.
- **Mobile y PC features**: multi-category room selection, light theme, time picker arrival, property settings endpoint, source dropdowns expandidos (Facebook, Instagram, Google).

### v1.2.0 — Pre-deployment ready (febrero 23 a marzo 17, 2026)
- **Test suite consolidada**: 313 tests, 83% coverage, StaticPool fix para SQLite + FastAPI threading.
- **KPI framework**: 9 KPIs scored 0-100 (Booking Integrity, Occupancy Accuracy, Pricing Accuracy, API Response Time, Data Consistency, Calendar Sync, Revenue Accuracy, Security Compliance, Agent Tool Reliability).
- **Performance benchmarks**: 7 benchmark classes, 19 tests con thresholds.
- **CI/CD**: GitHub Actions con coverage 75% min, KPI + perf steps, artifact upload, Discord alerts on failure.
- **Two-repo architecture**: público (`sistema-hotel-m`, deployment-only) + privado (`hotel-PMS-dev`, full code). Dual push URL.
- **GCP staging**: VM `hotel-munich-staging` (e2-small, southamerica-east1-a) provisionada. Tailscale VPN para acceso remoto. Linux systemd service manager.
- **Deploy automation**: `scripts/deploy_staging.sh` (one-command), `scripts/run_migrations.py` (numbered migrations), `scripts/seed_test_data.py` (80-100 reservas de prueba), `scripts/reset_local_db.py`.
- **Monitoring stack**: Discord webhook (runtime + CI), Healthchecks.io (uptime ping cada 15 min).
- **Document generation**: `DocumentService` con `fpdf2`, auto-genera PDFs de reserva y check-in. API `/documents/*` con regeneración on-demand y path traversal protection. Mobile fetch+blob download. Streamlit document browser.
- **Smart Reservation ↔ Check-in linking**: document scan en "Nueva Reserva" auto-crea CheckIn vinculado. Mobile incluye 6 identity fields.
- **Visualization**: Monthly room sheet (Gantt-style), source distribution chart, occupancy trend, parking utilization, revenue heatmap.
- **Status final v1.2.0**: 313 tests passing, 28/28 KPIs (100/100), 19/19 perf benchmarks, full monitoring stack activo. Auditoría: 88/90 findings resueltos.

---

## Decisiones arquitecturales

Decisiones de diseño que aplican a todo el proyecto, no a una versión específica.

### SQLite sobre PostgreSQL
**Contexto**: PMS para un hotel chico (Hospedaje Los Monges, ~15 habitaciones, <10 usuarios concurrentes).
**Decisión**: SQLite en modo WAL como motor único.
**Trade-off aceptado**: cero overhead de servidor de DB, backup = copiar 1 archivo. Migration trigger documentado: cliente #3 o >20 usuarios concurrentes simultáneos requiere migrar a PostgreSQL.

### Dos frontends — Streamlit (PC) + Next.js (mobile)
**Contexto**: el hotel necesita una UI desktop para administración interna (reception desk, admin) y una UI mobile-first para huéspedes y operaciones de recepción móvil.
**Decisión**: Streamlit para el PC admin (Python puro, cero curva de aprendizaje frontend, deploy local), Next.js para el mobile (SSR, TypeScript, SaaS-ready si en algún momento se exponen partes públicamente).
**Trade-off aceptado**: dos stacks de UI que mantener. Streamlit no escala más allá de ~10 usuarios concurrentes (revisar si supera ese umbral).

### WAL mode en SQLite
**Contexto**: backend FastAPI con threadpool + Streamlit accediendo a la misma DB en paralelo. SQLite por default usa journaling rollback que serializa lecturas y escrituras.
**Decisión**: habilitar Write-Ahead Logging (WAL).
**Trade-off aceptado**: lecturas concurrentes con escrituras (sin bloqueo); el archivo `hotel.db-wal` aparece junto al `hotel.db`.

### iCal sobre API directa de OTAs (Booking, Airbnb, Vrbo, Expedia)
**Contexto**: sincronización de reservas con plataformas externas. Las APIs directas (Booking Connect, Airbnb Partner) requieren acuerdos de partnership, certificación, y costos.
**Decisión**: iCal `.ics` (estándar abierto, soportado por todas las OTAs) con sync pull cada 15 min para import + export endpoint público para que las OTAs hagan pull de los datos del hotel.
**Trade-off aceptado**: latencia de hasta 15 min entre booking en OTA y aparición en el PMS (vs webhook real-time de las APIs nativas). Suficiente para un hotel chico, no requiere certificaciones ni costos.

### Hybrid Monolith — Frontend PC importa el backend directo
**Contexto**: el PC corre en la misma máquina que el backend. La opción "limpia" sería que el PC use HTTP igual que el mobile, pero eso agrega latencia de red local.
**Decisión**: el PC importa `services.*` directo via `PYTHONPATH=backend/`. Decorator `@with_db` autodetecta si está bajo FastAPI (sesión inyectada) o Streamlit (gestiona sesión propia).
**Trade-off aceptado**: el backend y el PC comparten el mismo Python env (deben tener las mismas deps instaladas — gotcha conocido con `cryptography` post-Phase 5). El PC no funciona si se quiere desplegar separado del backend (escenario no necesario).

### FastAPI sobre Django/Flask
**Contexto**: Razón no documentada — inferida de la arquitectura. FastAPI es la elección moderna para APIs REST en Python: validación automática con Pydantic, OpenAPI docs auto-generadas, async-friendly, type hints nativos, performance similar a Node.

### Gemini sobre OpenAI / Claude
**Contexto**: Razón no documentada — inferida. Gemini 2.5 Flash tiene tier free generoso, soporta function calling automático nativo (sin tener que parsear `tool_use` manualmente), y la integración via `google-genai` SDK es directa.

---

## Deuda técnica conocida

Items identificados en la auditoría del 2026-04-21 (informe del Senior Software Architect).

| ID | Descripción | Severidad | Estado |
|---|---|---|---|
| T2 | TODO `RoomStatusLog` en `backend/api/v1/endpoints/rooms.py:326` — feature de logging dormida (modelo planificado, no implementado) | Baja | Pendiente análisis |
| O1 | `scripts/migrate_monges.py` legacy referenciado por `scripts/seed_monges.py:750` y `frontend_pc/pages/98_🏠_Admin_Habitaciones.py:741`. Convive con el sistema canónico `scripts/migrations/NNN_*.py` | Media | Pendiente análisis |
| O5 | `backend/tests/verify_mobile_api.py` y `backend/tests/verify_parking.py` están en `tests/` pero sin prefijo `test_` — pytest no los colecta. Intención poco clara: ¿scripts manuales o tests rotos? | Baja | Pendiente análisis |
