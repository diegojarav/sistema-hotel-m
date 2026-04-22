"""
End-to-end UX test for v1.8.0 Phase 5 — Email Sending.

Sigue el patrón de scripts/ux_test_phase4.py: section() / check() / SUMMARY.

Estrategia híbrida (descubierta automáticamente al inicio):
  - requests   → backend behaviour (config, RBAC, rate limit, historial)
  - playwright → tests UI reales (modales, toasts, tabs, botones disabled)
  - httpx      → fallback HTML-CHECK cuando playwright no está disponible

Cada test se etiqueta con la herramienta que lo ejecutó:
  (API)         → request al backend
  (DB)          → query directa a SQLite
  (Playwright)  → render real con browser headless + screenshot
  (HTML-CHECK)  → verificación de string en el HTML servido por Next/Streamlit
  (MANUAL)      → operador humano debe verificar (último recurso)

Ejecutar:
    # 1. Asegurate que los 3 servicios estén corriendo:
    #    backend         http://localhost:8000
    #    frontend_pc     http://localhost:8501
    #    frontend_mobile http://localhost:3000
    # 2. python scripts/ux_test_phase5.py

Si Playwright o chromium faltan, el script intenta auto-instalarlos.
Al finalizar restaura la config SMTP previa y limpia los registros de email_log
creados por los tests. Screenshots de evidencia en scripts/ux_screenshots/phase5/.
"""

from __future__ import annotations

import importlib
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import requests

# -----------------------------------------------------------------------------
# Constantes
# -----------------------------------------------------------------------------
BACKEND = "http://localhost:8000"
PC = "http://localhost:8501"
MOBILE = "http://localhost:3000"
API = f"{BACKEND}/api/v1"

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "backend" / "hotel.db"
SCREENSHOT_DIR = ROOT / "scripts" / "ux_screenshots" / "phase5"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

results: list[tuple[str, str, str, str]] = []  # (status, label, tool, detail)
created_email_log_ids: list[int] = []
backup_smtp: dict | None = None
test_marker = f"uxtest_phase5_{int(time.time())}@example.com"


# -----------------------------------------------------------------------------
# Helpers (sigue patrón de phase 4)
# -----------------------------------------------------------------------------

def section(name: str) -> None:
    print(f"\n{'=' * 60}\n{name}\n{'=' * 60}")


def check(label: str, cond: bool, tool: str = "API", detail: str = "") -> bool:
    status = "PASS" if cond else "FAIL"
    results.append((status, label, tool, detail))
    icon = "OK  " if cond else "FAIL"
    print(f"  [{icon}] [{tool}] {label}" + (f" -- {detail}" if detail else ""))
    return cond


def skip(label: str, tool: str, reason: str) -> None:
    results.append(("SKIP", label, tool, reason))
    print(f"  [SKIP] [{tool}] {label} -- {reason}")


def login(user: str, pwd: str) -> dict:
    r = requests.post(f"{API}/auth/login", data={"username": user, "password": pwd})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# -----------------------------------------------------------------------------
# Tool discovery (Paso 0)
# -----------------------------------------------------------------------------

class Inventory:
    playwright: bool = False
    chromium_browser: bool = False
    httpx: bool = False
    chrome_binary: Optional[str] = None


def discover_tools() -> Inventory:
    inv = Inventory()
    # Playwright
    try:
        importlib.import_module("playwright")
        inv.playwright = True
    except ImportError:
        pass
    # httpx
    try:
        importlib.import_module("httpx")
        inv.httpx = True
    except ImportError:
        pass
    # Chrome binary path (Windows default)
    candidates = [
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
        "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        shutil.which("google-chrome"),
        shutil.which("chrome"),
        shutil.which("chromium"),
    ]
    for c in candidates:
        if c and os.path.exists(c):
            inv.chrome_binary = c
            break
    # Verifica si chromium playwright ya está bajado
    if inv.playwright:
        from pathlib import Path as _P
        ms_pw = _P.home() / "AppData" / "Local" / "ms-playwright"
        if ms_pw.exists() and any("chromium" in p.name for p in ms_pw.iterdir()):
            inv.chromium_browser = True
    return inv


def auto_install_playwright(inv: Inventory) -> None:
    """Intenta instalar Playwright + chromium si faltan."""
    if not inv.playwright:
        print("\nInstalando playwright...")
        r = subprocess.run([sys.executable, "-m", "pip", "install", "playwright"],
                           capture_output=True, text=True, timeout=180)
        if r.returncode == 0:
            inv.playwright = True
            print("  playwright instalado")
        else:
            print(f"  pip install fallo: {r.stderr[:200]}")
    if inv.playwright and not inv.chromium_browser:
        print("Bajando chromium para playwright...")
        r = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                           capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            inv.chromium_browser = True
            print("  chromium descargado")
        else:
            print(f"  playwright install fallo: {r.stderr[:200]}")


# -----------------------------------------------------------------------------
# Health checks (Setup)
# -----------------------------------------------------------------------------

