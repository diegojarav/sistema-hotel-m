import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import calendar as cal_module  # Renombrado para evitar conflicto con variable
import os
from PIL import Image
from dotenv import load_dotenv
from pydantic import ValidationError
from logging_config import get_logger

# Logger para este módulo
logger = get_logger(__name__)

# Importar Servicios y Esquemas
from services import (
    AuthService, ReservationService, GuestService, 
    ReservationCreate, CheckInCreate, UserDTO
)

# --- 1. CONFIGURACIÓN INICIAL ---
load_dotenv()
st.set_page_config(page_title="Hotel Munich - Recepción", page_icon="🏨", layout="wide")

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

MESES_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]

DIAS_SEMANA = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

# --- 3. CSS PERSONALIZADO ---
def inject_custom_css():
    """Inyecta CSS para el calendario nativo y tarjetas móviles."""
    st.markdown("""
    <style>
    /* Calendario Nativo */
    .calendar-header {
        display: flex;
        justify-content: space-around;
        background: linear-gradient(135deg, #1e3a5f, #2d5a87);
        padding: 8px;
        border-radius: 8px 8px 0 0;
        margin-bottom: 2px;
    }
    .calendar-header span {
        color: white;
        font-weight: bold;
        font-size: 12px;
        width: 14%;
        text-align: center;
    }
    .calendar-row {
        display: flex;
        justify-content: space-around;
        margin-bottom: 2px;
    }
    .day-circle {
        width: 38px;
        height: 38px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 14px;
        font-weight: 500;
        margin: 2px auto;
        cursor: pointer;
        transition: all 0.2s ease;
    }
    .day-circle:hover {
        transform: scale(1.1);
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    }
    .status-free {
        background: transparent;
        color: #aaa;
        border: 1px dashed #555;
    }
    .status-medium {
        background: rgba(76, 175, 80, 0.3);
        color: #4CAF50;
        border: 2px solid #4CAF50;
        font-weight: bold;
    }
    .status-high {
        background: rgba(244, 67, 54, 0.3);
        color: #F44336;
        border: 2px solid #F44336;
        font-weight: bold;
    }
    .status-today {
        box-shadow: 0 0 0 3px #2196F3, 0 0 10px rgba(33, 150, 243, 0.5);
    }
    .day-empty {
        width: 38px;
        height: 38px;
        margin: 2px auto;
    }
    
    /* Tarjetas Móviles */
    .mobile-card {
        background: linear-gradient(135deg, #1e3a5f, #2d5a87);
        border-radius: 12px;
        padding: 15px;
        margin: 8px 0;
        border-left: 4px solid #4CAF50;
    }
    .mobile-card.occupied {
        border-left-color: #F44336;
    }
    .mobile-card h4 {
        margin: 0 0 8px 0;
        color: white;
    }
    .mobile-card p {
        margin: 4px 0;
        color: #ccc;
        font-size: 14px;
    }
    
    /* Leyenda del Calendario */
    .calendar-legend {
        display: flex;
        justify-content: center;
        gap: 20px;
        padding: 10px;
        margin-top: 10px;
    }
    .legend-item {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 12px;
        color: #888;
    }
    .legend-dot {
        width: 12px;
        height: 12px;
        border-radius: 50%;
    }
    .legend-dot.free { background: transparent; border: 1px dashed #555; }
    .legend-dot.medium { background: rgba(76, 175, 80, 0.3); border: 2px solid #4CAF50; }
    .legend-dot.high { background: rgba(244, 67, 54, 0.3); border: 2px solid #F44336; }
    </style>
    """, unsafe_allow_html=True)

# --- 4. FUNCIONES AUXILIARES UI ---
def _format_validation_error(e: ValidationError) -> str:
    """Extrae mensajes legibles de ValidationError de Pydantic."""
    errors = e.errors()
    messages = []
    for err in errors:
        field = " -> ".join(str(loc) for loc in err['loc'])
        msg = err['msg']
        messages.append(f"• {field}: {msg}")
    return "Error de validación:\n" + "\n".join(messages)

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

