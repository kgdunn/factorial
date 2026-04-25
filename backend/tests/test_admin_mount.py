"""Smoke tests for the read-only sqladmin DB browser.

These tests don't talk to PostgreSQL — they verify wiring (routes
exist, the mount didn't fail), that unauthenticated visits are
redirected to the login form, and that sensitive columns
(``password_hash``, setup-token / invite-token strings) are
configured as excluded so they cannot leak into rendered detail
pages.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.admin.views import (
    ALL_VIEWS,
    SetupTokenAdmin,
    SignupRequestAdmin,
    UserAdmin,
)
from app.models.setup_token import SetupToken
from app.models.signup_request import SignupRequest
from app.models.user import User


@pytest.mark.asyncio
async def test_admin_root_redirects_when_unauthenticated(client: AsyncClient) -> None:
    resp = await client.get("/admin/", follow_redirects=False)
    assert resp.status_code in (302, 303, 307)
    assert "/admin/login" in resp.headers.get("location", "")


@pytest.mark.asyncio
async def test_admin_login_form_renders(client: AsyncClient) -> None:
    resp = await client.get("/admin/login", follow_redirects=False)
    assert resp.status_code == 200
    body = resp.text.lower()
    # The login form posts username + password fields.
    assert "username" in body
    assert "password" in body


@pytest.mark.asyncio
async def test_admin_login_rejects_blank_credentials(client: AsyncClient) -> None:
    resp = await client.post(
        "/admin/login",
        data={"username": "", "password": ""},
        follow_redirects=False,
    )
    # sqladmin signals failure with 400 / re-rendered form / redirect back
    # to the form; the load-bearing check is that no admin session exists
    # afterwards, so the next /admin/ hit still bounces to /admin/login.
    assert resp.status_code < 500
    follow_up = await client.get("/admin/", follow_redirects=False)
    assert follow_up.status_code in (302, 303, 307)
    assert "/admin/login" in follow_up.headers.get("location", "")


def test_every_model_view_is_read_only() -> None:
    assert ALL_VIEWS, "no ModelViews registered"
    for view in ALL_VIEWS:
        assert view.can_create is False, f"{view.__name__} allows create"
        assert view.can_edit is False, f"{view.__name__} allows edit"
        assert view.can_delete is False, f"{view.__name__} allows delete"
        assert view.can_export is False, f"{view.__name__} allows export"


def test_sensitive_columns_are_excluded_from_detail_view() -> None:
    assert User.password_hash in UserAdmin.column_details_exclude_list
    assert SetupToken.token in SetupTokenAdmin.column_details_exclude_list
    assert SignupRequest.invite_token in SignupRequestAdmin.column_details_exclude_list


def test_sensitive_columns_are_not_in_list_view() -> None:
    """Belt-and-braces: column_list never names the secret columns either."""
    assert User.password_hash not in UserAdmin.column_list
    assert SetupToken.token not in SetupTokenAdmin.column_list
    assert SignupRequest.invite_token not in SignupRequestAdmin.column_list
