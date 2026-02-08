import streamlit as st
import pandas as pd
import json
from datetime import datetime, date, timedelta
from pydantic import ValidationError

from logging_config import get_logger
from services import ReservationService, GuestService, PricingService, ReservationCreate
from helpers.constants import LISTA_TIPOS_LEGACY, LISTA_HABITACIONES_LEGACY
from helpers.data_fetchers import get_room_categories, get_available_rooms_for_dates, get_all_rooms_list, get_client_types
from helpers.ui_helpers import _format_validation_error
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

    # Valores por defecto
    d_checkin = date.today()
    d_checkout = date.today() + timedelta(days=1)
    d_nomb = ""
    d_habs = []
    d_categoria_id = None
    d_tipo = ""
    d_precio = 0.0
    d_hora = datetime.strptime("12:00", "%H:%M").time()
    d_tel = ""
    d_reservado = ""
    d_parking = False
    d_vehicle_model = ""
    d_vehicle_plate = ""
    d_source = "Direct"
    d_external_id = ""

    # Load categories for selection
    all_categories = get_room_categories()
    if all_categories:
        d_tipo = all_categories[0]["name"]
        d_categoria_id = all_categories[0]["id"]

    if res_data:
        if res_data.check_in_date:
            d_checkin = res_data.check_in_date
            d_checkout = res_data.check_in_date + timedelta(days=res_data.stay_days)
        d_nomb = res_data.guest_name
        d_habs = res_data.room_ids
        d_tipo = res_data.room_type or d_tipo
        d_precio = res_data.price
        if res_data.arrival_time: d_hora = res_data.arrival_time.time()
        d_tel = res_data.contact_phone
        d_reservado = res_data.reserved_by
        d_parking = res_data.parking_needed
        d_vehicle_model = res_data.vehicle_model or ""
        d_vehicle_plate = res_data.vehicle_plate or ""
        d_source = res_data.source or "Direct"
        d_external_id = res_data.external_id or ""

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

    with st.form("form_reserva", clear_on_submit=(mode_res == "Nueva Reserva")):
        st.markdown("#### 👤 Datos del Huésped")

        c1, c2 = st.columns(2)
        with c1:
            # Buscador de Clientes
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

            tel = st.text_input("📞 Teléfono", value=d_tel)
            reservado = st.text_input("📝 Reservado Por", value=d_reservado)

        with c2:
            # === CLIENT TYPE SELECTION ===
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
                help="Define descuentos y reglas de precio"
            )
            selected_client_type = client_type_options.get(selected_ct_name, {})
            client_type_id = selected_client_type.get('id')

            hora = st.time_input("🕐 Hora Llegada", value=d_hora)

            st.markdown("##### 🚗 Estacionamiento y Origen")
            source_options = ["Direct", "Booking.com", "Airbnb", "Walk-in", "Whatsapp", "Telefónica"]
            source_index = 0
            if d_source in source_options:
                source_index = source_options.index(d_source)

            source = st.selectbox("Origen Reserva", options=source_options, index=source_index)
            parking = st.checkbox("Requiere Parking", value=d_parking)
            v_model = st.text_input("Modelo Vehículo", value=d_vehicle_model, help="Opcional")
            v_plate = st.text_input("Chapa/Patente", value=d_vehicle_plate, help="Opcional")

        st.markdown("---")
        st.markdown("#### 🏷️ Categoría y Habitaciones")

        # === CATEGORY SELECTION WITH PRICING ===
        if all_categories:
            cat_options = {
                f"{c['name']} - {c['base_price']:,.0f} Gs/noche (máx {c['max_capacity']} pers.)": c
                for c in all_categories
            }
            cat_labels = list(cat_options.keys())

            default_idx = 0
            for i, label in enumerate(cat_labels):
                if d_tipo in label:
                    default_idx = i
                    break

            selected_cat_label = st.selectbox(
                "🛏️ Categoría de Habitación",
                cat_labels,
                index=default_idx,
                help="Seleccione el tipo de habitación. El precio se calcula automáticamente."
            )
            selected_category = cat_options[selected_cat_label]
            tipo = selected_category["name"]
            categoria_id = selected_category["id"]
            precio_por_noche = selected_category["base_price"]
        else:
            tipo = st.selectbox("🛏️ Tipo de Habitación", LISTA_TIPOS_LEGACY, index=0)
            categoria_id = None
            precio_por_noche = 0

        # === AVAILABLE ROOMS FOR SELECTED CATEGORY ===
        st.markdown("#### 🚪 Selección de Habitaciones")

        check_in_str = check_in.strftime("%Y-%m-%d")
        check_out_str = check_out.strftime("%Y-%m-%d")

        if all_categories and categoria_id:
            available_rooms = get_available_rooms_for_dates(check_in_str, check_out_str, categoria_id)

            if available_rooms:
                room_options = [r["internal_code"] or r["id"] for r in available_rooms]
                room_id_map = {(r["internal_code"] or r["id"]): r["id"] for r in available_rooms}

                default_selection = [h for h in d_habs if h in room_options or h in room_id_map.values()]

                habs_display = st.multiselect(
                    f"Habitaciones Disponibles ({len(available_rooms)} disponibles)",
                    room_options,
                    default=[k for k, v in room_id_map.items() if v in default_selection] if default_selection else [],
                    help=f"Habitaciones de categoría '{tipo}' disponibles para las fechas seleccionadas"
                )

                habs = [room_id_map.get(h, h) for h in habs_display]
            else:
                st.warning(f"⚠️ No hay habitaciones disponibles de '{tipo}' para las fechas seleccionadas")
                habs = []
                habs_display = []
        else:
            all_rooms = get_all_rooms_list()
            room_options = [r["internal_code"] or r["id"] for r in all_rooms] if all_rooms else LISTA_HABITACIONES_LEGACY
            habs = st.multiselect(
                "Seleccionar Habitaciones",
                room_options,
                default=[h for h in d_habs if h in room_options],
                help="Seleccione una o más habitaciones para esta reserva"
            )

        if habs:
            st.success(f"✅ {len(habs)} habitación(es) seleccionada(s)")
        else:
            st.warning("⚠️ Debe seleccionar al menos una habitación")

        # === AUTO-CALCULATE PRICE (DYNAMIC) ===
        st.markdown("#### 💰 Precio (Dinámico)")

        breakdown_json = "{}"

        if categoria_id and noches > 0 and habs:
            prop_id = selected_category.get("property_id", "los-monges")

            try:
                price_data = PricingService.calculate_price(
                    property_id=prop_id,
                    category_id=categoria_id,
                    check_in=check_in,
                    stay_days=noches,
                    client_type_id=client_type_id
                )

                final_unit_price = price_data.get("final_price", 0)
                breakdown = price_data.get("breakdown", {})
                breakdown_json = json.dumps(breakdown)

                total_calculado = final_unit_price * len(habs)

                # Show Receipt
                receipt_md = f"""
                | Concepto | Detalle | Monto (Gs) |
                | :--- | :--- | :--- |
                | **Base** | {breakdown.get('base_unit_price', 0):,.0f} x {breakdown.get('nights', 0)} noches | {breakdown.get('base_total', 0):,.0f} |
                """

                for mod in breakdown.get('modifiers', []):
                    receipt_md += f"| {mod['name']} | {mod['percent']:+.0f}% | {mod['amount']:+,.0f} |\n"

                receipt_md += f"| **Final x Habitación** | | **{final_unit_price:,.0f}** |\n"

                st.markdown(receipt_md)

                if len(habs) > 1:
                     st.info(f"💵 **Total General ({len(habs)} habitaciones): {total_calculado:,.0f} Gs**")

                precio_calculado = total_calculado

            except Exception as e:
                logger.error(f"Pricing Error: {e}")
                st.error("Error calculando precio dinámico")
                precio_calculado = precio_por_noche * noches * len(habs)

            price_key = f"price_input_{int(precio_calculado)}"
            input_value = float(precio_calculado)

            precio = st.number_input(
                "💰 Precio Final (Confirmar)",
                step=10000.0,
                value=input_value,
                min_value=0.0,
                help="El precio calculado incluye temporada y descuentos. Puede ajustar manualmente si es necesario.",
                key=price_key
            )
        else:
            precio = st.number_input("💰 Precio Total", step=10000.0, value=d_precio, min_value=0.0)

        recibido = st.session_state.user.username

        st.markdown("---")
        btn_txt = "🔄 Actualizar Reserva" if res_id_load else "✅ Guardar Reserva"

        if st.form_submit_button(btn_txt, type="primary", use_container_width=True):
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
                    arrival_dt = datetime.combine(check_in, hora)
                    estadia = (check_out - check_in).days

                    if res_id_load:
                        # === MODO EDICIÓN ===
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
                            received_by=recibido,
                            category_id=categoria_id,
                            client_type_id=client_type_id,
                            price_breakdown=breakdown_json,
                            parking_needed=parking,
                            vehicle_model=v_model,
                            vehicle_plate=v_plate,
                            source=source
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

                        for i, room_id in enumerate(habs):
                            try:
                                data = ReservationCreate(
                                    check_in_date=check_in,
                                    stay_days=estadia,
                                    guest_name=nombre,
                                    room_ids=[room_id],
                                    room_type=tipo,
                                    price=precio / len(habs),
                                    arrival_time=arrival_dt,
                                    reserved_by=reservado,
                                    contact_phone=tel,
                                    received_by=recibido,
                                    category_id=categoria_id,
                                    client_type_id=client_type_id,
                                    price_breakdown=breakdown_json,
                                    parking_needed=parking,
                                    vehicle_model=v_model,
                                    vehicle_plate=v_plate,
                                    source=source
                                )

                                ids = ReservationService.create_reservations(data)
                                created_ids.extend(ids)
                                st.success(f"✅ Habitación {room_id} reservada (ID: {ids[0]})")

                            except Exception as room_error:
                                errors.append(f"Habitación {room_id}: {room_error}")
                                st.error(f"❌ Habitación {room_id}: {room_error}")

                            progress_bar.progress((i + 1) / len(habs))

                        # Resumen final
                        st.markdown("---")
                        if created_ids:
                            force_refresh()
                            st.success(f"🎉 **{len(created_ids)} reserva(s) creada(s) exitosamente**")
                            st.info(f"IDs: {', '.join(created_ids)}")
                            logger.info(f"Reservas creadas: {created_ids} por {recibido}")
                            st.balloons()
                            st.info("🔄 Actualizando calendario...")
                            st.rerun()

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
            df_res = df_res[["id", "guest_name", "check_in", "status", "room_id"]]
            st.dataframe(df_res, hide_index=True)
        else:
            st.info("No hay reservas registradas.")
