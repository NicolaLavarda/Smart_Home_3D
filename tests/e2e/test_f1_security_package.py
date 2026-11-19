from __future__ import annotations

import asyncio
import dataclasses
import time

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient


@pytest.mark.tier1
def test_f1_t1_01_security_package_public_exports() -> None:
    import spatial_server.security as security_pkg
    from spatial_server.security import ha_auth

    for symbol in (
        "HAUserPrincipal",
        "HomeAssistantAuthVerifier",
        "require_authenticated_user",
        "require_admin_user",
    ):
        assert hasattr(security_pkg, symbol), f"Missing export {symbol} in spatial_server.security"
        assert hasattr(ha_auth, symbol), f"Missing export {symbol} in spatial_server.security.ha_auth"

    field_names = {f.name for f in dataclasses.fields(security_pkg.HAUserPrincipal)}
    expected_fields = {
        "user_id",
        "name",
        "is_admin",
        "is_owner",
        "authenticated_at",
        "expires_at",
    }
    assert expected_fields.issubset(field_names)


@pytest.mark.tier1
def test_f1_t1_02_verifier_validates_admin_via_ha_ws(fake_ha_server) -> None:
    from spatial_server.security import HAUserPrincipal, HomeAssistantAuthVerifier

    verifier = HomeAssistantAuthVerifier(
        ha_local_url=fake_ha_server.base_url,
        cache_ttl_s=120.0,
        session_secret_key="e2e-test-session-secret-0123456789abcdef",
    )
    principal = asyncio.run(verifier.verify_token("tok-admin"))

    assert isinstance(principal, HAUserPrincipal)
    assert principal.user_id == "u-admin"
    assert principal.name == "Admin"
    assert principal.is_admin is True
    assert principal.is_owner is False
    assert principal.expires_at > principal.authenticated_at
    assert fake_ha_server.state.ws_auth_calls == 1


@pytest.mark.tier1
def test_f1_t1_03_verifier_validates_owner_and_resident_roles(fake_ha_server) -> None:
    from spatial_server.security import HomeAssistantAuthVerifier

    verifier = HomeAssistantAuthVerifier(
        ha_local_url=fake_ha_server.base_url,
        cache_ttl_s=120.0,
        session_secret_key="e2e-test-session-secret-0123456789abcdef",
    )
    owner = asyncio.run(verifier.verify_token("tok-owner"))
    resident = asyncio.run(verifier.verify_token("tok-resident"))

    assert owner.user_id == "u-owner"
    assert owner.is_owner is True
    assert owner.is_admin is False

    assert resident.user_id == "u-res"
    assert resident.is_owner is False
    assert resident.is_admin is False


@pytest.mark.tier1
def test_f1_t1_04_verifier_ttl_cache_deduplicates_ha_calls(fake_ha_server) -> None:
    from spatial_server.security import HomeAssistantAuthVerifier

    verifier = HomeAssistantAuthVerifier(
        ha_local_url=fake_ha_server.base_url,
        cache_ttl_s=120.0,
        session_secret_key="e2e-test-session-secret-0123456789abcdef",
    )
    p1 = asyncio.run(verifier.verify_token("tok-admin"))
    p2 = asyncio.run(verifier.verify_token("tok-admin"))
    assert p1 == p2
    assert fake_ha_server.state.ws_auth_calls == 1

    # Distinct token must NOT hit the cached entry for tok-admin
    p3 = asyncio.run(verifier.verify_token("tok-resident"))
    assert p3.user_id == "u-res"
    assert fake_ha_server.state.ws_auth_calls == 2


@pytest.mark.tier1
def test_f1_t1_05_session_cookie_sign_and_verify_roundtrip(fake_ha_server) -> None:
    from spatial_server.security import HAUserPrincipal, HomeAssistantAuthVerifier

    verifier = HomeAssistantAuthVerifier(
        ha_local_url=fake_ha_server.base_url,
        session_secret_key="e2e-test-session-secret-0123456789abcdef",
    )
    now = time.time()
    principal = HAUserPrincipal(
        user_id="u-owner",
        name="Owner",
        is_admin=False,
        is_owner=True,
        authenticated_at=now,
        expires_at=now + 600.0,
    )
    cookie_val, expires_at = verifier.create_session_token(principal)
    assert isinstance(cookie_val, str) and "." in cookie_val
    assert expires_at > now

    verified = verifier.verify_session_cookie(cookie_val)
    assert verified.user_id == principal.user_id
    assert verified.name == principal.name
    assert verified.is_admin is False
    assert verified.is_owner is True


