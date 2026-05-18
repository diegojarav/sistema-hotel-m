"""
Hotel Munich — Huéspedes (Guest Master) page
=============================================

Admin/recepción surface for the master Guest entity introduced in v1.10.0
Phase 2a. Distinct from "Documentos del Hotel" → Fichas, which manages the
per-stay registration records (CheckIn).

Features
--------
- Search by name / document / email / phone
- Paginated list of all guests for the current property
- Detail view: editable personal info + reservation history + aggregates
- Create-new-guest form (manual entry — most guests are auto-created via
  reservation/check-in flows)
"""

from __future__ import annotations

from datetime import datetime
import math
import requests
import streamlit as st

from logging_config import get_logger

logger = get_logger(__name__)

API_BASE_URL = "http://localhost:8000/api/v1"


# ==========================================
# PAGE CONFIG
# ==========================================
st.set_page_config(
    page_title="Huéspedes — Hotel Munich",
    page_icon="👥",
    layout="wide",
)
# SWB branding footer (fixed bottom, every page).
from components.styles import inject_swb_brand
inject_swb_brand()



# ==========================================
# AUTH GATE
# ==========================================
def _check_access():
    if not st.session_state.get("logged_in"):
        st.error("⛔ Debe iniciar sesión para acceder.")
        st.stop()
    user = st.session_state.get("user")
    if not user:
        st.error("⛔ Sesión inválida.")
        st.stop()
    role = (getattr(user, "role", "") or "").lower()
    if role not in ("admin", "supervisor", "gerencia", "recepcion", "recepcionista"):
        st.error("⛔ No tiene permisos para gestionar huéspedes.")
        st.stop()
    return user


def _auth_headers() -> dict:
    # IMPORTANT (BUG-TOKEN-PC-01): use `api_token`, NOT `access_token` — see CLAUDE.md.
    token = st.session_state.get("api_token")
    if not token:
        st.error("Token de sesión no disponible. Iniciá sesión nuevamente.")
        st.stop()
    return {"Authorization": f"Bearer {token}"}


# ==========================================
# API helpers
# ==========================================
def _api_get(path: str, **params):
    r = requests.get(f"{API_BASE_URL}{path}", headers=_auth_headers(), params=params, timeout=15)
    if r.status_code != 200:
        st.error(f"Error {r.status_code}: {r.text[:200]}")
        return None
    return r.json()


def _api_post(path: str, payload: dict):
    r = requests.post(f"{API_BASE_URL}{path}", headers=_auth_headers(), json=payload, timeout=15)
    if r.status_code not in (200, 201):
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        st.error(f"Error {r.status_code}: {detail}")
        return None
    return r.json()


def _api_put(path: str, payload: dict):
    r = requests.put(f"{API_BASE_URL}{path}", headers=_auth_headers(), json=payload, timeout=15)
    if r.status_code != 200:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        st.error(f"Error {r.status_code}: {detail}")
        return None
    return r.json()


def _api_delete(path: str):
    r = requests.delete(f"{API_BASE_URL}{path}", headers=_auth_headers(), timeout=15)
    if r.status_code != 200:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        st.error(f"Error {r.status_code}: {detail}")
        return None
    return r.json()


def _format_price(amount) -> str:
    try:
        return f"{float(amount or 0):,.0f} Gs"
    except Exception:
        return "0 Gs"


def _format_date(s: str | None) -> str:
    if not s:
        return "-"
    try:
        # API returns ISO date or datetime
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).strftime("%d/%m/%Y")
        return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except Exception:
        return s


# ==========================================
# MAIN PAGE
# ==========================================
user = _check_access()
st.markdown("# 👥 Huéspedes")
st.caption("Catálogo maestro de huéspedes — distinto de las fichas de check-in (que viven en *Documentos del Hotel*).")

# Search bar — drives the list view
search_q = st.text_input(
    "🔎 Buscar por nombre, apellido, documento, email o teléfono",
    key="huesped_search_q",
    placeholder="Mínimo 2 caracteres",
)

st.divider()

