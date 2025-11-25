import streamlit as st
import pandas as pd
from datetime import datetime, date
import os

import google.generativeai as genai
from PIL import Image
from dotenv import load_dotenv

# Cargar variables de entorno desde el archivo .env
load_dotenv()

# --- CONFIGURACIÓN DE IA (GOOGLE GEMINI) ---
# ¡OJO! PRUEBA.
# Configurar la API Key de forma segura
API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    st.error("⚠️ Error: No se encontró la API KEY. Revisa tu archivo .env")
else:
    genai.configure(api_key=API_KEY)

def analizar_documento_con_ia(imagen_upload):
    """Envía la imagen a Google Gemini y extrae los datos en JSON"""
    try:
        # CORRECCIÓN DEL NOMBRE DEL MODELO (Para evitar el error 404)
        # Usamos 'gemini-1.5-flash-latest' que suele ser el alias más estable
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        img = Image.open(imagen_upload)

        # PROMPT UNIVERSAL (MERCOSUR + PASAPORTES)
        prompt = """
        Actúa como un recepcionista experto en documentos internacionales. Analiza esta imagen.
        Puede ser: Cédula de Paraguay, DNI de Argentina, RG/CNH de Brasil o Pasaporte de cualquier país.
        
        Tu tarea es identificar qué documento es y extraer los datos visibles.
        
        Reglas OBLIGATORIAS:
        1. Devuelve SOLO un JSON válido.
        2. Si un dato no aparece en la foto (ej: Estado Civil en DNI argentino), devuelve null o string vacío "".
        3. Fechas: Formato YYYY-MM-DD. Si no tiene año completo, deduce el siglo (19xx o 20xx).
        4. Nro_Documento: Solo números y letras, sin puntos ni guiones.
        
        Estructura JSON a completar:
        {
            "Apellidos": "string",
            "Nombres": "string",
            "Nacionalidad": "string (Si no dice explícitamente, infiérela del país emisor)",
            "Fecha_Nacimiento": "YYYY-MM-DD",
            "Nro_Documento": "string",
            "Pais": "string (Ej: Paraguay, Argentina, Brasil)",
            "Sexo": "string",
            "Estado_Civil": "string (Solo si aparece)",
            "Procedencia": "string (Ciudad o Domicilio si aparece)"
        }
        """
        
        response = model.generate_content([prompt, img])
        
        # Limpieza de seguridad por si la IA responde con ```json ... ```
        texto_limpio = response.text.replace("```json", "").replace("```", "").strip()
        
        import json
        return json.loads(texto_limpio)
        
    except Exception as e:
        st.error(f"Error: {e}")
        return None

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Hotel Munich - Recepción", page_icon="🏨", layout="wide")

# --- RUTAS DE ARCHIVOS (BASE DE DATOS LOCAL) ---
FILE_RESERVAS = "reservas.xlsx"
FILE_CLIENTES = "fichas_huespedes.xlsx"

# --- FUNCIONES DEL BACKEND ---

def init_db():
    """Crea los archivos Excel si no existen con las columnas de las fotos"""
    
    # 1. Mapeo exacto de la foto "REGISTRO DE RESERVAS"
    cols_reservas = [
        "Nro_Reserva", "Fecha_Registro", "Estadia_Dias", "A_Nombre_De", 
        "Tipo_Habitacion", "Precio", "Hora_Llegada", "Reservado_Por", 
        "Telefono", "Recibido_Por", "Fecha_Entrada", "Estado"
    ]
    
    # 2. Mapeo exacto de la foto "FICHA DE DATOS PERSONALES"
    cols_clientes = [
        "Fecha_Ingreso", "Habitacion", "Hora", "Apellidos", "Nombres", 
        "Nacionalidad", "Fecha_Nacimiento", "Procedencia", "Destino", 
        "Estado_Civil", "Nro_Documento", "Pais", "Facturacion", "RUC", "Firma_Digital"
    ]

    if not os.path.exists(FILE_RESERVAS):
        df = pd.DataFrame(columns=cols_reservas)
        df.to_excel(FILE_RESERVAS, index=False)
        
    if not os.path.exists(FILE_CLIENTES):
        df = pd.DataFrame(columns=cols_clientes)
        df.to_excel(FILE_CLIENTES, index=False)

def cargar_datos(archivo):
    return pd.read_excel(archivo)

