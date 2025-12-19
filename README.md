# 🏨 Hotel Munich LMS (Local Management System)

Un sistema de gestión hotelera (PMS) on-premise diseñado para alta disponibilidad local, seguridad de datos y automatización mediante IA.

---

## 🚀 Características Técnicas Destacadas

Este proyecto implementa prácticas de **Ingeniería de Software** y **DevSecOps** para garantizar robustez en un entorno local:

### 🏗️ Arquitectura y Diseño

- **Layered Architecture:** Separación estricta entre Capa de Presentación (`app.py`), Capa de Servicios (`services.py`) y Capa de Datos (`database.py`).
- **Modelo de Datos Relacional:** SQLite con integridad referencial.
- **Concurrencia Optimista:** Configuración de SQLite en **WAL Mode** (Write-Ahead Logging) y gestión de `scoped_session` para soportar múltiples usuarios simultáneos sin bloqueos.

### 🛡️ Seguridad y Robustez (Hardening)

- **Gestión de Secretos:** Credenciales aisladas mediante variables de entorno (`.env`).
- **Validación Estricta:** Uso de **Pydantic Schemas** para validar reglas de negocio (ej: `check_out > check_in`, precios no negativos) antes de persistir datos.
- **Manejo de Errores UX:** Excepciones de Pydantic y ValueError capturadas con mensajes amigables al usuario.
- **Observabilidad:** Sistema de **Logging Rotativo** (`RotatingFileHandler`) para auditoría de errores sin saturar el disco.

### 🔄 Resiliencia y Recuperación

- **Hot Backups:** Sistema automatizado de copias de seguridad en caliente usando la API nativa de SQLite (sin detener el servicio).
- **Infraestructura como Código (IaC):** Script `install_backup_task.bat` para despliegue automático de tareas programadas en Windows.

---

## 🛠️ Instalación y Despliegue

### 1. Clonar el repositorio

```bash
git clone https://github.com/diegojarav/sistema-hotel-m.git
cd sistema-hotel-m
```

### 2. Configurar entorno

```bash
# Crear entorno virtual (recomendado)
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con tus credenciales reales
```

### 3. Ejecutar

```bash
streamlit run app.py
```

Para acceso desde otros dispositivos en la red:

```bash
streamlit run app.py --server.address 0.0.0.0
```

---

## 🔐 Credenciales de Acceso (Por Defecto)

La primera vez que inicies el sistema, se crearán estos usuarios automáticamente:

| Rol              | Usuario     | Contraseña |
|------------------|-------------|------------|
| **Administrador** | `admin`     | `1234`     |
| **Recepción**     | `recepcion` | `1234`     |

> ⚠️ **Nota:** Cambia las contraseñas en producción.

---

## 📂 Estructura del Proyecto

```
hotel_munich/
├── app.py              # Capa de Presentación (Streamlit UI)
├── services.py         # Capa de Servicios (Lógica de negocio)
├── database.py         # Capa de Datos (SQLAlchemy + SQLite)
├── schemas.py          # DTOs y Validaciones (Pydantic)
├── logging_config.py   # Configuración centralizada de logging
├── backup_manager.py   # Sistema de backups automáticos
├── requirements.txt    # Dependencias Python
├── .env.example        # Template de variables de entorno
└── logs/               # Archivos de log (auto-generado)
```

---

## 📱 Funcionalidades

- **📅 Calendario de Ocupación:** Vistas semanal y diaria con estado de habitaciones.
- **📞 Gestión de Reservas:** Crear, editar, cancelar con trazabilidad.
- **👤 Fichas de Cliente:** Registro completo con datos de facturación y vehículo.
- **🤖 OCR con IA:** Lectura automática de documentos (Cédulas, DNI, Pasaportes) usando Google Gemini.
- **🧾 Historial de Facturación:** Autocompletado de datos de clientes recurrentes.

---

## ⚠️ Solución de Problemas

| Problema | Solución |
|----------|----------|
| "No encuentra la API Key" | Verifica que `.env` exista y no tenga extensión `.txt` oculta |
| "Database is locked" | El sistema usa WAL mode, reiniciar si persiste |
| "No conecta desde otro dispositivo" | Verificar firewall y usar `--server.address 0.0.0.0` |

---

## 📊 Tecnologías

| Componente | Tecnología |
|------------|------------|
| **Backend** | Python 3.10+ |
| **UI** | Streamlit |
| **Base de Datos** | SQLite + SQLAlchemy |
| **Validación** | Pydantic v2 |
| **IA/OCR** | Google Gemini 2.5 Flash |
| **Logging** | RotatingFileHandler |

---

**Desarrollado por Diego para Hotel Munich.**