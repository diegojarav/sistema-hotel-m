import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import os
import re
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

# --- CONSTANTES ---
FILE_RESERVAS = "reservas.xlsx"
FILE_CLIENTES = "fichas_huespedes.xlsx"

# LISTA OFICIAL DE HABITACIONES
LISTA_HABITACIONES = [
    "31", "32", "33", "34", "35", "36",
    "21", "22", "23", "24", "25", "26", "27", "28"
]
# Tipos de Habitación
LISTA_TIPOS = [
    "Matrimonial", 
    "Doble (2 Camas)", 
    "Triple", 
    "Cuádruple", 
    "Suite"
]
# --- FUNCIONES DEL BACKEND ---
def init_db():
    """Crea los archivos Excel si no existen con las columnas de las fotos"""
    
    # 1. Mapeo exacto de la foto "REGISTRO DE RESERVAS"
    cols_reservas = [
        "Nro_Reserva", "Fecha_Registro", "Estadia_Dias", "A_Nombre_De", 
        "Habitacion", "Tipo_Habitacion", "Precio", "Hora_Llegada",
        "Reservado_Por", "Telefono", "Recibido_Por", "Fecha_Entrada", "Estado"
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
    
# --- FUNCIONES AUXILIARES PARA EL CALENDARIO ---

def limpiar_estadia_a_int(estadia_str):
    """Extrae el número de días del texto"""
    try:
        match = re.search(r'\d+', str(estadia_str))
        if match:
            return int(match.group())
        return 1
    except:
        return 1

def generar_vista_semanal(fecha_inicio):
    """Genera la matriz para la planilla visual semanal"""
    df_reservas = cargar_datos(FILE_RESERVAS)
    
    # Si el excel es nuevo y está vacío, devolver estructura vacía
    if df_reservas.empty:
        df_reservas = pd.DataFrame(columns=["Fecha_Entrada", "Habitacion", "Estado"])

    df_reservas['Fecha_Entrada'] = pd.to_datetime(df_reservas['Fecha_Entrada']).dt.date
    
    lunes_inicio = fecha_inicio - timedelta(days=fecha_inicio.weekday())
    fechas_cols = [lunes_inicio + timedelta(days=i) for i in range(7)]
    nombres_cols = [f.strftime("%A %d/%m") for f in fechas_cols]

    matriz_semanal = pd.DataFrame(index=LISTA_HABITACIONES, columns=nombres_cols)
    matriz_semanal = matriz_semanal.fillna("")

    if not df_reservas.empty:
        for _, reserva in df_reservas.iterrows():
            if reserva['Estado'] == 'Cancelada': continue

            # DATOS DE LA RESERVA
            f_inicio_res = reserva['Fecha_Entrada']
            dias = limpiar_estadia_a_int(reserva['Estadia_Dias'])
            f_fin_res = f_inicio_res + timedelta(days=dias - 1)
            
            # AQUI USAMOS LA NUEVA COLUMNA 'Habitacion'
            hab = str(reserva['Habitacion']) 

            if hab not in LISTA_HABITACIONES: continue
            
            for i, fecha_col in enumerate(fechas_cols):
                if f_inicio_res <= fecha_col <= f_fin_res:
                    col_name = nombres_cols[i]
                    # Mostramos Nombre del Huésped
                    matriz_semanal.at[hab, col_name] = reserva['A_Nombre_De']

    return matriz_semanal

def generar_vista_diaria(fecha_seleccionada):
    """Genera lista estado diario"""
    df_reservas = cargar_datos(FILE_RESERVAS)
    if not df_reservas.empty:
        df_reservas['Fecha_Entrada'] = pd.to_datetime(df_reservas['Fecha_Entrada']).dt.date
    
    datos_diarios = []

    for hab in LISTA_HABITACIONES:
        estado = "Libre"
        huesped = "-"
        tipo = ""
        nro_reserva_a_cancelar = None

        if not df_reservas.empty:
            for _, reserva in df_reservas.iterrows():
                if reserva['Estado'] == 'Cancelada': continue
                
                # AQUI USAMOS LA NUEVA COLUMNA 'Habitacion'
                if str(reserva['Habitacion']) != hab: continue

                f_inicio = reserva['Fecha_Entrada']
                dias = limpiar_estadia_a_int(reserva['Estadia_Dias'])
                f_fin = f_inicio + timedelta(days=dias - 1)

                if f_inicio <= fecha_seleccionada <= f_fin:
                    estado = "OCUPADA"
                    huesped = reserva['A_Nombre_De']
                    tipo = reserva['Tipo_Habitacion'] # Dato extra para mostrar
                    nro_reserva_a_cancelar = reserva['Nro_Reserva']
                    break 

        datos_diarios.append({
            "Hab.": hab,
            "Estado": estado,
            "Huésped": huesped,
            "Tipo": tipo,
            "Nro_Reserva": nro_reserva_a_cancelar
        })
        
    return pd.DataFrame(datos_diarios)

def cancelar_reserva(nro_reserva):
    df = cargar_datos(FILE_RESERVAS)
    df.loc[df["Nro_Reserva"] == nro_reserva, "Estado"] = "Cancelada"
    df.to_excel(FILE_RESERVAS, index=False)
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

# --- PESTAÑA 1: CALENDARIO VISUAL (PLANILLAS) ---
with tab_calendario:
    st.header("📅 Planilla de Ocupación")
    
    # Selector de fecha principal
    col_fecha, col_ref = st.columns([1, 4])
    fecha_referencia = col_fecha.date_input("Ver situación al día:", value=date.today())
    
    # Sub-pestañas para Vista Semanal y Diaria
    tab_semanal, tab_diaria, tab_listado = st.tabs(["🗓️ Vista Semanal (Planilla Grande)", "📝 Vista Diaria (Planilla Chica)", "📃 Listado Histórico"])
    
    # --- SUB-PESTAÑA: VISTA SEMANAL ---
    with tab_semanal:
        st.caption(f"Mostrando semana que incluye el: {fecha_referencia.strftime('%d/%m/%Y')}")
        
        # Generar la matriz
        df_semanal = generar_vista_semanal(fecha_referencia)
        
        # Mostrar con estilo para resaltar celdas ocupadas
        # Usamos un truco de pandas style para pintar celdas que tienen texto
        st.dataframe(
            df_semanal.style.applymap(
                lambda x: "background-color: #ffcdd2; color: black; font-weight: bold" if x != "" else "",
            ),
            use_container_width=True,
            height=600 # Altura fija para que se vea como la hoja
        )
        st.info("💡 Para registrar una reserva en un hueco libre, ve a la pestaña roja 'NUEVA RESERVA'.")

    # --- SUB-PESTAÑA: VISTA DIARIA Y CANCELACIÓN ---
    with tab_diaria:
        st.caption(f"Situación detallada del día: {fecha_referencia.strftime('%d/%m/%Y')}")
        
        df_diario = generar_vista_diaria(fecha_referencia)

        # Iteramos sobre las filas para mostrar una "tarjeta" por habitación
        # Esto permite poner botones al lado de cada una
        for index, row in df_diario.iterrows():
            with st.container():
                # Creamos columnas para diseñar la fila (Habitacion | Estado | Huesped | Boton Cancelar)
                c1, c2, c3, c4 = st.columns([1, 2, 4, 2])
                
                c1.subheader(f"🚪{row['Hab.']}")
                
                if row['Estado'] == "OCUPADA":
                    c2.markdown(":red[**OCUPADA**]")
                    c3.write(f"👤 {row['Huésped']}")
                    
                    # Botón para cancelar (Usamos key única para que no se confundan los botones)
                    clave_boton = f"btn_cancel_{row['Hab.']}_{row['Nro_Reserva']}"
                    if c4.button("❌ Liberar/Cancelar", key=clave_boton, type="secondary"):
                        cancelar_reserva(row['Nro_Reserva'])
                        st.toast(f"Reserva de la Hab. {row['Hab.']} cancelada.")
                        st.rerun() # Recargar la página para ver el cambio
                else:
                    c2.markdown(":green[**LIBRE**]")
                    c3.caption("---")
                    c4.write("") # Espacio vacío
                
                st.divider()

    # --- SUB-PESTAÑA: HISTÓRICO (La tabla que tenías antes) ---
    with tab_listado:
        st.write("Historial completo de reservas:")
        df_res = cargar_datos(FILE_RESERVAS)
        if df_res.empty:
            st.info("No hay reservas.")
        else:
            st.dataframe(
                df_res.sort_values(by="Fecha_Entrada", ascending=False),
                use_container_width=True, hide_index=True
            )

# --- PESTAÑA 2: REGISTRO DE RESERVAS (Réplica foto "Nro 0001254") ---
with tab_reserva:
    st.markdown("### 📝 Formulario de Reserva Telefónica/WhatsApp")
    
    with st.form("form_reserva", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            fecha_registro = st.date_input("Fecha (Hoy)", value=date.today())
            a_nombre_de = st.text_input("A nombre de")
            habitacion_nro = st.selectbox("Número de Habitación", LISTA_HABITACIONES)
            tipo_habitacion = st.selectbox("Tipo de Habitación", LISTA_TIPOS)
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
                "Habitacion": habitacion_nro,
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
            st.success(f"✅ Reserva Nro {nro} guardada para la Habitación {habitacion_nro}.")

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