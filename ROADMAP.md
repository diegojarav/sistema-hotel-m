# Roadmap — Hotel Munich PMS

> Planificación activa del proyecto.
> Para historia de versiones → ver [CHANGELOG.md](CHANGELOG.md)
> Para instrucciones operativas → ver [CLAUDE.md](CLAUDE.md)

---

## Estado actual

| Item | Estado |
|---|---|
| Versión | v1.8.0 |
| Tests | 539 · 83% cobertura |
| KPIs | 9 métricas scoreadas 0-100 (último run: 100/100) |
| Cliente activo | Hospedaje Los Monges (15 habitaciones) |
| Entorno | GCP VM (e2-small) · SQLite WAL · un comando deploy |
| Phases completadas | 1 (Caja) · 2 (OTA Channel Manager v2) · 3 (Inventario) · 4 (Meal plans) · 5 (Email) |
| Próxima migración | `007_*.py` |

---

## Próximas features (priorizadas)

### Feature 1 — Control granular de herramientas IA por rol

**Por qué**: la tabla `AIAgentPermission` existe en `backend/database.py:512` como andamio intencional desde etapas tempranas del proyecto. El modelo ya tiene 13 columnas de permisos (can_view_reservations, can_modify_reservations, can_view_reports, can_export_data, etc.) pero **no tiene servicio, ni endpoints, ni middleware activo**. La idea original era que Recepcion no pueda consultar reportes financieros completos a través del agente IA, mientras que Admin sí.

**Scope**:
- `AIAgentPermissionService` con CRUD por rol y por property
- Endpoints `GET/PUT /api/v1/admin/ai-permissions` para configurar desde UI
- Middleware en `agent.py` que filtre el `TOOLS_LIST` antes de pasarlo a Gemini, según el rol del usuario autenticado
- Página PC nueva (sugerido: `93_🤖_Permisos_IA.py`) con tabla rol × tool y checkboxes de habilitación
- Migración `007_ai_agent_permissions_activation.py` para seedear permisos default por rol
- Tests: cubrir filtrado del agente cuando un rol intenta usar una tool no permitida (debe responder "no tenés acceso a esa información" en lugar de ejecutar)

**Dependencia**: ninguna · **Complejidad estimada**: media (modelo y andamio ya existen; falta capa de servicio + UI + middleware)

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

### Feature 3 — RoomStatusLog (logging de cambios de estado de habitaciones)

**Por qué**: existe un TODO confirmado en [`backend/api/v1/endpoints/rooms.py:326`](backend/api/v1/endpoints/rooms.py) (`# TODO: Add RoomStatusLog model to database.py and enable logging`). Hoy los cambios de estado quedan registrados en el `room` mismo (campos `status_changed_at`, `status_changed_by`) pero solo se preserva el último — no hay historial. Una tabla dedicada permitiría auditar cuándo, quién y por qué una habitación pasó de disponible a ocupada o a mantenimiento.

**Scope**:
- Modelo `RoomStatusLog` en `database.py` (id, room_id FK, old_status, new_status, reason, changed_by FK users, created_at)
- Migración nueva (probablemente `007_` o `008_` según orden con Feature 1)
- Insert automático en el endpoint `PATCH /rooms/{id}/status` actual
- Vista de historial por habitación en PC Admin (sub-tab dentro de Admin Habitaciones)
- Tests: que el log se inserte correctamente y que cambios consecutivos generen N filas

**Dependencia**: ninguna · **Complejidad estimada**: baja (modelo simple, un endpoint nuevo, una vista de tabla)

---

## Decisiones técnicas pendientes

Items identificados en la auditoría del 2026-04-21. No son features ni bugs — son decisiones abiertas que requieren análisis antes de actuar.

### D1 — Qué hacer con `scripts/migrate_monges.py`

**Contexto**: `scripts/migrate_monges.py` es un script legacy que predates el sistema canónico de migraciones (`scripts/migrations/NNN_*.py`). Sigue siendo referenciado en dos lugares:
- [`scripts/seed_monges.py:750`](scripts/seed_monges.py) — mensaje de error que sugiere correr `migrate_monges.py` cuando falta una tabla
- [`frontend_pc/pages/98_🏠_Admin_Habitaciones.py:741`](frontend_pc/pages/98_🏠_Admin_Habitaciones.py) — instrucción de uso al operador

Lectura del header del script confirma que **hace cambios reales de schema** (no es solo seed): "Dynamic property configuration, room categories, dynamic pricing, room status tracking".

**Opciones**:
- A) Portar su lógica al sistema canónico como `007_initial_schema.py` (o el número que toque) y actualizar las dos referencias
- B) Marcarlo como "legacy compatibility — don't run on new installs" si todos los entornos actuales (dev + VM staging) ya tienen el schema aplicado
- C) Eliminar las referencias en página 98 y seed_monges si el flujo ya no aplica al cliente actual

**Requiere**: confirmar si los entornos productivos (VM staging) tienen el schema aplicado y los hoteles nuevos lo necesitarían. Si sí → opción A. Si solo es histórico → opción B.

**Acción**: tomar decisión antes de la próxima migración numerada (la siguiente será `007_*` y conviene clarificar si `migrate_monges.py` queda fuera del sistema o se integra).

---

### D2 — Qué hacer con `verify_mobile_api.py` y `verify_parking.py`

**Contexto**: ambos archivos están en `backend/tests/` pero sin prefijo `test_`, por lo que pytest no los colecta. Lectura de sus primeras líneas confirma:
- `verify_mobile_api.py`: usa `requests` para hitear el API real corriendo (necesita backend en `localhost:8000`). Tiene credenciales hardcoded con comentario `"Adjust if needed"`. Es un **script manual de verificación end-to-end**, no un test automatizado.
- `verify_parking.py`: usa `database.SessionLocal` directo, crea reservas con prefijo "Test%" en la DB real, cleanup al final. Es un **script de smoke test integration** que toca la DB de desarrollo.

