import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import os
import re
import google.generativeai as genai
from PIL import Image
from dotenv import load_dotenv

# --- 1. CONFIGURACIÓN INICIAL ---
# Cargar variables de entorno
load_dotenv()

# Configuración de página (SIEMPRE debe ser el primer comando de Streamlit)
st.set_page_config(page_title="Hotel Munich - Recepción", page_icon="🏨", layout="wide")

# Configurar API Key de IA
API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    st.error("⚠️ Error: No se encontró la API KEY. Revisa tu archivo .env")
else:
    genai.configure(api_key=API_KEY)

# --- 2. CONSTANTES Y LISTAS ---
FILE_RESERVAS = "reservas.xlsx"
FILE_CLIENTES = "fichas_huespedes.xlsx"
FILE_USUARIOS = "usuarios.xlsx"

# Lista Oficial de Habitaciones
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

# --- 3. DEFINICIÓN DE FUNCIONES (BACKEND) ---

def cargar_datos(archivo):
    """Carga un archivo Excel y devuelve un DataFrame"""
    return pd.read_excel(archivo)

def init_db():
    """Inicializa la base de datos y crea archivos/columnas faltantes"""
    # 1. RESERVAS
    cols_reservas = [
        "Nro_Reserva", "Fecha_Registro", "Estadia_Dias", "A_Nombre_De", 
        "Habitacion", "Tipo_Habitacion", "Precio", "Hora_Llegada", 
        "Reservado_Por", "Telefono", "Recibido_Por", "Fecha_Entrada", 
        "Estado", "Cancelado_Por", "Motivo_Cancelacion"
    ]
    
    # 2. CLIENTES
    cols_clientes = [
        "Fecha_Ingreso", "Habitacion", "Hora", "Apellidos", "Nombres", 
        "Nacionalidad", "Fecha_Nacimiento", "Procedencia", "Destino", 
        "Estado_Civil", "Nro_Documento", "Pais", 
        "Facturacion_Nombre", "Facturacion_RUC",
        "Vehiculo_Chapa", "Vehiculo_Modelo",
        "Firma_Digital"
    ]

    # 3. USUARIOS
    cols_usuarios = ["Usuario", "Password", "Rol", "Nombre_Real"]

    # Crear Reservas
    if not os.path.exists(FILE_RESERVAS):
        pd.DataFrame(columns=cols_reservas).to_excel(FILE_RESERVAS, index=False)
    else:
        df = pd.read_excel(FILE_RESERVAS)
        if "Cancelado_Por" not in df.columns:
            df["Cancelado_Por"] = ""
            df["Motivo_Cancelacion"] = ""
            df.to_excel(FILE_RESERVAS, index=False)
        
    # Crear Clientes
    if not os.path.exists(FILE_CLIENTES):
        pd.DataFrame(columns=cols_clientes).to_excel(FILE_CLIENTES, index=False)
    else:
        df = pd.read_excel(FILE_CLIENTES)
        if "Vehiculo_Chapa" not in df.columns:
            df["Vehiculo_Chapa"] = ""
            df["Vehiculo_Modelo"] = ""
            df.to_excel(FILE_CLIENTES, index=False)

    # Crear Usuarios (Admin por defecto)
    if not os.path.exists(FILE_USUARIOS):
        df = pd.DataFrame(columns=cols_usuarios)
        admin = {"Usuario": "admin", "Password": "1234", "Rol": "admin", "Nombre_Real": "Administrador"}
        recep = {"Usuario": "recepcion", "Password": "1234", "Rol": "user", "Nombre_Real": "Recepción"}
        df = pd.concat([df, pd.DataFrame([admin, recep])], ignore_index=True)
        df.to_excel(FILE_USUARIOS, index=False)

def verificar_login(usuario, password):
    if not os.path.exists(FILE_USUARIOS): return None
    df = pd.read_excel(FILE_USUARIOS)
    df['Password'] = df['Password'].astype(str)
    user = df[df['Usuario'] == usuario]
    if not user.empty:
        if str(user.iloc[0]['Password']) == str(password):
            return user.iloc[0]['Nombre_Real']
    return None

def logout():
    st.session_state.logged_in = False
    st.rerun()

