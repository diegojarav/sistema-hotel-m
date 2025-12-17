import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import os
from PIL import Image
from dotenv import load_dotenv

# Importar Servicios y Esquemas
from services import (
    AuthService, ReservationService, GuestService, 
    ReservationCreate, CheckInCreate, UserDTO
)

# --- 1. CONFIGURACIÓN INICIAL ---
load_dotenv()
st.set_page_config(page_title="Hotel Munich - Recepción", page_icon="🏨", layout="wide")

# Inicializar Base de Datos (solo la primera vez si no existe, pero services lo maneja)
# database.init_db() se ejecuta manualmente o al importar si se desea, 
# pero aquí asumimos que ya corrió la migración.

# Configurar API Key de IA (si se usa en services o localmente)
# Nota: La lógica de IA para leer documentos todavía está en app.py o se puede mover.
# Para este refactor mantendremos la función de IA aquí por simplicidad o la moveremos a un 'utils' si es puro proceso.
# El usuario pidió "Desacople de Lógica", así que idealmente debería ir a servicios, 
# pero como es interacción con Gemini API y devuelve dicts, la dejaré en un helper aquí o la importaré.
# Por ahora la mantengo aquí como función auxiliar de UI, ya que procesa inputs de UI.

import google.generativeai as genai
API_KEY = os.getenv("GOOGLE_API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)

# --- 2. CONSTANTES ---
LISTA_HABITACIONES = [
    "31", "32", "33", "34", "35", "36",
    "21", "22", "23", "24", "25", "26", "27", "28"
]

LISTA_TIPOS = [
    "Matrimonial", "Doble (2 Camas)", "Triple", "Cuádruple", "Suite"
]

# --- 3. FUNCIONES AUXILIARES UI ---
def analizar_documento_con_ia(imagen_upload):
    """(Mantenida temporalmente en UI layer o mover a un AIService)"""
    try:
        if not API_KEY: return None
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

def logout():
    st.session_state.logged_in = False
    st.session_state.user = None
    st.rerun()

# --- 4. EJECUCIÓN PRINCIPAL ---

# A. Control de Login
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None

if not st.session_state.logged_in:
    st.markdown("## 🏨 Hotel Munich - Acceso (v3.0 SQLite)")
    with st.form("login_form"):
        u = st.text_input("Usuario")
        p = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Entrar", type="primary"):
            user_dto = AuthService.authenticate(u, p)
            if user_dto:
                st.session_state.logged_in = True
                st.session_state.user = user_dto
                st.rerun()
            else:
                st.error("Credenciales incorrectas")
    st.stop()

# B. Sidebar
with st.sidebar:
    st.write(f"👤 **{st.session_state.user.real_name}** ({st.session_state.user.role})")
    if st.button("Cerrar Sesión"): logout()
    st.divider()

# C. Interfaz Principal
st.title("🏨 Hotel Munich - Sistema de Recepción")

tab_calendario, tab_reserva, tab_checkin = st.tabs([
    "📅 CALENDARIO", 
    "📞 NUEVA RESERVA", 
    "👤 FICHA DE CLIENTE"
])

# --- PESTAÑA 1: CALENDARIO ---
with tab_calendario:
    st.header("📅 Planilla de Ocupación")
    col_fecha, col_ref = st.columns([1, 4])
    fecha_referencia = col_fecha.date_input("Ver situación al día:", value=date.today())
    
    tab_semanal, tab_diaria = st.tabs(["🗓️ Vista Semanal", "📝 Vista Diaria"])
    
    with tab_semanal:
        st.caption(f"Semana del: {fecha_referencia.strftime('%d/%m/%Y')}")
        # Llamada al Servicio
        matrix_data = ReservationService.get_weekly_view(fecha_referencia)
        
        # Convertir a DataFrame para display
        # Eje X: Fechas, Eje Y: Habitaciones
        # Necesitamos reconstruir las columnas de fecha
        lunes_inicio = fecha_referencia # Asumimos que el input es el inicio o calculamos lunes?
        # La logica del servicio usa start_date tal cual.
        
        fechas_cols = [fecha_referencia + timedelta(days=i) for i in range(7)]
        col_names = [f.strftime("%A %d/%m") for f in fechas_cols]
        date_keys = [f.strftime("%Y-%m-%d") for f in fechas_cols]
        
        # Armar rows
        rows = []
        for hab in LISTA_HABITACIONES:
            row_data = {"Habitación": hab}
            hab_data = matrix_data.get(hab, {})
            for i, d_key in enumerate(date_keys):
                row_data[col_names[i]] = hab_data.get(d_key, "")
            rows.append(row_data)
            
        df_semanal = pd.DataFrame(rows).set_index("Habitación")
        
        st.dataframe(
            df_semanal.style.applymap(lambda x: "background-color: #ffcdd2; color: black; font-weight: bold" if x != "" else ""),
            use_container_width=True, height=600
        )

    with tab_diaria:
        st.caption(f"Estado hoy: {fecha_referencia}")
        # Llamada al Servicio
        status_list = ReservationService.get_daily_status(fecha_referencia)
        
        # Filtrar o ordenar si es necesario, el servicio ya ordena por room_id
        for info in status_list:
            with st.container():
                c1, c2, c3, c4 = st.columns([1, 2, 4, 2])
                c1.subheader(f"🚪{info['room_id']}")
                if info['status'] == "OCUPADA":
                    c2.markdown(":red[**OCUPADA**]")
                    c3.write(f"👤 {info['huesped']}")
                    if info['res_id']:
                        c3.caption(f"🆔 {info['res_id']}")
                        with st.expander(f"❌ Cancelar"):
                            motivo = st.text_input("Motivo", key=f"m_{info['res_id']}")
                            if st.button("Confirmar", key=f"b_{info['res_id']}"):
                                if ReservationService.cancel_reservation(info['res_id'], motivo, st.session_state.user.username):
                                    st.success("Cancelada")
                                    st.rerun()
                else:
                    c2.markdown(":green[**LIBRE**]")
                st.divider()

# --- PESTAÑA 2: NUEVA RESERVA ---
with tab_reserva:
    st.markdown("### 📝 Gestión de Reservas")
    
    # Modo Edición
    col_mode_r, col_search_r = st.columns([1, 2])
    mode_res = col_mode_r.radio("Modo Reserva", ["Nueva Reserva", "Editar Reserva"], horizontal=True)
    
    res_id_load = None
    res_data = None
    
    if mode_res == "Editar Reserva":
        search_rid_raw = col_search_r.text_input("Ingresar ID Reserva (ej: 1255)", key="search_res_id_input")
        if search_rid_raw and col_search_r.button("Buscar ID"):
            # Auto-pad si es numerico
            search_rid = search_rid_raw
            if search_rid.isdigit():
                search_rid = search_rid.zfill(7)
                
            found_res = ReservationService.get_reservation(search_rid)
            if found_res:
                st.success(f"Reserva encontrada: {found_res.guest_name}")
                res_id_load = search_rid
                res_data = found_res
            else:
                st.error("No encontrada")

    # Valores por defecto
    d_checkin = date.today()
    d_nomb = ""
    d_habs = []
    d_tipo = LISTA_TIPOS[0]
    d_precio = 0.0
    d_estadia = 1
    d_hora = datetime.strptime("12:00", "%H:%M").time()
    d_tel = ""
    d_reservado = ""

    if res_data:
        # Cargar datos si existe
        if res_data.check_in_date: d_checkin = res_data.check_in_date
        d_nomb = res_data.guest_name
        d_habs = res_data.room_ids # Lista
        d_tipo = res_data.room_type if res_data.room_type in LISTA_TIPOS else LISTA_TIPOS[0]
        d_precio = res_data.price
        d_estadia = res_data.stay_days
        if res_data.arrival_time: d_hora = res_data.arrival_time.time()
        d_tel = res_data.contact_phone
        d_reservado = res_data.reserved_by

    with st.form("form_reserva", clear_on_submit=(mode_res == "Nueva Reserva")):
        c1, c2 = st.columns(2)
        with c1:
            check_in = st.date_input("Fecha Entrada", value=d_checkin)
            
            # Buscador de Clientes (Mixin con valor cargado)
            opciones_nombres = GuestService.get_all_guest_names()
            opciones_nombres.insert(0, "") 
            
            # Si estamos editando, queremos que el selectbox muestre el nombre actual si está en la lista
            idx_nomb = 0
            # Intentar encontrar indice
            # El formato en lista es "Apellido, Nombre" pero guardamos texto libre?
            # En get_all_guest_names devolvemos "Apellido, Nombre". 
            # Si guardamos "Juan Perez", no machea "Perez, Juan".
            # Asumamos que el usuario selecciona de la lista o escribe.
            # Intento simple de match:
            try:
                if d_nomb in opciones_nombres:
                    idx_nomb = opciones_nombres.index(d_nomb)
            except: pass

            seleccion_nombre = st.selectbox(
                "A Nombre De (Buscar)", 
                options=opciones_nombres, 
                index=idx_nomb,
                placeholder="Escribe para buscar..."
            )
            
            # Lógica híbrida
            if seleccion_nombre:
                nombre_final = seleccion_nombre
            else:
                # Si no seleccionó del dropdown, usamos el cargado o manual
                nombre_manual = st.text_input("...o escribe un nombre nuevo", value=d_nomb if not seleccion_nombre else "")
                nombre_final = nombre_manual

            nombre = nombre_final
            
            habs = st.multiselect("Habitaciones", LISTA_HABITACIONES, default=[h for h in d_habs if h in LISTA_HABITACIONES])
            tipo = st.selectbox("Tipo", LISTA_TIPOS, index=LISTA_TIPOS.index(d_tipo) if d_tipo in LISTA_TIPOS else 0)
            precio = st.number_input("Precio Total", step=10000.0, value=d_precio)
        with c2:
            estadia = st.number_input("Estadía (días)", min_value=1, value=d_estadia)
            hora = st.time_input("Hora Llegada", value=d_hora)
            tel = st.text_input("Teléfono", value=d_tel)
            reservado = st.text_input("Reservado Por", value=d_reservado)
        
        recibido = st.session_state.user.username

        btn_txt = "Actualizar Reserva" if res_id_load else "Guardar Reserva"

        if st.form_submit_button(btn_txt):
            try:
                # Crear DTO
                arrival_dt = datetime.combine(check_in, hora)
                
                data = ReservationCreate(
                    check_in_date=check_in,
                    stay_days=estadia,
                    guest_name=nombre,
                    room_ids=habs,
                    room_type=tipo,
                    price=precio,
                    arrival_time=arrival_dt,
                    reserved_by=reservado,
                    contact_phone=tel,
                    received_by=recibido
                )
                
                if res_id_load:
                    # Update
                    if ReservationService.update_reservation(res_id_load, data):
                        st.success(f"Reserva {res_id_load} actualizada")
                        # st.rerun() # Opcional para limpiar
                    else:
                        st.error("Error al actualizar")
                else:
                    # Create
                    ids = ReservationService.create_reservations(data)
                    st.success(f"Reservas creadas: {ids}")
                    
            except Exception as e:
                st.error(f"Error al guardar: {e}")
        
        st.divider()
        st.markdown("### 📋 Listado de Reservas (Últimas)")
        all_res = ReservationService.get_all_reservations()
        if all_res:
            # Simple dataframe
            df_res = pd.DataFrame([r.dict() for r in all_res])
            # Reorder cols
            df_res = df_res[["id", "guest_name", "check_in", "status", "room_id"]]
            st.dataframe(df_res, use_container_width=True, hide_index=True)
        else:
            st.info("No hay reservas registradas.")

# --- PESTAÑA 3: CHECK-IN ---
with tab_checkin:
    st.markdown("### 👤 Registro de Huésped")
    
    # ... Logica de IA igual que antes ...
    if 'datos_ia' not in st.session_state: st.session_state.datos_ia = {}
    uploaded_file = st.file_uploader("Documento (IA)", type=['jpg', 'jpeg'])
    if uploaded_file and st.button("Leer con IA"):
        with st.spinner("Leyendo..."):
            d = analizar_documento_con_ia(uploaded_file)
            if d: st.session_state.datos_ia = d

    ia = st.session_state.datos_ia
    
    # --- MODO EDICION / CREACION ---
    col_mode, col_search = st.columns([1, 3])
    mode_ficha = col_mode.radio("Modo", ["Crear Nuevo", "Editar Existente"], horizontal=True, key="mode_ficha")
    
    cid_to_load = None
    
    if mode_ficha == "Editar Existente":
        search_q = col_search.text_input("Buscar por Apellido o Documento", key="search_guest_q")
        if search_q:
            results = GuestService.search_checkins(search_q)
            # Format: ID - Label
            opts = {r['label']: r['id'] for r in results}
            selected_label = st.selectbox("Seleccionar Ficha", options=list(opts.keys()), key="sel_guest_res")
            if selected_label:
                cid_to_load = opts[selected_label]
    
    # Valores por defecto (o cargados)
    def_apellidos = ia.get("Apellidos", "")
    def_nombres = ia.get("Nombres", "")
    def_doc = ia.get("Nro_Documento", "")
    def_nac = ia.get("Nacionalidad", "")
    def_fecha_nac = None
    if ia.get("Fecha_Nacimiento"):
        try: def_fecha_nac = datetime.strptime(ia.get("Fecha_Nacimiento"), "%Y-%m-%d").date()
        except: pass
    def_procedencia = ia.get("Procedencia", "")
    def_ec = ia.get("Estado_Civil", "")
    def_pais = ia.get("Pais", "")
    def_bil_name = ""
    def_bil_ruc = ""
    def_v_modelo = ""
    def_v_chapa = ""

    # Si hay ID para cargar, pisamos los defaults (si la IA no está activa o si se prefiere DB)
    if cid_to_load:
        c_obj = GuestService.get_checkin(cid_to_load)
        if c_obj:
            def_apellidos = c_obj.last_name or ""
            def_nombres = c_obj.first_name or ""
            def_doc = c_obj.document_number or ""
            def_nac = c_obj.nationality or ""
            def_fecha_nac = c_obj.birth_date
            def_procedencia = c_obj.origin or ""
            def_ec = c_obj.civil_status or ""
            def_pais = c_obj.country or ""
            def_bil_name = c_obj.billing_name or ""
            def_bil_ruc = c_obj.billing_ruc or ""
            def_v_modelo = c_obj.vehicle_model or ""
            def_v_chapa = c_obj.vehicle_plate or ""
            st.toast(f"Datos cargados ID: {cid_to_load}")

    with st.form("ficha_form"):
        # Mapeo de campos a UI
        c1, c2 = st.columns(2)
        
        apellidos = c1.text_input("Apellidos", value=def_apellidos)
        nombres = c2.text_input("Nombres", value=def_nombres)
        
        c3, c4 = st.columns(2)
        doc = c3.text_input("Documento", value=def_doc)
        nac = c4.text_input("Nacionalidad", value=def_nac)

        c5, c6 = st.columns(2)
        
        # Fecha Nacimiento
        # Ajuste para date_input que no acepta None
        d_val = def_fecha_nac if def_fecha_nac else date(1980,1,1)
        fecha_nac = c5.date_input("Fecha Nacimiento", value=d_val)
        
        # Procedencia
        procedencia = c6.text_input("Procedencia (Origen)", value=def_procedencia)
        
        c_ec, c_pais = st.columns(2)
        estado_civil = c_ec.text_input("Estado Civil", value=def_ec)
        pais = c_pais.text_input("País", value=def_pais)
        
        st.markdown("### 🧾 Datos de Facturación")
        
        # Cargar perfiles existentes
        billing_profiles = GuestService.get_all_billing_profiles()
        # Formato para la lista: "Nombre | RUC"
        billing_options = [f"{p['name']} | {p['ruc']}" for p in billing_profiles]
        billing_options.insert(0, "")
        
        sel_billing = st.selectbox(
            "Buscar Razón Social Existente", 
            options=billing_options,
            placeholder="Escribe para buscar..."
        )
        
        billing_name_val = ""
        billing_ruc_val = ""
        
        if sel_billing:
            parts = sel_billing.split(" | ")
            if len(parts) >= 2:
                billing_name_val = parts[0]
                billing_ruc_val = parts[1]
            st.info(f"Seleccionado: {billing_name_val}")
        
        # Si estamos editando y ya tiene valor, usalo, salvo que el buscador de billing lo sobreescriba (complex UX, let's prefer search if active, else load)
        if not sel_billing and def_bil_name:
            billing_name_val = def_bil_name
            billing_ruc_val = def_bil_ruc

        # Permitir edición o nuevo entry
        fac_n = st.text_input("Razón Social", value=billing_name_val)
        fac_r = st.text_input("RUC", value=billing_ruc_val)

        # Vehiculo ya estaba
        st.markdown("### 🚗 Datos del Vehículo")
        c_v1, c_v2 = st.columns(2)
        vehiculo_modelo = c_v1.text_input("Modelo Vehículo", value=def_v_modelo)
        vehiculo_chapa = c_v2.text_input("Nro. Chapa", value=def_v_chapa)
        
        btn_label = "Actualizar Ficha" if cid_to_load else "Guardar Ficha"
        
        if st.form_submit_button(btn_label):
            try:
                checkin_data = CheckInCreate(
                    room_id=None,
                    last_name=apellidos,
                    first_name=nombres,
                    nationality=nac,
                    birth_date=fecha_nac, 
                    origin=procedencia,
                    destination="",
                    civil_status=estado_civil,
                    document_number=doc,
                    country=pais,
                    billing_name=fac_n,
                    billing_ruc=fac_r,
                    vehicle_model=vehiculo_modelo,
                    vehicle_plate=vehiculo_chapa
                )
                
                if cid_to_load:
                    if GuestService.update_checkin(cid_to_load, checkin_data):
                        st.success(f"Ficha actualizada ID: {cid_to_load}")
                        st.session_state.datos_ia = {}
                    else:
                        st.error("Error al actualizar")
                else:
                    gid = GuestService.register_checkin(checkin_data)
                    st.success(f"Check-in registrado ID: {gid}")
                    st.session_state.datos_ia = {}
            except Exception as e:
                st.error(f"Error: {e}")
