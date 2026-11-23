from __future__ import annotations

import re
from pathlib import Path

from tests.e2e.helpers.ps_bat_harness import (
    build_isolated_workspace,
    parse_ps1_ast,
    run_bat_dry_run,
    run_ps_dry_run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _collect_app_env_extra(res: dict) -> list[str]:
    """Collect AppEnvironmentExtra entries whether set via nssm CLI or HKLM registry Set-ItemProperty."""
    lines: list[str] = []
    for c in res.get("stub_calls", []):
        if c["exe"] == "nssm.exe" and "AppEnvironmentExtra" in c.get("args", []):
            lines.extend(c["args"])
    for p in res.get("ps_calls", []):
        if p.get("kind") == "Set-ItemProperty" and p.get("data", {}).get("Name") == "AppEnvironmentExtra":
            val = p["data"].get("Value")
            if isinstance(val, list):
                lines.extend(str(x) for x in val)
            elif val is not None:
                lines.append(str(val))
    return lines


# =============================================================================
# F15 Tier 1 — Core Contract & Happy-Path Tests (8 tests)
# =============================================================================


def test_t1_f15_01_powershell_scripts_parse_cleanly_via_ast():
    """T1-F15-01: PowerShell scripts parse cleanly via AST with valid ParamBlocks."""
    setup_ps1 = REPO_ROOT / "scripts" / "setup_windows_node.ps1"
    install_ps1 = REPO_ROOT / "scripts" / "install_windows_services.ps1"

    assert setup_ps1.exists(), f"Missing {setup_ps1}"
    assert install_ps1.exists(), f"Missing {install_ps1}"

    for ps1 in (setup_ps1, install_ps1):
        parsed = parse_ps1_ast(ps1)
        assert parsed["exists"] is True
        assert parsed["errors"] == [], f"AST errors in {ps1.name}: {parsed['errors']}"
        assert parsed["has_param_block"] is True, f"{ps1.name} must declare a param(...) block"


def test_t1_f15_02_setup_windows_node_contract_and_install_services_switch(tmp_path: Path):
    """T1-F15-02: setup_windows_node.ps1 exposes switches, checks VC_redist/binaries, creates .env, delegates -InstallServices."""
    setup_ps1 = REPO_ROOT / "scripts" / "setup_windows_node.ps1"
    parsed = parse_ps1_ast(setup_ps1)
    assert parsed["errors"] == []

    params = {p["name"]: p["types"] for p in parsed["parameters"]}
    assert "WithOpenVINO" in params, f"Missing -WithOpenVINO in {params}"
    assert "InstallServices" in params, f"Missing -InstallServices in {params}"
    assert any(t.lower() == "switch" for t in params["InstallServices"])

    ws_info = build_isolated_workspace(
        tmp_path,
        REPO_ROOT,
        include_binaries=False,
        include_venv=False,
        include_dist=False,
        include_env_file=False,
    )
    res = run_ps_dry_run(
        ws_info,
        "scripts/setup_windows_node.ps1",
        ["-InstallServices"],
        vc_redist_present=True,
        shadow_install_script=True,
    )
    assert res["returncode"] == 0, f"setup_windows_node.ps1 failed:\n{res['stdout']}\n{res['stderr']}"

    ws: Path = ws_info["workspace"]
    assert (ws / ".env").exists(), ".env must be created from .env.example"
    assert (ws / "go2rtc" / "go2rtc.exe").exists(), "go2rtc.exe must be provisioned"
    assert (ws / "caddy" / "caddy.exe").exists(), "caddy.exe must be provisioned"
    assert (ws / "tools" / "nssm.exe").exists(), "nssm.exe must be provisioned"

    delegated = [c for c in res["ps_calls"] if c["kind"] == "delegated_script"]
    assert delegated, "Expected -InstallServices to delegate to install_windows_services.ps1"

    vc_checks = [
        c for c in res["ps_calls"]
        if c["kind"] in ("Get-ItemProperty", "Get-ChildItem", "Test-Path")
    ]
    assert vc_checks, "Expected VC_redist.x64 registry/DLL check during setup"

    script_text = setup_ps1.read_text(encoding="utf-8")
    assert "REOLINK_CARRAIO_PASS" in script_text
    assert "REOLINK_CARRAIO_PASSWORD" not in script_text, "Stale REOLINK_CARRAIO_PASSWORD should be replaced by REOLINK_CARRAIO_PASS"


def test_t1_f15_03_install_windows_services_nssm_definitions_dry_run(tmp_path: Path):
    """T1-F15-03: install_windows_services.ps1 configures all 3 NSSM services with auto-start, restart, log rotation, and .env."""
    env_text = (
        "REOLINK_CARRAIO_PASS=dummy_pass\n"
        "GO2RTC_CANDIDATE_LAN=192.168.1.10:8555\n"
        "SPATIAL_SESSION_SECRET=testsecret_12345678901234567890\n"
        "SPATIAL_SERVER_HOST=127.0.0.1\n"
        "SPATIAL_SERVER_PORT=8765\n"
    )
    ws_info = build_isolated_workspace(
        tmp_path,
        REPO_ROOT,
        include_binaries=True,
        include_venv=True,
        env_content=env_text,
    )
    res = run_ps_dry_run(
        ws_info,
        "scripts/install_windows_services.ps1",
        vc_redist_present=True,
        existing_services=[],
        nssm_status_exit=1,
    )
    assert res["returncode"] == 0, f"install_windows_services.ps1 failed:\n{res['stdout']}\n{res['stderr']}"

    nssm_calls = [c for c in res["stub_calls"] if c["exe"] == "nssm.exe"]
    assert nssm_calls, "Expected nssm.exe stub invocations"

    joined_cmds = "\n".join(" ".join(c["args"]) for c in nssm_calls)
    for svc in ("SmartHome3D-go2rtc", "SmartHome3D-SpatialServer", "SmartHome3D-Caddy"):
        assert f"install {svc}".lower() in joined_cmds.lower(), (
            f"Missing NSSM install for {svc}. Calls:\n{joined_cmds}"
        )

    assert "SERVICE_AUTO_START" in joined_cmds, f"Missing auto-start configuration:\n{joined_cmds}"
    assert "AppExit" in joined_cmds and "Restart" in joined_cmds, f"Missing crash restart config:\n{joined_cmds}"
    assert "AppStdout" in joined_cmds and "AppStderr" in joined_cmds, f"Missing stdout/stderr logging:\n{joined_cmds}"
    assert "logs" in joined_cmds.lower(), "Service logs must target logs/ directory"
    assert "AppRotateFiles" in joined_cmds and "AppRotateOnline" in joined_cmds and "AppRotateBytes" in joined_cmds, (
        f"Missing NSSM log rotation settings:\n{joined_cmds}"
    )

    env_extra_lines = _collect_app_env_extra(res)
    assert env_extra_lines, "Expected AppEnvironmentExtra .env propagation"
    env_joined = "\n".join(env_extra_lines)
    assert "REOLINK_CARRAIO_PASS=dummy_pass" in env_joined
    assert "GO2RTC_CANDIDATE_LAN=192.168.1.10:8555" in env_joined
    assert "SPATIAL_SESSION_SECRET=testsecret_12345678901234567890" in env_joined


def test_t1_f15_04_install_windows_services_firewall_8555_scoping(tmp_path: Path):
    """T1-F15-04: install_windows_services.ps1 creates inbound :8555 TCP/UDP firewall rules scoped to LAN + 100.64.0.0/10."""
    env_text = (
        "REOLINK_CARRAIO_PASS=dummy\n"
        "SPATIAL_SESSION_SECRET=testsecret_12345678901234567890\n"
    )
    ws_info = build_isolated_workspace(tmp_path, REPO_ROOT, env_content=env_text)
    res = run_ps_dry_run(ws_info, "scripts/install_windows_services.ps1")
    assert res["returncode"] == 0, f"install_windows_services.ps1 failed:\n{res['stdout']}\n{res['stderr']}"

    fw_calls = [c["data"] for c in res["ps_calls"] if c["kind"] == "New-NetFirewallRule"]
    assert len(fw_calls) >= 2, f"Expected TCP and UDP New-NetFirewallRule calls, got: {fw_calls}"

    protocols = {str(c.get("Protocol", "")).upper() for c in fw_calls}
    assert {"TCP", "UDP"}.issubset(protocols), f"Firewall rules must cover TCP & UDP, got {protocols}"

    for rule in fw_calls:
        assert str(rule.get("LocalPort")) == "8555", f"Expected LocalPort 8555, got {rule}"
        assert str(rule.get("Direction", "")).lower() == "inbound"
        assert str(rule.get("Action", "")).lower() == "allow"

        remote = rule.get("RemoteAddress")
        remote_list = remote if isinstance(remote, list) else [remote]
        remote_strs = [str(r).strip() for r in remote_list if r is not None]
        assert remote_strs, f"RemoteAddress must be explicitly restricted, got {remote}"
        assert not any(r.lower() in ("any", "*", "0.0.0.0/0", "::/0") for r in remote_strs), (
            f"Firewall rule must NEVER allow Any/0.0.0.0/0: {remote_strs}"
        )
        assert any("100.64.0.0/10" in r for r in remote_strs), (
            f"Firewall rule must include Tailscale CGNAT 100.64.0.0/10: {remote_strs}"
        )
        assert any(
            r.lower() == "localsubnet"
            or r.startswith("192.168.")
            or r.startswith("10.")
            or r.startswith("172.")
            for r in remote_strs
        ), f"Firewall rule must include LAN subnet/LocalSubnet: {remote_strs}"


def test_t1_f15_05_start_services_bat_isolated_and_127_0_0_1_default(tmp_path: Path):
    """T1-F15-05: start_services.bat defaults SPATIAL_SERVER_HOST=127.0.0.1 and starts go2rtc, uvicorn, and Caddy."""
    ws_info = build_isolated_workspace(
        tmp_path,
        REPO_ROOT,
        include_binaries=True,
        include_venv=True,
        env_content="REOLINK_CARRAIO_PASS=dummy\nSPATIAL_SERVER_PORT=8765\n",
    )
    res = run_bat_dry_run(ws_info, "scripts/start_services.bat", nssm_status_exit=1)
    assert res["returncode"] == 0, f"start_services.bat failed:\n{res['stdout']}\n{res['stderr']}"

    calls = res["stub_calls"]
    exes = [c["exe"] for c in calls]
    assert "go2rtc.exe" in exes, f"go2rtc.exe was not started: {calls}"
    assert "uvicorn.exe" in exes, f"uvicorn.exe was not started: {calls}"
    assert "caddy.exe" in exes, f"caddy.exe was not started: {calls}"

    uvicorn_call = next(c for c in calls if c["exe"] == "uvicorn.exe")
    assert uvicorn_call["env"]["SPATIAL_SERVER_HOST"] == "127.0.0.1"
    assert "--host" in uvicorn_call["args"]
    host_idx = uvicorn_call["args"].index("--host")
    assert uvicorn_call["args"][host_idx + 1] == "127.0.0.1"

    caddy_call = next(c for c in calls if c["exe"] == "caddy.exe")
    caddy_args_joined = " ".join(caddy_call["args"])
    assert "run" in caddy_call["args"]
    assert "Caddyfile" in caddy_args_joined


def test_t1_f15_06_stop_services_bat_isolated_nssm_and_console(tmp_path: Path):
    """T1-F15-06: stop_services.bat cleanly handles both NSSM service stop and console process termination."""
    ws_nssm = build_isolated_workspace(tmp_path / "nssm_mode", REPO_ROOT)
    res_nssm = run_bat_dry_run(ws_nssm, "scripts/stop_services.bat", nssm_status_exit=0)
    assert res_nssm["returncode"] == 0, f"stop_services.bat (NSSM mode) failed:\n{res_nssm['stdout']}"
    nssm_or_sc = [c for c in res_nssm["stub_calls"] if c["exe"] in ("nssm.exe", "sc.exe")]
    joined_nssm = "\n".join(" ".join(c["args"]) for c in nssm_or_sc)
    for svc in ("SmartHome3D-Caddy", "SmartHome3D-SpatialServer", "SmartHome3D-go2rtc"):
        assert svc in joined_nssm, f"Expected stop for {svc} in NSSM mode:\n{joined_nssm}"

    ws_console = build_isolated_workspace(tmp_path / "console_mode", REPO_ROOT)
    res_console = run_bat_dry_run(ws_console, "scripts/stop_services.bat", nssm_status_exit=1)
    assert res_console["returncode"] == 0, f"stop_services.bat (console mode) failed:\n{res_console['stdout']}"
    taskkill_calls = [c for c in res_console["stub_calls"] if c["exe"] == "taskkill.exe"]
    ps_calls = [c for c in res_console["stub_calls"] if c["exe"] == "powershell.exe"]
    joined_kill = "\n".join(" ".join(c["args"]) for c in taskkill_calls + ps_calls)
    assert "go2rtc.exe" in joined_kill
    assert "caddy.exe" in joined_kill or "caddy" in joined_kill.lower()
    assert "spatial_server.main:app" in joined_kill or "uvicorn.exe" in joined_kill


def test_t1_f15_07_update_services_bat_first_deploy_missing_dist_rebuild(tmp_path: Path):
    """T1-F15-07: update_services.bat runs `npm.cmd run build` when dist/ is missing even if OLD_HEAD == NEW_HEAD."""
    ws_info = build_isolated_workspace(
        tmp_path,
        REPO_ROOT,
        include_binaries=True,
        include_venv=True,
        include_dist=False,
        env_content="REOLINK_CARRAIO_PASS=dummy\n",
    )
    assert not (ws_info["workspace"] / "dist").exists()

    res = run_bat_dry_run(
        ws_info,
        "scripts/update_services.bat",
        nssm_status_exit=1,
        extra_env={
            "SH3D_GIT_OLD_HEAD": "aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111",
            "SH3D_GIT_NEW_HEAD": "aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111",
        },
    )
    assert res["returncode"] == 0, f"update_services.bat failed:\n{res['stdout']}\n{res['stderr']}"

    npm_calls = [c for c in res["stub_calls"] if c["exe"] == "npm_stub.exe"]
    assert any(c["args"][:2] == ["run", "build"] for c in npm_calls), (
        f"Expected `npm.cmd run build` when dist/ is missing on first deploy, got: {npm_calls}"
    )


def test_t1_f15_08_update_services_bat_caddy_reload_or_restart_on_update(tmp_path: Path):
    """T1-F15-08: update_services.bat rebuilds dist/ and validates/restarts Caddy when frontend/Caddyfile updates."""
    ws_info = build_isolated_workspace(
        tmp_path,
        REPO_ROOT,
        include_binaries=True,
        include_venv=True,
        include_dist=True,
        env_content="REOLINK_CARRAIO_PASS=dummy\n",
    )
    res = run_bat_dry_run(
        ws_info,
        "scripts/update_services.bat",
        nssm_status_exit=0,
        extra_env={
            "SH3D_GIT_OLD_HEAD": "aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111",
            "SH3D_GIT_NEW_HEAD": "bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222",
            "SH3D_GIT_CHANGED_FILES": "src/main.js,caddy/Caddyfile",
        },
    )
    assert res["returncode"] == 0, f"update_services.bat failed:\n{res['stdout']}\n{res['stderr']}"

    npm_calls = [c for c in res["stub_calls"] if c["exe"] == "npm_stub.exe"]
    assert any(c["args"][:2] == ["run", "build"] for c in npm_calls), f"Expected npm run build: {npm_calls}"

    caddy_or_service_calls = [
        c for c in res["stub_calls"]
        if c["exe"] in ("caddy.exe", "nssm.exe", "sc.exe")
    ]
    joined = "\n".join(f"{c['exe']} {' '.join(c['args'])}" for c in caddy_or_service_calls)
    assert "SmartHome3D-Caddy" in joined or "caddy.exe" in joined.lower(), (
        f"Expected Caddy validate/reload or service restart on update, got:\n{joined}"
    )


# =============================================================================
# F15 Tier 2 — Boundary, Edge & Negative Tests (8 tests)
# =============================================================================


def test_t2_f15_01_setup_windows_node_warns_or_fails_when_vc_redist_missing(tmp_path: Path):
    """T2-F15-01: setup_windows_node.ps1 fails fast or explicitly warns naming VC_redist.x64 when missing."""
    ws_info = build_isolated_workspace(
        tmp_path,
        REPO_ROOT,
        include_binaries=True,
        include_venv=True,
        include_env_file=True,
    )
    res = run_ps_dry_run(
        ws_info,
        "scripts/setup_windows_node.ps1",
        ["-WithOpenVINO"],
        vc_redist_present=False,
    )
    combined = res["stdout"] + "\n" + res["stderr"]
    assert (
        res["returncode"] != 0
        or re.search(r"vc_redist|visual c\+\+|vcruntime140", combined, re.IGNORECASE)
    ), f"Expected failure or explicit VC_redist.x64 remediation message, got rc={res['returncode']}:\n{combined}"


def test_t2_f15_02_setup_windows_node_idempotency_when_binaries_exist(tmp_path: Path):
    """T2-F15-02: setup_windows_node.ps1 skips downloading existing binaries and preserves existing .env."""
    sentinel_env = "REOLINK_CARRAIO_PASS=keep_my_secret_value\nSPATIAL_SERVER_HOST=127.0.0.1\n"
    ws_info = build_isolated_workspace(
        tmp_path,
        REPO_ROOT,
        include_binaries=True,
        include_venv=True,
        env_content=sentinel_env,
    )
    res = run_ps_dry_run(
        ws_info,
        "scripts/setup_windows_node.ps1",
        vc_redist_present=True,
    )
    assert res["returncode"] == 0, f"setup_windows_node.ps1 failed:\n{res['stdout']}\n{res['stderr']}"

    web_requests = [c for c in res["ps_calls"] if c["kind"] == "Invoke-WebRequest"]
    assert web_requests == [], f"Must not download binaries already present, got: {web_requests}"
    assert (ws_info["workspace"] / ".env").read_text(encoding="utf-8") == sentinel_env


def test_t2_f15_03_install_windows_services_fails_cleanly_on_missing_prereqs(tmp_path: Path):
    """T2-F15-03: install_windows_services.ps1 exits non-zero and registers zero services if binaries/.env missing."""
    ws_info = build_isolated_workspace(
        tmp_path,
        REPO_ROOT,
        include_binaries=False,
        include_venv=False,
        include_env_file=False,
    )
    res = run_ps_dry_run(ws_info, "scripts/install_windows_services.ps1")
    assert res["returncode"] != 0, "Expected non-zero exit when tools/nssm.exe, caddy.exe, or .env are missing"
    nssm_installs = [
        c for c in res["stub_calls"]
        if c["exe"] == "nssm.exe" and "install" in [a.lower() for a in c["args"]]
    ]
    assert nssm_installs == [], f"Must not partially register NSSM services: {nssm_installs}"


def test_t2_f15_04_install_windows_services_idempotent_rerun_and_env_parsing(tmp_path: Path):
    """T2-F15-04: install_windows_services.ps1 handles re-run, skips # comments/blanks, preserves '=', normalizes REOLINK_CARRAIO_PASS."""
    messy_env = (
        "# Comment line with = sign\n"
        "\n"
        "   # Indented comment\n"
        "REOLINK_CARRAIO_PASSWORD=legacy_pw\n"
        "SPATIAL_SESSION_SECRET=abc=def=1234567890\n"
        "SPATIAL_SERVER_HOST=127.0.0.1\n"
    )
    ws_info = build_isolated_workspace(tmp_path, REPO_ROOT, env_content=messy_env)
    services = ["SmartHome3D-go2rtc", "SmartHome3D-SpatialServer", "SmartHome3D-Caddy"]

    res1 = run_ps_dry_run(
        ws_info,
        "scripts/install_windows_services.ps1",
        existing_services=services,
        nssm_status_exit=3,
        mock_fw_exists=True,
    )
    assert res1["returncode"] == 0, f"Re-run 1 failed:\n{res1['stdout']}\n{res1['stderr']}"

    res2 = run_ps_dry_run(
        ws_info,
        "scripts/install_windows_services.ps1",
        existing_services=services,
        nssm_status_exit=0,
        mock_fw_exists=True,
    )
    assert res2["returncode"] == 0, f"Re-run 2 failed:\n{res2['stdout']}\n{res2['stderr']}"

    env_extra_lines = _collect_app_env_extra(res2)
    assert env_extra_lines, "Expected AppEnvironmentExtra settings on re-run"
    joined = "\n".join(env_extra_lines)
    assert "Comment line" not in joined
    assert "SPATIAL_SESSION_SECRET=abc=def=1234567890" in joined
    assert "REOLINK_CARRAIO_PASS=legacy_pw" in joined


def test_t2_f15_05_start_services_bat_error_exits_on_missing_prereqs(tmp_path: Path):
    """T2-F15-05: start_services.bat exits non-zero with [ERRORE] for missing go2rtc/uvicorn, warns cleanly for missing caddy."""
    for fatal_rel in ("go2rtc/go2rtc.exe", ".venv/Scripts/uvicorn.exe"):
        sub = tmp_path / fatal_rel.replace("/", "_")
        ws_info = build_isolated_workspace(
            sub,
            REPO_ROOT,
            include_binaries=True,
            include_venv=True,
            env_content="REOLINK_CARRAIO_PASS=dummy\n",
        )
        (ws_info["workspace"] / fatal_rel).unlink()
        res = run_bat_dry_run(ws_info, "scripts/start_services.bat", nssm_status_exit=1)
        assert res["returncode"] != 0, f"Expected non-zero exit when {fatal_rel} is missing"
        assert "[ERRORE]" in res["stdout"]

    # Missing caddy.exe gracefully warns without crashing go2rtc/uvicorn
    ws_caddy = build_isolated_workspace(
        tmp_path / "missing_caddy",
        REPO_ROOT,
        include_binaries=True,
        include_venv=True,
        env_content="REOLINK_CARRAIO_PASS=dummy\n",
    )
    (ws_caddy["workspace"] / "caddy" / "caddy.exe").unlink()
    res_caddy = run_bat_dry_run(ws_caddy, "scripts/start_services.bat", nssm_status_exit=1)
    assert res_caddy["returncode"] == 0
    assert "[AVVISO]" in res_caddy["stdout"]
    assert "caddy.exe" not in [c["exe"] for c in res_caddy["stub_calls"]]


def test_t2_f15_06_start_services_bat_legacy_reolink_carraio_password_compat(tmp_path: Path):
    """T2-F15-06: start_services.bat maps legacy REOLINK_CARRAIO_PASSWORD -> REOLINK_CARRAIO_PASS and keeps 127.0.0.1."""
    ws_info = build_isolated_workspace(
        tmp_path,
        REPO_ROOT,
        env_content="REOLINK_CARRAIO_PASSWORD=legacy_cam_val\n",
    )
    res = run_bat_dry_run(ws_info, "scripts/start_services.bat", nssm_status_exit=1)
    assert res["returncode"] == 0, f"start_services.bat failed:\n{res['stdout']}\n{res['stderr']}"

    go2rtc_call = next(c for c in res["stub_calls"] if c["exe"] == "go2rtc.exe")
    assert go2rtc_call["env"]["REOLINK_CARRAIO_PASS"] == "legacy_cam_val"

    uvicorn_call = next(c for c in res["stub_calls"] if c["exe"] == "uvicorn.exe")
    assert uvicorn_call["env"]["SPATIAL_SERVER_HOST"] == "127.0.0.1"


def test_t2_f15_07_update_services_bat_aborts_safely_on_git_fetch_failure(tmp_path: Path):
    """T2-F15-07: update_services.bat aborts immediately if git fetch fails without stopping/restarting services."""
    ws_info = build_isolated_workspace(
        tmp_path,
        REPO_ROOT,
        include_dist=True,
        env_content="REOLINK_CARRAIO_PASS=dummy\n",
    )
    ws: Path = ws_info["workspace"]
    marker = ws / "dist" / "sentinel.txt"
    marker.write_text("keep", encoding="utf-8")

    res = run_bat_dry_run(
        ws_info,
        "scripts/update_services.bat",
        nssm_status_exit=0,
        extra_env={
            "SH3D_GIT_OLD_HEAD": "aaaa1111aaaa1111aaaa1111aaaa1111aaaa1111",
            "SH3D_GIT_FETCH_FAIL": "1",
        },
    )
    assert res["returncode"] != 0, "Expected non-zero exit on git fetch failure"
    assert marker.read_text(encoding="utf-8") == "keep"
    stopped_or_restarted = [
        c for c in res["stub_calls"]
        if c["exe"] in ("taskkill.exe", "sc.exe", "nssm.exe", "go2rtc.exe", "uvicorn.exe", "caddy.exe", "npm_stub.exe")
    ]
    assert stopped_or_restarted == [], f"Must not stop/restart/build on git fetch failure: {stopped_or_restarted}"


def test_t2_f15_08_scripts_hygiene_and_safety_static_scan(tmp_path: Path):
    """T2-F15-08: Static hygiene & space-in-path safety across scripts/*.ps1 and scripts/*.bat."""
    scripts_dir = REPO_ROOT / "scripts"
    ps1_files = sorted(scripts_dir.glob("*.ps1"))
    bat_files = sorted(scripts_dir.glob("*.bat"))
    assert ps1_files and bat_files

    for ps1 in ps1_files:
        text = ps1.read_text(encoding="utf-8")
        assert '$ErrorActionPreference = "Stop"' in text or "$ErrorActionPreference = 'Stop'" in text, (
            f"{ps1.name} must set $ErrorActionPreference = 'Stop'"
        )
        assert not re.search(r"eyJ[A-Za-z0-9_-]{15,}", text), f"Possible JWT literal in {ps1.name}"

    for bat in bat_files:
        text = bat.read_text(encoding="utf-8")
        assert not re.search(r"eyJ[A-Za-z0-9_-]{15,}", text), f"Possible JWT literal in {bat.name}"
        assert "SPATIAL_SERVER_HOST=0.0.0.0" not in text, (
            f"{bat.name} must not default SPATIAL_SERVER_HOST to 0.0.0.0"
        )

    spaced_tmp = tmp_path / "Spaced User Path"
    ws_info = build_isolated_workspace(
        spaced_tmp,
        REPO_ROOT,
        env_content="REOLINK_CARRAIO_PASS=dummy\n",
    )
    res = run_bat_dry_run(ws_info, "scripts/start_services.bat", nssm_status_exit=1)
    assert res["returncode"] == 0, f"start_services.bat failed on spaced path:\n{res['stdout']}\n{res['stderr']}"


def test_t1_f15_09_biometrics_deploy_switches_and_decommission_cpai_ast():
    """T1-F15-09: setup -WithBiometrics, install OMP_NUM_THREADS=2, and decommission_codeproject_ai.ps1 AST/safety."""
    setup_text = (REPO_ROOT / "scripts" / "setup_windows_node.ps1").read_text(encoding="utf-8")
    install_text = (REPO_ROOT / "scripts" / "install_windows_services.ps1").read_text(encoding="utf-8")
    decomm_ps1 = REPO_ROOT / "scripts" / "decommission_codeproject_ai.ps1"

    assert decomm_ps1.is_file(), f"Missing {decomm_ps1}"
    parsed = parse_ps1_ast(decomm_ps1)
    assert parsed["errors"] == [], f"AST errors in {decomm_ps1.name}: {parsed['errors']}"
    assert parsed["has_param_block"] is True
    params = {p["name"]: p["types"] for p in parsed["parameters"]}
    assert "Apply" in params and "SkipSpatialCheck" in params

    decomm_text = decomm_ps1.read_text(encoding="utf-8")
    assert "$ErrorActionPreference" in decomm_text
    assert "[DRY-RUN]" in decomm_text and "SmartHome3D-SpatialServer" in decomm_text
    assert "Set-Service" in decomm_text and "Disabled" in decomm_text

    assert "-WithBiometrics" in setup_text or "[switch]$WithBiometrics" in setup_text
    assert "download_biometric_models.py" in setup_text
    assert "OMP_NUM_THREADS" in install_text and '"2"' in install_text
