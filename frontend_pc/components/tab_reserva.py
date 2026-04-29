import streamlit as st
import pandas as pd
import json
from datetime import datetime, date, timedelta
from pydantic import ValidationError

from logging_config import get_logger
from services import ReservationService, GuestService, PricingService, ReservationCreate
from helpers.constants import LISTA_TIPOS_LEGACY, LISTA_HABITACIONES_LEGACY
from helpers.data_fetchers import (
    get_room_categories,
    get_available_rooms_for_dates,
    get_all_rooms_list,
    get_client_types,
    get_seasons,
    get_meals_config,
    get_meal_plans,
)
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
    d_vehicle_color = ""  # v1.10.0 Phase 2a-ext
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
    room_info_map = {}  # display_name -> {id, category_id, category_name, max_capacity}
    rooms_by_category = {}
    for r in available_rooms:
        display = r.get("internal_code") or r["id"]
        cat_name = r.get("category_name", "Sin Categoría")
        cat_id = r.get("category_id", "")
        cat = cat_lookup.get(cat_id, {})
        base_price = cat.get("base_price", r.get("base_price", 0))
        # Effective room capacity — used by the meal-plan selector to cap the
        # "huéspedes con desayuno" input. Falls back to category capacity when
        # the room has no per-room override.
        room_capacity = (
            r.get("custom_capacity")
            or r.get("max_capacity")
            or cat.get("max_capacity", 0)
            or 0
        )

        room_info_map[display] = {
            "id": r["id"],
            "category_id": cat_id,
            "category_name": cat_name,
            "base_price": base_price,
            "max_capacity": room_capacity,
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

    # Total capacity across selected rooms — bounds the "breakfast guests"
    # input (a hotel can never serve breakfast to more people than the rooms
    # can hold). Defaults to a generous 10 when no room is yet selected so
    # the input remains usable while the form is half-complete.
    total_room_capacity = sum(
        info.get("max_capacity", 0) or 0
        for display in all_selected_displays
        for info in [room_info_map.get(display)]
        if info
    ) or 10

    st.markdown("---")

    # ==============================================================
    # OUTSIDE FORM: Meal Plan selector (v1.7.0 — Phase 4)
    # Renders ONLY when the hotel has meals enabled AND the mode is not
    # INCLUIDO (in INCLUIDO mode the backend auto-assigns CON_DESAYUNO and
    # the user picks nothing). Mirrors the mobile reservation form.
    # ==============================================================
    meals_cfg = get_meals_config()
    meals_enabled = bool(meals_cfg.get("meals_enabled"))
    meal_mode = meals_cfg.get("meal_inclusion_mode")

    selected_meal_plan_id: str | None = None
    breakfast_guests_value: int | None = None

    if meals_enabled and meal_mode and meal_mode != "INCLUIDO":
        st.markdown("#### 🍽️ Plan de comidas")
        st.caption(
            "Solo se muestra para hoteles que cobran las comidas aparte. "
            "Elegí 'Solo habitación' para no cobrar plan."
        )

        plans_for_mode = get_meal_plans(mode_filter=meal_mode)
        active_plans = [p for p in plans_for_mode if p.get("is_active")]
        # SOLO_HABITACION is conceptually "no plan" in the UI — treat the
        # blank option as the explicit no-plan choice and hide it from the
        # dropdown body.
        non_solo = [p for p in active_plans if p.get("code") != "SOLO_HABITACION"]

        plan_labels = ["Solo habitación (sin comidas)"]
        plan_label_to_id: dict[str, str | None] = {plan_labels[0]: None}
        for p in non_solo:
            if meal_mode == "OPCIONAL_PERSONA" and (p.get("surcharge_per_person") or 0) > 0:
                price_str = f" — {int(p['surcharge_per_person']):,} Gs/pax/noche"
            elif meal_mode == "OPCIONAL_HABITACION" and (p.get("surcharge_per_room") or 0) > 0:
                price_str = f" — {int(p['surcharge_per_room']):,} Gs/hab/noche"
            else:
                price_str = ""
            label = f"{p['name']}{price_str}"
            plan_labels.append(label)
            plan_label_to_id[label] = p["id"]

        # Pre-select the existing plan when editing a reservation. Falls back
        # to "no plan" when the saved id no longer exists (plan deactivated).
        existing_plan_id = getattr(res_data, "meal_plan_id", None) if res_data else None
        existing_breakfast_guests = (
            getattr(res_data, "breakfast_guests", None) if res_data else None
        )
        default_idx = 0
        if existing_plan_id:
            for idx, lbl in enumerate(plan_labels):
                if plan_label_to_id.get(lbl) == existing_plan_id:
                    default_idx = idx
                    break

        meal_col_a, meal_col_b = st.columns([3, 2])
        with meal_col_a:
            picked_plan_label = st.selectbox(
                "Plan",
                options=plan_labels,
                index=default_idx,
                key="meal_plan_select",
                help="El recargo aparece en el desglose de precios al confirmar la reserva.",
            )
        selected_meal_plan_id = plan_label_to_id.get(picked_plan_label)

        # breakfast_guests input — only relevant in OPCIONAL_PERSONA mode AND
        # when a non-SOLO plan is picked. Capped by total selected-room
        # capacity (defense-in-depth: backend rejects with a Spanish error
        # if a caller bypasses this UI).
        if selected_meal_plan_id and meal_mode == "OPCIONAL_PERSONA":
            cap = max(int(total_room_capacity), 1)
            default_pax = (
                min(int(existing_breakfast_guests or 1), cap)
                if existing_breakfast_guests
                else 1
            )
            with meal_col_b:
                breakfast_guests_value = st.number_input(
                    "Huéspedes con desayuno",
                    min_value=1,
                    max_value=cap,
                    value=default_pax,
                    step=1,
                    key="meal_breakfast_guests",
                    help=(
                        f"Máximo {cap} (capacidad total de las habitaciones "
                        f"seleccionadas)."
                    ),
                )
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
                    season_id=season_id,
                    # v1.7.0 — Meal plan surcharge (Phase 4)
                    # Pass-through; the engine reads the hotel's mode and only
                    # adds a modifier line when the plan + mode combination
                    # actually charges (OPCIONAL_PERSONA / OPCIONAL_HABITACION).
                    meal_plan_id=selected_meal_plan_id,
                    breakfast_guests=breakfast_guests_value,
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
    # OUTSIDE FORM: Guest picker (Phase 2a Bug #2 Fix A)
    # Lives outside the form so picking a guest can rerun and pre-fill
    # the contact fields with the master Guest's data. The picked
    # `guest_id` is passed to ReservationCreate so the backend skips the
    # fuzzy find_or_create resolution.
    # ==============================================================
    st.markdown("#### 👤 Huésped")
    st.caption(
        "Buscá entre los huéspedes registrados. Si es nuevo, dejá vacío el "
        "selector y escribí el nombre dentro del formulario."
    )

    # Cache the dropdown list per-render (Streamlit reruns frequently; the
    # query is fast but no need to repeat within the same script execution).
    if "_guest_dropdown_cache" not in st.session_state:
        try:
            st.session_state["_guest_dropdown_cache"] = (
                GuestService.list_guests_for_dropdown(property_id="los-monges")
            )
        except Exception as _e:
            logger.warning(f"Guest dropdown fetch failed: {_e}")
            st.session_state["_guest_dropdown_cache"] = []
    guest_options = st.session_state["_guest_dropdown_cache"]

    # Try to pre-select the current reservation's linked guest when editing.
    if res_id_load and "_picked_guest_id" not in st.session_state:
        try:
            res_full = ReservationService.get_reservation_detail(res_id_load)
            picked_guest_id = getattr(res_full, "guest_id", None) if res_full else None
            if picked_guest_id:
                st.session_state["_picked_guest_id"] = picked_guest_id
        except Exception:
            pass

    label_to_id = {"(crear huésped nuevo)": None}
    id_to_item = {}
    for item in guest_options:
        label_to_id[item["label"]] = item["id"]
        id_to_item[item["id"]] = item

    # Pre-select current pick if present
    current_label = "(crear huésped nuevo)"
    _picked = st.session_state.get("_picked_guest_id")
    if _picked and _picked in id_to_item:
        current_label = id_to_item[_picked]["label"]

    label_options = list(label_to_id.keys())
    try:
        cur_idx = label_options.index(current_label)
    except ValueError:
        cur_idx = 0

    picked_label = st.selectbox(
        "Seleccionar huésped existente",
        options=label_options,
        index=cur_idx,
        key="_guest_picker_select",
        help="Los huéspedes están ordenados por cantidad de estadías previas.",
    )
    picked_guest_id = label_to_id.get(picked_label)
    st.session_state["_picked_guest_id"] = picked_guest_id

    # Show context for the picked guest + clear button
    if picked_guest_id:
        item = id_to_item[picked_guest_id]
        meta = []
        if item.get("document_number"):
            meta.append(f"Doc {item['document_number']}")
        if item.get("phone"):
            meta.append(f"📞 {item['phone']}")
        if item.get("email"):
            meta.append(f"✉️ {item['email']}")
        meta.append(f"{item.get('total_stays', 0)} estadía/s")
        st.success(f"✓ {item['label']}  ·  " + "  ·  ".join(meta))
        if st.button("🗑️ Limpiar selección", key="_clear_guest_picker"):
            st.session_state["_picked_guest_id"] = None
            st.session_state["_guest_picker_select"] = "(crear huésped nuevo)"
            st.rerun()

    # Compute defaults that the in-form widgets will use.
    if picked_guest_id:
        item = id_to_item[picked_guest_id]
        ln = (item.get("last_name") or "").strip()
        fn = (item.get("first_name") or "").strip()
        d_nomb = f"{ln}, {fn}".strip(", ")
        # Only override blank defaults — preserve any user-entered or
        # OCR-loaded values from above (e.g. document scan flow).
        if not d_tel:
            d_tel = item.get("phone") or ""
        if not d_email:
            d_email = item.get("email") or ""

    st.markdown("---")

    # ==============================================================
    # INSIDE FORM: Guest info, parking, manual price override, submit
    # ==============================================================

    with st.form("form_reserva", clear_on_submit=(mode_res == "Nueva Reserva")):
        st.markdown("#### 📝 Datos de la reserva")

        c1, c2 = st.columns(2)
        with c1:
            # Name field — editable. If picker is active, defaults to picked
            # guest's "Apellido, Nombre"; otherwise the existing default.
            nombre = st.text_input(
                "A Nombre De",
                value=d_nomb,
                placeholder="Apellido, Nombre",
                help=(
                    "Si seleccionaste un huésped arriba, este campo se completa solo. "
                    "Podés editarlo libremente — el snapshot del nombre queda guardado "
                    "en la reserva."
                ),
            )

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
            # v1.10.0 Phase 2a-ext: color → propagates a master GuestVehicle on save.
            # Habilita el lookup "¿de quién es el auto blanco?" + futuro OCR.
            v_color = st.text_input(
                "Color del Vehículo",
                value=d_vehicle_color,
                placeholder="Blanco, Negro, Rojo...",
                help="Se guarda en el catálogo del huésped (visible en Huéspedes → Vehículos).",
            )

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
                            vehicle_color=v_color or None,
                            source=source,
                            # v1.7.0 — Meal Plan (Phase 4)
                            meal_plan_id=selected_meal_plan_id,
                            breakfast_guests=breakfast_guests_value,
                            # Identity fields from document scan (FEAT-LINK-01)
                            document_number=ia_data.get("Nro_Documento", ""),
                            guest_last_name=ia_data.get("Apellidos", ""),
                            guest_first_name=ia_data.get("Nombres", ""),
                            nationality=ia_data.get("Nacionalidad", ""),
                            birth_date=birth_date_parsed,
                            country=ia_data.get("Pais", ""),
                            # v1.10.0 Phase 2a Bug #2 Fix A: explicit Guest link
                            guest_id=picked_guest_id,
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
                                    vehicle_color=v_color or None,
                                    source=source,
                                    paid=is_paid,
                                    # v1.7.0 — Meal Plan (Phase 4)
                                    meal_plan_id=selected_meal_plan_id,
                                    breakfast_guests=breakfast_guests_value,
                                    # Identity fields from document scan (FEAT-LINK-01)
                                    document_number=ia_data.get("Nro_Documento", ""),
                                    guest_last_name=ia_data.get("Apellidos", ""),
                                    guest_first_name=ia_data.get("Nombres", ""),
                                    nationality=ia_data.get("Nacionalidad", ""),
                                    birth_date=birth_date_parsed,
                                    country=ia_data.get("Pais", ""),
                                    # v1.10.0 Phase 2a Bug #2 Fix A: explicit Guest link
                                    guest_id=picked_guest_id,
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
                            # Phase 2a Bug #2 Fix A: clear the picker cache so
                            # the next reservation form load fetches a fresh
                            # list (which now includes any guest just created
                            # via find_or_create from this booking).
                            for k in ("_guest_dropdown_cache", "_picked_guest_id", "_guest_picker_select"):
                                st.session_state.pop(k, None)
                            status_text = "Confirmada" if is_paid else "Pendiente"
                            st.success(f"🎉 **{len(created_ids)} reserva(s) creada(s) — Estado: {status_text}**")
                            st.info(f"IDs: {', '.join(created_ids)}")
                            logger.info(f"Reservas creadas: {created_ids} por {recibido}")

                            # Store PDF paths in session_state — download_button can't
                            # be rendered inside st.form(), so we defer to outside
                            if pdf_paths:
                                st.session_state["_last_pdf_paths"] = pdf_paths

                        if errors:
                            st.warning(f"⚠️ Hubo {len(errors)} error(es) durante el proceso")

                except ValidationError as e:
                    st.error(_format_validation_error(e))
                except ValueError as e:
                    st.error(f"Error de datos: {e}")
                except Exception as e:
                    logger.error(f"Error inesperado al guardar reserva: {e}", exc_info=True)
                    st.error("Ocurrió un error inesperado. Contacte al soporte.")

    # PDF download buttons — OUTSIDE st.form (Streamlit forbids download_button inside forms)
    if "_last_pdf_paths" in st.session_state:
        import os
        _pdf_paths = st.session_state.pop("_last_pdf_paths")
        st.markdown("#### 📄 Documentos generados")
        for rid, path in _pdf_paths.items():
            if os.path.exists(path):
                with open(path, "rb") as f:
                    st.download_button(
                        f"📥 Descargar PDF — Reserva {rid}",
                        data=f.read(),
                        file_name=os.path.basename(path),
                        mime="application/pdf",
                        key=f"pdf_dl_{rid}",
                    )

    # ==========================================
    # ENVIAR POR CORREO (v1.8.0 — Phase 5)
    # Only shown in Editar Reserva mode after a reservation is loaded
    # ==========================================
    if res_data and res_id_load:
        st.divider()
        st.markdown("### 📧 Enviar confirmación por correo")

        from api_client import send_reservation_email, get_email_history, get_smtp_config

        _token = st.session_state.get("api_token", "")
        history = get_email_history(res_id_load, _token) if _token else []

        # Probe SMTP config so we can disable the send button BEFORE the user
        # clicks (ui-ux-pro-max rule: disabled-states + error-recovery — show
        # the recovery path next to the disabled control).
        # Recepcion role gets 403 on /settings/email; treat as "unknown" → keep
        # the button enabled (backend will still reject with a Spanish 400).
        _smtp_state = get_smtp_config(_token) if _token else {}
        _smtp_ready = bool(_smtp_state.get("smtp_enabled")) and bool(_smtp_state.get("smtp_password_set"))
        _smtp_state_known = bool(_smtp_state)  # empty dict if 403/401/network error

        if history:
            last = history[0]
            status_map = {"ENVIADO": "✅", "FALLIDO": "❌", "PENDIENTE": "⏳"}
            badge = status_map.get(last.get("status", ""), "·")
            sent_at = (last.get("sent_at") or last.get("created_at") or "")[:16].replace("T", " ")
            st.caption(
                f"Último envío: {sent_at} → {last.get('recipient_email', '')} {badge} {last.get('status', '')}"
            )
        else:
            st.caption("Aún no se ha enviado ningún correo para esta reserva.")

        existing_email = getattr(res_data, "contact_email", "") or ""
        _email_col1, _email_col2 = st.columns([3, 1])
        with _email_col1:
            email_override = st.text_input(
                "Email destinatario",
                value=existing_email,
                key=f"email_override_{res_id_load}",
                placeholder="guest@email.com",
                disabled=(_smtp_state_known and not _smtp_ready),
            )
        with _email_col2:
            st.write("")
            st.write("")
            _btn_disabled = _smtp_state_known and not _smtp_ready
            _btn_help = (
                "Activá el envío de emails en Configuración → 📧 Configuración de Correo."
                if _btn_disabled
                else None
            )
            if st.button(
                "📧 Enviar correo",
                key=f"send_email_btn_{res_id_load}",
                type="primary",
                disabled=_btn_disabled,
                help=_btn_help,
            ):
                if not email_override or "@" not in email_override:
                    st.error("Ingresá un email válido.")
                elif not _token:
                    st.error("Sesión expirada. Volvé a iniciar sesión.")
                else:
                    override = email_override if email_override != existing_email else None
                    with st.spinner("Enviando..."):
                        ok, msg = send_reservation_email(res_id_load, override, _token)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
        if _btn_disabled:
            st.caption(
                "ℹ️ El envío de emails está deshabilitado. Pedile a un Admin "
                "que lo active en **Configuración → Configuración de Correo**."
            )

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