@pytest.mark.tier1
def test_f1_t1_06_fastapi_deps_accept_cookie_or_bearer_and_enforce_admin(
    fake_ha_server, tmp_path
) -> None:
    from spatial_server.config import SpatialServerConfig
    from spatial_server.security import (
        SH3D_SESSION_COOKIE_NAME,
        HAUserPrincipal,
        HomeAssistantAuthVerifier,
        require_admin_user,
        require_authenticated_user,
    )

    cfg = dataclasses.replace(
        SpatialServerConfig.from_env(),
        data_dir=tmp_path,
        models_dir=tmp_path,
        ha_local_url=fake_ha_server.base_url,
        auth_required=True,
        session_secret_key="e2e-test-session-secret-0123456789abcdef",
    )
    verifier = HomeAssistantAuthVerifier.from_config(cfg)

    probe_app = FastAPI()
    probe_app.state.config = cfg
    probe_app.state.auth_verifier = verifier

    @probe_app.get("/probe/auth")
    async def probe_auth(user: HAUserPrincipal = Depends(require_authenticated_user)):
        return user.to_user_dict()

    @probe_app.get("/probe/admin")
    async def probe_admin(user: HAUserPrincipal = Depends(require_admin_user)):
        return user.to_user_dict()

    admin_principal = asyncio.run(verifier.verify_token("tok-admin"))
    owner_principal = asyncio.run(verifier.verify_token("tok-owner"))
    admin_cookie, _ = verifier.create_session_token(admin_principal)
    owner_cookie, _ = verifier.create_session_token(owner_principal)

    with TestClient(probe_app) as tc:
        # Bearer path
        r_bearer = tc.get("/probe/admin", headers={"Authorization": "Bearer tok-admin"})
        assert r_bearer.status_code == 200
        assert r_bearer.json()["user_id"] == "u-admin"

        # Cookie path (admin)
        r_cookie = tc.get(
            "/probe/auth", cookies={SH3D_SESSION_COOKIE_NAME: admin_cookie}
        )
        assert r_cookie.status_code == 200
        assert r_cookie.json()["is_admin"] is True

        # Owner-only (is_owner=True, is_admin=False) passes require_admin_user
        r_owner = tc.get(
            "/probe/admin", cookies={SH3D_SESSION_COOKIE_NAME: owner_cookie}
        )
        assert r_owner.status_code == 200
        assert r_owner.json()["is_owner"] is True


@pytest.mark.tier2
def test_f1_t2_01_tampered_session_cookie_rejected(fake_ha_server) -> None:
    from spatial_server.security import (
        AuthError,
        HAUserPrincipal,
        HomeAssistantAuthVerifier,
    )

    verifier = HomeAssistantAuthVerifier(
        ha_local_url=fake_ha_server.base_url,
        session_secret_key="e2e-test-session-secret-0123456789abcdef",
    )
    now = time.time()
    token, _ = verifier.create_session_token(
        HAUserPrincipal("u-res", "Residente", False, False, now, now + 300.0)
    )
    payload_b64, sig_b64 = token.split(".", 1)

    tampered_sig = sig_b64[:-1] + ("A" if sig_b64[-1] != "A" else "B")
    with pytest.raises(AuthError):
        verifier.verify_session_cookie(f"{payload_b64}.{tampered_sig}")

    tampered_payload = ("A" if payload_b64[0] != "A" else "B") + payload_b64[1:]
    with pytest.raises(AuthError):
        verifier.verify_session_cookie(f"{tampered_payload}.{sig_b64}")


@pytest.mark.tier2
def test_f1_t2_02_expired_session_cookie_rejected(fake_ha_server) -> None:
    from spatial_server.security import (
        AuthError,
        HAUserPrincipal,
        HomeAssistantAuthVerifier,
    )

    verifier = HomeAssistantAuthVerifier(
        ha_local_url=fake_ha_server.base_url,
        session_secret_key="e2e-test-session-secret-0123456789abcdef",
    )
    now = time.time()
    expired_token, _ = verifier.create_session_token(
        HAUserPrincipal("u-admin", "Admin", True, False, now - 100.0, now - 10.0),
        ttl_s=0.0,
    )
    with pytest.raises(AuthError):
        verifier.verify_session_cookie(expired_token)


