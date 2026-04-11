# 🏨 Hospedaje Los Monges PMS (Property Management System)

Un sistema de gestión hotelera (PMS) on-premise diseñado para alta disponibilidad local, seguridad de datos y automatización mediante IA.

---

## 🚀 Características Técnicas Destacadas

Este proyecto implementa prácticas de **Ingeniería de Software** y **DevSecOps** para garantizar robustez en un entorno local:

### 🏗️ Arquitectura y Diseño

- **Monorepo Multi-Frontend:** Arquitectura con un backend centralizado y dos frontends especializados (PC y Mobile).
- **API REST Versionada:** FastAPI con endpoints organizados por dominio (`/api/v1/`).
- **Motor de Precios Dinámico:** Sistema avanzado de pricing por Categoría, Temporada y Tipo de Cliente.
- **Layered Architecture:** Separación estricta entre API, Servicios y Datos.
- **Modelo de Datos Relacional:** SQLite con integridad referencial.
- **Concurrencia Optimista:** SQLite en **WAL Mode** (Write-Ahead Logging) y `scoped_session` para múltiples usuarios simultáneos.
- **Índices Optimizados:** Índices en columnas frecuentemente consultadas (status, fechas, room_id).
- **Constantes Centralizadas:** Single source of truth para tokens y URLs en frontend mobile.
- **API Paginada:** Endpoints `/rooms`, `/guests`, `/reservations` soportan `skip` y `limit`.

### 🛡️ Seguridad y Robustez (Hardening)

- **Autenticación JWT:** Tokens seguros con `python-jose` y hashing con `bcrypt`.
- **Gestión de Secretos:** Credenciales aisladas mediante variables de entorno (`.env`).
- **CORS Hardening:** Whitelist explícita de orígenes (sin wildcards).
- **Endpoints Protegidos:** Todos los endpoints sensibles requieren autenticación.
- **Validación Estricta:** Uso de **Pydantic Schemas** para validar reglas de negocio.
- **Rate Limiting:** Protección contra fuerza bruta (5 req/min en login).
- **RBAC:** Control de acceso basado en roles (`require_role()`) en endpoints administrativos.
- **Revocación JWT:** Invalidación de sesiones en tiempo real (password reset, eliminación de usuario).
- **Sanitización de Errores:** Mensajes genéricos al cliente, detalles internos solo en logs del servidor.
- **Global Exception Handler:** Safety net para errores no manejados (HTTP 500).
- **Vision Hardening:** Límite de 5MB y timeout de 30s en endpoint de OCR.
- **Observabilidad:** Sistema de **Logging Rotativo** para auditoría sin saturar disco.

### 🤖 Inteligencia Artificial

- **Agente IA con 14 Herramientas:** Asistente inteligente con function calling automático (Gemini 2.5 Flash). Consulta disponibilidad, tarifas, cotizaciones, ocupación mensual, rendimiento por habitación, fuentes de reserva, estacionamiento, ingresos financieros, estado de caja y más.
- **OCR Documental:** Extracción automática de datos de documentos usando Google Gemini 2.5 Flash.
- **Retry con Backoff Exponencial:** Reintentos automáticos ante errores transitorios de la API (429, 503).

### 💰 Gestión Financiera (v1.4.0)

- **Sistema de Caja (Cash Register):** Apertura/cierre de sesiones por usuario con reconciliación declarado vs esperado.
- **Transacciones Inmutables:** Pagos registrados como EFECTIVO, TRANSFERENCIA o POS — con referencias bancarias/voucher. Solo se pueden anular (voided=True con razón obligatoria), nunca modificar o eliminar.
- **Ciclo de vida de Reservas basado en Pagos:** Los estados `RESERVADA → SEÑADA → CONFIRMADA → COMPLETADA` se calculan automáticamente a partir de la suma de pagos vs el total de la reserva. Permite registrar señas y pagos parciales.
- **Reportes Financieros:** Ingresos del día por método, lista de transferencias para conciliación bancaria (con CSV export), resumen por período agrupado por método de pago.
- **RBAC:** Solo admin/supervisor pueden ver todas las sesiones; recepción ve solo las propias; anulación requiere razón auditada.

### 🔄 Resiliencia y Recuperacion

