# Changelog — Hotel Munich PMS

> Registro histórico del proyecto. Inmutable hacia el pasado.
> Para instrucciones operativas → ver `CLAUDE.md`
> Para próximos pasos → ver `ROADMAP.md`

## Convención de versiones

- **MAJOR**: cambio de stack o arquitectura que rompe compatibilidad
- **MINOR**: nueva feature completa (una Phase = una versión minor)
- **PATCH**: bugfix, ajuste, migración de datos sin nueva funcionalidad

---

## [v1.10.0] — abril 2026 · DB Audit Phase 1 (Postgres-readiness) + Phase 2a (Guests & Buildings)

> Versión en preparación. Phase 1 + Phase 2a (incluye sub-fixes A–E del Bug #2) ya en `dev`; Phase 2b (type harmonization, retención de tablas append-only, drop de `breakfast_included`) pendiente antes del tag v1.10.0 final.

### Phase 2a Bug #2 — Guest-flow consolidation (single entry point)

QA detectó 2 problemas estructurales en cómo el sistema linkeaba reservas/checkins al master Guest. Las fixes A–E refactorizan los 8 paths divergentes a un único modelo:

#### Fix A — Reservation dropdown ahora viene del master Guest
- `ReservationCreate.guest_id` (Optional[int]): cuando el frontend envía un id explícito (PC + mobile dropdown), el service skip-ea `find_or_create_guest` y usa el match directo. Validación: existe + property_id correcto + activo. Falla → fallback transparente a fuzzy match.
- `GuestService.list_guests_for_dropdown` (NEW): lista compacta optimizada para selectores. Labels limpios (sin parens embebidos — Phase 2a Bug #1 cleanup), ordenados por `total_stays DESC`. Cada item carga `guest_id` para el round-trip.
- `GET /api/v1/huespedes/dropdown` (NEW endpoint, todos los roles operacionales).
- **PC** (`frontend_pc/components/tab_reserva.py`): el selector "A Nombre De" ahora vive **fuera del form** (permite rerender + auto-fill de phone/email al elegir). Botón "🗑️ Limpiar selección" para volver al manual entry. Cache local (`session_state["_guest_dropdown_cache"]`) que se limpia post-submit.
- **Mobile** (`frontend_mobile/.../reservations/new/components/GuestForm.tsx`): autocomplete con debounce 250ms sobre `searchGuests`. Selección popula `formData.guestId` + pre-fill de campos vacíos (apellidos, nombres, documento, teléfono, email). "Limpiar" para volver a manual.
- `frontend_services/cache_service.get_all_guest_names_cached` repointed a `GuestService.list_guests_for_dropdown` — labels ahora vienen del master.
- `CheckInService.get_all_guest_names` sigue existiendo (la usa `tab_checkin.py` para billing profiles), pero ya NO es la fuente del dropdown de reservas.

#### Fix B — Auto-CheckIn (FEAT-LINK-01) hereda `guest_id` de la reserva
- En `ReservationService.create_reservations`, el `CheckIn(...)` inline cuando hay `document_number` ahora setea `guest_id=guest_id_for_booking`. Cierra la asimetría que dejaba checkins con `guest_id=NULL` después de auto-creación.
- También parchea el branch "link existing checkin" (cuando el doc ya existía sin link al guest).

#### Fix C — `update_checkin` propaga al master Guest ("fill empty, never overwrite")
- Helper nuevo `_augment_guest_from_checkin` en `checkin_service.py`. Al actualizar una ficha, walks contact + origen fields. Por cada campo donde el master Guest está vacío Y el checkin tiene valor → fill. Nunca pisa data existente.
- También se agregó persistencia de `contact_phone`/`contact_email` en `update_checkin` (estaban omitidos del SET — bug latente).
- Branch "duplicate doc" en `register_checkin` también augmenta.

#### Fix D — Detección de duplicados en alta manual de huésped
- Página `91_👥_Huespedes.py`: el form "Crear huésped nuevo" ahora hace una probe a `/huespedes/search` antes de insertar. Si encuentra candidatos por documento, apellido o email → muestra warning con la lista de sospechosos + botón "Usar este" por cada uno (selecciona ese huésped y limpia el form pendiente) + botones "Sí, crear de todos modos" / "Cancelar". UI fuera de st.form (botones interactivos no permitidos dentro).

#### Fix E — Ficha de cliente pre-fill desde el master
- `tab_checkin.py` modo "Crear Nuevo" suma una sección "💡 ¿Es un huésped recurrente?" con búsqueda en `GuestService.search_guests`. Cada match muestra meta-info + botón "Pre-llenar" → popula los campos vacíos del form (last_name, first_name, document_number, nationality, country, phone, email). Snapshot pattern preservado: ya re-rellenados se pueden seguir editando.

#### Snapshot freeze (intencional, NO cambiado)
- `ReservationService.update_reservation` NO re-llama `find_or_create_guest`. Editar el `guest_name` de una reserva NO cambia su `guest_id`. El nombre en la reserva es la foto al momento de la booking. Si hay que cambiar de huésped, se cancela y re-bookea. Documentado en CLAUDE.md.

#### Test data
- `scripts/seed_test_guests.py` (NEW): 10 guests con varied data quality (full / no email / OTA-no-doc / phone-only / repeat / special chars / corporate / dup-risk / international / minimal). Materializa 5 reservations + 1 checkin. Idempotente vía `--reset` flag, dry-run con `--dry-run`. Tagged con `[test-seed]` en notes para reset limpio.

#### Tests
- `backend/tests/test_guest_flows.py` (NEW): 20 end-to-end flow tests por path (A/B/C/D/E + 5 edge cases + 2 endpoint tests).
  - `TestFlowA_ExplicitGuestId` (5): explicit id wins, wrong property fallback, inactive fallback, augment from form data, no-guest_id fallback.
  - `TestFlowB_AutoCheckinGuestId` (2): auto-CheckIn inherits, existing checkin gets back-filled.
  - `TestFlowC_UpdateCheckinAugmentsGuest` (3): fills empty phone, doesn't overwrite, duplicate-doc branch augments.
  - `TestFlowD_DuplicateSuspectSearch` (2): finds by lastname, by doc.
  - `TestFlowE_FichaPrefillFromMaster` (1): search returns prefill data.
  - `TestEdgeCases` (5): embedded doc in name, special chars, minimal guest, OTA no-doc, repeat guest 3 reservations same id.
  - `TestDropdownEndpoint` (2): unauth + clean labels with no parens.
- Total backend: **652 tests** (632 prev + 20 new), 0 regresiones.

#### Verification
- 0 duplicate documents among active guests.
- 112/112 reservations linked (100%).
- 53/53 checkins linked (100%).
- 0 active guests with parens in name.
- Mobile `tsc --noEmit` clean, `next build` succeeds.

### Phase 2a Bug #1 — Duplicate guests from migration auto-population

QA caught dos duplicates en el dev DB (Acosta Rosa + Aquino Gabriel) tras Phase 2a inicial. Migration 011 creaba un Guest "limpio" en pass A (desde checkins por documento) y un segundo Guest "sucio" en pass B (desde reservations por nombre) cuando el `guest_name` traía el doc embebido tipo `"Acosta, Rosa (2362693)"`. El name-key lookup no normalizaba parens, así que la dedup fallaba.

#### Cleanup
- Script nuevo `scripts/cleanup_duplicate_guests.py`: descubre clusters por (property + doc_or_extracted_doc), pickea keeper por (clean-name, total_stays DESC, has-doc, oldest), re-linkea reservations + checkins, backfilla campos vacíos del keeper, soft-deletea dupes con audit en `notes`. Idempotente. Dry-run mode disponible.
- Aplicado al dev DB: 2 clusters merged → 5 reservations relinked, 2 dupes deactivated.

#### `find_or_create_guest` mejorado
- Helper `_extract_embedded_doc(name)`: regex `\s*\(([^)]+)\)\s*` extrae paren content, normaliza a digits-only si tiene >=4 dígitos. Limpia el nombre.
- Helper `_norm_ws(s)`: collapse whitespace + trim.
- Helper `_augment_guest_if_empty(db, guest, **fields)`: backfill empty fields on existing guests, never overwrite. Usado tanto por `find_or_create_guest` (en match) como por `_augment_guest_from_checkin` (Bug #2 Fix C).
- Match priority redefinida:
  1. `(property, document)` — STRONGEST (extracted doc también usado)
  2. `(property, email)` — STRONG
  3. `(property, normalized_name)` — WEAK (solo si no hay doc/email)
- Phone YA NO es un match tier (falsos positivos por familia/parejas que comparten teléfono).
- Si se pasa doc explícito y no matchea, NO cae a name match (asumimos: "este es nuevo CON este doc").

#### Bug #3 — Pagination fix (paralelo)
- `91_👥_Huespedes.py`: `st.number_input("Página", ...)` no tenía `max_value`. Agregado: probe del total → `total_pages = ceil(total/page_size)` → `max_value=total_pages`. Defensive auto-reset si el dataset shrink-ea.

### Phase 2a — Master Guest entity + Buildings

#### Qué se agregó
- **Tabla `guests`** (entidad maestra de huésped): un row por persona, persiste a través de múltiples reservas y check-ins. Distinta de `checkins` (registro per-estadía). Schema: `id`, `property_id` FK, `first_name`, `last_name`, `document_type`, `document_number`, `email`, `phone`, `nationality`, `country`, `city`, `notes`, `source`, `is_active`, agregados `total_stays`/`total_spent`/`last_visit_at`, timestamps.
- **Tabla `buildings`** (edificios/anexos): un row por estructura física dentro de una property. Schema: `id`, `property_id` FK, `name`, `description`, `floors`, `sort_order`, `is_active`, timestamps. Único por `(property_id, name)`.
- **Renombrado `GuestService` → `CheckInService`**: la clase original gestionaba CheckIns (fichas) — el nombre quedó libre para la nueva entidad maestra. Archivo `services/guest_service.py` → `services/checkin_service.py`. Todos los imports actualizados (7 archivos: endpoints/guests.py, endpoints/ai_tools.py, frontend_pc/components/tab_reserva.py, tab_checkin.py, frontend_services/cache_service.py, tests/test_feat_link_01.py, tests/test_guest_service.py → `test_checkin_service.py`).
- **`GuestService` nuevo** (entidad maestra): `create_guest`, `get_guest`, `update_guest`, `list_guests`, `count_guests`, `search_guests`, `find_or_create_guest` (smart-match: documento → email → phone → exact name), `get_guest_history`, `refresh_aggregates`. Excepción `GuestServiceError` para violaciones de reglas (mensajes en español).
- **`BuildingService`**: `create_building`, `get_building`, `list_buildings` (con `room_count` agregado), `update_building`. Validaciones de unicidad (`uq_buildings_property_name`).
- **Endpoints nuevos** `/api/v1/huespedes/*` (Spanish path para evitar colisión con el legado `/api/v1/guests/*`):
  - `GET /huespedes/search?q=&limit=` — autocomplete (mín. 2 caracteres)
  - `GET /huespedes` — listado paginado con `total`/`skip`/`limit`
  - `POST /huespedes` — crear (admin / supervisor / gerencia / recepcion / recepcionista)
  - `GET /huespedes/{id}` — detalle
  - `PUT /huespedes/{id}` — actualizar
  - `GET /huespedes/{id}/history` — historial completo + agregados
- **Endpoints nuevos** `/api/v1/buildings/*`: `GET` (todos los roles operacionales), `POST`/`PUT` (admin only).
- **AI tool 19** `buscar_huesped_historial(query)` — busca por nombre/documento/email/teléfono y devuelve historial agregado. Mapeada a `can_view_guests` en `TOOL_PERMISSION_MAP`.
- **`reservations.guest_id`** (Integer FK nullable, SET NULL): cada reserva ahora apunta opcionalmente al Guest maestro. Los snapshots `guest_name`/`contact_email` quedan congelados en la reserva (no se rescriben al editar el Guest).
- **`checkins.guest_id`** (mismo patrón).
- **`rooms.building_id`** promovido de `Column(String)` a FK real con `ondelete=SET NULL`. Migración 012 seedea un "Edificio Principal" por property y backfilla todas las habitaciones.
- **Wire al flujo de reserva**: `ReservationService.create_reservations` ahora resuelve el Guest una vez por booking (vía `find_or_create_guest`) y enlaza `guest_id` en cada reserva creada. Best-effort: si la resolución falla, la reserva sigue sin Guest (no es load-bearing).
- **CheckIn flow**: `CheckInService.register_checkin` también enlaza al Guest maestro (`_try_link_guest`) en cada nueva ficha.
- **UI mobile**: badge "N estadías previas" / "Primera visita" en detalle de reserva (`/dashboard/calendar/[id]`). Tap expande historial inline (estadías, total gastado, promedio, últimas 5 reservas).
- **UI PC**: nueva página `91_👥_Huespedes.py` (búsqueda + listado paginado + detalle editable + tabs Datos/Historial). Botón "Crear huésped nuevo" para entrada manual (la mayoría se autocrean vía reserva/check-in).
- **UI PC**: en `98_🏠_Admin_Habitaciones.py` se agrega un selector "🏢 Filtrar por edificio" arriba de las tabs (visible cuando hay >1 edificio) y un expander "Gestionar edificios" admin-only para CRUD. Tabla de inventario suma columna "Edificio".
- **Mobile services**: nuevo `frontend_mobile/src/services/guests.ts` con `getGuest`, `getGuestHistory`, `searchGuests`. `reservations.ts` extendido con `guest_id` en `ReservationDetail`.
- **Migración 011** (`011_guests_table.py`): crea la tabla, agrega `guest_id` a `reservations` y `checkins`, y autopobla:
  1. Distintos `document_number` de `checkins` → un Guest por documento (señal más fuerte).
  2. Distintos `(property_id, guest_name)` de `reservations` no cubiertos → un Guest por nombre, con split heurístico ("Apellido, Nombre" / "Nombre Apellido" / single token).
  3. Backfill de `reservations.guest_id` y `checkins.guest_id`.
  4. Refresca agregados (`total_stays`, `total_spent`, `last_visit_at`) excluyendo cancelaciones.
  - Resultado en dev DB: 107 reservas + 52 checkins → 96 guests (dedup por nombre + doc), 100% de reservas linkeadas.
- **Migración 012** (`012_buildings_table.py`): crea la tabla, seedea `<property_id>-principal` "Edificio Principal" por property, backfillea `rooms.building_id` donde NULL. Resultado en dev DB: 1 edificio, 15 habitaciones backfilleadas.

#### Bonus items (también en este release)
- **3 FKs lógicas promovidas en `reservations`**: `category_id`, `client_type_id`, `contract_id` ahora declaran `ForeignKey(...)` con `ondelete=SET NULL` en el modelo. Sigue patrón Phase 1 Option A (model-only, enforcement queda para Postgres). Audit confirmó cero orphan rows.
- **`Property.slug` UNIQUE**: marcado en el modelo como prep para SaaS multi-tenant (URL canónica `app.hotel.com/los-monges/`). Backfill de NULLs queda para Phase 2b junto al resto de migraciones de tipo.
- **`backend/migrate_sessions.py` eliminado**: script legacy ya aplicado en todos los DBs conocidos (audit issue #17).
- **`backend/tests/test_db_constraints.py`** (NUEVO): 13 tests que verifican UNIQUE + CHECK + CASCADE/SET NULL declarados en `database.py`. Cubre `meal_plans (property_id, code)`, `system_settings (property_id, setting_key)`, `buildings (property_id, name)`, los 8 CHECK constraints de Phase 1 (rooms.status, caja_sesion.status, transaccion.payment_method, producto.category, ajuste_inventario.reason, email_log.status, ical_feeds.last_sync_status, meal_plans.applies_to_mode), y CASCADE en `room_status_log` + `ical_feeds`, SET NULL en `reservations.meal_plan_id`.

#### Tests
- **78 tests nuevos** (`test_guests.py` 28 + `test_buildings.py` 12 + `test_db_constraints.py` 13 + `test_checkin_service.py` 14 renombrado + 11 ya existentes en `test_feat_link_01.py` actualizados a `CheckInService`).
- Total backend: **590 tests** (no incluye perf/kpi), 0 regresiones.
- KPI suite: 28/28 passing — incluye nueva tool `buscar_huesped_historial` en el conjunto de tools verificadas por `test_tools_return_strings`.

#### Decisiones técnicas destacadas
- **Identity model: auto-ID, sin business-key UNIQUE** (Q1 confirmado). El mismo huésped con dos spelling distintos vive como dos rows hasta que un futuro merge tool los una. Trade-off aceptado: evitamos forzar al recepcionista a pelear con UNIQUE constraints durante un check-in real.
- **Per-tenant scope** (Q1 confirmado): un huésped que se hospeda en Hotel A y Hotel B = dos rows separados. El SaaS futuro será schema-per-tenant, así que reuso cross-hotel no aplica de todos modos.
- **Endpoints en español (`/huespedes/`) vs legacy `/guests/`**: el path `/api/v1/guests/*` ya estaba ocupado por endpoints de CheckIn (mobile + PC dependen). En vez de romper compat, se eligió Spanish path para la entidad nueva — alineado con `91_Huespedes.py` y consistente con `/caja/`, `/transacciones/`, `/reportes/cocina`.
- **`GuestService` no se aliasea a `CheckInService`** en `services/__init__.py`: el nombre `GuestService` ahora pertenece a la entidad maestra. Cualquier import viejo `from services import GuestService` que esperaba CheckIn methods falla en import-time → fácil de detectar y reparar.
- **Snapshot pattern preservado**: `reservations.guest_name`, `reservations.contact_email`, `checkins.last_name` siguen como valores frozen-at-creation. El Guest es la versión "viva". Mismo patrón que `consumo.producto_name + unit_price`.

### Phase 1 — Postgres-readiness (commit `61dda6e`)
- 19 ForeignKey `ondelete=` declarations agregadas a `database.py` (RESTRICT para datos financieros/audit, CASCADE para config/log, SET NULL para datos independientes).
- 7 CHECK constraints declarados en `__table_args__` (rooms.status, caja_sesion.status, transaccion.payment_method, producto.category, ajuste_inventario.reason, email_log.status, ical_feeds.last_sync_status, meal_plans.applies_to_mode).
- 6 índices compuestos para hot queries (idx_email_log_reserva_status_sent, idx_transaccion_reserva_voided, idx_consumo_reserva_voided, idx_room_status_log_room_changed, idx_ajuste_producto_created, idx_producto_property_active).
- 3 UNIQUE constraints expresados como `UniqueConstraint` (meal_plans, system_settings, ai_agent_permissions) + 1 nuevo `MigrationHistory` model.
- `email_log.sent_by` String → Integer FK to `users.id` (migración 009 con table-rebuild dance).
- `PRAGMA foreign_keys=ON` activado en `set_sqlite_pragma` listener.
- Migración 010 con UNIQUE + composite indexes (idempotente).

---

## [v1.9.0] — abril 2026 · Cleanup + Features 1 & 3

### Cleanup
- **D1 cerrado** — eliminado `scripts/migrate_monges.py` (731 LOC). Era 100% schema bootstrap, 0% seeding, completamente reemplazable por `database.init_db()` (Base.metadata.create_all). Actualizadas las 2 referencias UI: `seed_monges.py:750` y `frontend_pc/pages/98_🏠_Admin_Habitaciones.py:741` ahora apuntan al flujo canónico (`scripts/run_migrations.py`).
- **D2 cerrado** — movidos `verify_mobile_api.py` y `verify_parking.py` de `backend/tests/` a `scripts/` (no eran tests automatizados sino scripts manuales de smoke/E2E). Fix de sys.path en `verify_parking.py`.
- **D3 cerrado** — TODO de RoomStatusLog implementado (ver Feature 3 abajo).
- Comentario stale en `database.py:347` actualizado: "Remove in v1.8" → "Removal tracked in ROADMAP.md (backlog)".

### Feature 3 — RoomStatusLog (audit trail de estados de habitación)
- Tabla nueva `room_status_log` (append-only): `id`, `room_id` FK, `previous_status`, `new_status`, `changed_by` (username), `reason`, `changed_at`. Indexes en `(room_id)` y `(changed_at)`.
- Modelo `RoomStatusLog` agregado a `backend/database.py` (junto a las demás tablas v1.x).
- Migración `007_room_status_log.py` aplicada. La migración detecta y limpia la tabla phantom dejada por `migrate_monges.py` antes de crear la nueva (el schema legacy tenía `property_id` y `changed_by_type`, sin `previous_status` — incompatible).
- Endpoint nuevo `PATCH /api/v1/rooms/{id}/status` ahora inserta automáticamente una fila por cada cambio (admin/supervisor).
- Endpoint nuevo `GET /api/v1/rooms/{id}/status-log?limit=N` (admin/supervisor/recepcion/recepcionista/gerencia). Devuelve historial DESC por `changed_at`.
- TODO en `rooms.py:326` removido.
- UI PC: nuevo expander "📋 Historial de cambios de estado" en `98_🏠_Admin_Habitaciones.py` debajo del botón Eliminar. Tabla con Fecha, Estado anterior, Estado nuevo, Usuario, Motivo.
- Tests: `test_room_status_log.py` con 10 casos (write-on-change, captura previous/changed_by, GET listado/orden/limit/404/RBAC/unauth).

### Feature 1 — AIAgentPermission activation (control granular de tools IA por rol)
- La tabla `AIAgentPermission` (definida en `database.py:512` desde versiones tempranas) deja de ser andamio y pasa a estar activa.
- Servicio nuevo `backend/services/ai_agent_permission_service.py` con: `get_or_create`, `list_all`, `update_permissions` (con safety check anti-lockout para admin/supervisor/gerencia), `get_allowed_tools`.
- Mapeo `TOOL_PERMISSION_MAP` que asocia cada una de las 18 tools del agente a una de 5 columnas de permisos (`can_view_reservations`, `can_view_guests`, `can_view_rooms`, `can_view_prices`, `can_view_reports`). Las otras 9 columnas booleanas quedan reservadas para futuros tools de modificación.
- Middleware `filter_tools_for_role()` en `backend/api/v1/endpoints/agent.py` filtra `TOOLS_LIST` antes de pasarlo a Gemini según el rol del JWT. Cuando una tool está bloqueada, Gemini simplemente no la conoce → responde naturalmente "no tengo herramienta para esa consulta".
- 4 endpoints nuevos en `backend/api/v1/endpoints/admin.py` (todos admin-only):
  - `GET /api/v1/admin/ai-permissions` — listado con seed automático
  - `GET /api/v1/admin/ai-permissions/{role}` — detalle por rol
  - `PUT /api/v1/admin/ai-permissions/{role}` — partial update
  - `GET /api/v1/admin/ai-permissions/{role}/allowed-tools` — diagnóstico (devuelve también `tool_permission_map`)
- Migración `008_ai_agent_permissions_activation.py` seedea defaults por rol (admin/supervisor/gerencia=all-true, recepcion/recepcionista=view-only sin reports, cocina=all-false).
- UI PC: nueva página `93_🤖_Permisos_IA.py` (admin-only) con expander por rol, checkboxes con tooltip mostrando qué tools controla cada permiso, partial-update por diff, panel de referencia agrupado por permiso.
- Schemas: `AIAgentPermissionDTO` + `AIAgentPermissionUpdate` en `backend/schemas.py`.
- Tests: `test_ai_agent_permissions.py` con 27 casos (defaults por rol, normalización, get_allowed_tools, partial updates, safety anti-lockout, RBAC en endpoints, list/get/put endpoints, diagnostic endpoint, middleware filtering).

### Tests
- 37 tests nuevos (10 RoomStatusLog + 27 AIAgentPermission).
- Total backend: **576 tests**, 0 regresiones, 83% cobertura.

### Tech debt cerrada
- T2: TODO RoomStatusLog implementado.
- O1: `migrate_monges.py` eliminado.
- O5: `verify_*.py` reclasificados como scripts manuales.

### Decisión técnica destacada
- **Tabla phantom de `migrate_monges.py`**: el script legacy creaba `room_status_log` con un schema incompatible (TEXT room_id + property_id + changed_by_type, sin previous_status) que ningún código usaba. La migración 007 detecta esta tabla legacy y la dropea antes de crear la nueva — sin pérdida de datos (la phantom nunca tuvo INSERTs).
- **Tools sin gating son siempre permitidas**: el middleware tiene defensive default — si una tool nueva se agrega a `TOOLS_LIST` y se olvida agregar al `TOOL_PERMISSION_MAP`, queda accesible para todos los roles. Más fácil detectar "esta tool aparece para todos" que "los recepcionistas no pueden hacer X" después de un deploy.
- **Safety anti-lockout en `update_permissions`**: admin/supervisor/gerencia no pueden quedar con TODOS los permisos en false (bloquearía el agente para roles de gestión). Otros roles sí pueden ser totalmente bloqueados (caso cocina).

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
| T2 | TODO `RoomStatusLog` en `backend/api/v1/endpoints/rooms.py:326` | Baja | ✅ Cerrada en v1.9.0 (Feature 3 implementada) |
| O1 | `scripts/migrate_monges.py` legacy referenciado por `scripts/seed_monges.py:750` y `frontend_pc/pages/98_🏠_Admin_Habitaciones.py:741` | Media | ✅ Cerrada en v1.9.0 (script eliminado, refs actualizadas) |
| O5 | `backend/tests/verify_mobile_api.py` y `backend/tests/verify_parking.py` están en `tests/` sin prefijo `test_` | Baja | ✅ Cerrada en v1.9.0 (movidos a `scripts/`) |
