import streamlit as st
from datetime import datetime, date, timedelta
from pydantic import ValidationError

from logging_config import get_logger
from services import GuestService, CheckInCreate
from helpers.ui_helpers import _format_validation_error, analizar_documento_con_ia

logger = get_logger(__name__)


def render_tab_checkin():
    """Renders the Guest Check-in / Registration tab."""
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

    # === VINCULAR A RESERVA (FEAT-LINK-01) ===
    st.markdown("---")
    st.markdown("#### 🔗 Vincular a Reserva (Opcional)")
    st.caption("Conecta esta ficha con una reserva existente sin check-in")

    unlinked_reservations = GuestService.get_unlinked_reservations()
    reservation_options = [""]
    reservation_id_map = {}
    for r in unlinked_reservations:
        reservation_options.append(r['label'])
        reservation_id_map[r['label']] = r['id']

    selected_reservation_label = st.selectbox(
        "Reserva sin Check-in",
        options=reservation_options,
        key="link_reservation_select",
        help="Vincula esta ficha a una reserva confirmada"
    )

    linked_reservation_id = None
    if selected_reservation_label:
        linked_reservation_id = reservation_id_map.get(selected_reservation_label)
        if linked_reservation_id:
            st.info(f"✓ Se vinculará a reserva: {selected_reservation_label}")

    st.markdown("---")

    c_obj = None
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

        # Calculate date range for birth date
        min_birth_date = date.today() - timedelta(days=365*100)
        max_birth_date = date.today()

        d_val = def_fecha_nac if def_fecha_nac else date(1990, 1, 1)
        fecha_nac = c5.date_input(
            "Fecha Nacimiento",
            value=d_val,
            min_value=min_birth_date,
            max_value=max_birth_date,
            help="Fecha de nacimiento del huésped (hasta 100 años atrás)"
        )

        procedencia = c6.text_input("Procedencia (Origen)", value=def_procedencia)

        c_ec, c_pais = st.columns(2)
        estado_civil = c_ec.text_input("Estado Civil", value=def_ec)
        pais = c_pais.text_input("País", value=def_pais)

        st.markdown("### 📞 Contacto")
        c_tel, c_email = st.columns(2)
        def_phone = (getattr(c_obj, 'contact_phone', '') or '') if c_obj else ''
        def_email_val = (getattr(c_obj, 'contact_email', '') or '') if c_obj else ''
        contact_phone_val = c_tel.text_input("Teléfono", value=def_phone, placeholder="0981...")
        contact_email_val = c_email.text_input("Email", value=def_email_val, placeholder="correo@ejemplo.com")

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
                    reservation_id=linked_reservation_id,  # FEAT-LINK-01
                    last_name=apellidos,
                    first_name=nombres,
                    nationality=nac,
                    birth_date=fecha_nac,
                    origin=procedencia,
                    destination="",
                    civil_status=estado_civil,
                    document_number=doc,
                    country=pais,
                    contact_phone=contact_phone_val,
                    contact_email=contact_email_val,
                    billing_name=fac_n,
                    billing_ruc=fac_r,
                    vehicle_model=vehiculo_modelo,
                    vehicle_plate=vehiculo_chapa
                )

                if cid_to_load:
                    if GuestService.update_checkin(cid_to_load, checkin_data):
                        st.success(f"Ficha actualizada ID: {cid_to_load}")
                        st.session_state.datos_ia = {}
                        st.rerun()
                    else:
                        st.error("Error al actualizar")
                else:
                    gid = GuestService.register_checkin(checkin_data)
                    st.success(f"Check-in registrado ID: {gid}")
                    st.session_state.datos_ia = {}
                    st.rerun()
            except ValidationError as e:
                st.error(_format_validation_error(e))
            except ValueError as e:
                st.error(f"Error de datos: {e}")
            except Exception as e:
                logger.error(f"Error inesperado al guardar ficha: {e}", exc_info=True)
                st.error("Ocurrió un error inesperado. Contacte al soporte.")
