"""
Hotel Munich - Inventario (v1.6.0 — Phase 3)
==============================================

Panel admin para gestionar el catalogo de productos, stock, ajustes y
reportes de ventas. Acceso restringido a admin / supervisor / gerencia.

Tabs:
1. Productos  — CRUD (crear / editar / desactivar)
2. Stock y ajustes — aplicar ajustes (COMPRA / MERMA / AJUSTE) y ver historial
3. Stock bajo — productos con stock_current <= stock_minimum
4. Mas vendidos — top N por periodo con export CSV
"""

import io
import csv
from datetime import date, timedelta

import pandas as pd
import requests
import streamlit as st

from logging_config import get_logger
from api_client import get_session

_s = get_session()
logger = get_logger(__name__)

API_BASE_URL = "http://localhost:8000/api/v1"
CATEGORIES = ["BEBIDA", "SNACK", "SERVICIO", "MINIBAR", "OTRO"]
REASONS = ["COMPRA", "MERMA", "AJUSTE"]

# ==========================================
# PAGE CONFIG + AUTH
# ==========================================

st.set_page_config(page_title="Inventario", page_icon="📦", layout="wide")

if "logged_in" not in st.session_state or not st.session_state.logged_in:
    st.error("Debe iniciar sesion para acceder a esta pagina")
    st.stop()

user = st.session_state.get("user")
if not user or not user.role or user.role.lower() not in ["admin", "supervisor", "gerencia"]:
    st.error("🛑 No tiene permisos para ver esta pagina (solo admin/supervisor/gerencia).")
    st.stop()

st.title("📦 Inventario")
st.caption(
    f"Catalogo de productos, stock y reportes — "
    f"{st.session_state.get('hotel_name', 'Hotel')}"
)

# ==========================================
# API helpers
# ==========================================

