# 🏨 Sistema de Gestión - Hotel Munich (v2.0)

Sistema de gestión hotelera local desarrollado en **Python** y **Streamlit**. Moderniza la recepción manteniendo la familiaridad de los formularios en papel, con automatización por IA y control de seguridad.

## 🚀 Nuevas Funcionalidades (v2.0)

* **🔐 Control de Acceso (Login):** Sistema de usuarios y contraseñas para administradores y recepcionistas.
* **📅 Planillas Visuales:**
    * **Vista Semanal:** Grilla tipo Excel para ver ocupación de 7 días de un vistazo.
    * **Vista Diaria:** Detalle habitación por habitación con botones de acción rápida.
* **❌ Gestión de Cancelaciones:** Registro de quién canceló la reserva y el motivo.
* **🚗 Registro Vehicular:** Campos específicos para Marca y Chapa del vehículo en la ficha.
* **🤖 IA Avanzada (OCR):** Lectura de Cédulas (Paraguay, Brasil, Argentina) usando **Google Gemini 2.5**.
* **🧾 Historial de Facturación:** El sistema recuerda los datos de RUC/Razón Social de clientes recurrentes.
* **📱 Acceso Móvil:** Diseño adaptable para acceder desde celulares dentro de la red Wi-Fi.

## 🛠️ Tecnologías

* **Core:** Python 3.10+, Streamlit.
* **Datos:** Pandas (Excel local).
* **IA:** Google Generative AI (Gemini 2.5 Flash).
* **Seguridad:** Python-Dotenv.

## 📋 Instalación Inicial

1.  **Clonar el repositorio:**
    ```bash
    git clone [https://github.com/diegojarav/sistema-hotel-munich.git](https://github.com/diegojarav/sistema-hotel-munich.git)
    cd sistema-hotel-munich
    ```

2.  **Preparar entorno (Miniconda):**
    ```bash
    conda create -n hotel_munich python=3.10
    conda activate hotel_munich
    pip install -r requirements.txt
    ```

3.  **Configurar la Llave de IA (¡Vital!):**
    Crea un archivo llamado `.env` en la carpeta principal y pega tu API Key:
    ```env
    GOOGLE_API_KEY="TU_CLAVE_AIza_AQUI"
    ```

## 🔐 Credenciales de Acceso (Por Defecto)

La primera vez que inicies el sistema, se crearán estos usuarios automáticamente en `usuarios.xlsx`:

| Rol | Usuario | Contraseña |
| :--- | :--- | :--- |
| **Administrador** | `admin` | `1234` |
| **Recepción** | `recepcion` | `1234` |

> **Nota:** Puedes cambiar las contraseñas editando directamente el archivo `usuarios.xlsx` una vez creado.

## ▶️ Cómo Iniciar el Sistema

### En el Servidor (Laptop Server)
Ejecuta este comando para iniciar el sistema visible para toda la red:
```bash
python -m streamlit run app.py --server.address 0.0.0.0
````

### En Clientes (Laptop recepcion / Celulares)

1.  Asegúrate de estar en el mismo **Wi-Fi**.
2.  Abre Chrome o Safari.
3.  Ingresa a: `http://IP_DEL_SERVER:8501`
      * *Ejemplo:* `http://192.168.1.15:8501`

## 📂 Estructura de Datos (Archivos Excel)

El sistema genera y administra estos archivos automáticamente. **No borrarlos** a menos que quieras reiniciar el sistema de fábrica.

  * `reservas.xlsx`: Base de datos de reservas, fechas y estados.
  * `fichas_huespedes.xlsx`: Datos personales, facturación y vehículos.
  * `usuarios.xlsx`: Credenciales de acceso y roles.

## ⚠️ Solución de Problemas Comunes

1.  **"No encuentro la API Key":** Verifica que el archivo `.env` no tenga extensión `.txt` oculta y esté en la misma carpeta que `app.py`.
2.  **"Columnas faltantes en Excel":** Si actualizaste el código y el Excel es viejo, el sistema intentará arreglarlo solo. Si falla, borra los `.xlsx` (haz backup antes) y reinicia el programa para que se creen limpios.
3.  **"No conecta desde la Acer":** Verifica que la Dell no haya entrado en suspensión y que el Firewall de Windows permita conexiones a Python.

-----

**Desarrollado por Diego para Hotel Munich.**

```
```