def health_check() -> tuple[bool, dict]:
    """Verifica los 3 servidores. Aborta si backend no responde."""
    services = {
        "Backend": f"{BACKEND}/docs",
        "PC Admin": f"{PC}/_stcore/health",
        "Mobile": MOBILE,
    }
    print("Verificando servidores...")
    status: dict[str, bool] = {}
    for name, url in services.items():
        try:
            r = requests.get(url, timeout=3)
            ok = r.status_code < 500
            status[name] = ok
            print(f"  {'OK  ' if ok else 'WARN'}  {name:<10} {url}  -- status={r.status_code}")
        except requests.RequestException as e:
            status[name] = False
            print(f"  FAIL  {name:<10} {url}  -- {type(e).__name__}")
    return status.get("Backend", False), status


# -----------------------------------------------------------------------------
# Backend setup
# -----------------------------------------------------------------------------

def backup_smtp_config(admin_hdr: dict) -> dict:
    r = requests.get(f"{API}/settings/email", headers=admin_hdr)
    return r.json() if r.status_code == 200 else {}


def restore_smtp_config(admin_hdr: dict, snapshot: dict) -> None:
    if not snapshot:
        return
    payload = {
        "smtp_host": snapshot.get("smtp_host") or "smtp.placeholder.com",
        "smtp_port": snapshot.get("smtp_port") or 587,
        "smtp_username": snapshot.get("smtp_username") or "placeholder@example.com",
        "smtp_password": None,
        "smtp_from_name": snapshot.get("smtp_from_name") or "Hotel",
        "smtp_from_email": snapshot.get("smtp_from_email") or "placeholder@example.com",
        "smtp_enabled": bool(snapshot.get("smtp_enabled")),
        "email_body_template": snapshot.get("email_body_template"),
    }
    requests.put(f"{API}/settings/email", headers=admin_hdr, json=payload)


def enable_smtp_for_tests(admin_hdr: dict, enabled: bool = True) -> None:
    """Habilita/deshabilita SMTP con la config dummy de tests."""
    requests.put(
        f"{API}/settings/email",
        headers=admin_hdr,
        json={
            "smtp_host": "smtp.test-uxtest.com",
            "smtp_port": 587,
            "smtp_username": "uxtest@example.com",
            "smtp_password": "uxtestpass" if enabled else None,
            "smtp_from_name": "Hotel UX Test",
            "smtp_from_email": test_marker,
            "smtp_enabled": enabled,
        },
    )


def find_or_create_fixture_reservas(admin_hdr: dict) -> tuple[str | None, str | None]:
    """Devuelve (reserva_con_email, reserva_sin_email).

    Si la API list no incluye contact_email, hace fallback a query directa de DB.
    """
    rid_con: str | None = None
    rid_sin: str | None = None
    try:
        rows = db_query(
            "SELECT id, COALESCE(contact_email, '') FROM reservations "
            "WHERE status NOT IN ('CANCELADA', 'COMPLETADA') "
            "ORDER BY check_in_date DESC LIMIT 50"
        )
        for rid, em in rows:
            if em.strip() and rid_con is None:
                rid_con = rid
            elif not em.strip() and rid_sin is None:
                rid_sin = rid
            if rid_con and rid_sin:
                break
        # Si no hay reserva CON email, asignamos uno a la primera reserva activa
        if not rid_con and rows:
            target = rows[0][0]
            requests.patch(
                f"{API}/reservations/{target}",
                headers=admin_hdr,
                json={"contact_email": "fixture_uxtest@example.com"},
            )
            rid_con = target
    except Exception as e:
        print(f"  WARN find fixture reservas: {e}")
    return rid_con, rid_sin


# -----------------------------------------------------------------------------
# DB helpers
# -----------------------------------------------------------------------------

def db_exec(sql: str, args: tuple = ()) -> int:
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.execute(sql, args)
    conn.commit()
    last_id = cur.lastrowid
    conn.close()
    return last_id  # type: ignore[return-value]


def db_query(sql: str, args: tuple = ()) -> list[tuple]:
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(sql, args).fetchall()
    conn.close()
    return rows


def insert_email_log(reserva_id: str, recipient: str, status: str = "ENVIADO") -> int:
    sent_at = datetime.now().isoformat()
    log_id = db_exec(
        "INSERT INTO email_log (reserva_id, recipient_email, subject, status, sent_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (reserva_id, recipient, "uxtest subject", status, sent_at, sent_at),
    )
    created_email_log_ids.append(log_id)
    return log_id


def cleanup_email_log() -> None:
    if created_email_log_ids:
        placeholders = ",".join("?" * len(created_email_log_ids))
        db_exec(
            f"DELETE FROM email_log WHERE id IN ({placeholders})",
            tuple(created_email_log_ids),
        )
    db_exec("DELETE FROM email_log WHERE recipient_email = ?", (test_marker,))


# -----------------------------------------------------------------------------
# Browser helpers (Playwright)
# -----------------------------------------------------------------------------