def _headers():
    token = st.session_state.get("api_token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _fmt_gs(amount) -> str:
    if amount is None:
        return "-"
    try:
        return f"{float(amount):,.0f} Gs".replace(",", ".")
    except (ValueError, TypeError):
        return str(amount)


def _get(path: str):
    try:
        r = _s.get(f"{API_BASE_URL}{path}", headers=_headers(), timeout=10)
        if r.ok:
            return r.json()
        st.error(f"Error cargando datos: {r.status_code} {r.text}")
    except Exception as e:
        st.error(f"Error de conexion: {e}")
    return None


def _post(path: str, data: dict):
    try:
        r = _s.post(f"{API_BASE_URL}{path}", json=data, headers=_headers(), timeout=10)
        if r.ok:
            return True, r.json()
        detail = r.json().get("detail", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
        return False, detail
    except Exception as e:
        return False, str(e)


def _patch(path: str, data: dict):
    try:
        r = _s.patch(f"{API_BASE_URL}{path}", json=data, headers=_headers(), timeout=10)
        if r.ok:
            return True, r.json()
        detail = r.json().get("detail", r.text) if r.headers.get("content-type", "").startswith("application/json") else r.text
        return False, detail
    except Exception as e:
        return False, str(e)


def _delete(path: str):
    try:
        r = _s.delete(f"{API_BASE_URL}{path}", headers=_headers(), timeout=10)
        return r.ok, (r.text if not r.ok else "")
    except Exception as e:
        return False, str(e)


# ==========================================
# TABS
# ==========================================

tab_productos, tab_ajustes, tab_bajo, tab_vendidos = st.tabs([
    "🛒 Productos",
    "📊 Stock y ajustes",
    "⚠️ Stock bajo",
    "🏆 Mas vendidos",
])


# ---------------- Productos tab ----------------
with tab_productos:
    st.subheader("Catalogo de productos")

    col_top_1, col_top_2 = st.columns([1, 3])
    with col_top_1:
        show_inactive = st.checkbox("Mostrar inactivos", value=False)
    with col_top_2:
        filter_cat = st.selectbox("Categoria", ["(todas)"] + CATEGORIES)

    params = []
    if not show_inactive:
        params.append("active_only=true")
    else:
        params.append("active_only=false")
    if filter_cat != "(todas)":
        params.append(f"category={filter_cat}")
    qs = "?" + "&".join(params) if params else ""

    products = _get(f"/productos/{qs}") or []

    if products:
        rows = []
        for p in products:
            stock_val = p.get("stock_current")
            min_val = p.get("stock_minimum")
            low = (
                p.get("is_stocked")
                and min_val is not None
                and stock_val is not None
                and stock_val <= min_val
            )
            rows.append({
                "ID": p["id"],
                "Nombre": p["name"],
                "Categoria": p["category"],
                "Precio": _fmt_gs(p["price"]),
                "Stock": stock_val if p.get("is_stocked") else "—",
                "Minimo": min_val if p.get("is_stocked") else "—",
                "Tipo": "Producto" if p.get("is_stocked") else "Servicio",
                "Estado": "Activo" if p.get("is_active") else "Inactivo",
                "⚠️": "🔴" if low else "",
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, width="stretch", hide_index=True)
    else:
        st.info("No hay productos para mostrar. Agrega el primero abajo.")

    st.markdown("---")
    st.subheader("➕ Agregar nuevo producto")
    with st.form("create_product"):
        col_a, col_b = st.columns(2)
        with col_a:
            new_id = st.text_input("ID (slug unico)", placeholder="ej: los-monges-coca-500")
            new_name = st.text_input("Nombre", placeholder="ej: Coca-Cola 500ml")
            new_cat = st.selectbox("Categoria", CATEGORIES, key="new_cat")
            new_price = st.number_input("Precio (Gs)", min_value=0.0, value=0.0, step=100.0, format="%.0f")
        with col_b:
            new_is_stocked = st.checkbox("Tiene stock (producto fisico)", value=True)
            new_stock = st.number_input("Stock inicial", min_value=0, value=0, step=1, disabled=not new_is_stocked)
            new_min = st.number_input("Stock minimo (alerta)", min_value=0, value=0, step=1, disabled=not new_is_stocked)

        if st.form_submit_button("Crear producto", type="primary"):
            ok, result = _post("/productos/", {
                "id": new_id.strip(),
                "name": new_name.strip(),
                "category": new_cat,
                "price": float(new_price),
                "stock_current": int(new_stock) if new_is_stocked else None,
                "stock_minimum": int(new_min) if new_is_stocked else None,
                "is_stocked": bool(new_is_stocked),
            })
            if ok:
                st.success(f"✓ Producto creado: {result.get('name')}")
                st.rerun()
            else:
                st.error(f"Error: {result}")

    st.markdown("---")
    st.subheader("✏️ Editar producto")
    if products:
        product_options = {f"{p['name']} ({p['id']})": p["id"] for p in products}
        sel_label = st.selectbox(
            "Selecciona un producto", options=list(product_options.keys()),
            key="edit_select"
        )
        sel_id = product_options[sel_label]
        sel_product = next(p for p in products if p["id"] == sel_id)

        with st.form("edit_product"):
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                edit_name = st.text_input("Nombre", value=sel_product["name"])
                edit_cat = st.selectbox("Categoria", CATEGORIES,
                                        index=CATEGORIES.index(sel_product["category"]))
                edit_price = st.number_input(
                    "Precio (Gs)", min_value=0.0,
                    value=float(sel_product["price"]), step=100.0, format="%.0f",
                )
            with col_e2:
                edit_min = st.number_input(
                    "Stock minimo", min_value=0,
                    value=int(sel_product.get("stock_minimum") or 0),
                    disabled=not sel_product.get("is_stocked"),
                )
                edit_active = st.checkbox("Activo", value=bool(sel_product["is_active"]))

            c1, c2 = st.columns(2)
            with c1:
                submit_edit = st.form_submit_button("Guardar cambios", type="primary")
            with c2:
                submit_delete = st.form_submit_button("🗑️ Desactivar producto")

        if submit_edit:
            ok, result = _patch(f"/productos/{sel_id}", {
                "name": edit_name.strip(),
                "category": edit_cat,
                "price": float(edit_price),
                "stock_minimum": int(edit_min),
                "is_active": bool(edit_active),
            })
            if ok:
                st.success("✓ Producto actualizado")
                st.rerun()
            else:
                st.error(f"Error: {result}")

        if submit_delete:
            ok, result = _delete(f"/productos/{sel_id}")
            if ok:
                st.success("✓ Producto desactivado")
                st.rerun()
            else:
                st.error(f"Error: {result}")


# ---------------- Stock & adjustments tab ----------------
with tab_ajustes:
    st.subheader("Registrar ajuste de stock")
    st.caption(
        "COMPRA (+) para reposiciones; MERMA (-) para perdidas/vencimientos; "
        "AJUSTE para correcciones por diferencias fisicas."
    )

    stocked_products = [p for p in (_get("/productos/?active_only=true") or []) if p.get("is_stocked")]

    if not stocked_products:
        st.info("No hay productos con stock para ajustar.")
    else:
        with st.form("stock_adjust"):
            col_s1, col_s2, col_s3 = st.columns([2, 1, 1])
            with col_s1:
                adj_opts = {f"{p['name']} (stock actual: {p.get('stock_current', 0)})": p["id"]
                            for p in stocked_products}
                adj_sel = st.selectbox("Producto", options=list(adj_opts.keys()))
                adj_id = adj_opts[adj_sel]
            with col_s2:
                adj_reason = st.selectbox("Razon", REASONS)
            with col_s3:
                default_val = 10 if adj_reason == "COMPRA" else -1
                adj_qty = st.number_input("Cambio (signo)", value=default_val, step=1)
            adj_notes = st.text_input("Notas (opcional)", placeholder="Ej: proveedor, motivo, referencia")

            if st.form_submit_button("Aplicar ajuste", type="primary"):
                if adj_qty == 0:
                    st.error("El cambio no puede ser 0.")
                else:
                    ok, result = _post(f"/productos/{adj_id}/ajuste-stock", {
                        "quantity_change": int(adj_qty),
                        "reason": adj_reason,
                        "notes": adj_notes or None,
                    })
                    if ok:
                        st.success(
                            f"✓ Ajuste aplicado. Nuevo stock: "
                            f"{result.get('new_stock')} unidad(es)"
                        )
                        st.rerun()
                    else:
                        st.error(f"Error: {result}")

    st.markdown("---")
    st.subheader("Historial de ajustes por producto")
    if stocked_products:
        hist_opts = {f"{p['name']} ({p['id']})": p["id"] for p in stocked_products}
        hist_label = st.selectbox("Producto para ver historial", options=list(hist_opts.keys()), key="hist_sel")
        hist_id = hist_opts[hist_label]
        hist_limit = st.slider("Ultimos N ajustes", 10, 200, 50, key="hist_limit")
        ajustes = _get(f"/productos/{hist_id}/ajustes?limit={hist_limit}") or []
        if ajustes:
            rows = [
                {
                    "Fecha": (a.get("created_at") or "")[:19].replace("T", " "),
                    "Razon": a["reason"],
                    "Cambio": f"{a['quantity_change']:+d}",
                    "Notas": a.get("notes") or "-",
                    "Usuario": a.get("created_by") or "-",
                }
                for a in ajustes
            ]
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        else:
            st.info("Sin ajustes registrados para este producto.")


# ---------------- Low stock tab ----------------
with tab_bajo:
    st.subheader("⚠️ Productos con stock bajo")
    st.caption("Productos donde stock actual <= stock minimo. Reponer pronto.")
    low = _get("/productos/stock-bajo") or []
    if not low:
        st.success("✓ Todos los productos tienen stock suficiente.")
    else:
        rows = [
            {
                "ID": p["id"],
                "Nombre": p["name"],
                "Categoria": p["category"],
                "Stock actual": p["stock_current"],
                "Stock minimo": p["stock_minimum"],
                "Faltan": max(p["stock_minimum"] - p["stock_current"], 0) + 1,
            }
            for p in low
        ]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        st.warning(
            f"⚠️ {len(low)} producto(s) necesita(n) reposicion. Registra las compras "
            f"en la pestaña 'Stock y ajustes' con razon=COMPRA."
        )


# ---------------- Top selling tab ----------------
with tab_vendidos:
    st.subheader("🏆 Productos mas vendidos")
    col_d1, col_d2, col_d3 = st.columns([1, 1, 1])
    with col_d1:
        ts_desde = st.date_input("Desde", value=date.today() - timedelta(days=30),
                                 key="ts_desde")
    with col_d2:
        ts_hasta = st.date_input("Hasta", value=date.today(), key="ts_hasta")
    with col_d3:
        ts_limit = st.slider("Top N", 5, 50, 10, key="ts_limit")

    url = f"/productos/mas-vendidos?desde={ts_desde.isoformat()}&hasta={ts_hasta.isoformat()}&limit={ts_limit}"
    top = _get(url) or []

    if not top:
        st.info("Sin ventas en el periodo seleccionado.")
    else:
        rows = [
            {
                "Producto": t["producto_name"],
                "Unidades vendidas": t["units_sold"],
                "Ingresos": _fmt_gs(t["revenue"]),
                "Cant. consumos": t["consumo_count"],
            }
            for t in top
        ]
        df_top = pd.DataFrame(rows)
        st.dataframe(df_top, width="stretch", hide_index=True)

        # CSV export
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(["producto", "unidades_vendidas", "ingresos_gs", "consumos"])
        for t in top:
            writer.writerow([t["producto_name"], t["units_sold"], t["revenue"], t["consumo_count"]])
        st.download_button(
            "📥 Descargar CSV",
            csv_buffer.getvalue(),
            f"top_vendidos_{ts_desde.isoformat()}_{ts_hasta.isoformat()}.csv",
            "text/csv",
        )