- **Hot Backups:** Copias de seguridad en caliente usando la API nativa de SQLite.
- **Admin API:** Endpoints protegidos para gestion remota (backups, logs, system-info).
- **Staging Environment:** Script de provisionamiento GCP (`scripts/setup_gcp_staging.sh`).
- **Linux Service Manager:** Control de servicios systemd para despliegue en Linux (`scripts/service_control_linux.sh`).
- **Acceso Remoto:** VPN mesh con Tailscale para acceso SSH seguro sin port forwarding.

### 🔗 Integraciones OTA (Booking.com / Airbnb)

- **Importacion:** Pull automatico de feeds .ics cada 15 minutos.
- **Exportacion:** Endpoints publicos `.ics` para que OTAs consulten disponibilidad.
- **Admin:** UI de configuracion en pagina Configuracion (PC).
- **Fuentes soportadas:** Booking.com, Airbnb, WhatsApp, Facebook, Instagram, Google.

### 🧪 Testing

```bash
cd backend
python -m pytest tests/ -v
```

- **369 tests** con **83% coverage** en 27 archivos de test.
- Cubre: auth, reservas, huespedes, habitaciones, pricing, calendario, iCal, settings, usuarios, schemas, seguridad, integridad de DB, **KPIs (9 métricas)**, **performance benchmarks**, **agent tool reliability**, **caja & transacciones (56 tests nuevos)**.
- SQLite in-memory con `StaticPool` (thread-safe para FastAPI).
- **CI automático** en GitHub Actions: tests + coverage (75% min) + KPI evaluations + perf benchmarks.

---

## 📂 Estructura del Proyecto

```
hotel_munich/
├── backend/                    # API REST (FastAPI + SQLAlchemy)
│   ├── api/
│   │   ├── core/              # config.py (app settings), security.py (JWT/bcrypt)
│   │   ├── deps.py            # Auth dependencies + RBAC (require_role)
│   │   ├── main.py            # App + CORS + lifespan (iCal auto-sync cada 15min)
│   │   └── v1/endpoints/      # Endpoints por dominio
│   │       ├── admin.py       # Gestion remota (backups, logs, system-info)
│   │       ├── agent.py       # Agente IA con herramientas
│   │       ├── ai_tools.py    # 11 herramientas IA (Gemini function calling)
│   │       ├── auth.py        # Autenticacion JWT
│   │       ├── calendar.py    # Eventos de calendario
│   │       ├── guests.py      # Gestion de huespedes / check-in
│   │       ├── ical.py        # Sync iCal (Booking.com / Airbnb)
│   │       ├── pricing.py     # Motor de precios y cotizaciones
│   │       ├── reservations.py# Reservas
│   │       ├── rooms.py       # Habitaciones
│   │       ├── settings.py    # Configuracion hotel
│   │       ├── users.py       # Administracion de usuarios
│   │       └── vision.py      # OCR con Gemini
│   ├── database.py            # Capa de datos (SQLAlchemy, 14 modelos)
│   ├── schemas.py             # DTOs y validaciones (Pydantic)
│   ├── services/              # Logica de negocio (paquete, 8 modulos)
│   │   ├── __init__.py        # Re-exports para compatibilidad
│   │   ├── _base.py           # @with_db decorator (hibrido Streamlit/FastAPI)
│   │   ├── auth_service.py    # Autenticacion y sesiones
│   │   ├── reservation_service.py # Reservas y disponibilidad
│   │   ├── guest_service.py   # Huespedes y check-in
│   │   ├── room_service.py    # Habitaciones y categorias
│   │   ├── pricing_service.py # Motor de precios
│   │   ├── settings_service.py# Configuracion del hotel
│   │   └── ical_service.py    # Import/export iCal para OTAs
│   ├── tests/                 # 313 tests (pytest + SQLite in-memory)
│   │   ├── conftest.py        # Fixtures (StaticPool, test client, auth, SessionLocal patching)
│   │   └── test_*.py          # 24 archivos de test
│   ├── logging_config.py      # Configuracion de logging
│   ├── backup_manager.py      # Sistema de backups
│   └── requirements.txt       # Dependencias Python
│
├── frontend_pc/               # Interfaz Desktop (Streamlit)
│   ├── app.py                 # Orquestador (116 LOC) — login, sidebar, tabs
│   ├── api_client.py          # Cliente HTTP para backend
│   ├── components/            # Modulos de UI
│   │   ├── tab_calendario.py  # Vistas de calendario
│   │   ├── tab_reserva.py     # Formulario de reserva (multi-categoria)
│   │   └── tab_checkin.py     # Formulario de check-in
│   ├── helpers/               # Utilidades compartidas
│   ├── pages/
│   │   ├── 04_Asistente_IA.py     # Chat con agente IA
│   │   ├── 09_Configuracion.py    # Settings + admin iCal feeds
│   │   ├── 98_Admin_Habitaciones.py # Inventario + Ficha Mensual + Revenue Heatmap
│   │   └── 99_Admin_Users.py      # Gestion de usuarios
│   └── requirements.txt       # Dependencias Streamlit
│
├── frontend_mobile/           # Interfaz Mobile-First (Next.js 16 + React 19)
│   ├── app/
│   │   ├── login/             # Autenticacion
│   │   └── dashboard/         # Panel principal
│   │       ├── availability/  # Disponibilidad por rango de fechas
│   │       ├── calendar/      # Calendario visual mensual
│   │       ├── chat/          # Chat con agente IA
│   │       └── reservations/new/ # Nueva reserva (orquestador + 4 componentes)
│   ├── src/
│   │   ├── constants/keys.ts  # API_BASE_URL, tokens
│   │   ├── services/          # rooms, pricing, auth, reservations, vision, chat, settings
│   │   └── hooks/             # useAuth, useBeaconLogout
│   └── package.json           # Dependencias Node.js
│
├── scripts/                   # Deployment, migracion y operaciones
│   ├── deploy.py              # Deployment automatizado con rollback
│   ├── deploy_staging.sh      # Deploy a GCP staging (push + SSH + restart)
│   ├── seed_monges.py         # Datos iniciales (propiedad, habitaciones, categorias)
│   ├── seed_client_types.py   # Seed tipos de cliente (idempotente)
│   ├── seed_test_data.py      # Generador de datos de prueba
│   ├── run_migrations.py      # Ejecuta migraciones de esquema
│   ├── reset_local_db.py      # Reset DB local para desarrollo
│   ├── service_control.bat    # Control de servicios Windows
│   ├── service_control_linux.sh # Control de servicios Linux (systemd)
│   ├── setup_gcp_staging.sh   # Provisioning VM en GCP
│   ├── setup_gcp_staging.md   # Guia de staging GCP
│   └── setup_tailscale.md     # Guia de acceso remoto via VPN
│
├── README.md
└── REQUIREMENTS.md             # Requisitos de negocio
```

