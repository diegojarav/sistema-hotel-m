# 🏨 Sistema de Gestión - Hotel Munich (MVP)

Sistema de gestión hotelera local desarrollado en **Python** y **Streamlit**. Diseñado para modernizar la recepción del hotel manteniendo la familiaridad de los formularios en papel, optimizado para ser utilizado por personas mayores gracias a su interfaz intuitiva y automatización con Inteligencia Artificial.

## 🚀 Características Principales

* **Interfaz Amigable (+60 años):** Diseño visual limpio que replica los formularios físicos de papel (Ficha Roja de Reserva y Ficha Marrón de Registro).
* **Calendario en Tiempo Real:** Visualización clara de las habitaciones ocupadas y reservas futuras.
* **IA integrada (OCR):** Lectura automática de documentos de identidad (Cédulas Paraguay/Brasil, DNI Argentina, Pasaportes) utilizando **Google Gemini 2.5 Flash**.
* **Base de Datos Local:** Persistencia de datos en archivos Excel (`.xlsx`) para fácil respaldo y manipulación administrativa.
* **Arquitectura Cliente-Servidor:** Se ejecuta en el servidor central (Dell G16) y es accesible vía navegador desde la recepción (Laptop Acer).

## 🛠️ Tecnologías Utilizadas

* **Lenguaje:** Python 3.10+
* **Frontend:** Streamlit
* **Datos:** Pandas & OpenPyXL
* **IA/Vision:** Google Generative AI (Gemini 2.5 Flash)
* **Seguridad:** Python-Dotenv (Manejo de API Keys)

## 📋 Requisitos Previos

Antes de instalar, asegúrate de tener:
1.  **Python 3.10** o superior instalado (recomendado usar Miniconda).
2.  Una **Google API Key** activa (AI Studio).
3.  Conexión a red local (Wi-Fi/LAN) para conectar las laptops.

## ⚙️ Instalación (Paso a Paso)

1.  **Clonar el repositorio:**
    ```bash
    git clone [https://github.com/diegojarav/sistema-hotel-m.git](https://github.com/diegojarav/sistema-hotel-m.git)
    cd sistema-hotel-m
    ```

2.  **Crear y activar el entorno virtual (Conda):**
    ```bash
    conda create -n hotel_munich python=3.10
    conda activate hotel_munich
    ```

3.  **Instalar dependencias:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configurar Variables de Entorno (IMPORTANTE):**
    Crea un archivo llamado `.env` en la raíz del proyecto y agrega tu clave de API:
    ```env
    GOOGLE_API_KEY="TU_CLAVE_DE_GEMINI_AQUI"
    ```

## ▶️ Ejecución del Sistema

### Modo Local (Solo en la máquina servidor)
```bash
streamlit run app.py

### Modo Servidor (Para acceder desde la recepción)
    Para que la laptop Acer pueda entrar, ejecuta este comando en la Dell:

```bash
python -m streamlit run app.py --server.address 0.0.0.0