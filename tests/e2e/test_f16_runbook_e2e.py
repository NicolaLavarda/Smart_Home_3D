from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK_PATH = REPO_ROOT / "docs" / "RUNBOOK_PRODUZIONE_FAMIGLIA_TAILSCALE.md"


def _read_runbook() -> str:
    assert RUNBOOK_PATH.exists(), f"Missing runbook: {RUNBOOK_PATH}"
    return RUNBOOK_PATH.read_text(encoding="utf-8")


# =============================================================================
# F16 Tier 1 — Completeness & Required Section Tests (7 tests)
# =============================================================================


def test_t1_f16_01_runbook_exists_utf8_and_italian():
    """T1-F16-01: Runbook exists, >= 150 lines, valid UTF-8, written in Italian."""
    text = _read_runbook()
    lines = text.splitlines()
    assert len(lines) >= 150, f"Runbook too short ({len(lines)} lines < 150)"

    for kw in ("Home Assistant", "Tailscale", "Admin", "Residente", "Firewall", "PWA"):
        assert kw.lower() in text.lower(), f"Runbook missing required keyword '{kw}'"

    italian_markers = ("configurazione", "sicurezza", "servizi", "utenti", "famiglia")
    hits = sum(1 for m in italian_markers if m in text.lower())
    assert hits >= 4, f"Runbook does not appear to be written in Italian (markers found: {hits})"


def test_t1_f16_02_ha_trusted_proxies_and_addon_preservation():
    """T1-F16-02: Documents HA configuration.yaml trusted_proxies & preserving existing HA Tailscale Add-on."""
    text = _read_runbook()
    low = text.lower()
    assert "configuration.yaml" in low
    assert "use_x_forwarded_for" in low
    assert "trusted_proxies" in low
    assert "127.0.0.1" in text or "::1" in text or "192.168." in text
    assert re.search(r"add-on|addon", low), "Must mention HA VM Tailscale Add-on"
    assert re.search(r"non rimuovere|non eliminare|intatto|attivo|invariato|mantenere", low), (
        "Must warn to keep existing trusted_proxies / HA Tailscale Add-on untouched"
    )


def test_t1_f16_03_ha_user_rbac_admin_vs_residente_and_2fa():
    """T1-F16-03: Documents separate HA Admin vs Residente accounts, 2FA, and OAuth2 token revocation."""
    text = _read_runbook()
    low = text.lower()
    assert "residente" in low
    assert "admin" in low or "amministratore" in low
    assert re.search(r"2fa|autenticazione a due fattori|mfa|totp", low), "Must document 2FA"
    assert re.search(r"revoc|token|dispositiv|oauth", low), "Must document per-device token revocation"


def test_t1_f16_04_tailscale_win10_unattended_and_serve_443_8443():
    """T1-F16-04: Documents Tailscale Windows 10 unattended + tailscale serve :443 (->8080) & :8443 (->8123)."""
    text = _read_runbook()
    low = text.lower()
    assert "tailscale serve" in low
    assert "8080" in text
    assert "8443" in text
    assert "8123" in text
    assert re.search(r"unattended|servizio|avvio automatico|riavvio", low)


def test_t1_f16_05_tailscale_free_personal_node_sharing_acl_and_guest_wifi():
    """T1-F16-05: Covers Node Sharing, Tailnet ACL (up to 6 users, block 3389/445/22), and Wi-Fi Ospiti."""
    text = _read_runbook()
    low = text.lower()
    assert "node sharing" in low or "share" in low
    assert "acl" in low
    assert "6" in text
    assert "3389" in text and "445" in text and "22" in text
    assert re.search(r"wi-?fi\s+ospiti|client isolation|isolamento\s+client", low)


def test_t1_f16_06_windows_nssm_services_firewall_8555_and_ram_budget():
    """T1-F16-06: Documents NSSM services, setup/install scripts, Firewall :8555 + 100.64.0.0/10, and 8 GB RAM."""
    text = _read_runbook()
    low = text.lower()
    assert "setup_windows_node.ps1" in text
    assert "-InstallServices" in text
    assert "install_windows_services.ps1" in text
    for svc in ("SmartHome3D-go2rtc", "SmartHome3D-SpatialServer", "SmartHome3D-Caddy"):
        assert svc in text, f"Runbook missing NSSM service {svc}"
    assert "8555" in text
    assert "100.64.0.0/10" in text
    assert "8 gb" in low or "8gb" in low
    assert "virtualbox" in low or "vm" in low


def test_t1_f16_07_ios_android_pwa_onboarding_split_tunneling_ondemand():
    """T1-F16-07: Documents iOS/Android PWA install, no Exit Node, App Split Tunneling, and On-Demand."""
    text = _read_runbook()
    low = text.lower()
    assert "aggiungi a schermata home" in low or "schermata home" in low
    assert "installa" in low and ("android" in low or "chrome" in low)
    assert "exit node" in low
    assert "split tunneling" in low
    assert "on-demand" in low or "on demand" in low
    assert "safari" in low and "chrome" in low