def guardar_reserva(datos):
    df = cargar_datos(FILE_RESERVAS)
    # Generar Nro de Reserva automático (ej: 0001255)
    nuevo_nro = 1254 + len(df) + 1 
    datos["Nro_Reserva"] = f"{nuevo_nro:07d}" # Formato 0001255
    
    nuevo_df = pd.DataFrame([datos])
    df = pd.concat([df, nuevo_df], ignore_index=True)
    df.to_excel(FILE_RESERVAS, index=False)
    return datos["Nro_Reserva"]

def guardar_cliente(datos):
    df = cargar_datos(FILE_CLIENTES)
    nuevo_df = pd.DataFrame([datos])
    df = pd.concat([df, nuevo_df], ignore_index=True)
    df.to_excel(FILE_CLIENTES, index=False)

# Inicializar DB al arrancar
init_db()

# --- INTERFAZ DE USUARIO (FRONTEND) ---

st.title("🏨 Hotel Munich - Sistema de Recepción")

# Menú de Navegación Grande y Claro
tab_calendario, tab_reserva, tab_checkin = st.tabs([
    "📅 CALENDARIO Y ESTADO", 
    "📞 NUEVA RESERVA (Papel Rojo)", 
    "👤 REGISTRO HUÉSPED (Ficha Marrón)"
])

# --- PESTAÑA 1: CALENDARIO (Visión General) ---
with tab_calendario:
    st.header("Estado de Habitaciones y Reservas")
    
    df_res = cargar_datos(FILE_RESERVAS)
    
    if df_res.empty:
        st.info("No hay reservas registradas aún.")
    else:
        # Mostrar las últimas reservas primero
        st.dataframe(
            df_res.sort_values(by="Fecha_Entrada", ascending=False),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Nro_Reserva": "Nº Ficha",
                "A_Nombre_De": "Huésped",
                "Fecha_Entrada": st.column_config.DateColumn("Llegada"),
                "Precio": st.column_config.NumberColumn("Precio Gs.", format="$%d")
            }
        )
    
    col_refresh, col_dummy = st.columns([1,4])
    if col_refresh.button("🔄 Actualizar Tabla"):
        st.rerun()