---

## 🛠️ Instalación y Despliegue

### 1. Clonar el repositorio

```bash
git clone https://github.com/diegojarav/sistema-hotel-m.git
cd sistema-hotel-m
```

### 2. Configurar Backend

```bash
cd backend

# Crear entorno virtual (recomendado)
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con GOOGLE_API_KEY y SECRET_KEY
```

### 3. Configurar Frontend PC (Streamlit)

```bash
cd frontend_pc

# Usar el mismo entorno o crear uno nuevo
pip install -r requirements.txt
```

### 4. Configurar Frontend Mobile (Next.js)

```bash
cd frontend_mobile

# Instalar dependencias Node.js
npm install

# Configurar API URL
cp .env.local.example .env.local
# Editar con la URL del backend
```

### 5. Ejecutar

#### Opción A: Scripts de Windows

```bash
# Desde la raíz del proyecto
.\start_backend.bat   # Inicia FastAPI en puerto 8000
.\start_pc.bat        # Inicia Streamlit en puerto 8501
```

Para el frontend mobile:
```bash
cd frontend_mobile
npm run dev           # Inicia Next.js en puerto 3000
```

#### Opción B: Comandos manuales

```bash
# Terminal 1: Backend
cd backend
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Frontend PC
cd frontend_pc
streamlit run app.py --server.address 0.0.0.0

# Terminal 3: Frontend Mobile
cd frontend_mobile
npm run dev
```

---

## 🔐 Credenciales de Acceso (Por Defecto)

La primera vez que inicies el sistema, se crearán estos usuarios automáticamente:

| Rol               | Usuario            | Contraseña |
|-------------------|--------------------|------------|
| **Administrador** | `admin`            | `1234`     |
| **Recepción**     | `recepcion`        | `1234`     |
| **Sistema (IA)**  | `system_chat_bot`  | (interno)  |

