from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest


def _parse_env_example(repo_root: Path) -> tuple[str, list[tuple[str, str]]]:
    env_example = repo_root / ".env.example"
    assert env_example.is_file(), f"Missing {env_example}"
    raw = env_example.read_text(encoding="utf-8")
    active: list[tuple[str, str]] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            key, val = stripped.split("=", 1)
            active.append((key.strip(), val.strip()))
    return raw, active


def _git_check_ignore(repo_root: Path, rel_path: str) -> int:
    proc = subprocess.run(
        ["git", "check-ignore", "-q", rel_path],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return proc.returncode


@pytest.mark.tier1
def test_f7_t1_01_gitignore_excludes_required_binaries_logs_and_runtime_data(
    repo_root: Path,
) -> None:
    required_ignored = [
        "spatial_server/data/camera_calibrations.json",
        "caddy/caddy.exe",
        "tools/nssm.exe",
        "logs/app.log",
        "go2rtc/go2rtc.exe",
        ".env",
        ".env.local",
        "spatial_server/data/spatial_tracks.db-wal",
    ]
    for rel_path in required_ignored:
        rc = _git_check_ignore(repo_root, rel_path)
        assert rc == 0, f"Expected {rel_path!r} to be gitignored (rc={rc})"


@pytest.mark.tier1
def test_f7_t1_02_env_example_documents_all_new_production_vars(
    repo_root: Path,
) -> None:
    _, active = _parse_env_example(repo_root)
    keys = {k for k, _ in active}
    for required_key in (
        "VITE_HA_PUBLIC_URL",
        "VITE_HA_TOKEN",
        "SPATIAL_SERVER_HOST",
        "SPATIAL_AUTH_REQUIRED",
        "SPATIAL_ALLOWED_ORIGINS",
        "GO2RTC_CANDIDATE_LAN",
        "GO2RTC_CANDIDATE_TAILSCALE",
        "REOLINK_CARRAIO_PASS",
    ):
        assert required_key in keys, f"Missing {required_key} in .env.example"


@pytest.mark.tier1
def test_f7_t1_03_env_example_has_secure_production_defaults(repo_root: Path) -> None:
    _, active = _parse_env_example(repo_root)
    env_map = dict(active)
    assert env_map.get("SPATIAL_SERVER_HOST") == "127.0.0.1"
    assert env_map.get("SPATIAL_AUTH_REQUIRED", "").lower() == "true"
    assert env_map.get("VITE_HA_TOKEN") == ""


@pytest.mark.tier1
def test_f7_t1_04_env_example_uses_uniform_reolink_carraio_pass(
    repo_root: Path,
) -> None:
    _, active = _parse_env_example(repo_root)
    keys = {k for k, _ in active}
    assert "REOLINK_CARRAIO_PASS" in keys
    assert "REOLINK_CARRAIO_PASSWORD" not in keys


@pytest.mark.tier1
def test_f7_t1_05_sensitive_and_binary_artifacts_not_tracked_by_git(
    repo_root: Path,
) -> None:
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0
    tracked = proc.stdout.splitlines()
    for path in tracked:
        assert path != ".env" and not path.endswith("/.env")
        assert not path.endswith(".exe"), f"Tracked binary executable: {path}"
        assert path != "spatial_server/data/camera_calibrations.json"
        assert not path.startswith("logs/"), f"Tracked log artifact: {path}"


@pytest.mark.tier2
def test_f7_t2_01_env_example_contains_no_real_secrets_or_tokens(
    repo_root: Path,
) -> None:
    raw, active = _parse_env_example(repo_root)
    assert "eyJ" not in raw, "JWT-like token detected in .env.example"
    env_map = dict(active)
    for secret_key in (
        "VITE_HA_TOKEN",
        "REOLINK_CARRAIO_PASS",
        "MQTT_PASS",
        "SPATIAL_SESSION_SECRET",
    ):
        val = env_map.get(secret_key, "")
        assert val == "" or len(val) < 32, (
            f"Unexpected non-empty/long secret value for {secret_key}"
        )


@pytest.mark.tier2
def test_f7_t2_02_env_example_contains_no_wildcard_allowed_origins(
    repo_root: Path,
) -> None:
    _, active = _parse_env_example(repo_root)
    env_map = dict(active)
    origins = env_map.get("SPATIAL_ALLOWED_ORIGINS", "")
    assert origins != "*"
    assert "*" not in [o.strip() for o in origins.split(",") if o.strip()]


@pytest.mark.tier2
def test_f7_t2_03_env_example_uses_https_for_vite_ha_public_url_example(
    repo_root: Path,
) -> None:
    raw, _ = _parse_env_example(repo_root)
    matches = re.findall(r"VITE_HA_PUBLIC_URL\s*=\s*(https?://\S+)", raw)
    assert matches, "Expected documented VITE_HA_PUBLIC_URL example URL"
    for url in matches:
        assert url.startswith("https://"), f"Expected https:// example, got {url}"


@pytest.mark.tier2
def test_f7_t2_04_env_example_has_no_duplicate_active_variable_definitions(
    repo_root: Path,
) -> None:
    _, active = _parse_env_example(repo_root)
    seen: set[str] = set()
    duplicates: list[str] = []
    for key, _ in active:
        if key in seen:
            duplicates.append(key)
        seen.add(key)
    assert duplicates == [], f"Duplicate active keys in .env.example: {duplicates}"


@pytest.mark.tier2
def test_f7_t2_05_gitignore_preserves_essential_config_files_unignored(
    repo_root: Path,
) -> None:
    must_not_be_ignored = [
        "caddy/Caddyfile",
        "go2rtc/go2rtc.yaml",
        ".env.example",
        "spatial_server/config.py",
        "public/models/scene_manifest.json",
    ]
    for rel_path in must_not_be_ignored:
        rc = _git_check_ignore(repo_root, rel_path)
        assert rc == 1, f"Essential config file {rel_path!r} is unexpectedly gitignored"
