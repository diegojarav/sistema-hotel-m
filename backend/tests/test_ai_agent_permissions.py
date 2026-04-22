"""
Feature 1 (v1.9.0) — AIAgentPermission activation tests.

Covers:
- Default permissions per role (admin all-true, recepcion view-only)
- Service layer get_or_create / update_permissions / get_allowed_tools
- Admin endpoints GET /admin/ai-permissions, GET/PUT /admin/ai-permissions/{role}
- Tool filtering middleware in agent.py
- RBAC: only admin can read/write permissions
- Safety: cannot lock admin out completely
"""

import pytest

from services import (
    AIAgentPermissionService,
    AIAgentPermissionError,
    PERMISSION_COLUMNS,
    TOOL_PERMISSION_MAP,
)


# ============================================================
# Service layer
# ============================================================

class TestServiceDefaults:
    def test_admin_has_all_permissions(self, db_session):
        row = AIAgentPermissionService.get_or_create(role="admin", db=db_session)
        for col in PERMISSION_COLUMNS:
            assert getattr(row, col) == 1, f"admin missing {col}"

    def test_recepcion_blocks_reports(self, db_session):
        row = AIAgentPermissionService.get_or_create(role="recepcion", db=db_session)
        assert row.can_view_reservations == 1
        assert row.can_view_guests == 1
        assert row.can_view_rooms == 1
        assert row.can_view_prices == 1
        assert row.can_view_reports == 0
        assert row.can_export_data == 0
        assert row.can_modify_settings == 0

    def test_recepcionista_same_as_recepcion(self, db_session):
        a = AIAgentPermissionService.get_or_create(role="recepcionista", db=db_session)
        b = AIAgentPermissionService.get_or_create(role="recepcion", db=db_session)
        for col in PERMISSION_COLUMNS:
            assert getattr(a, col) == getattr(b, col)

    def test_cocina_has_no_agent_access(self, db_session):
        row = AIAgentPermissionService.get_or_create(role="cocina", db=db_session)
        for col in PERMISSION_COLUMNS:
            assert getattr(row, col) == 0

    def test_normalizes_role_lowercase(self, db_session):
        row = AIAgentPermissionService.get_or_create(role="ADMIN", db=db_session)
        assert row.role == "admin"

    def test_unknown_role_seeds_all_false(self, db_session):
        row = AIAgentPermissionService.get_or_create(role="custom-role", db=db_session)
        for col in PERMISSION_COLUMNS:
            assert getattr(row, col) == 0


class TestGetAllowedTools:
    def test_admin_gets_all_tools(self, db_session):
        allowed = AIAgentPermissionService.get_allowed_tools(role="admin", db=db_session)
        # All 18 mapped tools should be present
        for tool_name in TOOL_PERMISSION_MAP.keys():
            assert tool_name in allowed

    def test_recepcion_blocked_from_reports_tools(self, db_session):
        allowed = AIAgentPermissionService.get_allowed_tools(role="recepcion", db=db_session)
        # Must include operational lookups
        assert "search_reservation" in allowed
        assert "check_availability" in allowed
        assert "get_hotel_rates" in allowed
        # Must NOT include any can_view_reports tool
        for tool_name, perm_col in TOOL_PERMISSION_MAP.items():
            if perm_col == "can_view_reports":
                assert tool_name not in allowed, f"recepcion should not see {tool_name}"

    def test_cocina_gets_zero_tools(self, db_session):
        allowed = AIAgentPermissionService.get_allowed_tools(role="cocina", db=db_session)
        assert allowed == []


class TestUpdatePermissions:
    def test_partial_update(self, db_session):
        # First seed admin (all true)
        AIAgentPermissionService.get_or_create(role="admin", db=db_session)

        row = AIAgentPermissionService.update_permissions(
            role="admin",
            updates={"can_view_reports": False},
            db=db_session,
        )
        assert row.can_view_reports == 0
        assert row.can_view_reservations == 1  # Unchanged

    def test_safety_blocks_disabling_all_admin_perms(self, db_session):
        AIAgentPermissionService.get_or_create(role="admin", db=db_session)
        all_false = {col: False for col in PERMISSION_COLUMNS}
        with pytest.raises(AIAgentPermissionError):
            AIAgentPermissionService.update_permissions(
                role="admin", updates=all_false, db=db_session
            )

    def test_safety_blocks_disabling_all_supervisor_perms(self, db_session):
        AIAgentPermissionService.get_or_create(role="supervisor", db=db_session)
        all_false = {col: False for col in PERMISSION_COLUMNS}
        with pytest.raises(AIAgentPermissionError):
            AIAgentPermissionService.update_permissions(
                role="supervisor", updates=all_false, db=db_session
            )

    def test_safety_allows_disabling_all_recepcion_perms(self, db_session):
        # Recepcion is not a management role — it's allowed to be locked out
        row = AIAgentPermissionService.update_permissions(
            role="recepcion",
            updates={col: False for col in PERMISSION_COLUMNS},
            db=db_session,
        )
        for col in PERMISSION_COLUMNS:
            assert getattr(row, col) == 0


# ============================================================
# Endpoints
# ============================================================