# --- PESTAÑA 2: REGISTRO DE RESERVAS (Réplica foto "Nro 0001254") ---
with tab_reserva:
    st.markdown("### 📝 Formulario de Reserva Telefónica/WhatsApp")
    
    with st.form("form_reserva", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            fecha_registro = st.date_input("Fecha (Hoy)", value=date.today())
            a_nombre_de = st.text_input("A nombre de")
            tipo_habitacion = st.selectbox("Tipo de Habitación", ["Matrimonial", "Doble", "Triple", "Suite"])
            precio = st.number_input("Precio (Gs)", step=10000)
            reservado_por = st.text_input("Reservado por (Cliente/Agencia)")
            
        with col2:
            estadia = st.text_input("Estadía (ej: 3 días)")
            hora_llegada = st.time_input("Hora de Llegada", value=datetime.strptime("12:00", "%H:%M").time())
            telefono = st.text_input("Teléfono")
            recibido_por = st.text_input("Recibido por (Recepcionista)")
            fecha_entrada = st.date_input("Fecha de Entrada Real")

        # Botón grande para guardar
        submitted = st.form_submit_button("💾 GUARDAR RESERVA", type="primary", use_container_width=True)
        
        if submitted:
            datos_reserva = {
                "Fecha_Registro": fecha_registro,
                "Estadia_Dias": estadia,
                "A_Nombre_De": a_nombre_de,
                "Tipo_Habitacion": tipo_habitacion,
                "Precio": precio,
                "Hora_Llegada": hora_llegada,
                "Reservado_Por": reservado_por,
                "Telefono": telefono,
                "Recibido_Por": recibido_por,
                "Fecha_Entrada": fecha_entrada,
                "Estado": "Confirmada"
            }
            nro = guardar_reserva(datos_reserva)
            st.success(f"✅ Reserva guardada correctamente con el Nro: {nro}")

# --- PESTAÑA 3: FICHA DE DATOS (Réplica foto "Ficha marrón") ---
# --- PESTAÑA 3: FICHA DE DATOS (CON IA) ---
with tab_checkin:
    st.markdown("### 👤 Ficha de Ingreso (Check-In)")
    
    # 1. Crear memoria para guardar los datos de la IA (si no existe)
    if 'datos_ia' not in st.session_state:
        st.session_state.datos_ia = {}

    # 2. Subir archivo
    st.info("📷 Sube una foto del documento para llenar esto automáticamente.")
    uploaded_file = st.file_uploader("Foto del Documento (Cédula/DNI)", type=['jpg', 'png', 'jpeg'])
    
    if uploaded_file is not None:
        st.image(uploaded_file, caption="Documento cargado", width=300)
        
        # 3. Botón Mágico de la IA
        if st.button("✨ EXTRAER DATOS CON IA", type="primary"):
            with st.spinner("Leyendo documento..."):
                # Llamamos a la función que pusiste arriba
                datos = analizar_documento_con_ia(uploaded_file)
                if datos:
                    st.session_state.datos_ia = datos
                    st.success("¡Datos extraídos! Verifica el formulario abajo.")
                else:
                    st.error("No se pudo leer el documento.")

    st.markdown("---")
    
    # 4. Recuperamos los datos de la memoria para llenar el formulario
    ia = st.session_state.datos_ia
    
    # IMPORTANTE: clear_on_submit=False para que no se borre lo que llenó la IA
    with st.form("form_ficha", clear_on_submit=False): 
        c1, c2, c3 = st.columns(3)
        ingreso_fecha = c1.date_input("Fecha Ingreso", value=date.today())
        habitacion = c2.text_input("Habitación Nro.")
        hora_ingreso = c3.time_input("Hora")
        
        st.markdown("---")
        
        c4, c5 = st.columns(2)
        # Aquí usamos .get() para llenar si la IA trajo el dato
        apellidos = c4.text_input("Apellidos", value=ia.get("Apellidos", ""))
        nombres = c5.text_input("Nombres", value=ia.get("Nombres", ""))
        
        c6, c7 = st.columns(2)
        nacionalidad = c6.text_input("Nacionalidad", value=ia.get("Nacionalidad", ""))
        
        # Lógica para evitar errores con la fecha de nacimiento
        fecha_nac_val = date(1980,1,1)
        if ia.get("Fecha_Nacimiento"):
            try:
                fecha_nac_val = datetime.strptime(ia.get("Fecha_Nacimiento"), "%Y-%m-%d").date()
            except:
                pass 
                
        fecha_nac = c7.date_input("Fecha de Nacimiento", value=fecha_nac_val)
        
        c8, c9 = st.columns(2)
        procedencia = c8.text_input("Procedencia", value=ia.get("Procedencia", ""))
        destino = c9.text_input("Destino", value=ia.get("Destino", ""))
        
        c10, c11 = st.columns(2)
        # Lógica para seleccionar el estado civil correcto
        estado_civil_val = ia.get("Estado_Civil", "Soltero/a") 
        opciones_civil = ["Soltero/a", "Casado/a", "Viudo/a", "Divorciado/a"]
        idx_civil = 0
        if estado_civil_val in opciones_civil:
            idx_civil = opciones_civil.index(estado_civil_val)
            
        estado_civil = c10.selectbox("Estado Civil", opciones_civil, index=idx_civil)
        nro_documento = c11.text_input("Nº de Documento", value=ia.get("Nro_Documento", ""))
        
        pais = st.text_input("País", value=ia.get("Pais", ""))
        
        st.markdown("### 🧾 Datos de Facturación")
        facturacion = st.text_input("Nombre / Razón Social")
        ruc = st.text_input("RUC")
        
        if st.form_submit_button("🖨️ GUARDAR FICHA DE HUÉSPED", type="primary", use_container_width=True):
            datos_ficha = {
                "Fecha_Ingreso": ingreso_fecha,
                "Habitacion": habitacion,
                "Hora": hora_ingreso,
                "Apellidos": apellidos,
                "Nombres": nombres,
                "Nacionalidad": nacionalidad,
                "Fecha_Nacimiento": fecha_nac,
                "Procedencia": procedencia,
                "Destino": destino,
                "Estado_Civil": estado_civil,
                "Nro_Documento": nro_documento,
                "Pais": pais,
                "Facturacion": facturacion,
                "RUC": ruc,
                "Firma_Digital": "Pendiente"
            }
            guardar_cliente(datos_ficha)
            st.success(f"✅ Ficha creada para {nombres} {apellidos}. Guardada en Excel.")
            # Limpiamos la memoria de la IA para el siguiente cliente
            st.session_state.datos_ia = {}