# --- 5. CALENDARIO NATIVO ---
def render_native_calendar(year: int, month: int, occupancy_map: dict, mobile: bool = False):
    """
    Renderiza un calendario mensual visual con HTML/CSS usando st.components.
    
    Args:
        year: Año a mostrar
        month: Mes a mostrar (1-12)
        occupancy_map: Dict de ocupación del servicio
        mobile: Si es True, usa estilo compacto para móvil
    """
    import streamlit.components.v1 as components
    
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    
    # Obtener matriz del mes
    month_matrix = cal_module.monthcalendar(year, month)
    
    # CSS del calendario
    css = """
    <style>
        .calendar-container {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 500px;
            margin: 0 auto;
            padding: 10px;
        }
        .calendar-header {
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            text-align: center;
            padding: 8px 0;
            font-weight: 600;
            color: #888;
            font-size: 11px;
            border-bottom: 1px solid #333;
            margin-bottom: 8px;
        }
        .calendar-grid {
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 3px;
        }
        .day-cell {
            height: 36px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 500;
            cursor: pointer;
            transition: transform 0.1s ease;
        }
        .day-cell:hover {
            transform: scale(1.08);
        }
        .day-empty {
            background: transparent;
        }
        .status-free {
            background: #2a2a2a;
            color: #aaa;
            border: 1px solid #444;
        }
        .status-medium {
            background: linear-gradient(135deg, #1b4332, #2d6a4f);
            color: #95d5b2;
            border: 1px solid #40916c;
        }
        .status-high {
            background: linear-gradient(135deg, #7f1d1d, #991b1b);
            color: #fca5a5;
            border: 1px solid #dc2626;
        }
        .day-today {
            box-shadow: 0 0 0 2px #3b82f6;
            font-weight: bold;
        }
        .legend {
            display: flex;
            justify-content: center;
            gap: 12px;
            margin-top: 12px;
            padding-top: 10px;
            border-top: 1px solid #333;
        }
        .legend-item {
            display: flex;
            align-items: center;
            gap: 4px;
            font-size: 10px;
            color: #888;
        }
        .legend-dot {
            width: 10px;
            height: 10px;
            border-radius: 3px;
        }
        .dot-free { background: #2a2a2a; border: 1px solid #444; }
        .dot-medium { background: #2d6a4f; border: 1px solid #40916c; }
        .dot-high { background: #991b1b; border: 1px solid #dc2626; }
    </style>
    """
    
    # Header días de semana
    header_html = '<div class="calendar-header">'
    for dia in DIAS_SEMANA:
        header_html += f'<span>{dia}</span>'
    header_html += '</div>'
    
    # Grid del calendario
    grid_html = '<div class="calendar-grid">'
    
    for week in month_matrix:
        for day in week:
            if day == 0:
                grid_html += '<div class="day-cell day-empty"></div>'
            else:
                day_date = date(year, month, day)
                day_key = day_date.strftime("%Y-%m-%d")
                day_data = occupancy_map.get(day_key, {"status": "free", "count": 0})
                
                status = day_data['status']
                count = day_data['count']
                is_today = day_key == today_str
                
                status_class = f"status-{status}"
                today_class = "day-today" if is_today else ""
                
                tooltip = f"{count} reserva(s)" if count > 0 else "Libre"
                
                grid_html += f'<div class="day-cell {status_class} {today_class}" title="{tooltip}">{day}</div>'
    
    grid_html += '</div>'
    
    # Leyenda
    legend_html = """
    <div class="legend">
        <div class="legend-item"><div class="legend-dot dot-free"></div> Libre</div>
        <div class="legend-item"><div class="legend-dot dot-medium"></div> 1-5</div>
        <div class="legend-item"><div class="legend-dot dot-high"></div> +5</div>
    </div>
    """
    
    # HTML completo
    full_html = f"""
    <div class="calendar-container">
        {css}
        {header_html}
        {grid_html}
        {legend_html}
    </div>
    """
    
    # Altura según cantidad de semanas (6 semanas máx = 6*36 + header + legend + padding)
    num_weeks = len(month_matrix)
    height = 80 + (num_weeks * 40)  # Base + altura por semana
    
    components.html(full_html, height=height)

