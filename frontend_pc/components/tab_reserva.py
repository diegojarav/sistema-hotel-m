import streamlit as st
import pandas as pd
import json
from datetime import datetime, date, timedelta
from pydantic import ValidationError

from logging_config import get_logger
from services import ReservationService, GuestService, PricingService, ReservationCreate
from helpers.constants import LISTA_TIPOS_LEGACY, LISTA_HABITACIONES_LEGACY
from helpers.data_fetchers import get_room_categories, get_available_rooms_for_dates, get_all_rooms_list, get_client_types, get_seasons
from helpers.ui_helpers import _format_validation_error, analizar_documento_con_ia
from frontend_services.cache_service import force_refresh

logger = get_logger(__name__)


def render_tab_reserva():
    """Renders the New Reservation tab with create/edit functionality."""
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

    # === DOCUMENT SCANNER (FEAT-LINK-01) ===
    st.markdown("---")
    st.markdown("#### ✨ Escanear Documento (Opcional)")
    st.caption("Usa Gemini 2.5 para extraer datos automáticamente y crear ficha de cliente vinculada")

    if 'reserva_datos_ia' not in st.session_state:
        st.session_state.reserva_datos_ia = {}

    uploaded_doc = st.file_uploader("Documento (IA)", type=['jpg', 'jpeg'], key="reserva_doc_upload")
    if uploaded_doc and st.button("Leer con IA", key="reserva_scan_btn"):
        with st.spinner("Leyendo documento con Gemini 2.5..."):
            extracted = analizar_documento_con_ia(uploaded_doc)
            if extracted:
                st.session_state.reserva_datos_ia = extracted
                st.success(f"✓ Datos extraídos: {extracted.get('Nombres', '')} {extracted.get('Apellidos', '')}")
            else:
                st.error("No se pudieron extraer datos del documento")

    ia_data = st.session_state.reserva_datos_ia

    # Valores por defecto
    d_checkin = date.today()
    d_checkout = date.today() + timedelta(days=1)
    d_nomb = ""
    d_habs = []
    d_precio = 0.0
    d_hora = datetime.strptime("12:00", "%H:%M").time()
    d_tel = ""
    d_email = ""
    d_reservado = ""
    d_parking = False
    d_vehicle_model = ""
    d_vehicle_plate = ""
    d_source = "Direct"
    d_external_id = ""

    # Load categories for selection
    all_categories = get_room_categories()
    cat_lookup = {c["id"]: c for c in all_categories} if all_categories else {}

    if res_data:
        if res_data.check_in_date:
            d_checkin = res_data.check_in_date
            d_checkout = res_data.check_in_date + timedelta(days=res_data.stay_days)
        d_nomb = res_data.guest_name
        d_habs = res_data.room_ids
        d_precio = res_data.price
        if res_data.arrival_time: d_hora = res_data.arrival_time if isinstance(res_data.arrival_time, time) else res_data.arrival_time.time()
        d_tel = res_data.contact_phone
        d_email = getattr(res_data, 'contact_email', '') or ''
        d_reservado = res_data.reserved_by
        d_parking = res_data.parking_needed
        d_vehicle_model = res_data.vehicle_model or ""
        d_vehicle_plate = res_data.vehicle_plate or ""
        d_source = res_data.source or "Direct"
        d_external_id = res_data.external_id or ""

    # === AUTO-FILL FROM SCANNED DOCUMENT (FEAT-LINK-01) ===
    if ia_data and (ia_data.get("Apellidos") or ia_data.get("Nombres")):
        apellidos = ia_data.get("Apellidos", "").strip()
        nombres = ia_data.get("Nombres", "").strip()
        if apellidos or nombres:
            d_nomb = f"{apellidos}, {nombres}".strip(", ")

    # === INICIALIZAR SESSION STATE PARA FECHAS ===
    if 'res_checkin' not in st.session_state:
        st.session_state.res_checkin = d_checkin
    if 'res_checkout' not in st.session_state:
        st.session_state.res_checkout = d_checkout

    # Si hay datos de reserva cargados, actualizar session state
    if res_data and res_data.check_in_date:
        st.session_state.res_checkin = d_checkin
        st.session_state.res_checkout = d_checkout

    # === CALLBACK PARA ACTUALIZAR CHECK-OUT AUTOMÁTICAMENTE ===
    def update_checkout_on_checkin_change():
        """Cuando cambia check-in, actualiza check-out a check-in + 1 día"""
        new_checkin = st.session_state.checkin_input
        new_checkout = new_checkin + timedelta(days=1)
        st.session_state.res_checkout = new_checkout

    # === FECHA CHECK-IN / CHECK-OUT ===
    st.markdown("#### 📅 Fechas de Estadía")
    col_in, col_out = st.columns(2)
    with col_in:
        check_in = st.date_input(
            "📥 Check-in (Entrada)",
            value=st.session_state.res_checkin,
            min_value=date.today() if mode_res == "Nueva Reserva" else None,
            help="Fecha de llegada del huésped",
            key="checkin_input",
            on_change=update_checkout_on_checkin_change
        )
    with col_out:
        checkout_min = check_in + timedelta(days=1)
        checkout_value = max(st.session_state.res_checkout, checkout_min)

        check_out = st.date_input(
            "📤 Check-out (Salida)",
            value=checkout_value,
            min_value=checkout_min,
            help="Fecha de salida del huésped",
            key="checkout_input"
        )

    # Calcular noches y mostrar info
    noches = (check_out - check_in).days
    if noches > 0:
        st.info(f"🌙 **{noches} noche{'s' if noches > 1 else ''}** ({check_in.strftime('%d/%m/%Y')} → {check_out.strftime('%d/%m/%Y')})")
    elif noches <= 0:
        st.error("⚠️ La fecha de Check-out debe ser posterior a Check-in")

    st.markdown("---")

    # ==============================================================
    # OUTSIDE FORM: Client Type + Room Selection + Dynamic Pricing
    # These are outside so changes trigger immediate rerun
    # ==============================================================

    # === CLIENT TYPE SELECTION (outside form for dynamic pricing) ===
    st.markdown("#### 🏷️ Tipo de Cliente")
    client_types = get_client_types()
    client_type_options = {ct['name']: ct for ct in client_types}
    client_type_names = list(client_type_options.keys())

    default_ct_idx = 0
    if "Particular" in client_type_options:
        default_ct_idx = client_type_names.index("Particular")

    selected_ct_name = st.selectbox(
        "🏷️ Tipo de Cliente",
        options=client_type_names,
        index=default_ct_idx if client_types else 0,
        help="Define descuentos y reglas de precio",
        key="client_type_select",
        label_visibility="collapsed"
    )
    selected_client_type = client_type_options.get(selected_ct_name, {})
    client_type_id = selected_client_type.get('id')

    st.markdown("---")

    # === SEASON OVERRIDE (manual selection) ===
    st.markdown("#### 📅 Temporada")
    all_seasons = get_seasons()
    season_labels = ["🔄 Automática (según fecha)"]
    season_map = {}  # label -> season dict
    for s in all_seasons:
        pct = (s["price_modifier"] - 1.0) * 100
        mod_str = f"+{pct:.0f}%" if pct > 0 else (f"{pct:.0f}%" if pct < 0 else "base")
        label = f"{s['name']} ({mod_str})"
        season_labels.append(label)
        season_map[label] = s

    selected_season_label = st.selectbox(
        "📅 Override de Temporada",
        options=season_labels,
        index=0,
        help="Seleccione manualmente una temporada o deje 'Automática' para detección por fecha",
        key="season_select",
        label_visibility="collapsed"
    )
    selected_season = season_map.get(selected_season_label)
    season_id = selected_season["id"] if selected_season else None

    st.markdown("---")

    # === ROOM SELECTION: ALL rooms grouped by category (outside form) ===
    st.markdown("#### 🚪 Selección de Habitaciones")

    check_in_str = check_in.strftime("%Y-%m-%d")
    check_out_str = check_out.strftime("%Y-%m-%d")

    # Fetch ALL available rooms (no category filter)
    available_rooms = get_available_rooms_for_dates(check_in_str, check_out_str)

    # Build room lookup and group by category
    room_info_map = {}  # display_name -> {id, category_id, category_name}
    rooms_by_category = {}
    for r in available_rooms:
        display = r.get("internal_code") or r["id"]
        cat_name = r.get("category_name", "Sin Categoría")
        cat_id = r.get("category_id", "")
        cat = cat_lookup.get(cat_id, {})
        base_price = cat.get("base_price", r.get("base_price", 0))

        room_info_map[display] = {
            "id": r["id"],
            "category_id": cat_id,
            "category_name": cat_name,
            "base_price": base_price
        }

        if cat_name not in rooms_by_category:
            rooms_by_category[cat_name] = {
                "category_id": cat_id,
                "base_price": base_price,
                "max_capacity": cat.get("max_capacity", r.get("max_capacity", 0)),
                "rooms": []
            }
        rooms_by_category[cat_name]["rooms"].append(display)

    # Show rooms grouped by category with multiselect per group
    all_selected_displays = []

    if rooms_by_category:
        for cat_name, cat_data in rooms_by_category.items():
            price_str = f"{cat_data['base_price']:,.0f}" if cat_data['base_price'] else "N/A"
            room_list = cat_data["rooms"]

            # Pre-select rooms from loaded reservation
            default_for_cat = []
            if d_habs:
                for display_name in room_list:
                    room_id = room_info_map[display_name]["id"]
                    if room_id in d_habs or display_name in d_habs:
                        default_for_cat.append(display_name)

            with st.expander(
                f"🛏️ {cat_name} — {price_str} Gs/noche (máx {cat_data['max_capacity']} pers.) — {len(room_list)} disponibles",
                expanded=True
            ):
                # Show category description if available
                cat_detail = cat_lookup.get(cat_data.get("category_id", ""), {})
                cat_desc = cat_detail.get("description", "")
                if cat_desc:
                    st.caption(cat_desc)
                picked = st.multiselect(
                    f"Seleccionar habitaciones de {cat_name}",
                    room_list,
                    default=default_for_cat,
                    key=f"rooms_{cat_name}",
                    label_visibility="collapsed"
                )
                all_selected_displays.extend(picked)
    else:
        # Fallback: no categories, show legacy list
        all_rooms = get_all_rooms_list()
        room_options = [r["internal_code"] or r["id"] for r in all_rooms] if all_rooms else LISTA_HABITACIONES_LEGACY
        picked = st.multiselect(
            "Seleccionar Habitaciones",
            room_options,
            default=[h for h in d_habs if h in room_options],
            help="Seleccione una o más habitaciones para esta reserva"
        )
        all_selected_displays = picked

    # Resolve display names to room IDs and build category groups
    habs = []
    habs_by_category = {}  # category_id -> [room_id, ...]
    for display in all_selected_displays:
        info = room_info_map.get(display)
        if info:
            habs.append(info["id"])
            cat_id = info["category_id"]
            if cat_id not in habs_by_category:
                habs_by_category[cat_id] = []
            habs_by_category[cat_id].append(info["id"])
        else:
            habs.append(display)

    if habs:
        st.success(f"✅ {len(habs)} habitación(es) seleccionada(s)")
    else:
        st.warning("⚠️ Debe seleccionar al menos una habitación")

    st.markdown("---")

    # === DYNAMIC PRICING (outside form, per-category) ===
    st.markdown("#### 💰 Precio Dinámico")

    breakdown_json = "{}"
    precio_calculado = 0.0
    all_breakdowns = {}  # category_id -> price_data

    if noches > 0 and habs and habs_by_category:
        try:
            total_price = 0.0
            receipt_rows = []

            for cat_id, cat_room_ids in habs_by_category.items():
                cat_info = cat_lookup.get(cat_id, {})
                prop_id = cat_info.get("property_id", "los-monges")
                cat_name = cat_info.get("name", cat_id)

                price_data = PricingService.calculate_price(
                    property_id=prop_id,
                    category_id=cat_id,
                    check_in=check_in,
                    stay_days=noches,
                    client_type_id=client_type_id,
                    season_id=season_id
                )

                all_breakdowns[cat_id] = price_data
                unit_price = price_data.get("final_price", 0)
                breakdown = price_data.get("breakdown", {})
                cat_total = unit_price * len(cat_room_ids)
                total_price += cat_total

                # Build receipt rows for this category
                receipt_rows.append(
                    f"| **{cat_name}** | {breakdown.get('base_unit_price', 0):,.0f} x {noches} noches | {breakdown.get('base_total', 0):,.0f} |"
                )
                for mod in breakdown.get('modifiers', []):
                    receipt_rows.append(
                        f"| ↳ {mod['name']} | {mod['percent']:+.0f}% | {mod['amount']:+,.0f} |"
                    )
                receipt_rows.append(
                    f"| ↳ **Subtotal** ({len(cat_room_ids)} hab.) | {unit_price:,.0f} x {len(cat_room_ids)} | **{cat_total:,.0f}** |"
                )

            # Show receipt table
            receipt_md = "| Concepto | Detalle | Monto (Gs) |\n| :--- | :--- | :--- |\n"
            receipt_md += "\n".join(receipt_rows)
            st.markdown(receipt_md)

            st.info(f"💵 **Total General ({len(habs)} habitaciones, {noches} noches): {total_price:,.0f} Gs**")

            precio_calculado = total_price
            breakdown_json = json.dumps(all_breakdowns)

        except Exception as e:
            logger.error(f"Pricing Error: {e}")
            st.error("Error calculando precio dinámico. Ingrese precio manualmente.")
    else:
        if not habs:
            st.caption("Seleccione habitaciones para ver el precio calculado.")

    st.markdown("---")

    # ==============================================================
    # INSIDE FORM: Guest info, parking, manual price override, submit
    # ==============================================================

    with st.form("form_reserva", clear_on_submit=(mode_res == "Nueva Reserva")):
        st.markdown("#### 👤 Datos del Huésped")

        c1, c2 = st.columns(2)
        with c1:
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

            c_tel_email = st.columns(2)
            tel = c_tel_email[0].text_input("📞 Teléfono", value=d_tel)
            email_input = c_tel_email[1].text_input("📧 Email", value=d_email, placeholder="correo@ejemplo.com")
            reservado = st.text_input("📝 Reservado Por", value=d_reservado)

        with c2:
            hora = st.time_input("🕐 Hora Llegada", value=d_hora)

            st.markdown("##### 🚗 Estacionamiento y Origen")
            source_options = ["Direct", "Booking.com", "Airbnb", "Walk-in", "Whatsapp", "Facebook", "Instagram", "Google", "Telefónica"]
            source_index = 0
            if d_source in source_options:
                source_index = source_options.index(d_source)

            source = st.selectbox("Origen Reserva", options=source_options, index=source_index)
            parking = st.checkbox("Requiere Parking", value=d_parking)
            v_model = st.text_input("Modelo Vehículo", value=d_vehicle_model, help="Opcional")
            v_plate = st.text_input("Chapa/Patente", value=d_vehicle_plate, help="Opcional")

        st.markdown("---")

        # Manual price override
        if precio_calculado > 0:
            price_key = f"price_input_{int(precio_calculado)}"
            precio = st.number_input(
                "💰 Precio Final (Confirmar o Ajustar)",
                step=10000.0,
                value=float(precio_calculado),
                min_value=0.0,
                help="El precio calculado incluye temporada y descuentos. Puede ajustar manualmente.",
                key=price_key
            )
        else:
            precio = st.number_input("💰 Precio Total", step=10000.0, value=d_precio, min_value=0.0)

        recibido = st.session_state.user.username

        st.markdown("---")

        # Payment status (only for new reservations)
        if not res_id_load:
            paid_option = st.radio(
                "💰 ¿El huesped ya pago?",
                options=["Si, pagado (Confirmada)", "No, pendiente (Pendiente)"],
                index=0,
                horizontal=True,
                key="paid_radio"
            )
            is_paid = paid_option.startswith("Si")
        else:
            is_paid = True  # Updates keep existing status

        btn_txt = "🔄 Actualizar Reserva" if res_id_load else "✅ Guardar Reserva"

        if st.form_submit_button(btn_txt, type="primary", width="stretch"):
            # === VALIDACIONES ===
            has_errors = False

            if check_out <= check_in:
                st.error("❌ Error: La fecha de Check-out debe ser posterior a Check-in")
                has_errors = True

            if not nombre or len(nombre.strip()) < 2:
                st.error("❌ Error: Debe ingresar el nombre del huésped (mínimo 2 caracteres)")
                has_errors = True

            if not habs:
                st.error("❌ Error: Debe seleccionar al menos una habitación")
                has_errors = True

            if not has_errors:
                try:
                    arrival_dt = hora
                    estadia = (check_out - check_in).days

                    if res_id_load:
                        # === MODO EDICIÓN ===
                        # Use first room's category for backwards compatibility
                        first_cat_id = next(iter(habs_by_category), None) if habs_by_category else None
                        first_cat_name = cat_lookup.get(first_cat_id, {}).get("name", "") if first_cat_id else ""

                        # FEAT-LINK-01: Prepare identity fields from scanned document
                        birth_date_parsed = None
                        if ia_data.get("Fecha_Nacimiento"):
                            try:
                                birth_date_parsed = datetime.strptime(ia_data.get("Fecha_Nacimiento"), "%Y-%m-%d").date()
                            except:
                                pass

                        data = ReservationCreate(
                            check_in_date=check_in,
                            stay_days=estadia,
                            guest_name=nombre,
                            room_ids=habs,
                            room_type=first_cat_name,
                            price=precio,
                            arrival_time=arrival_dt,
                            reserved_by=reservado,
                            contact_phone=tel,
                            contact_email=email_input,
                            received_by=recibido,
                            category_id=first_cat_id,
                            client_type_id=client_type_id,
                            price_breakdown=breakdown_json,
                            parking_needed=parking,
                            vehicle_model=v_model,
                            vehicle_plate=v_plate,
                            source=source,
                            # Identity fields from document scan (FEAT-LINK-01)
                            document_number=ia_data.get("Nro_Documento", ""),
                            guest_last_name=ia_data.get("Apellidos", ""),
                            guest_first_name=ia_data.get("Nombres", ""),
                            nationality=ia_data.get("Nacionalidad", ""),
                            birth_date=birth_date_parsed,
                            country=ia_data.get("Pais", "")
                        )
                        if ReservationService.update_reservation(res_id_load, data):
                            force_refresh()
                            st.success(f"✅ Reserva {res_id_load} actualizada. Actualizando calendario...")
                            st.rerun()
                        else:
                            st.error("Error al actualizar")
                    else:
                        # === MODO CREACIÓN ===
                        st.markdown("#### 📊 Procesando reservas...")
                        progress_bar = st.progress(0)
                        created_ids = []
                        errors = []

                        # FEAT-LINK-01: Prepare identity fields from scanned document
                        birth_date_parsed = None
                        if ia_data.get("Fecha_Nacimiento"):
                            try:
                                birth_date_parsed = datetime.strptime(ia_data.get("Fecha_Nacimiento"), "%Y-%m-%d").date()
                            except:
                                pass

                        for i, room_id in enumerate(habs):
                            try:
                                # Resolve this room's category
                                room_cat_id = None
                                room_cat_name = ""
                                for display, info in room_info_map.items():
                                    if info["id"] == room_id:
                                        room_cat_id = info["category_id"]
                                        room_cat_name = info["category_name"]
                                        break

                                data = ReservationCreate(
                                    check_in_date=check_in,
                                    stay_days=estadia,
                                    guest_name=nombre,
                                    room_ids=[room_id],
                                    room_type=room_cat_name or "",
                                    price=precio / len(habs),
                                    arrival_time=arrival_dt,
                                    reserved_by=reservado,
                                    contact_phone=tel,
                                    contact_email=email_input,
                                    received_by=recibido,
                                    category_id=room_cat_id,
                                    client_type_id=client_type_id,
                                    price_breakdown=breakdown_json,
                                    parking_needed=parking,
                                    vehicle_model=v_model,
                                    vehicle_plate=v_plate,
                                    source=source,
                                    paid=is_paid,
                                    # Identity fields from document scan (FEAT-LINK-01)
                                    document_number=ia_data.get("Nro_Documento", ""),
                                    guest_last_name=ia_data.get("Apellidos", ""),
                                    guest_first_name=ia_data.get("Nombres", ""),
                                    nationality=ia_data.get("Nacionalidad", ""),
                                    birth_date=birth_date_parsed,
                                    country=ia_data.get("Pais", "")
                                )

                                ids = ReservationService.create_reservations(data)
                                created_ids.extend(ids)
                                # Show friendly room name
                                room_display = next((d for d, info in room_info_map.items() if info["id"] == room_id), room_id)
                                st.success(f"✅ Habitación {room_display} reservada (ID: {ids[0]})")

                            except Exception as room_error:
                                room_display = next((d for d, info in room_info_map.items() if info["id"] == room_id), room_id)
                                errors.append(f"Habitación {room_display}: {room_error}")
                                st.error(f"❌ Habitación {room_display}: {room_error}")

                            progress_bar.progress((i + 1) / len(habs))

                        # Resumen final
                        st.markdown("---")
                        if created_ids:
                            # Auto-generate PDF confirmations
                            from services import DocumentService
                            from services.document_service import RESERVAS_DIR
                            import os

                            pdf_paths = {}
                            for rid in created_ids:
                                try:
                                    path = DocumentService.generate_reservation_pdf(rid)
                                    if path and os.path.exists(path):
                                        pdf_paths[rid] = path
                                except Exception as pdf_err:
                                    logger.warning(f"PDF generation failed for {rid}: {pdf_err}")

                            force_refresh()
                            status_text = "Confirmada" if is_paid else "Pendiente"
                            st.success(f"🎉 **{len(created_ids)} reserva(s) creada(s) — Estado: {status_text}**")
                            st.info(f"IDs: {', '.join(created_ids)}")
                            logger.info(f"Reservas creadas: {created_ids} por {recibido}")

                            # PDF download buttons
                            if pdf_paths:
                                st.markdown("#### 📄 Documentos generados")
                                for rid, path in pdf_paths.items():
                                    with open(path, "rb") as f:
                                        st.download_button(
                                            f"📥 Descargar PDF — Reserva {rid}",
                                            data=f.read(),
                                            file_name=os.path.basename(path),
                                            mime="application/pdf",
                                            key=f"pdf_dl_{rid}",
                                            width="stretch"
                                        )

                        if errors:
                            st.warning(f"⚠️ Hubo {len(errors)} error(es) durante el proceso")

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
            df_res = pd.DataFrame([r.model_dump() for r in all_res])
            if "room_internal_code" in df_res.columns:
                df_res = df_res[["id", "guest_name", "check_in", "status", "room_internal_code"]]
                df_res = df_res.rename(columns={"room_internal_code": "habitacion"})
            else:
                df_res = df_res[["id", "guest_name", "check_in", "status", "room_id"]]
            st.dataframe(df_res, hide_index=True)
        else:
            st.info("No hay reservas registradas.")
