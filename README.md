# Hotel Munich PMS

Sistema de gestión hotelera (PMS) desarrollado para hoteles pequeños y medianos en Paraguay. Incluye gestión de reservas, caja, inventario, planes de comida, sincronización con OTAs y envío de documentos por email.

**Versión**: v1.8.0 · **Estado**: en producción (cliente activo — Hospedaje Los Monges)

---

## Stack tecnológico

| Capa | Tecnología | Versión |
|---|---|---|
| Backend | FastAPI | ≥ 0.109 |
| Base de datos | SQLite (WAL mode) | 3.35+ |
| ORM | SQLAlchemy + Pydantic v2 | — |
| Admin PC | Streamlit | ≥ 1.51 |
| Mobile / Web | Next.js + React + TypeScript | 16.1 / 19.2 |
| Estilos mobile | Tailwind CSS | 4 |
| Auth | JWT (`python-jose`) + bcrypt | — |
| Encripción | `cryptography.fernet` (PBKDF2 desde SECRET_KEY) | ≥ 42.0 |
| IA conversacional | Google Gemini 2.5 Flash | — |
| Generación PDF | `fpdf2` | ≥ 2.8 |
| Rate limiting | `slowapi` | ≥ 0.1.9 |
| CI/CD | GitHub Actions | — |
| Deploy | GCP VM (e2-small, Ubuntu 22.04) | — |
| Monitoring | Discord webhooks + Healthchecks.io | — |

---

## Funcionalidades principales

**Reservas**. Ciclo de vida completo con cinco estados auto-derivados de los pagos: `RESERVADA → SEÑADA → CONFIRMADA → COMPLETADA / CANCELADA`. El estado se recalcula automáticamente cada vez que se registra o anula un pago. Soporta selección multi-categoría (varias habitaciones de tipos distintos en una misma reserva), cálculo dinámico de precio por temporada y tipo de cliente, override manual de temporada para eventos puntuales, y vinculación con check-in vía OCR de documento.

**Caja y pagos**. Sistema de sesiones de caja por usuario con apertura/cierre y reconciliación entre el saldo declarado y el esperado. Tres métodos de pago (efectivo / transferencia / POS) con referencia bancaria o voucher. Las transacciones son inmutables: solo se pueden anular con razón obligatoria, nunca modificar. Los pagos en efectivo requieren caja abierta; transferencia y POS no.

**Inventario y consumos**. Catálogo de productos vendibles a habitación (bebidas, snacks, servicios, minibar) con stock y stock mínimo. Cada consumo cargado a una reserva captura snapshot de precio y nombre del producto al momento del cargo (preserva auditoría histórica si los datos cambian después). Al pasar la reserva a `COMPLETADA` se genera automáticamente el folio del huésped (PDF) con todos los cargos itemizados, pagos y saldo.

**Planes de comida**. Configuración opcional por hotel — los hoteles que no sirven comida no ven nada de meal plans. Tres modos cuando está habilitado: incluido en la tarifa, opcional con recargo por persona, opcional con recargo por habitación. Incluye página dedicada para el rol `cocina` (read-only) con date picker (default mañana), métricas, tabla detallada y export CSV/PDF.

**Channel Manager (OTA sync)**. Sincronización vía iCal con cinco fuentes: Booking.com, Airbnb, Vrbo, Expedia y Custom (cualquier `.ics`). Pull automático cada 15 minutos. Detección de cancelaciones cuando un UID desaparece del feed (la reserva se marca para revisión y el operador decide). Detección y log de overbooking entre OTAs. Health monitoring por feed con badges visuales y alertas Discord si hay 3 o más fallos consecutivos. Endpoint público `.ics` para que las OTAs hagan pull de los datos del hotel.

**Documentos y email**. Generación automática de PDFs en español al crear cada reserva, cada check-in y cada folio (al checkout). Configuración SMTP por hotel (admin la edita desde la UI; password se almacena encriptado con Fernet derivado de `SECRET_KEY`). Envío del PDF de confirmación al huésped con un click, asíncrono (response inmediato + send en background). Rate limit de 3 envíos por hora por reserva (cuenta solo envíos exitosos). Historial completo de envíos con filtros y export CSV.