def render_day_reservations(selected_date: date, occupancy_map: dict):
    """Renderiza las reservas de un día específico como tarjetas."""
    day_key = selected_date.strftime("%Y-%m-%d")
    day_data = occupancy_map.get(day_key, {"count": 0, "ids": [], "guests": []})
    
    if day_data["count"] == 0:
        st.success(f"✅ No hay reservas para {selected_date.strftime('%d/%m/%Y')}")
        return
    
    st.markdown(f"### 📅 Reservas del {selected_date.strftime('%d/%m/%Y')}")
    
    for i, (res_id, guest) in enumerate(zip(day_data["ids"], day_data["guests"])):
        with st.expander(f"🏠 {guest}", expanded=(i == 0)):
            st.write(f"**ID Reserva:** {res_id}")
            st.write(f"**Huésped:** {guest}")
            if st.button(f"❌ Cancelar", key=f"cancel_{res_id}_{day_key}"):
                if ReservationService.cancel_reservation(res_id, "Cancelación desde calendario", st.session_state.user.username):
                    st.success("Reserva cancelada")
                    st.rerun()

# --- 6. EJECUCIÓN PRINCIPAL ---

# A. Control de Login
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None

if not st.session_state.logged_in:
    st.markdown("## 🏨 Hotel Munich - Acceso (v4.0 Native Calendar)")
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

# B. Inyectar CSS
inject_custom_css()

# C. Sidebar con Toggle de Modo Móvil
with st.sidebar:
    st.write(f"👤 **{st.session_state.user.real_name}** ({st.session_state.user.role})")
    if st.button("Cerrar Sesión"): logout()
    st.divider()
    
    st.markdown("### ⚙️ Configuración de Vista")
    modo_movil = st.toggle("📱 Modo Móvil", value=False, help="Activa vista optimizada para móviles")
    
    if modo_movil:
        st.info("📱 Vista móvil activa")
    else:
        st.info("🖥️ Vista escritorio")
    
    st.divider()

# ==========================================
# D. INTERFAZ PRINCIPAL - CONDICIONAL
# ==========================================

if modo_movil:
    # ==========================================
    # 📱 MODO MÓVIL - Vista tipo Agenda
    # ==========================================
    st.title("🏨 Hotel Munich")
    
    # Selector de fecha compacto
    fecha_sel = st.date_input("📅 Seleccionar fecha", value=date.today(), key="mobile_date")
    
    # Obtener datos del mes seleccionado
    selected_year = fecha_sel.year
    selected_month = fecha_sel.month
    occupancy_map = ReservationService.get_occupancy_map(selected_year, selected_month)
    
    # Métricas del día
    summary = ReservationService.get_today_summary()
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🛎️ Llegadas", summary.llegadas_hoy)
    col2.metric("🚪 Salidas", summary.salidas_hoy)
    col3.metric("🏠 Ocupadas", summary.ocupadas)
    col4.metric("✅ Libres", summary.libres)
    
    st.divider()
    
    # Calendario visual compacto
    st.markdown(f"### 📆 {MESES_ES[selected_month-1]} {selected_year}")
    render_native_calendar(selected_year, selected_month, occupancy_map, mobile=True)
    
    st.divider()
    
    # Reservas del día seleccionado
    render_day_reservations(fecha_sel, occupancy_map)
    
    st.divider()
    
    # Botón Reserva Rápida
    st.markdown("### ➕ Nueva Reserva Rápida")
    
    with st.form("form_reserva_rapida", clear_on_submit=True):
        nombre_rapido = st.text_input("👤 Nombre del Huésped", placeholder="Juan Pérez")
        
        col_f, col_hab = st.columns(2)
        with col_f:
            fecha_entrada = st.date_input("📅 Fecha Entrada", value=fecha_sel, key="mobile_checkin")
        with col_hab:
            hab_seleccionada = st.selectbox("🚪 Habitación", options=LISTA_HABITACIONES)
        
        col_dias, col_precio = st.columns(2)
        with col_dias:
            dias_estadia = st.number_input("🌙 Noches", min_value=1, value=1)
        with col_precio:
            precio_rapido = st.number_input("💵 Precio", min_value=0.0, step=10000.0, value=150000.0)
        
        telefono_rapido = st.text_input("📞 Teléfono", placeholder="0981...")
        
        if st.form_submit_button("✅ Crear Reserva", type="primary", use_container_width=True):
            try:
                data = ReservationCreate(
                    check_in_date=fecha_entrada,
                    stay_days=dias_estadia,
                    guest_name=nombre_rapido,
                    room_ids=[hab_seleccionada],
                    room_type="Sin especificar",
                    price=precio_rapido,
                    arrival_time=datetime.combine(fecha_entrada, datetime.strptime("14:00", "%H:%M").time()),
                    reserved_by="Reserva Móvil",
                    contact_phone=telefono_rapido,
                    received_by=st.session_state.user.username
                )
                ids = ReservationService.create_reservations(data)
                st.success(f"✅ Reserva creada: {ids[0]}")
                st.balloons()
            except ValidationError as e:
                st.error(_format_validation_error(e))
            except Exception as e:
                logger.error(f"Error en reserva rápida: {e}", exc_info=True)
                st.error("Error al crear reserva")