def verificar_no_shows():
    """Verifica si hay reservas confirmadas que ya pasaron su hora de llegada hoy"""
    df = cargar_datos(FILE_RESERVAS)
    hoy = date.today()
    hora_actual = datetime.now().time()
    
    alertas = []
    if not df.empty:
        df['Fecha_Entrada'] = pd.to_datetime(df['Fecha_Entrada']).dt.date
        for _, row in df.iterrows():
            if row['Fecha_Entrada'] == hoy and row['Estado'] == 'Confirmada':
                try:
                    h_llegada = datetime.strptime(str(row['Hora_Llegada']), "%H:%M:%S").time()
                    if hora_actual > h_llegada:
                        alertas.append(f"Hab {row['Habitacion']} - {row['A_Nombre_De']} (Llegada: {row['Hora_Llegada']})")
                except:
                    continue
    
    if alertas:
        st.warning(f"⚠️ **ATENCIÓN: Reservas atrasadas ({len(alertas)})**\n" + "\n".join([f"- {a}" for a in alertas]))

def guardar_reserva(datos):
    df = cargar_datos(FILE_RESERVAS)
    
    # Generar ID
    start_id = 1254
    if not df.empty:
        try:
            last_id = int(df["Nro_Reserva"].max())
            nuevo_nro = last_id + 1
        except:
            nuevo_nro = start_id + 1 + len(df)
    else:
        nuevo_nro = start_id + 1

    datos["Nro_Reserva"] = f"{nuevo_nro:07d}" 
    
    # Campos opcionales vacíos
    if "Cancelado_Por" not in datos: datos["Cancelado_Por"] = ""
    if "Motivo_Cancelacion" not in datos: datos["Motivo_Cancelacion"] = ""

    nuevo_df = pd.DataFrame([datos])
    df = pd.concat([df, nuevo_df], ignore_index=True)
    df.to_excel(FILE_RESERVAS, index=False)
    return datos["Nro_Reserva"]

def guardar_cliente(datos):
    df = cargar_datos(FILE_CLIENTES)
    # Campos opcionales vacíos
    if "Vehiculo_Chapa" not in datos: datos["Vehiculo_Chapa"] = ""
    if "Vehiculo_Modelo" not in datos: datos["Vehiculo_Modelo"] = ""
    
    nuevo_df = pd.DataFrame([datos])
    df = pd.concat([df, nuevo_df], ignore_index=True)
    df.to_excel(FILE_CLIENTES, index=False)

def cancelar_reserva(nro_reserva):
    df = cargar_datos(FILE_RESERVAS)
    df.loc[df["Nro_Reserva"] == nro_reserva, "Estado"] = "Cancelada"
    df.to_excel(FILE_RESERVAS, index=False)

def buscar_historial_facturacion(nro_doc):
    df = cargar_datos(FILE_CLIENTES)
    if df.empty: return []
    # Verifica si existe la columna antes de buscar
    if 'Facturacion_Nombre' in df.columns:
        return df[df['Nro_Documento'] == str(nro_doc)][['Facturacion_Nombre', 'Facturacion_RUC']].drop_duplicates().to_dict('records')
    return []

# --- FUNCIONES DE IA ---
def analizar_documento_con_ia(imagen_upload):
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        img = Image.open(imagen_upload)
        prompt = """
        Actúa como un recepcionista experto en documentos internacionales. Analiza esta imagen.
        Puede ser: Cédula de Paraguay, DNI de Argentina, RG/CNH de Brasil o Pasaporte.
        
        Reglas OBLIGATORIAS:
        1. Devuelve SOLO un JSON válido.
        2. Si un dato no aparece, devuelve null o string vacío.
        3. Fechas: Formato YYYY-MM-DD.
        4. Nro_Documento: Solo números y letras, sin puntos.
        
        Estructura JSON:
        {
            "Apellidos": "string",
            "Nombres": "string",
            "Nacionalidad": "string",
            "Fecha_Nacimiento": "YYYY-MM-DD",
            "Nro_Documento": "string",
            "Pais": "string",
            "Sexo": "string",
            "Estado_Civil": "string",
            "Procedencia": "string"
        }
        """
        response = model.generate_content([prompt, img])
        texto_limpio = response.text.replace("```json", "").replace("```", "").strip()
        import json
        return json.loads(texto_limpio)
    except Exception as e:
        st.error(f"Error IA: {e}")
        return None

# --- FUNCIONES VISUALES (CALENDARIO) ---
def limpiar_estadia_a_int(estadia_str):
    try:
        match = re.search(r'\d+', str(estadia_str))
        if match: return int(match.group())
        return 1
    except: return 1