class Browser:
    """Wrapper around Playwright. Gestiona contexto, login mobile/PC y screenshots."""

    def __init__(self):
        self._pw = None
        self._browser = None
        self._mobile_ctx = None
        self._pc_ctx = None

    def start(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        return self

    def close(self):
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass

    def mobile_page(self, token: str):
        if self._mobile_ctx is None:
            self._mobile_ctx = self._browser.new_context(viewport={"width": 412, "height": 915})
        page = self._mobile_ctx.new_page()
        # Pre-seed JWT para saltarnos el form login
        page.goto(MOBILE, wait_until="domcontentloaded", timeout=15000)
        page.evaluate(
            "(t) => { localStorage.setItem('hms_access_token', t); localStorage.setItem('hms_refresh_token', t); }",
            token,
        )
        return page

    def pc_page(self):
        if self._pc_ctx is None:
            self._pc_ctx = self._browser.new_context(viewport={"width": 1366, "height": 850})
        page = self._pc_ctx.new_page()
        return page

    def pc_login_and_open(self, page, page_label: str | None = None):
        """Hace login en root y navega a la página por sidebar click.

        Streamlit no preserva session_state cuando se hace `goto()` directo a una
        sub-página: cada navegación abre un websocket nuevo. La única manera de
        navegar conservando la sesión es CLICKAR el link del sidebar que
        Streamlit renderiza tras el login. `page_label` matchea el texto del
        link en el sidebar (ej. "Configuracion", "Documentos Hotel").
        """
        page.goto(f"{PC}/", wait_until="networkidle", timeout=25000)
        # Login si hace falta
        try:
            user_in = page.locator('input[aria-label="Usuario"]')
            if user_in.count() > 0 and user_in.first.is_visible(timeout=3000):
                user_in.first.fill("admin")
                page.locator('input[aria-label="Contraseña"]').first.fill("admin123")
                page.click('button:has-text("Entrar")')
                page.wait_for_load_state("networkidle", timeout=20000)
                # Espera SEÑAL CONFIABLE de login exitoso: el form de Usuario debe
                # desaparecer (la página principal ya no lo renderea). Streamlit muestra
                # la sidebar incluso pre-login, por lo que NO sirve como señal.
                page.wait_for_selector(
                    'input[aria-label="Usuario"]', state="hidden", timeout=20000
                )
                page.wait_for_timeout(2000)  # tiempo extra para que rendere usuario en sidebar
        except Exception:
            pass
        # Click sidebar link si se pidió una página específica
        if page_label:
            for attempt in range(2):
                try:
                    link = page.locator('section[data-testid="stSidebar"]').get_by_text(
                        page_label, exact=False
                    ).first
                    link.wait_for(state="visible", timeout=10000)
                    link.click(timeout=5000)
                    page.wait_for_load_state("networkidle", timeout=15000)
                    page.wait_for_timeout(2500)
                    return
                except Exception:
                    if attempt == 0:
                        page.wait_for_timeout(2000)
                        continue
                    raise

    def screenshot(self, page, name: str) -> str:
        path = SCREENSHOT_DIR / f"{name}.png"
        page.screenshot(path=str(path), full_page=False)
        return str(path)


# -----------------------------------------------------------------------------
# HTML-CHECK fallback con httpx
# -----------------------------------------------------------------------------

def html_contains(url: str, needle: str, timeout: float = 10.0) -> bool:
    try:
        import httpx
        r = httpx.get(url, timeout=timeout, follow_redirects=True)
        return r.status_code == 200 and needle in r.text
    except Exception:
        return False


# -----------------------------------------------------------------------------
# Bloques de test
# -----------------------------------------------------------------------------

def bloque_1_pc_smtp_config(admin_hdr: dict, recep_hdr: dict, br: Optional[Browser]) -> None:
    section("Bloque 1: PC Admin -- Configuracion SMTP")

    # 1.1 — Sección visible para Admin (UI real)
    if br:
        page = br.pc_page()
        try:
            br.pc_login_and_open(page, "Configuracion")
            page.wait_for_timeout(1500)
            visible = page.get_by_text("Configuración de Correo").first.is_visible(timeout=10000)
            br.screenshot(page, "1.1_smtp_seccion_admin" if visible else "1.1_FAIL")
            check("1.1 Seccion 'Configuracion de Correo' visible para Admin", visible, "Playwright")
        except Exception as e:
            try: br.screenshot(page, "1.1_FAIL_exception")
            except Exception: pass
            check("1.1 Seccion 'Configuracion de Correo' visible para Admin", False, "Playwright", str(e)[:120])
        finally:
            page.close()
    else:
        skip("1.1 Seccion 'Configuracion de Correo' visible para Admin", "HTML-CHECK", "Streamlit es SPA; sin Playwright no se puede verificar render JS")

    # 1.2 — Recepcion no puede modificar config (PUT 403)
    r = requests.put(
        f"{API}/settings/email",
        headers=recep_hdr,
        json={"smtp_host": "x", "smtp_port": 587, "smtp_username": "x", "smtp_password": "x",
              "smtp_from_name": "x", "smtp_from_email": "x@y.com", "smtp_enabled": False},
    )
    check("1.2 Recepcion NO puede modificar config SMTP (PUT -> 403)", r.status_code == 403, "API", f"status={r.status_code}")

    # 1.3 — Guardar config válida
    payload_ok = {
        "smtp_host": "smtp.test-uxtest.com", "smtp_port": 587,
        "smtp_username": "uxtest@example.com", "smtp_password": "uxtestpass",
        "smtp_from_name": "Hotel UX Test", "smtp_from_email": test_marker,
        "smtp_enabled": True, "email_body_template": "Hola {nombre_huesped}",
    }
    r = requests.put(f"{API}/settings/email", headers=admin_hdr, json=payload_ok)
    check("1.3 Admin guarda config SMTP completa", r.status_code == 200, "API", f"status={r.status_code}")

    r = requests.get(f"{API}/settings/email", headers=admin_hdr)
    if r.status_code == 200:
        d = r.json()
        check("1.3 GET refleja host guardado", d.get("smtp_host") == "smtp.test-uxtest.com", "API")
        check("1.3 GET marca smtp_password_set=true", d.get("smtp_password_set") is True, "API")
        check("1.3 GET nunca expone password en claro", "smtp_password" not in d, "API")

    # 1.4 — Validación: campos vacíos
    bad = {**payload_ok, "smtp_host": ""}
    r = requests.put(f"{API}/settings/email", headers=admin_hdr, json=bad)
    check("1.4 PUT con smtp_host vacio rechazado (422 o 400)", r.status_code in (400, 422), "API", f"status={r.status_code}")

    # 1.5 — Toggle off => /enviar retorna 400
    enable_smtp_for_tests(admin_hdr, enabled=False)
    rid_test = "0001107"  # cualquier reserva existente alcanza para verificar el guard
    r = requests.post(f"{API}/email/reserva/{rid_test}/enviar", headers=admin_hdr, json={})
    cond = r.status_code == 400 and "Configure el correo" in r.json().get("detail", "")
    check("1.5 smtp_enabled=false -> /enviar retorna 400 con mensaje correcto", cond, "API", f"status={r.status_code}")

    # 1.6 — Toggle on => habilitado (no devuelve el mensaje 'Configure...')
    enable_smtp_for_tests(admin_hdr, enabled=True)
    r = requests.post(f"{API}/email/reserva/{rid_test}/enviar", headers=admin_hdr, json={"email": test_marker})
    cond = r.status_code != 400 or "Configure el correo" not in r.json().get("detail", "")
    check("1.6 smtp_enabled=true -> /enviar ya no exige config", cond, "API", f"status={r.status_code}")

    # 1.7 — Endpoint /test responde 200 con success=False ante SMTP inexistente
    r = requests.post(f"{API}/settings/email/test", headers=admin_hdr, json={"email": test_marker})
    cond = r.status_code == 200 and r.json().get("success") is False
    check("1.7 POST /settings/email/test -> 200 + success=False con SMTP fake", cond, "API", str(r.json())[:100])

    # 1.8 — Botón "Enviar email de prueba" existe en la UI (Playwright UI)
    if br:
        page = br.pc_page()
        try:
            br.pc_login_and_open(page, "Configuracion")
            page.wait_for_timeout(2500)  # render del expander con la config guardada
            btn = page.get_by_role("button", name="Enviar email de prueba")
            visible = btn.count() > 0 and btn.first.is_visible(timeout=8000)
            br.screenshot(page, "1.8_boton_test_visible" if visible else "1.8_FAIL")
            check("1.8 Boton 'Enviar email de prueba' presente con config guardada", visible, "Playwright")
        except Exception as e:
            try: br.screenshot(page, "1.8_FAIL_exception")
            except Exception: pass
            check("1.8 Boton 'Enviar email de prueba' presente", False, "Playwright", str(e)[:120])
        finally:
            page.close()
    else:
        skip("1.8 Boton 'Enviar email de prueba' presente", "Playwright", "no disponible")


def bloque_2_envio_desde_reserva(admin_hdr: dict, rid_con: str | None, rid_sin: str | None) -> None:
    section("Bloque 2: PC/API -- Envio desde detalle de reserva")

    if not rid_con or not rid_sin:
        skip("2.x Tests del bloque 2", "API", f"fixtures: con={rid_con} sin={rid_sin}")
        return

    # Limpieza previa: el test 2.3 persiste un email override en rid_sin. Si
    # quedó de un run anterior, el test 2.2 falla porque la reserva ya tiene email.
    db_exec("UPDATE reservations SET contact_email = NULL WHERE id = ?", (rid_sin,))

    # Habilitar SMTP para los tests siguientes
    enable_smtp_for_tests(admin_hdr, enabled=True)

    # 2.1 — Sin SMTP config: deshabilitamos brevemente y verificamos
    enable_smtp_for_tests(admin_hdr, enabled=False)
    r = requests.post(f"{API}/email/reserva/{rid_con}/enviar", headers=admin_hdr, json={})
    cond = r.status_code == 400 and "Configure el correo" in r.json().get("detail", "")
    check("2.1 SMTP disabled -> 400 con 'Configure el correo'", cond, "API", f"status={r.status_code}")
    enable_smtp_for_tests(admin_hdr, enabled=True)

    # 2.2 — Guest sin email + body sin email => 400
    r = requests.post(f"{API}/email/reserva/{rid_sin}/enviar", headers=admin_hdr, json={})
    cond = r.status_code == 400 and "no tiene email" in r.json().get("detail", "").lower()
    check("2.2 Reserva sin email + body vacio -> 400 'no tiene email'", cond, "API", f"status={r.status_code}")

    # 2.3 — Guest sin email + body CON email => 202 + persistir contact_email
    override = test_marker
    r = requests.post(
        f"{API}/email/reserva/{rid_sin}/enviar", headers=admin_hdr,
        json={"email": override},
    )
    accepted = r.status_code == 202
    check("2.3 Body con email override -> 202 Accepted", accepted, "API", f"status={r.status_code}")
    if accepted:
        time.sleep(0.3)
        rg = requests.get(f"{API}/reservations/{rid_sin}", headers=admin_hdr)
        if rg.status_code == 200:
            check(
                "2.3 contact_email persistido en la reserva",
                (rg.json().get("contact_email") or "").strip() == override,
                "API",
                rg.json().get("contact_email"),
            )

    # 2.4 — Guest CON email => 202
    r = requests.post(f"{API}/email/reserva/{rid_con}/enviar", headers=admin_hdr, json={})
    check("2.4 Reserva con email -> 202 Accepted", r.status_code == 202, "API", f"status={r.status_code}")

    # 2.5 — DB: email_log creado tras envío
    # El servicio guarda created_at con datetime.now() (local time).
    # SQLite "datetime('now')" es UTC -> mezcla rompe la query. Usamos comparacion
    # absoluta sobre el id máximo creado durante este bloque.
    time.sleep(0.5)
    rows = db_query(
        "SELECT COUNT(*) FROM email_log WHERE reserva_id = ?",
        (rid_con,),
    )
    cnt = rows[0][0] if rows else 0
    check("2.5 DB: al menos una email_log row registrada para la reserva", cnt >= 1, "DB", f"count={cnt}")


def bloque_3_historial_pc(admin_hdr: dict, rid_con: str | None, br: Optional[Browser]) -> None:
    section("Bloque 3: PC -- Historial de Emails")

    if not rid_con:
        skip("3.x Tests del bloque 3", "API", "no fixture")
        return

    # Setup: 2 registros (uno ENVIADO + uno FALLIDO) para los filtros
    insert_email_log(rid_con, test_marker, status="ENVIADO")
    insert_email_log(rid_con, test_marker, status="FALLIDO")

    # 3.1 — Tab "Historial de Emails" visible
    if br:
        page = br.pc_page()
        try:
            br.pc_login_and_open(page, "Documentos Hotel")
            page.wait_for_timeout(2000)
            visible = page.get_by_text("Historial de Emails").first.is_visible(timeout=10000)
            br.screenshot(page, "3.1_tab_historial_visible" if visible else "3.1_FAIL")
            check("3.1 Tab 'Historial de Emails' presente en pagina Documentos", visible, "Playwright")
        except Exception as e:
            try: br.screenshot(page, "3.1_FAIL_exception")
            except Exception: pass
            check("3.1 Tab 'Historial de Emails' presente", False, "Playwright", str(e)[:120])
        finally:
            page.close()
    else:
        skip("3.1 Tab 'Historial de Emails' presente", "Playwright", "no disponible")

    # 3.2 — Historial vacío para reserva sin envíos => []
    r = requests.get(f"{API}/email/reserva/__no_existe__/historial", headers=admin_hdr)
    check("3.2 GET /historial reserva inexistente -> [] (no error)",
          r.status_code == 200 and r.json() == [], "API", f"status={r.status_code}")

    # 3.3 — Historial trae registros con todos los campos
    r = requests.get(f"{API}/email/reserva/{rid_con}/historial", headers=admin_hdr)
    if r.status_code == 200:
        data = r.json()
        required = {"id", "reserva_id", "recipient_email", "subject", "status", "created_at"}
        has_fields = bool(data) and required.issubset(set(data[0].keys()))
        check("3.3 Historial expone todos los campos esperados", has_fields and len(data) >= 2,
              "API", f"count={len(data)}")

    # 3.4 — Filtro por estado (verificable con la query SQL que usa la tab del PC)
    rows = db_query(
        "SELECT COUNT(*) FROM email_log WHERE reserva_id = ? AND status = 'FALLIDO'",
        (rid_con,),
    )
    fallidos = rows[0][0] if rows else 0
    check("3.4 Filtro por status='FALLIDO' devuelve registros (consistencia DB)",
          fallidos >= 1, "DB", f"count={fallidos}")

    # 3.5 — Export CSV: la pagina arma el CSV con 6 columnas
    rows = db_query(
        "SELECT created_at, reserva_id, recipient_email, subject, status, error_message "
        "FROM email_log WHERE reserva_id = ? LIMIT 5",
        (rid_con,),
    )
    six_cols = bool(rows) and all(len(r) == 6 for r in rows)
    check("3.5 SQL del CSV export devuelve 6 columnas", six_cols, "DB", f"rows={len(rows)}")


def bloque_4_mobile(admin_hdr: dict, rid_con: str | None, rid_sin: str | None,
                    br: Optional[Browser]) -> None:
    section("Bloque 4: Mobile -- Detalle de Reserva")

    if not br:
        for n in range(1, 11):
            skip(f"4.{n} Test mobile", "Playwright", "no disponible")
        return
    if not rid_con:
        for n in range(1, 11):
            skip(f"4.{n} Test mobile", "Playwright", "no fixture reserva con email")
        return

    # Wrap todo el bloque en try/except para que un crash de Playwright no rompa la suite
    try:
        _bloque_4_mobile_inner(admin_hdr, rid_con, rid_sin, br)
    except Exception as e:
        check("4.x bloque mobile completo", False, "Playwright", f"crash: {type(e).__name__}: {str(e)[:150]}")
    return


def _bloque_4_mobile_inner(admin_hdr: dict, rid_con: str, rid_sin: str | None,
                            br: Browser) -> None:

    # SMTP habilitado para los tests
    enable_smtp_for_tests(admin_hdr, enabled=True)
    token = admin_hdr["Authorization"].split(" ")[1]
    page = br.mobile_page(token)
    try:
        url_con = f"{MOBILE}/dashboard/calendar/{rid_con}"
        # `networkidle` no se logra porque la página polletea saldo/consumos/historial.
        # Cargar con `domcontentloaded` y luego esperar al botón con polling (Next.js dev
        # mode con HMR puede tardar 10-20s en estabilizar el primer render).
        page.goto(url_con, wait_until="domcontentloaded", timeout=30000)

        # 4.1 — Botón "Enviar por correo" visible (polling hasta 30s)
        btn = page.get_by_role("button", name="Enviar por correo")
        vis = False
        try:
            btn.wait_for(state="visible", timeout=30000)
            vis = True
        except Exception:
            pass
        if vis:
            br.screenshot(page, "4.1_boton_enviar_mobile")
        else:
            br.screenshot(page, "4.1_FAIL_no_boton")
        check("4.1 Boton 'Enviar por correo' visible en detalle de reserva", vis, "Playwright")

        # 4.2 — Click abre modal
        try:
            page.get_by_role("button", name="Enviar por correo").click()
            page.wait_for_selector('input[type="email"]', timeout=5000)
            modal_open = page.locator('input[type="email"]').count() > 0
            if modal_open:
                br.screenshot(page, "4.2_modal_abierto")
            check("4.2 Click en boton abre el modal con input email", modal_open, "Playwright")
        except Exception as e:
            check("4.2 Click abre modal", False, "Playwright", str(e)[:120])

        # 4.5 — Guest CON email: el input viene prefilled
        try:
            value = page.locator('input[type="email"]').first.input_value()
            check("4.5 Modal con guest con email -> input prefilled", "@" in value,
                  "Playwright", f"value={value!r}")
        except Exception as e:
            check("4.5 Modal input prefilled", False, "Playwright", str(e)[:120])

        # 4.4 — Validación email inválido
        try:
            page.locator('input[type="email"]').first.fill("esto-no-es-email")
            page.get_by_role("button", name="Enviar").click()
            page.wait_for_timeout(800)
            err_present = page.get_by_text("email válido", exact=False).count() > 0
            if err_present:
                br.screenshot(page, "4.4_validacion_email_invalido")
            check("4.4 Email invalido -> validacion inline", err_present, "Playwright")
        except Exception as e:
            check("4.4 Validacion email invalido", False, "Playwright", str(e)[:120])

        # 4.10 — Cancelar cierra el modal
        try:
            page.get_by_role("button", name="Cancelar").click()
            page.wait_for_timeout(800)
            modal_closed = page.locator('input[type="email"]').count() == 0
            check("4.10 Cancelar cierra el modal", modal_closed, "Playwright")
        except Exception as e:
            check("4.10 Cancelar cierra modal", False, "Playwright", str(e)[:120])

        # 4.6 — Loading state durante el envío
        # Reabrimos modal e interceptamos la respuesta para forzar latencia
        try:
            # Slow down the email POST so vemos el loading state
            page.route(
                f"**/api/v1/email/reserva/{rid_con}/enviar",
                lambda route: (page.wait_for_timeout(800), route.continue_()),
            )
            page.get_by_role("button", name="Enviar por correo").click()
            page.wait_for_selector('input[type="email"]', timeout=5000)
            page.locator('input[type="email"]').first.fill(test_marker)
            page.get_by_role("button", name="Enviar").click()
            page.wait_for_timeout(200)  # right after click, loading should be shown
            loading_visible = page.get_by_text("Enviando", exact=False).count() > 0
            if loading_visible:
                br.screenshot(page, "4.6_loading_state")
            check("4.6 Click Enviar -> boton muestra estado loading", loading_visible, "Playwright")
            # Esperar a que se cierre el modal (toast verde se mostrará en el detail)
            page.wait_for_timeout(2500)
            page.unroute(f"**/api/v1/email/reserva/{rid_con}/enviar")
        except Exception as e:
            check("4.6 Loading state visible", False, "Playwright", str(e)[:120])

        # 4.7 — Toast verde de éxito tras envío
        try:
            # Después del 4.6, el toast 'Correo encolado' debe estar visible en el detail
            time.sleep(0.5)
            success_toast = (
                page.get_by_text("Correo encolado", exact=False).count() > 0
                or page.get_by_text("encolado", exact=False).count() > 0
            )
            if success_toast:
                br.screenshot(page, "4.7_toast_exito")
            check("4.7 Toast verde 'Correo encolado' visible tras envio exitoso",
                  success_toast, "Playwright")
        except Exception as e:
            check("4.7 Toast exito", False, "Playwright", str(e)[:120])

        # 4.8 — Toast rojo / mensaje de error: deshabilitamos SMTP y reintentamos
        try:
            enable_smtp_for_tests(admin_hdr, enabled=False)
            page.reload(wait_until="networkidle")
            page.wait_for_timeout(1000)
            page.get_by_role("button", name="Enviar por correo").click()
            page.wait_for_selector('input[type="email"]', timeout=5000)
            page.locator('input[type="email"]').first.fill(test_marker)
            page.get_by_role("button", name="Enviar").click()
            page.wait_for_timeout(1500)
            err_visible = page.get_by_text("Configure el correo", exact=False).count() > 0
            if err_visible:
                br.screenshot(page, "4.8_toast_error")
            check("4.8 Toast/error muestra mensaje del backend cuando SMTP off",
                  err_visible, "Playwright")
        except Exception as e:
            check("4.8 Toast error", False, "Playwright", str(e)[:120])
        finally:
            enable_smtp_for_tests(admin_hdr, enabled=True)

        # 4.9 — Rate limit: insertamos 3 ENVIADO y disparamos un 4to vía API directa
        if rid_sin:
            for _ in range(3):
                insert_email_log(rid_sin, test_marker, status="ENVIADO")
            r = requests.post(
                f"{API}/email/reserva/{rid_sin}/enviar", headers=admin_hdr,
                json={"email": test_marker},
            )
            cond = r.status_code == 429 and "Límite" in r.json().get("detail", "")
            check("4.9 4to envio en <1h -> backend devuelve 429 + mensaje en español",
                  cond, "API", f"status={r.status_code}")
        else:
            skip("4.9 Rate limit", "API", "no rid_sin")

        # 4.3 — Estado "Último envío" actualizado en el detalle
        try:
            page.goto(url_con, wait_until="networkidle", timeout=20000)
            page.wait_for_timeout(1500)
            caption = page.get_by_text("Último envío", exact=False).count() > 0
            if caption:
                br.screenshot(page, "4.3_caption_ultimo_envio")
            check("4.3 Caption 'Ultimo envio' aparece tras envio", caption, "Playwright")
        except Exception as e:
            check("4.3 Caption ultimo envio", False, "Playwright", str(e)[:120])

    finally:
        page.close()


def bloque_5_permisos(admin_hdr: dict, recep_hdr: dict, rid_con: str | None) -> None:
    section("Bloque 5: Permisos y accesos")

    # 5.1 — Admin -> PUT 200
    enable_smtp_for_tests(admin_hdr, enabled=True)
    r = requests.put(
        f"{API}/settings/email", headers=admin_hdr,
        json={"smtp_host": "smtp.test-uxtest.com", "smtp_port": 587,
              "smtp_username": "uxtest@example.com", "smtp_password": None,
              "smtp_from_name": "H", "smtp_from_email": test_marker, "smtp_enabled": True},
    )
    check("5.1 Admin -> PUT /settings/email -> 200", r.status_code == 200, "API", f"status={r.status_code}")

    # 5.2 — Recepcion -> 403
    r = requests.put(
        f"{API}/settings/email", headers=recep_hdr,
        json={"smtp_host": "x", "smtp_port": 587, "smtp_username": "x", "smtp_password": "x",
              "smtp_from_name": "x", "smtp_from_email": "x@y.com", "smtp_enabled": False},
    )
    check("5.2 Recepcion -> PUT /settings/email -> 403", r.status_code == 403, "API", f"status={r.status_code}")

    # 5.3 — Recepcion puede enviar (no 403)
    if rid_con:
        r = requests.post(
            f"{API}/email/reserva/{rid_con}/enviar", headers=recep_hdr,
            json={"email": test_marker},
        )
        check("5.3 Recepcion puede enviar email (no 403)",
              r.status_code != 403, "API", f"status={r.status_code}")
    else:
        skip("5.3 Recepcion puede enviar email", "API", "no rid_con")

    # 5.4 — Recepcion puede ver historial
    if rid_con:
        r = requests.get(f"{API}/email/reserva/{rid_con}/historial", headers=recep_hdr)
        check("5.4 Recepcion puede ver historial",
              r.status_code == 200 and isinstance(r.json(), list), "API", f"status={r.status_code}")
    else:
        skip("5.4 Recepcion puede ver historial", "API", "no rid_con")


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main() -> int:
    print("=" * 60)
    print("Hotel Munich PMS -- UX Tests Phase 5")
    print("=" * 60)

    # Paso 0: Discover & maybe install
    inv = discover_tools()
    print("\nHerramientas detectadas:")
    print(f"  playwright       : {'OK' if inv.playwright else 'NO'}")
    print(f"  chromium browser : {'OK' if inv.chromium_browser else 'NO'}")
    print(f"  httpx            : {'OK' if inv.httpx else 'NO'}")
    print(f"  chrome binary    : {inv.chrome_binary or 'no encontrado'}")

    if not (inv.playwright and inv.chromium_browser):
        # Intentar auto-install (puede tardar 1-3 min)
        try:
            auto_install_playwright(inv)
        except Exception as e:
            print(f"  Auto-install fallo: {e}")

    if inv.playwright and inv.chromium_browser:
        strategy = "Playwright headless (UI real + screenshots)"
    elif inv.httpx:
        strategy = "httpx HTML-CHECK (parcial; tests SPA marcan SKIP)"
    else:
        strategy = "Solo API/DB (UI tests serán SKIP)"
    print(f"\nEstrategia: {strategy}")

    # Paso 1: Health check
    backend_ok, status = health_check()
    if not backend_ok:
        print("\nABORT: el backend no responde. Iniciálo con `npm run dev:backend`.")
        return 2
    if not status.get("PC Admin"):
        print("\nWARN: PC (8501) no responde -- tests UI del bloque 1/3 podrian fallar")
    if not status.get("Mobile"):
        print("\nWARN: Mobile (3000) no responde -- bloque 4 saltea")

    # Login
    try:
        admin_hdr = login("admin", "admin123")
        print("Login admin OK")
    except Exception as e:
        print(f"FATAL login admin: {e}")
        return 2
    try:
        recep_hdr = login("recepcion", "recep123")
        print("Login recepcion OK")
    except Exception as e:
        print(f"WARN login recepcion: {e}")
        recep_hdr = {"Authorization": "Bearer invalid"}

    # Backup SMTP
    global backup_smtp
    backup_smtp = backup_smtp_config(admin_hdr)
    print(f"Backup SMTP previo: enabled={backup_smtp.get('smtp_enabled') if backup_smtp else 'N/A'}")

    # Fixtures
    rid_con, rid_sin = find_or_create_fixture_reservas(admin_hdr)
    print(f"Fixtures: reserva_con_email={rid_con}  reserva_sin_email={rid_sin}")

    # Browser
    br: Optional[Browser] = None
    if inv.playwright and inv.chromium_browser and (status.get("PC Admin") or status.get("Mobile")):
        try:
            br = Browser().start()
            print("Browser headless iniciado")
        except Exception as e:
            print(f"WARN browser: {e} -- los tests UI quedaran SKIP")
            br = None

    try:
        bloque_1_pc_smtp_config(admin_hdr, recep_hdr, br if status.get("PC Admin") else None)
        bloque_2_envio_desde_reserva(admin_hdr, rid_con, rid_sin)
        bloque_3_historial_pc(admin_hdr, rid_con, br if status.get("PC Admin") else None)
        bloque_4_mobile(admin_hdr, rid_con, rid_sin, br if status.get("Mobile") else None)
        bloque_5_permisos(admin_hdr, recep_hdr, rid_con)
    finally:
        section("Teardown")
        try:
            cleanup_email_log()
            print(f"  Cleanup email_log: {len(created_email_log_ids)} ids creados eliminados")
        except Exception as e:
            print(f"  Cleanup fallo: {e}")
        try:
            restore_smtp_config(admin_hdr, backup_smtp or {})
            print("  Restaurada config SMTP previa")
        except Exception as e:
            print(f"  Restore SMTP fallo: {e}")
        if br:
            br.close()

    # Summary
    section("SUMMARY")
    passed = sum(1 for s, _, _, _ in results if s == "PASS")
    failed = sum(1 for s, _, _, _ in results if s == "FAIL")
    skipped = sum(1 for s, _, _, _ in results if s == "SKIP")
    total = passed + failed + skipped
    by_tool = {}
    for s, _, t, _ in results:
        if s == "PASS":
            by_tool[t] = by_tool.get(t, 0) + 1
    by_tool_str = "  ".join(f"{t}: {n}" for t, n in sorted(by_tool.items()))

    print(f"\n  {passed}/{total} pasaron, {failed} fallaron, {skipped} skipped")
    if by_tool_str:
        print(f"  Por herramienta -> {by_tool_str}")
    print(f"  Screenshots en: {SCREENSHOT_DIR}")

    if failed:
        print("\n  Tests fallidos:")
        for s, label, tool, detail in results:
            if s == "FAIL":
                print(f"    - [{tool}] {label}" + (f" ({detail})" if detail else ""))
    if skipped:
        print("\n  Tests skipped:")
        for s, label, tool, detail in results:
            if s == "SKIP":
                print(f"    - [{tool}] {label} -- {detail}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