else:
    # ==========================================
    # 🖥️ MODO ESCRITORIO - Vista completa
    # ==========================================
    st.title("🏨 Hotel Munich - Sistema de Recepción")

    tab_calendario, tab_reserva, tab_checkin = st.tabs([
        "📅 CALENDARIO Y ESTADO", 
        "📞 NUEVA RESERVA", 
        "👤 FICHA DE CLIENTE"
    ])

    # --- PESTAÑA 1: CALENDARIO ---
    with tab_calendario:
        st.header("📅 Planilla de Ocupación")
        
        # Selectores de año y mes
        col_year, col_month, col_view = st.columns([1, 1, 2])
        with col_year:
            selected_year = st.selectbox(
                "Año", 
                options=list(range(2024, 2030)),
                index=list(range(2024, 2030)).index(date.today().year),
                key="desk_year"
            )
        with col_month:
            selected_month = st.selectbox(
                "Mes",
                options=list(range(1, 13)),
                index=date.today().month - 1,
                format_func=lambda x: MESES_ES[x-1],
                key="desk_month"
            )
        
        # Sub-tabs
        tab_mensual, tab_semanal, tab_diaria = st.tabs([
            "📆 Vista Mensual", 
            "🗓️ Vista Semanal", 
            "📝 Vista Diaria"
        ])
        
        with tab_mensual:
            st.markdown(f"### 📆 {MESES_ES[selected_month-1]} {selected_year}")
            
            # Obtener mapa de ocupación
            occupancy_map = ReservationService.get_occupancy_map(selected_year, selected_month)
            
            # Renderizar calendario nativo
            render_native_calendar(selected_year, selected_month, occupancy_map)
            
            st.divider()
            
            # Selector de día para ver detalle
            col_day_sel, col_day_info = st.columns([1, 3])
            with col_day_sel:
                dia_detalle = st.date_input(
                    "Ver detalle del día:",
                    value=date.today(),
                    key="detail_day"
                )
            with col_day_info:
                render_day_reservations(dia_detalle, occupancy_map)
        
        with tab_semanal:
            fecha_referencia = st.date_input("Ver situación al día:", value=date.today(), key="week_ref")
            st.caption(f"Semana del: {fecha_referencia.strftime('%d/%m/%Y')}")
            
            matrix_data = ReservationService.get_weekly_view(fecha_referencia)
            
            fechas_cols = [fecha_referencia + timedelta(days=i) for i in range(7)]
            col_names = [f.strftime("%A %d/%m") for f in fechas_cols]
            date_keys = [f.strftime("%Y-%m-%d") for f in fechas_cols]
            
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
            fecha_diaria = st.date_input("Estado del día:", value=date.today(), key="daily_ref")
            st.caption(f"Estado: {fecha_diaria}")
            
            status_list = ReservationService.get_daily_status(fecha_diaria)
            
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
        
        col_mode_r, col_search_r = st.columns([1, 2])
        mode_res = col_mode_r.radio("Modo Reserva", ["Nueva Reserva", "Editar Reserva"], horizontal=True)
        
        res_id_load = None
        res_data = None
        
        if mode_res == "Editar Reserva":
            search_rid_raw = col_search_r.text_input("Ingresar ID Reserva (ej: 1255)", key="search_res_id_input")
            if search_rid_raw and col_search_r.button("Buscar ID"):
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
            if res_data.check_in_date: d_checkin = res_data.check_in_date
            d_nomb = res_data.guest_name
            d_habs = res_data.room_ids
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
                
                opciones_nombres = GuestService.get_all_guest_names()
                opciones_nombres.insert(0, "") 
                
                idx_nomb = 0
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
                
                if seleccion_nombre:
                    nombre_final = seleccion_nombre
                else:
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
                        if ReservationService.update_reservation(res_id_load, data):
                            st.success(f"Reserva {res_id_load} actualizada")
                        else:
                            st.error("Error al actualizar")
                    else:
                        ids = ReservationService.create_reservations(data)
                        st.success(f"Reservas creadas: {ids}")
                        
                except ValidationError as e:
                    st.error(_format_validation_error(e))
                except ValueError as e:
                    st.error(f"Error de datos: {e}")
                except Exception as e:
                    logger.error(f"Error inesperado al guardar reserva: {e}", exc_info=True)
                    st.error("Ocurrió un error inesperado. Contacte al soporte.")
            
            st.divider()
            st.markdown("### 📋 Listado de Reservas (Últimas)")
            all_res = ReservationService.get_all_reservations()
            if all_res:
                df_res = pd.DataFrame([r.dict() for r in all_res])
                df_res = df_res[["id", "guest_name", "check_in", "status", "room_id"]]
                st.dataframe(df_res, use_container_width=True, hide_index=True)
            else:
                st.info("No hay reservas registradas.")

    # --- PESTAÑA 3: CHECK-IN ---
    with tab_checkin:
        st.markdown("### 👤 Registro de Huésped")
        
        if 'datos_ia' not in st.session_state: st.session_state.datos_ia = {}
        uploaded_file = st.file_uploader("Documento (IA)", type=['jpg', 'jpeg'])
        if uploaded_file and st.button("Leer con IA"):
            with st.spinner("Leyendo..."):
                d = analizar_documento_con_ia(uploaded_file)
                if d: st.session_state.datos_ia = d

        ia = st.session_state.datos_ia
        
        col_mode, col_search = st.columns([1, 3])
        mode_ficha = col_mode.radio("Modo", ["Crear Nuevo", "Editar Existente"], horizontal=True, key="mode_ficha")
        
        cid_to_load = None
        
        if mode_ficha == "Editar Existente":
            search_q = col_search.text_input("Buscar por Apellido o Documento", key="search_guest_q")
            if search_q:
                results = GuestService.search_checkins(search_q)
                opts = {r['label']: r['id'] for r in results}
                selected_label = st.selectbox("Seleccionar Ficha", options=list(opts.keys()), key="sel_guest_res")
                if selected_label:
                    cid_to_load = opts[selected_label]
        
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
            c1, c2 = st.columns(2)
            
            apellidos = c1.text_input("Apellidos", value=def_apellidos)
            nombres = c2.text_input("Nombres", value=def_nombres)
            
            c3, c4 = st.columns(2)
            doc = c3.text_input("Documento", value=def_doc)
            nac = c4.text_input("Nacionalidad", value=def_nac)

            c5, c6 = st.columns(2)
            
            d_val = def_fecha_nac if def_fecha_nac else date(1980,1,1)
            fecha_nac = c5.date_input("Fecha Nacimiento", value=d_val)
            
            procedencia = c6.text_input("Procedencia (Origen)", value=def_procedencia)
            
            c_ec, c_pais = st.columns(2)
            estado_civil = c_ec.text_input("Estado Civil", value=def_ec)
            pais = c_pais.text_input("País", value=def_pais)
            
            st.markdown("### 🧾 Datos de Facturación")
            
            billing_profiles = GuestService.get_all_billing_profiles()
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
            
            if not sel_billing and def_bil_name:
                billing_name_val = def_bil_name
                billing_ruc_val = def_bil_ruc

            fac_n = st.text_input("Razón Social", value=billing_name_val)
            fac_r = st.text_input("RUC", value=billing_ruc_val)

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
                except ValidationError as e:
                    st.error(_format_validation_error(e))
                except ValueError as e:
                    st.error(f"Error de datos: {e}")
                except Exception as e:
                    logger.error(f"Error inesperado al guardar ficha: {e}", exc_info=True)
                    st.error("Ocurrió un error inesperado. Contacte al soporte.")