> ⚠️ **Nota:** Cambia las contraseñas en producción.

---

## 📊 Stack Tecnológico

| Componente | Tecnología |
|------------|------------|
| **Backend API** | FastAPI + SQLAlchemy + Pydantic |
| **Base de Datos** | SQLite (WAL Mode) |
| **Autenticación** | JWT (python-jose) + bcrypt |
| **Frontend PC** | Streamlit 1.51+ |
| **Frontend Mobile** | Next.js 16 + React 19 + TypeScript |
| **Estilos Mobile** | TailwindCSS 4 |
| **IA/OCR** | Google Gemini 2.5 Flash (google-genai SDK) |
| **Agente IA** | google-genai SDK + automatic function calling |
| **Logging** | RotatingFileHandler + Discord webhooks |
| **CI/CD** | GitHub Actions + GCP staging deploy |
| **Monitoreo** | Healthchecks.io (uptime) + Discord (errores) |

---

## 📱 Funcionalidades

### Frontend PC (Streamlit)
- 📅 **Calendario de Ocupacion:** Vista mensual y semanal con estado de habitaciones.
- 📊 **Ficha Mensual:** Vista Gantt de ocupacion room x day con estadisticas (fuentes de reserva, tendencia de ocupacion, estacionamiento).
- 📈 **Revenue Heatmap:** Mapa de calor room x month con totales anuales.
- 🔗 **Vinculacion Reserva-Checkin:** Escaneo OCR de documentos crea check-in vinculado automaticamente.
- ⚙️ **Configuracion iCal:** CRUD de feeds, sync manual/masivo, URLs de exportacion.
- 👤 **Gestion de Usuarios:** CRUD completo con roles y auditoria.
- 💬 **Asistente IA:** Chat interno para consultas operativas.

### Frontend Mobile (Next.js)
- 📱 **Diseno Mobile-First:** Optimizado para tablets y celulares.
- 📊 **Dashboard:** Resumen de ocupacion del dia.
- 📅 **Calendario:** Navegacion mensual con indicadores visuales.
- 📝 **Nueva Reserva:** Formulario con seleccion multi-categoria y multiples habitaciones.
- 📋 **Datos de Identidad:** Captura de documento, nacionalidad y fecha de nacimiento.
- 💬 **Chat IA:** Interfaz conversacional con el agente.
- 🔍 **Disponibilidad:** Busqueda rapida por rango de fechas.

### API Backend
- 🔑 **Autenticacion:** Login, tokens JWT, refresh, revocacion.
- 🏠 **Habitaciones:** CRUD y estado de ocupacion por rango de fechas.
- 📅 **Reservas:** Creacion, edicion, cancelacion con prevencion de overbooking.
- 👥 **Huespedes:** Registro, busqueda y vinculacion con reservas.
- 🔄 **iCal Sync:** Importacion/exportacion iCal para Booking.com y Airbnb (auto-sync cada 15 min).
- 🛠️ **Admin Remoto:** Backups, logs, deploy log, system info via API protegida.
- 🤖 **Agente IA:** Consultas en lenguaje natural.
- 📷 **OCR Vision:** Extraccion de datos de documentos.
- 💰 **Pricing Engine:** Calculo automatico de tarifas por categoria, temporada y tipo de cliente.
- 🚗 **Control Operativo:** Registro de Estacionamiento (Chapa/Modelo) y Origen de Reserva.
- 🧪 **313 Tests:** Suite de tests con **83% coverage** (pytest, SQLite in-memory, CI automático).

---

## ⚠️ Solución de Problemas

| Problema | Solución |
|----------|----------|
| "No encuentra la API Key" | Verifica que `.env` exista en `/backend` con `GOOGLE_API_KEY` |
| "Database is locked" | El sistema usa WAL mode, reiniciar si persiste |
| "CORS error en mobile" | Verificar que backend esté corriendo y URL en `.env.local` |
| "401 Unauthorized" | Token expirado, re-autenticar desde login |
| "No module named bcrypt" | `pip install bcrypt` en el entorno correcto |

---

## 📝 API Endpoints

Documentación interactiva disponible en:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

---

**Version:** 1.3.0
**Last Updated:** 2026-04-06

**Desarrollado por Diego para Hospedaje Los Monges.**