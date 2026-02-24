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

- **Agente IA Interno:** Asistente con herramientas para consultar disponibilidad, tarifas y resúmenes.
- **OCR Documental:** Extracción automática de datos de documentos usando Google Gemini 2.5 Flash.

### 🔄 Resiliencia y Recuperación

- **Hot Backups:** Copias de seguridad en caliente usando la API nativa de SQLite.
- **Infraestructura como Código (IaC):** Script `install_backup_task.bat` para tareas programadas en Windows.

---

## 📂 Estructura del Proyecto

```
hotel_munich/
├── backend/                    # API REST (FastAPI + SQLAlchemy)
│   ├── api/
│   │   ├── core/              # Configuración y seguridad
│   │   ├── deps.py            # Dependencias de inyección
│   │   ├── main.py            # Punto de entrada FastAPI
│   │   └── v1/endpoints/      # Endpoints por dominio
│   │       ├── agent.py       # Agente IA con herramientas
│   │       ├── ai_tools.py    # Herramientas LangChain
│   │       ├── auth.py        # Autenticación JWT
│   │       ├── calendar.py    # Eventos de calendario
│   │       ├── guests.py      # Gestión de huéspedes
│   │       ├── reservations.py# Reservas
│   │       ├── rooms.py       # Habitaciones
│   │       ├── settings.py    # Configuración hotel
│   │       ├── pricing.py     # Motor de precios y cotizaciones
│   │       └── vision.py      # OCR con Gemini
│   ├── database.py            # Capa de datos (SQLAlchemy)
│   ├── schemas.py             # DTOs y validaciones (Pydantic)
│   ├── services.py            # Lógica de negocio
│   ├── logging_config.py      # Configuración de logging
│   ├── backup_manager.py      # Sistema de backups
│   └── requirements.txt       # Dependencias Python
│
├── frontend_pc/               # Interfaz Desktop (Streamlit)
│   ├── app.py                 # Aplicación principal
│   ├── api_client.py          # Cliente HTTP para backend
│   ├── pages/
│   │   ├── 04_💬_Asistente_IA.py   # Chat con agente IA
│   │   └── 99_👤_Admin_Users.py    # Gestión de usuarios
│   └── requirements.txt       # Dependencias Streamlit
│
├── frontend_mobile/           # Interfaz Mobile-First (Next.js)
│   ├── app/
│   │   ├── login/             # Autenticación
│   │   └── dashboard/         # Panel principal
│   │       ├── availability/  # Disponibilidad
│   │       ├── calendar/      # Calendario visual
│   │       ├── chat/          # Chat con agente IA
│   │       └── reservations/  # Nueva reserva
│   ├── src/                   # Componentes y utilidades
│   └── package.json           # Dependencias Node.js
│
├── logs/                      # Archivos de log (auto-generado)
├── start_backend.bat          # Launcher: Backend API
├── start_pc.bat               # Launcher: Streamlit PC
└── install_backup_task.bat    # Instalador de tarea programada
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
| **Agente IA** | LangChain Tools |
| **Logging** | RotatingFileHandler |

---

## 📱 Funcionalidades

### Frontend PC (Streamlit)
- 📅 **Calendario de Ocupación:** Vista mensual y semanal con estado de habitaciones.
- 👤 **Gestión de Usuarios:** CRUD completo con roles y auditoría.
- 💬 **Asistente IA:** Chat interno para consultas operativas.

### Frontend Mobile (Next.js)
- 📱 **Diseño Mobile-First:** Optimizado para tablets y celulares.
- 📊 **Dashboard:** Resumen de ocupación del día.
- 📅 **Calendario:** Navegación mensual con indicadores visuales.
- 📝 **Nueva Reserva:** Formulario con selección de fechas y múltiples habitaciones.
- 💬 **Chat IA:** Interfaz conversacional con el agente.
- 🔍 **Disponibilidad:** Búsqueda rápida por rango de fechas.

### API Backend
- 🔑 **Autenticación:** Login, tokens JWT, refresh.
- 🏠 **Habitaciones:** CRUD y estado de ocupación.
- 📅 **Reservas:** Creación, edición, cancelación con validación.
- 👥 **Huéspedes:** Registro y búsqueda de clientes.
- 🤖 **Agente IA:** Consultas en lenguaje natural.
- 📷 **OCR Vision:** Extracción de datos de documentos.
- 💰 **Pricing Engine:** Cálculo automático de tarifas con reglas de negocio.
- 🚗 **Control Operativo:** Registro de Estacionamiento (Chapa/Modelo) y Origen de Reserva.

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

**Desarrollado por Diego para Hospedaje Los Monges.**