@pytest.mark.tier2
def test_f1_t2_03_ttl_cache_expiration_triggers_revalidation(fake_ha_server) -> None:
    from spatial_server.security import AuthError, HomeAssistantAuthVerifier

    verifier = HomeAssistantAuthVerifier(
        ha_local_url=fake_ha_server.base_url,
        cache_ttl_s=0.15,
        session_secret_key="e2e-test-session-secret-0123456789abcdef",
    )
    principal = asyncio.run(verifier.verify_token("tok-admin"))
    assert principal.user_id == "u-admin"
    assert fake_ha_server.state.ws_auth_calls == 1

    # Wait past TTL and revoke token in Fake HA
    time.sleep(0.25)
    fake_ha_server.state.tokens.pop("tok-admin")

    with pytest.raises(AuthError):
        asyncio.run(verifier.verify_token("tok-admin"))
    assert fake_ha_server.state.ws_auth_calls == 2


@pytest.mark.tier2
def test_f1_t2_04_ws_unavailable_rest_api_fallback_fail_closed(fake_ha_server) -> None:
    from spatial_server.security import AuthError, HomeAssistantAuthVerifier

    verifier = HomeAssistantAuthVerifier(
        ha_local_url=fake_ha_server.base_url,
        cache_ttl_s=0.0,
        session_secret_key="e2e-test-session-secret-0123456789abcdef",
    )

    # WS auth/current_user fails, REST GET /api/ returns 200 -> fail-closed non-admin
    fake_ha_server.state.ws_mode = "auth_current_user_error"
    principal = asyncio.run(verifier.verify_token("tok-admin"))
    assert principal.is_admin is False
    assert principal.is_owner is False
    assert fake_ha_server.state.rest_auth_calls == 1

    # WS drops and REST returns 401 -> rejected
    fake_ha_server.state.ws_mode = "drop"
    fake_ha_server.state.rest_status_override = 401
    with pytest.raises(AuthError):
        asyncio.run(verifier.verify_token("tok-admin"))


@pytest.mark.tier2
def test_f1_t2_05_ha_completely_unreachable_fails_closed(closed_port_url) -> None:
    from spatial_server.security import AuthError, HomeAssistantAuthVerifier

    verifier = HomeAssistantAuthVerifier(
        ha_local_url=closed_port_url,
        request_timeout_s=0.5,
        session_secret_key="e2e-test-session-secret-0123456789abcdef",
    )
    with pytest.raises(AuthError):
        asyncio.run(verifier.verify_token("tok-admin"))


@pytest.mark.tier2
def test_f1_t2_06_non_admin_resident_denied_by_require_admin_user(
    fake_ha_server, tmp_path
) -> None:
    from spatial_server.config import SpatialServerConfig
    from spatial_server.security import (
        HAUserPrincipal,
        HomeAssistantAuthVerifier,
        require_admin_user,
        require_authenticated_user,
    )

    cfg = dataclasses.replace(
        SpatialServerConfig.from_env(),
        data_dir=tmp_path,
        models_dir=tmp_path,
        ha_local_url=fake_ha_server.base_url,
        auth_required=True,
        session_secret_key="e2e-test-session-secret-0123456789abcdef",
    )
    verifier = HomeAssistantAuthVerifier.from_config(cfg)

    probe_app = FastAPI()
    probe_app.state.config = cfg
    probe_app.state.auth_verifier = verifier

    @probe_app.get("/probe/auth")
    async def probe_auth(user: HAUserPrincipal = Depends(require_authenticated_user)):
        return user.to_user_dict()

    @probe_app.get("/probe/admin")
    async def probe_admin(user: HAUserPrincipal = Depends(require_admin_user)):
        return user.to_user_dict()

    with TestClient(probe_app) as tc:
        headers = {"Authorization": "Bearer tok-resident"}
        assert tc.get("/probe/auth", headers=headers).status_code == 200
        assert tc.get("/probe/admin", headers=headers).status_code == 403