**Opciones**:
- A) Mover ambos a `scripts/` con nombres descriptivos (`scripts/verify_mobile_api.py`, `scripts/verify_parking.py`) y actualizarlos para no depender de credenciales hardcoded
- B) Eliminarlos si su función ya está cubierta por los 539 tests automáticos del CI
- C) Reescribirlos como tests pytest reales (renombrar a `test_*` con fixtures de conftest) si vale la pena automatizarlos

**Requiere**: cruzar lo que verifica cada uno contra los tests existentes. Si la lógica ya está cubierta → opción B. Si aporta cobertura única → opción C. Si es debugging puntual → opción A.

**Acción**: revisar antes de la próxima limpieza de directorios; no urgente pero genera ruido al colectar tests.

---

### D3 — Qué hacer con el TODO de `RoomStatusLog`

**Contexto**: el TODO en `rooms.py:326` está abierto desde hace tiempo. La pregunta no es técnica (cómo implementarlo está claro — ver Feature 3) sino de producto: **¿el cliente actual usa o necesita el historial de cambios de estado de habitación?**

**Opciones**:
- A) Implementar (ver Feature 3 arriba) si el cliente lo pide o si se planea ofrecerlo como SaaS
- B) Cerrar como "won't do por ahora" — eliminar el TODO del código y documentar la decisión en CHANGELOG. Los datos del último cambio siguen disponibles en el room mismo
- C) Esperar — dejar el TODO como recordatorio hasta que SaaS lo justifique como feature de auditoría

**Requiere**: confirmar con el operador del hotel si tiene casos de uso reales para auditar cambios de estado (mantenimiento, limpieza, ocupación) o si con la columna actual del room alcanza.

---

## Backlog (sin prioridad asignada)

Ideas documentadas para no perderlas. **No tienen estimación ni fecha.**

- **Sistema de plantillas de email** — continuación de Phase 5. Templates configurables para pre-checkin reminder (X días antes), post-checkout thank-you, recordatorio de pago pendiente. Requiere extender `email_body_template` a múltiples templates por evento.
- **OTA API nativa** — integración directa con Booking.com / Expedia / Airbnb API en lugar de iCal. Elimina el delay de 15 min de polling pero requiere certificación con cada OTA, costos y mantenimiento de credenciales.
- **Notificaciones push mobile** — alertas en el frontend mobile para nueva reserva entrante por OTA, stock bajo, sync failure de un feed iCal. Requiere service worker + suscripción FCM o similar.
- **Portal de huéspedes** — acceso web público (sin login del staff) para que el huésped vea su reserva, modifique datos, haga checkin online y descargue su propio PDF. Implica auth separada (token por reserva) y endpoints públicos.
- **Reportes avanzados / Revenue Management** — dashboard de KPIs de negocio (RevPAR, ADR, ocupación forecast), recomendaciones automáticas de pricing dinámico según demanda histórica, comparativa year-over-year.
- **Subir cobertura de tests 75% → 80%** (TEST-01 del backlog histórico). Las áreas con menor cobertura hoy son los servicios de reportes y las rutas administrativas.
- **PERF-12 — capa de cache Redis** entre el agente IA y los servicios pesados (`get_revenue_summary`, `get_occupancy_for_month`). Hoy los cálculos se hacen on-demand cada vez que el agente los pide.
- **Limpieza de back-compat de status legacy** — los filtros de reserva todavía aceptan ambos sets (`["RESERVADA", "Confirmada", ...]`). Una vez confirmado que no quedan reservas con valores legacy en la DB, simplificar.
- **Migración futura para remover `Property.breakfast_included`** — deprecated desde v1.7. Pendiente de número de migración (probablemente v1.9+).

---

## Visión a mediano plazo

El producto fue diseñado para un caso de uso específico (hotel pequeño-mediano paraguayo, ~15 habitaciones, operación familiar) y ese sigue siendo el sweet spot. La arquitectura — SQLite, hybrid monolith con Streamlit + Next.js, deploy en VM única de GCP — encaja exactamente con esa escala y mantiene los costos operativos bajos (un VM e2-small alcanza para todo el stack).

La dirección natural es **estabilizar al cliente actual** mientras se prepara el sistema para escalar horizontalmente cuando aparezca el cliente #2. Eso significa: mantener la cobertura de tests, mantener los KPIs en 100/100, y completar las features de tenant isolation antes de aceptar un segundo hotel. El umbral técnico documentado para migrar SQLite → PostgreSQL es cliente #3 o >20 usuarios concurrentes simultáneos.

El **agente IA conversacional** es uno de los diferenciadores fuertes — 18 herramientas en español que cubren todas las consultas operativas habituales, sin que el operador necesite memorizar dónde está cada reporte en el menú. La activación de `AIAgentPermission` (Feature 1) lo lleva al siguiente nivel: agente personalizado por rol, con políticas de acceso granulares. Esto es especialmente valioso si el sistema escala a SaaS y diferentes hoteles quieren limitar qué información expone el agente a cada tipo de empleado.

A más corto plazo, la prioridad operativa es cerrar las **decisiones técnicas pendientes (D1/D2/D3)** para limpiar el repo de ambigüedades, y ejecutar los deploys pendientes de v1.7.0 + v1.8.0 cuando el cliente lo apruebe (ambas versiones están listas, validadas con tests, y no rompen nada existente).
