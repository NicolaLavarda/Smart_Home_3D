from __future__ import annotations

import pytest


@pytest.mark.tier1
def test_f2_t1_01_default_host_is_loopback_127_0_0_1(monkeypatch) -> None:
    from spatial_server.config import SpatialServerConfig

    monkeypatch.delenv("SPATIAL_SERVER_HOST", raising=False)
    cfg = SpatialServerConfig.from_env()
    assert cfg.host == "127.0.0.1"


@pytest.mark.tier1
def test_f2_t1_02_default_auth_required_and_cache_ttl(monkeypatch) -> None:
    from spatial_server.config import SpatialServerConfig

    monkeypatch.delenv("SPATIAL_AUTH_REQUIRED", raising=False)
    cfg = SpatialServerConfig.from_env()
    assert cfg.auth_required is True
    assert cfg.auth_cache_ttl_s == 120.0


@pytest.mark.tier1
def test_f2_t1_03_allowed_origins_parsed_from_comma_separated_env(monkeypatch) -> None:
    from spatial_server.config import SpatialServerConfig

    monkeypatch.setenv(
        "SPATIAL_ALLOWED_ORIGINS",
        "https://a.ts.net, http://127.0.0.1:8080 ",
    )
    cfg = SpatialServerConfig.from_env()
    assert list(cfg.allowed_origins) == ["https://a.ts.net", "http://127.0.0.1:8080"]


@pytest.mark.tier1
def test_f2_t1_04_session_secret_key_loaded_from_env(monkeypatch) -> None:
    from spatial_server.config import SpatialServerConfig

    monkeypatch.setenv("SPATIAL_SESSION_SECRET", "custom-secret-value-9876543210abcdef")
    cfg = SpatialServerConfig.from_env()
    assert cfg.session_secret_key == "custom-secret-value-9876543210abcdef"


@pytest.mark.tier1
def test_f2_t1_05_ha_public_url_loaded_and_normalized(monkeypatch) -> None:
    from spatial_server.config import SpatialServerConfig

    monkeypatch.setenv(
        "VITE_HA_PUBLIC_URL",
        "wss://pc.tailnet.ts.net:8443/api/websocket/",
    )
    cfg = SpatialServerConfig.from_env()
    assert cfg.ha_public_url == "https://pc.tailnet.ts.net:8443"


@pytest.mark.tier2
@pytest.mark.parametrize(
    ("raw_val", "expected"),
    [
        ("false", False),
        ("FALSE", False),
        ("0", False),
        ("no", False),
        ("true", True),
        ("1", True),
    ],
)
def test_f2_t2_01_auth_required_false_variants_parsed(
    monkeypatch, raw_val: str, expected: bool
) -> None:
    from spatial_server.config import SpatialServerConfig

    monkeypatch.setenv("SPATIAL_AUTH_REQUIRED", raw_val)
    cfg = SpatialServerConfig.from_env()
    assert cfg.auth_required is expected


@pytest.mark.tier2
def test_f2_t2_02_missing_session_secret_generates_nonempty_ephemeral_secret(
    monkeypatch,
) -> None:
    import time
    from spatial_server.config import SpatialServerConfig
    from spatial_server.security import AuthError, HAUserPrincipal, HomeAssistantAuthVerifier

    monkeypatch.delenv("SPATIAL_SESSION_SECRET", raising=False)
    cfg1 = SpatialServerConfig.from_env()
    assert isinstance(cfg1.session_secret_key, str)

    monkeypatch.setenv("SPATIAL_SESSION_SECRET", "")
    cfg2 = SpatialServerConfig.from_env()
    assert isinstance(cfg2.session_secret_key, str)

    # Even when cfg.session_secret_key is "", verifier must generate a random
    # per-instance ephemeral HMAC secret (never an empty/static key).
    v1 = HomeAssistantAuthVerifier.from_config(cfg2)
    v2 = HomeAssistantAuthVerifier.from_config(cfg2)
    now = time.time()
    principal = HAUserPrincipal("u-admin", "Admin", True, False, now, now + 300.0)
    cookie_val, _ = v1.create_session_token(principal)
    assert v1.verify_session_cookie(cookie_val).user_id == "u-admin"
    with pytest.raises(AuthError):
        v2.verify_session_cookie(cookie_val)


@pytest.mark.tier2
def test_f2_t2_03_empty_or_whitespace_allowed_origins_handled_safely(
    monkeypatch,
) -> None:
    from spatial_server.config import SpatialServerConfig

    for raw in (" , , ", "*"):
        monkeypatch.setenv("SPATIAL_ALLOWED_ORIGINS", raw)
        cfg = SpatialServerConfig.from_env()
        assert "*" not in cfg.allowed_origins
        for origin in cfg.allowed_origins:
            assert origin.startswith(
                (
                    "http://localhost:",
                    "http://127.0.0.1:",
                    "https://localhost:",
                    "https://127.0.0.1:",
                )
            ), f"Unexpected fallback origin {origin!r} for {raw!r}"


@pytest.mark.tier2
def test_f2_t2_04_ha_public_url_empty_and_http_ws_schemes(monkeypatch) -> None:
    from spatial_server.config import SpatialServerConfig

    monkeypatch.delenv("VITE_HA_PUBLIC_URL", raising=False)
    assert SpatialServerConfig.from_env().ha_public_url == ""

    monkeypatch.setenv("VITE_HA_PUBLIC_URL", "ws://192.168.1.5:8123/api/websocket")
    assert SpatialServerConfig.from_env().ha_public_url == "http://192.168.1.5:8123"


@pytest.mark.tier2
def test_f2_t2_05_host_override_from_env_still_respected(monkeypatch) -> None:
    from spatial_server.config import SpatialServerConfig

    monkeypatch.setenv("SPATIAL_SERVER_HOST", "0.0.0.0")
    cfg = SpatialServerConfig.from_env()
    assert cfg.host == "0.0.0.0"