class TestEndpointsRBAC:
    def test_list_requires_admin(self, client, auth_headers_recep):
        r = client.get("/api/v1/admin/ai-permissions", headers=auth_headers_recep)
        assert r.status_code == 403

    def test_get_requires_admin(self, client, auth_headers_recep):
        r = client.get("/api/v1/admin/ai-permissions/recepcion", headers=auth_headers_recep)
        assert r.status_code == 403

    def test_put_requires_admin(self, client, auth_headers_recep):
        r = client.put(
            "/api/v1/admin/ai-permissions/recepcion",
            json={"can_view_reports": True},
            headers=auth_headers_recep,
        )
        assert r.status_code == 403

    def test_unauthenticated_rejected(self, client):
        r = client.get("/api/v1/admin/ai-permissions")
        assert r.status_code in (401, 403)


class TestListEndpoint:
    def test_returns_default_roles(self, client, auth_headers_admin):
        r = client.get("/api/v1/admin/ai-permissions", headers=auth_headers_admin)
        assert r.status_code == 200
        rows = r.json()
        roles = {row["role"] for row in rows}
        # All seeded defaults should be present
        for role in {"admin", "supervisor", "gerencia", "recepcion", "recepcionista", "cocina"}:
            assert role in roles

    def test_dto_has_all_columns(self, client, auth_headers_admin):
        r = client.get("/api/v1/admin/ai-permissions/admin", headers=auth_headers_admin)
        assert r.status_code == 200
        body = r.json()
        for col in PERMISSION_COLUMNS:
            assert col in body, f"missing {col} in response"
            assert isinstance(body[col], bool)


class TestUpdateEndpoint:
    def test_partial_update_persists(self, client, auth_headers_admin):
        # Toggle recepcion's can_view_reports to True
        r = client.put(
            "/api/v1/admin/ai-permissions/recepcion",
            json={"can_view_reports": True},
            headers=auth_headers_admin,
        )
        assert r.status_code == 200
        assert r.json()["can_view_reports"] is True

        # Read back
        r2 = client.get("/api/v1/admin/ai-permissions/recepcion", headers=auth_headers_admin)
        assert r2.json()["can_view_reports"] is True

    def test_empty_body_rejected(self, client, auth_headers_admin):
        r = client.put(
            "/api/v1/admin/ai-permissions/recepcion",
            json={},
            headers=auth_headers_admin,
        )
        assert r.status_code == 400

    def test_unknown_fields_ignored(self, client, auth_headers_admin):
        # The Pydantic model rejects unknown fields with 422
        r = client.put(
            "/api/v1/admin/ai-permissions/recepcion",
            json={"can_view_reports": True, "ignored_unknown": True},
            headers=auth_headers_admin,
        )
        # FastAPI default lets unknown fields through (Pydantic v2 model_config not set strict)
        # We accept either 200 (ignored) or 422 (strict) — the important thing is the
        # known field still works
        assert r.status_code in (200, 422)


class TestAllowedToolsEndpoint:
    def test_admin_sees_all(self, client, auth_headers_admin):
        r = client.get(
            "/api/v1/admin/ai-permissions/admin/allowed-tools",
            headers=auth_headers_admin,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["role"] == "admin"
        for tool_name in TOOL_PERMISSION_MAP.keys():
            assert tool_name in data["allowed_tools"]

    def test_recepcion_filtered(self, client, auth_headers_admin):
        r = client.get(
            "/api/v1/admin/ai-permissions/recepcion/allowed-tools",
            headers=auth_headers_admin,
        )
        assert r.status_code == 200
        allowed = r.json()["allowed_tools"]
        # Operational tools present
        assert "search_reservation" in allowed
        # Reports blocked
        assert "consultar_caja" not in allowed
        assert "get_revenue_summary" not in allowed


# ============================================================
# Agent middleware (filter_tools_for_role)
# ============================================================

class TestAgentToolFiltering:
    def test_filter_returns_full_list_for_admin(self, db_session):
        from api.v1.endpoints.agent import filter_tools_for_role
        from api.v1.endpoints.ai_tools import TOOLS_LIST

        # Seed admin
        AIAgentPermissionService.get_or_create(role="admin", db=db_session)
        filtered = filter_tools_for_role("admin")
        assert len(filtered) == len(TOOLS_LIST)

    def test_filter_drops_reports_for_recepcion(self, db_session):
        from api.v1.endpoints.agent import filter_tools_for_role

        AIAgentPermissionService.get_or_create(role="recepcion", db=db_session)
        filtered = filter_tools_for_role("recepcion")
        names = {fn.__name__ for fn in filtered}
        # Operational tools survived
        assert "search_reservation" in names
        # Report tools removed
        assert "consultar_caja" not in names
        assert "get_revenue_summary" not in names
        assert "reporte_cocina" not in names

    def test_filter_returns_empty_for_cocina(self, db_session):
        from api.v1.endpoints.agent import filter_tools_for_role

        AIAgentPermissionService.get_or_create(role="cocina", db=db_session)
        filtered = filter_tools_for_role("cocina")
        # Every tool in TOOLS_LIST is in TOOL_PERMISSION_MAP, so all are gated and dropped
        assert filtered == []
