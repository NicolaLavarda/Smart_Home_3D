from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest


def _read_caddyfile(repo_root: Path) -> str:
    caddyfile = repo_root / "caddy" / "Caddyfile"
    assert caddyfile.is_file(), f"Missing {caddyfile}"
    lines: list[str] = []
    for line in caddyfile.read_text(encoding="utf-8").splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _extract_handle_block(text: str, prefix: str) -> str:
    idx = text.find(prefix)
    assert idx != -1, f"Missing block starting with {prefix!r}"
    brace_start = text.find("{", idx)
    assert brace_start != -1, f"Missing opening '{{' for {prefix!r}"
    depth = 0
    for pos in range(brace_start, len(text)):
        ch = text[pos]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[idx : pos + 1]
    raise AssertionError(f"Unbalanced braces in block {prefix!r}")


@pytest.mark.tier1
def test_f6_t1_01_caddyfile_exists_and_binds_loopback_8080(repo_root: Path) -> None:
    text = _read_caddyfile(repo_root)
    has_direct_loopback = bool(
        re.search(r"(?:http://)?127\.0\.0\.1:8080\b", text)
    )
    has_split_loopback = bool(
        re.search(r"http://:8080\s*\{[\s\S]*?\bbind\s+127\.0\.0\.1\b", text)
    )
    assert has_direct_loopback or has_split_loopback


@pytest.mark.tier1
def test_f6_t1_02_caddyfile_sets_required_security_headers(repo_root: Path) -> None:
    text = _read_caddyfile(repo_root)
    assert "X-Content-Type-Options" in text
    assert "X-Frame-Options" in text
    assert "Referrer-Policy" in text


@pytest.mark.tier1
def test_f6_t1_03_caddyfile_proxies_api_and_ws_to_spatial_server(
    repo_root: Path,
) -> None:
    text = _read_caddyfile(repo_root)
    api_block = _extract_handle_block(text, "handle /api/v1/*")
    ws_block = _extract_handle_block(text, "handle /ws/spatial")
    assert "reverse_proxy 127.0.0.1:8765" in api_block
    assert "reverse_proxy 127.0.0.1:8765" in ws_block


@pytest.mark.tier1
def test_f6_t1_04_caddyfile_protects_go2rtc_webrtc_and_ws_with_forward_auth(
    repo_root: Path,
) -> None:
    text = _read_caddyfile(repo_root)
    for route in ("handle /go2rtc/api/webrtc*", "handle /go2rtc/api/ws*"):
        block = _extract_handle_block(text, route)
        assert "forward_auth 127.0.0.1:8765" in block
        assert "uri /api/v1/auth/verify" in block
        assert "uri strip_prefix /go2rtc" in block
        assert "reverse_proxy 127.0.0.1:1984" in block


@pytest.mark.tier1
def test_f6_t1_05_caddyfile_blocks_other_go2rtc_routes_with_403(
    repo_root: Path,
) -> None:
    text = _read_caddyfile(repo_root)
    block = _extract_handle_block(text, "handle /go2rtc/*")
    assert "respond" in block and "403" in block


@pytest.mark.tier1
def test_f6_t1_06_caddyfile_serves_dist_with_compression_and_spa_fallback(
    repo_root: Path,
) -> None:
    text = _read_caddyfile(repo_root)
    assert re.search(r"\broot\s+\*\s+dist\b", text)
    assert "encode zstd gzip" in text
    assert "try_files {path} /index.html" in text
    assert "file_server" in text


@pytest.mark.tier2
def test_f6_t2_01_caddyfile_disables_caching_for_pwa_control_files(
    repo_root: Path,
) -> None:
    text = _read_caddyfile(repo_root)
    assert "no-cache" in text and "must-revalidate" in text
    for pwa_path in (
        "/index.html",
        "/sw.js",
        "/workbox-*.js",
        "/manifest.webmanifest",
        "/models/scene_manifest.json",
    ):
        assert pwa_path in text, f"Missing no-cache matcher for {pwa_path}"
    assert re.search(r"@no_cache\s+path\s+(?:[^\n]*\s)?/(?:\s|$)", text)


@pytest.mark.tier2
def test_f6_t2_02_caddyfile_sets_immutable_cache_for_hashed_assets(
    repo_root: Path,
) -> None:
    text = _read_caddyfile(repo_root)
    assert "/assets/*" in text
    assert re.search(r"Cache-Control[^\n]*max-age=\d+[^\n]*immutable", text)


@pytest.mark.tier2
def test_f6_t2_03_caddyfile_route_ordering_protects_go2rtc_without_exposing_ui(
    repo_root: Path,
) -> None:
    text = _read_caddyfile(repo_root)
    webrtc_block = _extract_handle_block(text, "handle /go2rtc/api/webrtc*")
    ws_block = _extract_handle_block(text, "handle /go2rtc/api/ws*")
    # Every reverse_proxy to go2rtc (:1984) must live inside one of the two protected blocks.
    all_1984 = len(re.findall(r"127\.0\.0\.1:1984", text))
    protected_1984 = len(re.findall(r"127\.0\.0\.1:1984", webrtc_block)) + len(
        re.findall(r"127\.0\.0\.1:1984", ws_block)
    )
    assert all_1984 == 2 and protected_1984 == 2

    deny_block = _extract_handle_block(text, "handle /go2rtc/*")
    assert "1984" not in deny_block and "403" in deny_block


@pytest.mark.tier2
def test_f6_t2_04_caddyfile_forward_auth_targets_auth_verify_not_auth_session(
    repo_root: Path,
) -> None:
    text = _read_caddyfile(repo_root)
    assert "/api/v1/auth/verify" in text
    assert "/api/v1/auth/session" not in text


@pytest.mark.tier2
def test_f6_t2_05_caddyfile_uses_balanced_braces_and_valid_syntax(
    repo_root: Path,
) -> None:
    text = _read_caddyfile(repo_root)
    depth = 0
    for ch in text:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            assert depth >= 0, "Unexpected closing brace in Caddyfile"
    assert depth == 0, "Unclosed brace in Caddyfile"
    assert not re.search(r"<[A-Za-z0-9_-]+>", text), "Unreplaced <placeholder> in Caddyfile"

    caddy_exe = repo_root / "caddy" / "caddy.exe"
    if caddy_exe.is_file():
        proc = subprocess.run(
            [
                str(caddy_exe),
                "validate",
                "--config",
                str(repo_root / "caddy" / "Caddyfile"),
                "--adapter",
                "caddyfile",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0, f"caddy validate failed:\n{proc.stdout}\n{proc.stderr}"


@pytest.mark.tier2
def test_f6_t2_06_caddyfile_does_not_enable_auto_https_or_expose_repo_root(
    repo_root: Path,
) -> None:
    text = _read_caddyfile(repo_root)
    assert "auto_https off" in text
    assert "0.0.0.0" not in text
    assert ":443" not in text
    assert not re.search(r"\broot\s+\*\s+\.(?:/|\\|\s|$)", text)