def generar_vista_semanal(fecha_inicio):
    df_reservas = cargar_datos(FILE_RESERVAS)
    if df_reservas.empty:
        df_reservas = pd.DataFrame(columns=["Fecha_Entrada", "Habitacion", "Estado", "Estadia_Dias", "A_Nombre_De"])

    df_reservas['Fecha_Entrada'] = pd.to_datetime(df_reservas['Fecha_Entrada']).dt.date
    
    lunes_inicio = fecha_inicio - timedelta(days=fecha_inicio.weekday())
    fechas_cols = [lunes_inicio + timedelta(days=i) for i in range(7)]
    nombres_cols = [f.strftime("%A %d/%m") for f in fechas_cols]

    matriz_semanal = pd.DataFrame(index=LISTA_HABITACIONES, columns=nombres_cols).fillna("")

    if not df_reservas.empty:
        for _, reserva in df_reservas.iterrows():
            if reserva['Estado'] == 'Cancelada': continue

            f_inicio_res = reserva['Fecha_Entrada']
            dias = limpiar_estadia_a_int(reserva['Estadia_Dias'])
            f_fin_res = f_inicio_res + timedelta(days=dias - 1)
            hab = str(reserva['Habitacion'])

            if hab in LISTA_HABITACIONES:
                for i, fecha_col in enumerate(fechas_cols):
                    if f_inicio_res <= fecha_col <= f_fin_res:
                        matriz_semanal.at[hab, nombres_cols[i]] = reserva['A_Nombre_De']
    return matriz_semanal

def generar_vista_diaria(fecha_seleccionada):
    df_reservas = cargar_datos(FILE_RESERVAS)
    if not df_reservas.empty:
        df_reservas['Fecha_Entrada'] = pd.to_datetime(df_reservas['Fecha_Entrada']).dt.date
    
    datos_diarios = []
    for hab in LISTA_HABITACIONES:
        estado, huesped, tipo, nro_res = "Libre", "-", "", None

        if not df_reservas.empty:
            for _, reserva in df_reservas.iterrows():
                if reserva['Estado'] == 'Cancelada': continue
                if str(reserva['Habitacion']) != hab: continue

                f_inicio = reserva['Fecha_Entrada']
                dias = limpiar_estadia_a_int(reserva['Estadia_Dias'])
                f_fin = f_inicio + timedelta(days=dias - 1)

                if f_inicio <= fecha_seleccionada <= f_fin:
                    estado = "OCUPADA"
                    huesped = reserva['A_Nombre_De']
                    tipo = reserva['Tipo_Habitacion']
                    nro_res = reserva['Nro_Reserva']
                    break 

        datos_diarios.append({"Hab.": hab, "Estado": estado, "Huésped": huesped, "Tipo": tipo, "Nro_Reserva": nro_res})
    return pd.DataFrame(datos_diarios)

# ==========================================
# 4. EJECUCIÓN PRINCIPAL DEL SISTEMA
# ==========================================

# A. Inicializar DB (CREAR ARCHIVOS PRIMERO QUE NADA)
init_db()

# B. Control de Login
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.markdown("## 🏨 Hotel Munich - Acceso")
    with st.form("login_form"):
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Entrar", type="primary"):
            nombre = verificar_login(u, p)
            if nombre:
                st.session_state.logged_in = True
                st.session_state.usuario_actual = nombre
                st.rerun()
            else:
                st.error("Credenciales incorrectas")
    st.stop() # DETIENE EL SISTEMA SI NO ENTRA

# C. Sidebar (Solo si está logueado)
with st.sidebar:
    st.write(f"👤 **{st.session_state.usuario_actual}**")
    if st.button("Cerrar Sesión"): logout()
    st.divider()

# D. Notificaciones de No-Show
verificar_no_shows()

# E. Interfaz Principal
st.title("🏨 Hotel Munich - Sistema de Recepción")

tab_calendario, tab_reserva, tab_checkin = st.tabs([
    "📅 CALENDARIO Y ESTADO", 
    "📞 NUEVA RESERVA (Papel Rojo)", 
    "👤 REGISTRO HUÉSPED (Ficha Marrón)"
])