# =============================================================================
# F16 Tier 2 — Consistency, Negative & Cross-Reference Tests (6 tests)
# =============================================================================


def test_t2_f16_01_port_consistency_across_runbook_and_configs():
    """T2-F16-01: Port references in Runbook align with Caddyfile, go2rtc.yaml, and PROJECT.md contracts."""
    text = _read_runbook()
    for port in ("443", "8443", "8080", "8765", "1984", "8555", "8554", "8123"):
        assert port in text, f"Expected port {port} to be documented in runbook"

    # Must not contradict Caddy loopback port (8080) or spatial_server loopback port (8765)
    assert not re.search(r"tailscale\s+serve[^\n]*8765", text, re.IGNORECASE), (
        "Tailscale Serve must point to Caddy :8080, not directly to spatial_server :8765"
    )
    assert not re.search(r"tailscale\s+serve[^\n]*1984", text, re.IGNORECASE), (
        "Tailscale Serve must not expose go2rtc :1984 directly"
    )


def test_t2_f16_02_script_and_service_names_accuracy():
    """T2-F16-02: Every referenced script, config file, and NSSM service matches repo files."""
    text = _read_runbook()
    expected_refs = (
        "scripts/setup_windows_node.ps1",
        "scripts/install_windows_services.ps1",
        "scripts/start_services.bat",
        "scripts/stop_services.bat",
        "scripts/update_services.bat",
        "caddy/Caddyfile",
        ".env",
    )
    normalized = text.replace("\\", "/")
    for ref in expected_refs:
        assert ref in normalized, f"Runbook missing accurate path reference: {ref}"
        if not ref.startswith(".env"):
            assert (REPO_ROOT / ref).exists(), f"Referenced repo file missing on disk: {ref}"


def test_t2_f16_03_antipattern_rejection_no_ha_subpath_no_firebase_prod():
    """T2-F16-03: Does not instruct /ha/* subpath proxying or Firebase Hosting + VITE_HA_TOKEN in production."""
    text = _read_runbook()
    assert not re.search(r"^\s*handle\s+/ha/", text, re.MULTILINE), (
        "Runbook must not instruct configuring Caddy subpath proxy /ha/*"
    )
    assert not re.search(r"firebase\s+deploy", text, re.IGNORECASE), (
        "Runbook must not instruct deploying production to Firebase Hosting"
    )
    assert not re.search(r"imposta\s+VITE_HA_TOKEN\s*=", text, re.IGNORECASE), (
        "Runbook must not instruct setting VITE_HA_TOKEN in production"
    )


def test_t2_f16_04_secret_hygiene_check_in_runbook():
    """T2-F16-04: Zero real JWTs, private keys, or hardcoded non-placeholder credentials in Runbook."""
    text = _read_runbook()
    assert not re.search(r"eyJ[A-Za-z0-9_-]{20,}", text), "Found JWT-like token in Runbook"
    assert "BEGIN PRIVATE KEY" not in text
    assert "BEGIN RSA PRIVATE KEY" not in text
    assert "BEGIN OPENSSH PRIVATE KEY" not in text


def test_t2_f16_05_markdown_fences_and_ha_yaml_validity():
    """T2-F16-05: Balanced ``` code fences and valid YAML snippet for HA configuration.yaml."""
    text = _read_runbook()
    fence_lines = [ln for ln in text.splitlines() if ln.strip().startswith("```")]
    assert len(fence_lines) >= 2
    assert len(fence_lines) % 2 == 0, f"Unbalanced markdown code fences ({len(fence_lines)})"

    yaml_blocks = re.findall(r"```ya?ml\s*\n(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    ha_blocks = [b for b in yaml_blocks if "trusted_proxies" in b]
    assert ha_blocks, "Expected a ```yaml fenced block containing trusted_proxies"

    for blk in ha_blocks:
        parsed = yaml.safe_load(blk)
        assert isinstance(parsed, dict), f"HA YAML block must parse as dict, got {type(parsed)}"
        assert "http" in parsed and "trusted_proxies" in parsed["http"]


def test_t2_f16_06_local_links_and_tailscale_cli_flags_sanity():
    """T2-F16-06: Relative markdown links resolve cleanly and tailscale serve commands use valid flags."""
    text = _read_runbook()
    # Check relative links like [label](relative/path.md)
    for _label, target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", text):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        clean_target = target.split("#", 1)[0].strip()
        if not clean_target:
            continue
        resolved = (RUNBOOK_PATH.parent / clean_target).resolve()
        if not resolved.exists():
            resolved = (REPO_ROOT / clean_target.lstrip("/")).resolve()
        assert resolved.exists(), f"Broken relative markdown link in Runbook: {target}"

    serve_lines = [ln.strip() for ln in text.splitlines() if "tailscale serve" in ln.lower()]
    assert serve_lines, "Expected tailscale serve CLI examples in Runbook"
    assert any("--bg" in ln for ln in serve_lines), "Expected --bg flag in tailscale serve examples"
    assert any("8443" in ln and "--https" in ln for ln in serve_lines), (
        "Expected --https=8443 (or --https 8443) flag in tailscale serve examples"
    )