col_list, col_detail = st.columns([1.0, 1.6])

# ---- LEFT: list / search results ----
with col_list:
    st.markdown("### Resultados")
    if search_q and len(search_q.strip()) >= 2:
        results = _api_get("/huespedes/search", q=search_q.strip(), limit=50) or []
        st.caption(f"{len(results)} coincidencia(s)")
    else:
        page_size = 25
        # Fetch the count first so we can cap the page selector to the actual
        # number of pages (avoids landing on empty pages when the user types a
        # number above the last valid page).
        _count_probe = _api_get("/huespedes", skip=0, limit=1, active_only=True) or {"total": 0}
        total = _count_probe.get("total", 0)
        total_pages = max(1, math.ceil(total / page_size))
        # Reset stored page if the dataset shrank below the previously-selected page.
        _stored_page = int(st.session_state.get("huesped_page", 1))
        if _stored_page > total_pages:
            st.session_state["huesped_page"] = total_pages
        page = st.number_input(
            "Página",
            min_value=1,
            max_value=total_pages,
            value=min(_stored_page, total_pages),
            step=1,
            key="huesped_page",
            help=f"De 1 a {total_pages}",
        )
        listing = _api_get(
            "/huespedes",
            skip=(page - 1) * page_size,
            limit=page_size,
            active_only=True,
        ) or {"items": [], "total": 0}
        results = listing.get("items", [])
        if not results and total > 0:
            # Defensive: shouldn't happen with the cap above, but if a race
            # leaves us on an empty page, message instead of empty render.
            st.info("No hay más huéspedes en esta página. Volviendo a la página 1.")
        st.caption(
            f"Mostrando {(page - 1) * page_size + 1}–{(page - 1) * page_size + len(results)} "
            f"de {total} huéspedes activos · Página {page}/{total_pages}"
        )

    selected_id = None
    for g in results:
        last = g.get("last_name") or ""
        first = g.get("first_name") or ""
        doc = g.get("document_number") or ""
        stays = g.get("total_stays") or 0
        label = f"**{last}, {first}**"
        if doc:
            label += f"  ·  Doc {doc}"
        if stays:
            label += f"  ·  {stays} estadía/s"
        # Single-button per row for selection
        if st.button(label, key=f"sel_g_{g['id']}", use_container_width=True):
            st.session_state["huesped_selected_id"] = g["id"]
            selected_id = g["id"]

    selected_id = selected_id or st.session_state.get("huesped_selected_id")

    st.divider()
    with st.expander("➕ Crear huésped nuevo"):
        # Phase 2a Bug #2 Fix D: two-step create with duplicate-suspect warning.
        # The form captures the data; before INSERT we search for likely
        # duplicates (same doc OR same name) and show them with an "Usar este"
        # button. The user has to explicitly click "Crear de todos modos" to
        # bypass.
        with st.form("create_guest_form", clear_on_submit=False):
            c1, c2 = st.columns(2)
            with c1:
                fn = st.text_input("Nombres *", key="new_g_first")
                doc_t = st.text_input("Tipo de documento", placeholder="CI / DNI / Pasaporte", key="new_g_doctype")
                em = st.text_input("Email", key="new_g_email")
                nat = st.text_input("Nacionalidad", key="new_g_nat")
            with c2:
                ln = st.text_input("Apellidos *", key="new_g_last")
                doc_n = st.text_input("N° documento", key="new_g_docnum")
                ph = st.text_input("Teléfono", key="new_g_phone")
                country = st.text_input("País", key="new_g_country")
            notes = st.text_area("Notas internas", key="new_g_notes")
            check_btn = st.form_submit_button("Buscar duplicados y crear", type="primary")

        if check_btn:
            if not fn.strip() or not ln.strip():
                st.error("Nombres y apellidos son obligatorios.")
            else:
                # Probe for likely duplicates: same doc, or same name.
                suspects: list[dict] = []
                seen_ids: set[int] = set()

                def _add_suspects(query: str):
                    if not query:
                        return
                    found = _api_get("/huespedes/search", q=query, limit=10) or []
                    for hit in found:
                        if hit["id"] not in seen_ids:
                            suspects.append(hit)
                            seen_ids.add(hit["id"])

                if doc_n.strip():
                    _add_suspects(doc_n.strip())
                # Name search — try lastname (more selective than first name)
                _add_suspects(ln.strip())
                if em.strip():
                    _add_suspects(em.strip())

                if suspects:
                    st.session_state["_dupe_suspects"] = suspects
                    st.session_state["_dupe_pending_payload"] = {
                        "first_name": fn.strip(),
                        "last_name": ln.strip(),
                        "document_type": doc_t.strip() or None,
                        "document_number": doc_n.strip() or None,
                        "email": em.strip() or None,
                        "phone": ph.strip() or None,
                        "nationality": nat.strip() or None,
                        "country": country.strip() or None,
                        "notes": notes.strip() or None,
                    }
                else:
                    # No suspects → create directly
                    payload = {
                        "first_name": fn.strip(),
                        "last_name": ln.strip(),
                        "document_type": doc_t.strip() or None,
                        "document_number": doc_n.strip() or None,
                        "email": em.strip() or None,
                        "phone": ph.strip() or None,
                        "nationality": nat.strip() or None,
                        "country": country.strip() or None,
                        "notes": notes.strip() or None,
                    }
                    created = _api_post("/huespedes", payload)
                    if created:
                        st.success(f"✅ Huésped #{created['id']} creado.")
                        st.session_state["huesped_selected_id"] = created["id"]
                        st.rerun()

        # Render the suspect-resolution UI OUTSIDE the form (needs interactive
        # buttons, which Streamlit forbids inside a form).
        suspects = st.session_state.get("_dupe_suspects", [])
        pending = st.session_state.get("_dupe_pending_payload")
        if suspects and pending:
            st.warning(
                f"⚠️ Encontré {len(suspects)} huésped/es que podrían ser la misma persona. "
                "Revisalos antes de crear uno nuevo."
            )
            for s in suspects[:5]:
                with st.container(border=True):
                    cs1, cs2, cs3 = st.columns([3, 2, 1])
                    cs1.markdown(f"**{s['last_name']}, {s['first_name']}**")
                    meta_bits = []
                    if s.get("document_number"):
                        meta_bits.append(f"Doc {s['document_number']}")
                    if s.get("email"):
                        meta_bits.append(f"✉️ {s['email']}")
                    if s.get("phone"):
                        meta_bits.append(f"📞 {s['phone']}")
                    cs2.caption(" · ".join(meta_bits) or "—")
                    cs3.markdown(f"`{s['total_stays']} est.`")
                    if st.button("Usar este", key=f"_use_dupe_{s['id']}", use_container_width=True):
                        st.session_state["huesped_selected_id"] = s["id"]
                        st.session_state.pop("_dupe_suspects", None)
                        st.session_state.pop("_dupe_pending_payload", None)
                        st.rerun()

            cf1, cf2 = st.columns(2)
            if cf1.button("Sí, crear de todos modos", type="primary", use_container_width=True, key="_force_create_dupe"):
                created = _api_post("/huespedes", pending)
                if created:
                    st.success(f"✅ Huésped #{created['id']} creado.")
                    st.session_state["huesped_selected_id"] = created["id"]
                    st.session_state.pop("_dupe_suspects", None)
                    st.session_state.pop("_dupe_pending_payload", None)
                    st.rerun()
            if cf2.button("Cancelar", use_container_width=True, key="_cancel_create_dupe"):
                st.session_state.pop("_dupe_suspects", None)
                st.session_state.pop("_dupe_pending_payload", None)
                st.rerun()