**Agente IA**. Asistente conversacional con 18 herramientas en español usando Google Gemini 2.5 Flash con automatic function calling. Responde preguntas operativas como "¿hay habitaciones disponibles para mañana?", "¿cuánto se facturó hoy?", "¿se le mandó el correo a la reserva 1234?", "¿qué planes de desayuno tiene Juan Pérez para el lunes?". También extrae datos de documentos (cédula, pasaporte) vía OCR.

**Reportes**. Ingresos del día por método de pago, lista de transferencias para conciliación bancaria (con CSV export), resumen por período, ocupación mensual, distribución por canal, ficha mensual estilo Gantt por habitación, mapa de calor de ingresos por habitación × mes, productos más vendidos, stock bajo, reporte diario de cocina.

---

## Arquitectura

```
┌──────────────────────────────────────────────────────────────────┐
│                        FastAPI Backend                            │
│                                                                   │
│   22 endpoint modules · ~120 routes · 22 SQLite tables           │
│   18 AI tools · auto-backups · WAL mode · iCal sync background   │
│                                                                   │
└──────────┬─────────────────────────────────┬─────────────────────┘
           │                                 │
   import directo                       HTTP / JWT
   (PYTHONPATH=backend/)                     │
           │                                 │
   ┌───────▼────────┐                ┌───────▼────────┐
   │   Streamlit    │                │   Next.js 16   │
   │   PC Admin     │                │   Mobile App   │
   │                │                │                │
   │   8 páginas    │                │   11 rutas     │
   │   (caja,       │                │   (calendar,   │
   │    inventario, │                │    reservas,   │
   │    cocina,     │                │    caja,       │
   │    docs, ...)  │                │    chat IA,    │
   │                │                │    meals, ...) │
   └────────────────┘                └────────────────┘
```

**Hybrid Monolith**: el frontend PC corre en la misma máquina que el backend e importa los servicios Python directamente (decorator `@with_db` autodetecta si la sesión la inyecta FastAPI o si la maneja Streamlit). El frontend mobile usa la API REST estándar con JWT. Esta arquitectura elimina latencia de red local en el admin pero requiere que ambos compartan el mismo Python env (PYTHONPATH=backend/).

---

## Requisitos del sistema

- Python 3.11+ (CI corre en 3.11; desarrollo local usa 3.12+)
- Node.js 20+ (requerido por Next.js 16)
- SQLite 3.35+ (incluido con Python)
- gcloud CLI (solo si se va a deployar a GCP)

---

## Instalación y setup

### 1. Clonar el repositorio

```bash
git clone https://github.com/diegojarav/sistema-hotel-m.git
cd sistema-hotel-m
```

### 2. Backend (FastAPI)

```bash
cd backend
python -m venv venv
venv\Scripts\activate         # Windows
# source venv/bin/activate    # Linux/Mac

pip install -r requirements.txt

cp .env.example .env
# Editar .env: GOOGLE_API_KEY, JWT_SECRET_KEY, DISCORD_WEBHOOK_URL (opcional)
```

### 3. Frontend PC (Streamlit)

Comparte el Python env del backend o crea uno separado:

```bash
cd ../frontend_pc
pip install -r requirements.txt
```

### 4. Frontend Mobile (Next.js)

```bash
cd ../frontend_mobile
npm install
cp .env.local.example .env.local   # apunta NEXT_PUBLIC_API_URL al backend
```

### 5. Base de datos

```bash
cd ..
python scripts/run_migrations.py    # aplica todas las migraciones pendientes
python scripts/seed_monges.py       # datos iniciales (hotel, habitaciones, usuarios)
```

### 6. Levantar los 3 servicios

Opción A — script todo en uno (Windows):

```bash
start_all.bat
```

Opción B — manual, una terminal cada uno:

```bash
# Terminal 1 — Backend
cd backend && python -m uvicorn api.main:app --reload --port 8000

# Terminal 2 — Frontend PC
cd frontend_pc && streamlit run app.py --server.port 8501

# Terminal 3 — Frontend Mobile
cd frontend_mobile && npm run dev
```

URLs por defecto: API en `http://localhost:8000` (Swagger en `/docs`), PC en `http://localhost:8501`, mobile en `http://localhost:3000`.

---

## Credenciales de demo

| Usuario | Contraseña | Rol |
|---|---|---|
| `admin` | `1234` | Administrador |
| `recepcion` | `1234` | Recepcionista |

> Estas credenciales son exclusivas del entorno de demo del repositorio público. En producción se cambian al primer arranque.

---

## Tests

**539 tests automatizados · 83% cobertura · CI corre en cada push a `main` y `dev`.**

```bash
cd backend
pytest                                          # todos los tests
pytest --cov=services --cov=api                 # con reporte de cobertura
pytest -m kpi                                   # solo KPIs (9 métricas scoreadas 0-100)
pytest -m perf                                  # solo benchmarks de performance
```

El CI de GitHub Actions corre los 539 tests + 9 KPIs + 19 benchmarks de performance + build del frontend mobile + falla si la cobertura cae bajo 75%. Las fallas notifican por Discord.

---

## Estructura del proyecto

```
sistema-hotel-m/
├── backend/                    # FastAPI + SQLAlchemy + servicios
│   ├── api/                    # routers + auth + config
│   │   └── v1/endpoints/       # 22 módulos de endpoints
│   ├── services/               # 15 servicios de negocio
│   ├── tests/                  # 539 tests + KPIs + perf
│   ├── database.py             # 22 modelos SQLAlchemy
│   ├── schemas.py              # validación Pydantic v2
│   ├── hotel/                  # PDFs generados (gitignored)
│   └── requirements.txt
│
├── frontend_pc/                # Streamlit admin desktop
│   ├── app.py                  # entry + login
│   ├── components/             # tabs reusables
│   ├── pages/                  # 8 páginas multipage
│   └── requirements.txt
│
├── frontend_mobile/            # Next.js 16 + React 19
│   ├── app/                    # rutas (App Router)
│   │   └── dashboard/          # calendar, reservas, caja, meals, chat...
│   ├── src/
│   │   ├── components/         # modales y componentes UI
│   │   └── services/           # cliente HTTP por dominio
│   └── package.json
│
├── scripts/
│   ├── migrations/             # migraciones numeradas (006 actuales)
│   ├── deploy_staging.sh       # deploy one-command a GCP
│   ├── seed_monges.py          # datos iniciales
│   └── run_migrations.py       # runner idempotente
│
├── .github/workflows/ci.yml    # tests + build + Discord alerts
├── CLAUDE.md                   # instrucciones operativas internas
├── CHANGELOG.md                # historial de versiones
└── README.md                   # este archivo
```

---

## Documentación adicional

- [`CHANGELOG.md`](CHANGELOG.md) — historial completo de versiones, decisiones arquitecturales y deuda técnica conocida
- [`CLAUDE.md`](CLAUDE.md) — instrucciones operativas internas (convenciones, gotchas, patrones de código)
- Swagger UI auto-generado: `http://localhost:8000/docs`

---

## Changelog

Ver [CHANGELOG.md](CHANGELOG.md) para el historial completo.

**Últimas versiones:**

- **v1.8.0** — Email sending (envío del PDF de reserva al huésped, configuración SMTP encriptada, AI tool 18, historial de envíos con filtros)
- **v1.7.0** — Meal plans y reportes de cocina (3 modos de servicio + rol `cocina` + página dedicada)
- **v1.6.0** — Inventario y consumos por habitación (catálogo, stock tracking, folio del huésped al checkout)
- **v1.5.0** — Channel Manager v2 (5 fuentes OTA, detección de cancelaciones, health monitoring por feed)
- **v1.4.0** — Caja y sistema de pagos (sesiones, transacciones inmutables, status auto-derivado de pagos)

---

## Licencia y contacto

Desarrollado por Diego Jara para Hospedaje Los Monges (Paraguay).