# --- PESTAÑA 1: CALENDARIO ---
with tab_calendario:
    st.header("📅 Planilla de Ocupación")
    col_fecha, col_ref = st.columns([1, 4])
    fecha_referencia = col_fecha.date_input("Ver situación al día:", value=date.today())
    
    tab_semanal, tab_diaria, tab_listado = st.tabs(["🗓️ Vista Semanal", "📝 Vista Diaria", "📃 Listado Histórico"])
    
    with tab_semanal:
        st.caption(f"Semana del: {fecha_referencia.strftime('%d/%m/%Y')}")
        df_semanal = generar_vista_semanal(fecha_referencia)
        st.dataframe(
            df_semanal.style.applymap(lambda x: "background-color: #ffcdd2; color: black; font-weight: bold" if x != "" else ""),
            use_container_width=True, height=600
        )
        st.info("💡 Para reservar, ve a la pestaña 'NUEVA RESERVA'.")

    with tab_diaria:
        st.caption(f"Detalle del día: {fecha_referencia.strftime('%d/%m/%Y')}")
        df_diario = generar_vista_diaria(fecha_referencia)
        for index, row in df_diario.iterrows():
            with st.container():
                c1, c2, c3, c4 = st.columns([1, 2, 4, 2])
                c1.subheader(f"🚪{row['Hab.']}")
                if row['Estado'] == "OCUPADA":
                    c2.markdown(":red[**OCUPADA**]")
                    c3.write(f"👤 {row['Huésped']}")
                    with st.expander(f"❌ Cancelar Reserva"):
                        motivo = st.text_input("Motivo/Quien avisa?", key=f"mot_{row['Nro_Reserva']}")
                        if st.button("Confirmar", key=f"btn_cn_{row['Nro_Reserva']}"):
                            df = cargar_datos(FILE_RESERVAS)
                            idx = df[df["Nro_Reserva"] == row['Nro_Reserva']].index
                            if not idx.empty:
                                df.at[idx[0], "Estado"] = "Cancelada"
                                df.at[idx[0], "Cancelado_Por"] = st.session_state.usuario_actual
                                df.at[idx[0], "Motivo_Cancelacion"] = motivo
                                df.to_excel(FILE_RESERVAS, index=False)
                                st.success("Cancelada.")
                                st.rerun()
                else:
                    c2.markdown(":green[**LIBRE**]")
                st.divider()

    with tab_listado:
        st.write("Historial completo:")
        df_res = cargar_datos(FILE_RESERVAS)
        if not df_res.empty:
            st.dataframe(df_res.sort_values(by="Fecha_Entrada", ascending=False), use_container_width=True, hide_index=True)