# ---- RIGHT: detail + history ----
with col_detail:
    sel_id = st.session_state.get("huesped_selected_id")
    if not sel_id:
        st.info("Seleccioná un huésped del listado para ver su detalle.")
        st.stop()

    detail = _api_get(f"/huespedes/{sel_id}")
    if not detail:
        st.warning("No se pudo cargar el detalle del huésped.")
        st.stop()

    # Header card
    st.markdown(f"### {detail['last_name']}, {detail['first_name']}")
    if detail.get("document_number"):
        st.caption(f"Documento: {detail['document_number']}")

    # Aggregates
    history = _api_get(f"/huespedes/{sel_id}/history") or {}
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Estadías", history.get("total_stays", 0))
    m2.metric("Total gastado", _format_price(history.get("total_spent", 0)))
    m3.metric("Promedio", f"{history.get('avg_stay_length', 0)}n")
    m4.metric("Última visita", _format_date(history.get("last_visit_at")))

    tab_info, tab_hist, tab_billing, tab_vehicles = st.tabs(
        ["📝 Datos", "📜 Historial", "🧾 Facturación", "🚗 Vehículos"]
    )

    # --- Datos tab ---
    with tab_info:
        with st.form(f"edit_guest_form_{sel_id}", clear_on_submit=False):
            c1, c2 = st.columns(2)
            with c1:
                fn = st.text_input("Nombres *", value=detail.get("first_name", ""), key=f"e_first_{sel_id}")
                dt = st.text_input("Tipo de documento", value=detail.get("document_type") or "", key=f"e_dt_{sel_id}")
                em = st.text_input("Email", value=detail.get("email") or "", key=f"e_em_{sel_id}")
                nat = st.text_input("Nacionalidad", value=detail.get("nationality") or "", key=f"e_nat_{sel_id}")
                city = st.text_input("Ciudad", value=detail.get("city") or "", key=f"e_city_{sel_id}")
            with c2:
                ln = st.text_input("Apellidos *", value=detail.get("last_name", ""), key=f"e_last_{sel_id}")
                dn = st.text_input("N° documento", value=detail.get("document_number") or "", key=f"e_dn_{sel_id}")
                ph = st.text_input("Teléfono", value=detail.get("phone") or "", key=f"e_ph_{sel_id}")
                country = st.text_input("País", value=detail.get("country") or "", key=f"e_country_{sel_id}")
                src = st.text_input("Origen", value=detail.get("source") or "Direct", key=f"e_src_{sel_id}")
            # v1.10.0 Phase 2a-ext: birth_date (hook for birthday automation)
            from datetime import date as _date_t
            existing_bd = detail.get("birth_date")
            try:
                bd_default = (
                    _date_t.fromisoformat(existing_bd[:10]) if existing_bd else None
                )
            except Exception:
                bd_default = None
            bd = st.date_input(
                "🎂 Fecha de nacimiento",
                value=bd_default,
                min_value=_date_t(1900, 1, 1),
                max_value=_date_t.today(),
                key=f"e_bd_{sel_id}",
                help="Opcional. Habilita futuros saludos de cumpleaños automáticos.",
                format="DD/MM/YYYY",
            )
            notes = st.text_area("Notas internas", value=detail.get("notes") or "", key=f"e_notes_{sel_id}")
            active = st.checkbox("Activo", value=detail.get("is_active", True), key=f"e_act_{sel_id}")
            saved = st.form_submit_button("Guardar cambios", type="primary")
            if saved:
                payload = {
                    "first_name": fn.strip(),
                    "last_name": ln.strip(),
                    "document_type": dt.strip() or None,
                    "document_number": dn.strip() or None,
                    "email": em.strip() or None,
                    "phone": ph.strip() or None,
                    "nationality": nat.strip() or None,
                    "country": country.strip() or None,
                    "city": city.strip() or None,
                    "source": src.strip() or None,
                    "notes": notes.strip() or None,
                    "birth_date": bd.isoformat() if bd else None,
                    "is_active": active,
                }
                updated = _api_put(f"/huespedes/{sel_id}", payload)
                if updated:
                    st.success("Cambios guardados.")
                    st.rerun()

    # --- Historial tab ---
    with tab_hist:
        reservas = history.get("reservations", []) if history else []
        if not reservas:
            st.info("Este huésped no tiene reservas registradas todavía.")
        else:
            # Render as a clean table (no horizontal scroll on common widths)
            rows = []
            for r in reservas:
                rows.append({
                    "Reserva": r["id"],
                    "Check-in": _format_date(r.get("check_in_date")),
                    "Check-out": _format_date(r.get("check_out_date")),
                    "Noches": r.get("stay_days"),
                    "Habitación": r.get("room_internal_code") or r.get("room_id") or "",
                    "Estado": r.get("status", ""),
                    "Origen": r.get("source") or "Direct",
                    "Importe": _format_price(r.get("price", 0)),
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)

    # --- Facturación tab (Phase 2a-ext) ---
    with tab_billing:
        st.caption(
            "Perfiles de facturación reutilizables. El predeterminado se autoselecciona "
            "en el formulario de check-in (a menos que el recepcionista elija otro)."
        )
        profiles = _api_get(f"/huespedes/{sel_id}/billing") or []
        if profiles:
            for p in profiles:
                with st.container(border=True):
                    head_l, head_r = st.columns([4, 1])
                    label_txt = p.get("label") or "(sin etiqueta)"
                    head_l.markdown(f"**{label_txt}**" + ("  ⭐ Predeterminado" if p.get("is_default") else ""))
                    if not p.get("is_default"):
                        if head_r.button("Marcar predet.", key=f"_def_{p['id']}", use_container_width=True):
                            _api_post(f"/huespedes/{sel_id}/billing/{p['id']}/default", {})
                            st.rerun()
                    bits = []
                    if p.get("tax_id_type"):
                        bits.append(f"**{p['tax_id_type']}** {p.get('tax_id_number') or ''}")
                    elif p.get("tax_id_number"):
                        bits.append(f"Doc {p['tax_id_number']}")
                    if p.get("business_name"):
                        bits.append(f"Razón Social: {p['business_name']}")
                    addr_bits = [p.get(c) or "" for c in ("address", "city", "state", "country")]
                    addr = ", ".join([a for a in addr_bits if a])
                    if addr:
                        bits.append(addr)
                    st.caption("  ·  ".join(bits) or "—")
                    with st.popover("✏️ Editar"):
                        with st.form(f"_edit_bp_{p['id']}", clear_on_submit=False):
                            new_label = st.text_input("Etiqueta", value=p.get("label") or "", key=f"bp_lbl_{p['id']}")
                            new_type = st.text_input("Tipo", value=p.get("tax_id_type") or "", key=f"bp_tt_{p['id']}", placeholder="RUC | CI | CUIT | CPF | CNPJ")
                            new_num = st.text_input("Número", value=p.get("tax_id_number") or "", key=f"bp_tn_{p['id']}")
                            new_bn = st.text_input("Razón Social", value=p.get("business_name") or "", key=f"bp_bn_{p['id']}")
                            cca, ccb = st.columns(2)
                            new_addr = cca.text_input("Dirección", value=p.get("address") or "", key=f"bp_ad_{p['id']}")
                            new_city = ccb.text_input("Ciudad", value=p.get("city") or "", key=f"bp_ci_{p['id']}")
                            new_state = cca.text_input("Estado/Depto.", value=p.get("state") or "", key=f"bp_st_{p['id']}")
                            new_country = ccb.text_input("País", value=p.get("country") or "", key=f"bp_co_{p['id']}")
                            cdel, csave = st.columns([1, 2])
                            del_clicked = cdel.form_submit_button("🗑 Eliminar")
                            save_clicked = csave.form_submit_button("Guardar", type="primary")
                            if save_clicked:
                                _api_put(f"/huespedes/{sel_id}/billing/{p['id']}", {
                                    "label": new_label.strip() or None,
                                    "tax_id_type": new_type.strip() or None,
                                    "tax_id_number": new_num.strip() or None,
                                    "business_name": new_bn.strip() or None,
                                    "address": new_addr.strip() or None,
                                    "city": new_city.strip() or None,
                                    "state": new_state.strip() or None,
                                    "country": new_country.strip() or None,
                                })
                                st.rerun()
                            if del_clicked:
                                _api_delete(f"/huespedes/{sel_id}/billing/{p['id']}")
                                st.rerun()
        else:
            st.info("Sin perfiles de facturación. Agregá uno abajo.")

        st.divider()
        with st.expander("➕ Agregar perfil de facturación"):
            with st.form(f"_create_bp_{sel_id}", clear_on_submit=True):
                c1, c2 = st.columns(2)
                lbl = c1.text_input("Etiqueta", placeholder="Personal / Empresa XYZ")
                make_default = c2.checkbox("Marcar como predeterminado", value=False)
                c1, c2 = st.columns(2)
                tt = c1.text_input("Tipo de documento fiscal", placeholder="RUC | CI | CUIT | CPF | CNPJ")
                tn = c2.text_input("Número")
                bn = st.text_input("Razón Social")
                c1, c2 = st.columns(2)
                addr = c1.text_input("Dirección")
                city = c2.text_input("Ciudad")
                c1, c2 = st.columns(2)
                state = c1.text_input("Estado / Departamento")
                country = c2.text_input("País")
                if st.form_submit_button("Crear perfil", type="primary"):
                    _api_post(f"/huespedes/{sel_id}/billing", {
                        "label": lbl.strip() or None,
                        "is_default": make_default,
                        "tax_id_type": tt.strip() or None,
                        "tax_id_number": tn.strip() or None,
                        "business_name": bn.strip() or None,
                        "address": addr.strip() or None,
                        "city": city.strip() or None,
                        "state": state.strip() or None,
                        "country": country.strip() or None,
                    })
                    st.rerun()

    # --- Vehículos tab (Phase 2a-ext) ---
    with tab_vehicles:
        vehicles = _api_get(f"/huespedes/{sel_id}/vehicles") or []
        st.caption(f"{len(vehicles)}/5 vehículos registrados.")
        if vehicles:
            for v in vehicles:
                with st.container(border=True):
                    cv1, cv2, cv3 = st.columns([2, 3, 1])
                    cv1.markdown(f"**{v['plate_number']}**")
                    cv2.caption(
                        (v.get("model") or "—")
                        + (f" · {v['color']}" if v.get("color") else "")
                    )
                    if cv3.button("🗑", key=f"_rm_v_{v['id']}", help="Dar de baja"):
                        _api_delete(f"/huespedes/{sel_id}/vehicles/{v['id']}")
                        st.rerun()
                    with st.popover("✏️ Editar"):
                        with st.form(f"_edit_v_{v['id']}", clear_on_submit=False):
                            new_plate = st.text_input("Chapa", value=v["plate_number"])
                            new_model = st.text_input("Modelo", value=v.get("model") or "")
                            new_color = st.text_input("Color", value=v.get("color") or "")
                            if st.form_submit_button("Guardar", type="primary"):
                                _api_put(f"/huespedes/{sel_id}/vehicles/{v['id']}", {
                                    "plate_number": new_plate.strip() or None,
                                    "model": new_model.strip() or None,
                                    "color": new_color.strip() or None,
                                })
                                st.rerun()
        else:
            st.info("Sin vehículos registrados. Agregá uno abajo (máx. 5).")

        st.divider()
        if len(vehicles) < 5:
            with st.expander("➕ Agregar vehículo"):
                with st.form(f"_create_v_{sel_id}", clear_on_submit=True):
                    plate = st.text_input("Chapa *", placeholder="ABC-123")
                    cv1, cv2 = st.columns(2)
                    model = cv1.text_input("Modelo / Año", placeholder="Toyota Corolla 2020")
                    color = cv2.text_input("Color", placeholder="Blanco")
                    if st.form_submit_button("Registrar vehículo", type="primary"):
                        if not plate.strip():
                            st.error("La chapa es obligatoria.")
                        else:
                            _api_post(f"/huespedes/{sel_id}/vehicles", {
                                "plate_number": plate.strip(),
                                "model": model.strip() or None,
                                "color": color.strip() or None,
                            })
                            st.rerun()
        else:
            st.warning("Límite de 5 vehículos alcanzado. Eliminá uno antes de agregar otro.")
