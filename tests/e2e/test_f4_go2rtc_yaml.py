from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml


def _load_go2rtc_yaml(repo_root: Path) -> tuple[str, dict]:
    yaml_path = repo_root / "go2rtc" / "go2rtc.yaml"
    assert yaml_path.is_file(), f"Missing {yaml_path}"
    raw = yaml_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    assert isinstance(data, dict)
    return raw, data


@pytest.mark.tier1
def test_f4_t1_01_go2rtc_yaml_valid_and_api_loopback_bound(repo_root: Path) -> None:
    _, data = _load_go2rtc_yaml(repo_root)
    assert data["api"]["listen"] == "127.0.0.1:1984"


@pytest.mark.tier1
def test_f4_t1_02_go2rtc_api_origin_restricted_not_wildcard(repo_root: Path) -> None:
    _, data = _load_go2rtc_yaml(repo_root)
    assert "origin" in data["api"]
    assert data["api"]["origin"] == ""
    assert data["api"]["origin"] != "*"


@pytest.mark.tier1
def test_f4_t1_03_go2rtc_rtsp_loopback_bound(repo_root: Path) -> None:
    _, data = _load_go2rtc_yaml(repo_root)
    assert data["rtsp"]["listen"] == "127.0.0.1:8554"


@pytest.mark.tier1
def test_f4_t1_04_go2rtc_webrtc_listen_and_parametric_candidates(
    repo_root: Path,
) -> None:
    _, data = _load_go2rtc_yaml(repo_root)
    webrtc = data["webrtc"]
    assert webrtc["listen"] == ":8555"
    candidates = [str(c) for c in webrtc["candidates"]]
    assert "${GO2RTC_CANDIDATE_LAN:127.0.0.1:8555}" in candidates
    assert "${GO2RTC_CANDIDATE_TAILSCALE:127.0.0.1:8555}" in candidates
    assert "stun:8555" in candidates


@pytest.mark.tier1
def test_f4_t1_05_go2rtc_streams_configured_with_env_placeholders(
    repo_root: Path,
) -> None:
    _, data = _load_go2rtc_yaml(repo_root)
    streams = data["streams"]
    for stream_name in ("carraio_main", "carraio_sub", "carraio_scorrevole"):
        assert stream_name in streams
        assert len(streams[stream_name]) >= 1

    for cam_stream in ("carraio_main", "carraio_sub"):
        joined = " ".join(str(x) for x in streams[cam_stream])
        assert "${REOLINK_CARRAIO_PASS:" in joined


@pytest.mark.tier2
def test_f4_t2_01_no_wildcard_api_or_rtsp_bind_addresses(repo_root: Path) -> None:
    _, data = _load_go2rtc_yaml(repo_root)
    for section in ("api", "rtsp"):
        listen = str(data[section]["listen"]).strip()
        assert listen.startswith("127.0.0.1:"), f"{section}.listen={listen!r} not loopback"
        assert not listen.startswith(":")
        assert not listen.startswith("0.0.0.0:")


@pytest.mark.tier2
def test_f4_t2_02_no_hardcoded_lan_or_tailscale_ips_in_webrtc_candidates(
    repo_root: Path,
) -> None:
    _, data = _load_go2rtc_yaml(repo_root)
    for candidate in data["webrtc"]["candidates"]:
        stripped = re.sub(r"\$\{[^}]+\}", "", str(candidate))
        assert not re.search(r"\b192\.168\.\d+\.\d+\b", stripped)
        assert not re.search(r"\b100\.\d+\.\d+\.\d+\b", stripped)


@pytest.mark.tier2
def test_f4_t2_03_no_plaintext_passwords_in_go2rtc_yaml(repo_root: Path) -> None:
    _, data = _load_go2rtc_yaml(repo_root)
    for name, entries in data["streams"].items():
        for entry in entries:
            url = str(entry)
            userinfo_match = re.match(r"^[a-zA-Z]+://([^@/]+)@", url)
            if userinfo_match:
                userinfo = userinfo_match.group(1)
                stripped = re.sub(r"\$\{[^}]+\}", "", userinfo)
                if ":" in stripped:
                    _, literal_pw = stripped.split(":", 1)
                    assert literal_pw == "", (
                        f"Stream {name} contains plaintext password in URL"
                    )


@pytest.mark.tier2
def test_f4_t2_04_no_deprecated_reolink_carraio_password_var_name(
    repo_root: Path,
) -> None:
    raw, _ = _load_go2rtc_yaml(repo_root)
    assert "REOLINK_CARRAIO_PASSWORD" not in raw


@pytest.mark.tier2
def test_f4_t2_05_carraio_scorrevole_references_loopback_rtsp(repo_root: Path) -> None:
    _, data = _load_go2rtc_yaml(repo_root)
    entries = [str(x) for x in data["streams"]["carraio_scorrevole"]]
    assert any(url.startswith("rtsp://127.0.0.1:8554/") for url in entries)