# --- PESTAÑA 2: NUEVA RESERVA ---
with tab_reserva:
    st.markdown("### 📝 Formulario de Reserva")
    with st.form("form_reserva", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            fecha_registro = st.date_input("Fecha (Hoy)", value=date.today())
            a_nombre_de = st.text_input("A nombre de")
            habitaciones_seleccionadas = st.multiselect("Número de Habitación", LISTA_HABITACIONES)
            tipo_habitacion = st.selectbox("Tipo de Habitación", LISTA_TIPOS)
            precio = st.number_input("Precio Total", step=10000)
        with col2:
            estadia = st.text_input("Estadía (ej: 3 días)")
            hora_llegada = st.time_input("Hora Llegada", value=datetime.strptime("12:00", "%H:%M").time())
            telefono = st.text_input("Teléfono")
            reservado_por = st.text_input("Reservado por")
            fecha_entrada = st.date_input("Fecha Entrada")

        submitted = st.form_submit_button("💾 GUARDAR RESERVA", type="primary", use_container_width=True)
        
        if submitted:
            if not habitaciones_seleccionadas:
                st.error("⚠️ Debes seleccionar al menos una habitación.")
            else:
                nros_generados = []
                # Bucle para guardar múltiples habitaciones
                for hab in habitaciones_seleccionadas:
                    datos_reserva = {
                        "Fecha_Registro": fecha_registro,
                        "Estadia_Dias": estadia,
                        "A_Nombre_De": a_nombre_de,
                        "Habitacion": hab, # Guardamos UNA habitación por fila
                        "Tipo_Habitacion": tipo_habitacion,
                        "Precio": precio,
                        "Hora_Llegada": hora_llegada,
                        "Reservado_Por": reservado_por,
                        "Telefono": telefono,
                        "Recibido_Por": st.session_state.usuario_actual, # Usamos el login
                        "Fecha_Entrada": fecha_entrada,
                        "Estado": "Confirmada"
                    }
                    nro = guardar_reserva(datos_reserva)
                    nros_generados.append(str(nro))
                st.success(f"✅ Reservas generadas: {', '.join(nros_generados)}")

# --- PESTAÑA 3: FICHA HUESPED ---
with tab_checkin:
    st.markdown("### 👤 Ficha de Ingreso")
    
    if 'datos_ia' not in st.session_state: st.session_state.datos_ia = {}

    uploaded_file = st.file_uploader("Subir documento (IA)", type=['jpg', 'png', 'jpeg'])
    if uploaded_file and st.button("✨ EXTRAER DATOS CON IA", type="primary"):
        with st.spinner("Procesando..."):
            datos = analizar_documento_con_ia(uploaded_file)
            if datos:
                st.session_state.datos_ia = datos
                st.success("Leído correctamente.")

    st.markdown("---")
    ia = st.session_state.datos_ia
    
    with st.form("form_ficha", clear_on_submit=False): 
        c1, c2, c3 = st.columns(3)
        ingreso_fecha = c1.date_input("Fecha Ingreso", value=date.today())
        habitacion = c2.text_input("Habitación Nro.")
        hora_ingreso = c3.time_input("Hora")
        
        c4, c5 = st.columns(2)
        apellidos = c4.text_input("Apellidos", value=ia.get("Apellidos", ""))
        nombres = c5.text_input("Nombres", value=ia.get("Nombres", ""))
        
        c6, c7 = st.columns(2)
        nacionalidad = c6.text_input("Nacionalidad", value=ia.get("Nacionalidad", ""))
        
        fecha_nac_val = date(1980,1,1)
        if ia.get("Fecha_Nacimiento"):
            try: fecha_nac_val = datetime.strptime(ia.get("Fecha_Nacimiento"), "%Y-%m-%d").date()
            except: pass
        fecha_nac = c7.date_input("Fecha Nacimiento", value=fecha_nac_val)
        
        c8, c9 = st.columns(2)
        procedencia = c8.text_input("Procedencia", value=ia.get("Procedencia", ""))
        destino = c9.text_input("Destino", value=ia.get("Destino", ""))
        
        c10, c11 = st.columns(2)
        nro_documento = c11.text_input("Nº Documento", value=ia.get("Nro_Documento", ""))
        estado_civil = c10.text_input("Estado Civil", value=ia.get("Estado_Civil", ""))
        pais = st.text_input("País", value=ia.get("Pais", ""))

        st.markdown("### 🧾 Datos de Facturación")
        
        # Historial Facturación
        opciones_fact = ["Nueva..."]
        historial = []
        if nro_documento:
            historial = buscar_historial_facturacion(nro_documento)
            if historial:
                opciones_fact = [f"{h['Facturacion_Nombre']} ({h['Facturacion_RUC']})" for h in historial] + ["Nueva..."]
        
        seleccion_fact = st.selectbox("Perfil de Facturación", opciones_fact)
        
        if seleccion_fact == "Nueva...":
            fact_nombre = st.text_input("Razón Social")
            fact_ruc = st.text_input("RUC")
        else:
            datos_selec = next(h for h in historial if f"{h['Facturacion_Nombre']} ({h['Facturacion_RUC']})" == seleccion_fact)
            fact_nombre = st.text_input("Razón Social", value=datos_selec['Facturacion_Nombre'])
            fact_ruc = st.text_input("RUC", value=datos_selec['Facturacion_RUC'])

        st.markdown("---")
        st.markdown("### 🚗 Datos del Vehículo")
        c_v1, c_v2 = st.columns(2)
        vehiculo_modelo = c_v1.text_input("Modelo Vehículo")
        vehiculo_chapa = c_v2.text_input("Nro. Chapa")

        if st.form_submit_button("🖨️ GUARDAR FICHA", type="primary", use_container_width=True):
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
                "Facturacion_Nombre": fact_nombre,
                "Facturacion_RUC": fact_ruc,
                "Vehiculo_Modelo": vehiculo_modelo,
                "Vehiculo_Chapa": vehiculo_chapa,
                "Firma_Digital": "Pendiente"
            }
            guardar_cliente(datos_ficha)
            st.success("✅ Ficha guardada.")
            st.session_state.datos_ia = {}