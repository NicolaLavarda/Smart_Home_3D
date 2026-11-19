"""Read-only build/asset artifact inspection and Node Vite SSR harness runners."""

from __future__ import annotations

import json
import re
import struct
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
HELPERS_DIR = Path(__file__).resolve().parent
JS_HARNESS_PATH = HELPERS_DIR / "js_harness.mjs"
VITE_INSPECT_PATH = HELPERS_DIR / "vite_config_inspect.mjs"

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{8,}")
_BEARER_LITERAL_RE = re.compile(r"Bearer\s+(?!\$\{)[A-Za-z0-9._\-+/=]{20,}")
_VITE_HA_TOKEN_LITERAL_RE = re.compile(
    r"""VITE_HA_TOKEN\s*[:=]\s*["'](?!\s*["'])([A-Za-z0-9._\-+/=]{16,})["']"""
)


def parse_png_info(path: Path | str) -> dict[str, Any]:
    """Validate a PNG file using stdlib struct (IHDR) and cv2.imdecode (no Pillow).

    Returns:
        {"width": int, "height": int, "channels": int, "valid": bool}
    """
    file_path = Path(path)
    if not file_path.is_file():
        return {"width": 0, "height": 0, "channels": 0, "valid": False}

    data = file_path.read_bytes()
    if len(data) < 24 or data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
        return {"width": 0, "height": 0, "channels": 0, "valid": False}

    ihdr_width, ihdr_height = struct.unpack(">II", data[16:24])
    if ihdr_width <= 0 or ihdr_height <= 0:
        return {"width": 0, "height": 0, "channels": 0, "valid": False}

    buf = np.frombuffer(data, dtype=np.uint8)
    decoded = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
    if decoded is None:
        return {"width": ihdr_width, "height": ihdr_height, "channels": 0, "valid": False}

    dec_height, dec_width = decoded.shape[:2]
    channels = 1 if decoded.ndim == 2 else int(decoded.shape[2])
    valid = (dec_width == ihdr_width) and (dec_height == ihdr_height) and channels > 0
    return {
        "width": int(ihdr_width),
        "height": int(ihdr_height),
        "channels": channels,
        "valid": bool(valid),
    }


def scan_dist_js_secrets(dist_dir: Path | str) -> list[str]:
    """Scan built JS bundles and sourcemaps in dist/assets/ for leaked tokens/secrets.

    Returns a list of finding descriptions (empty list = clean).
    """
    assets_dir = Path(dist_dir) / "assets"
    if not assets_dir.is_dir():
        return []

    findings: list[str] = []
    targets = sorted(
        list(assets_dir.glob("*.js")) + list(assets_dir.glob("*.js.map"))
    )
    for asset_path in targets:
        text = asset_path.read_text(encoding="utf-8", errors="replace")
        rel = asset_path.name

        for match in _JWT_RE.finditer(text):
            snippet = match.group(0)[:24]
            findings.append(f"{rel}: JWT secret literal detected ({snippet}...)")

        for match in _BEARER_LITERAL_RE.finditer(text):
            snippet = match.group(0)[:28]
            findings.append(f"{rel}: Literal Bearer token detected ({snippet}...)")

        for match in _VITE_HA_TOKEN_LITERAL_RE.finditer(text):
            findings.append(f"{rel}: Non-empty VITE_HA_TOKEN literal embedded")

    return findings


class _MetaHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: list[dict[str, str]] = []
        self.meta_by_name: dict[str, str] = {}
        self.links: list[dict[str, str]] = []
        self.scripts: list[dict[str, str]] = []
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_l = tag.lower()
        attr_dict = {k.lower(): (v if v is not None else "") for k, v in attrs}
        if tag_l == "meta":
            self.meta.append(attr_dict)
            key = (attr_dict.get("name") or attr_dict.get("property") or "").strip().lower()
            if key and "content" in attr_dict:
                self.meta_by_name[key] = attr_dict["content"]
        elif tag_l == "link":
            self.links.append(attr_dict)
        elif tag_l == "script":
            self.scripts.append(attr_dict)
        elif tag_l == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)

    @property
    def title(self) -> str:
        return "".join(self._title_parts).strip()


def parse_html_meta(html_path: Path | str) -> dict[str, Any]:
    """Parse <title>, <meta>, <link>, and <script> tags from an HTML file."""
    path = Path(html_path)
    content = path.read_text(encoding="utf-8")
    parser = _MetaHtmlParser()
    parser.feed(content)
    parser.close()
    return {
        **parser.meta_by_name,
        "title": parser.title,
        "meta": parser.meta,
        "meta_by_name": parser.meta_by_name,
        "links": parser.links,
        "scripts": parser.scripts,
    }


def run_js_scenario(scenario: dict[str, Any], timeout_s: int = 30) -> dict[str, Any]:
    """Execute a frontend scenario via Node + Vite SSR ESM harness."""
    payload = json.dumps(scenario)
    proc = subprocess.run(
        ["node", str(JS_HARNESS_PATH)],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
        timeout=timeout_s,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"JS harness failed (exit {proc.returncode}).\n"
            f"STDERR:\n{proc.stderr.strip()}\nSTDOUT:\n{proc.stdout.strip()}"
        )
    stdout = proc.stdout.strip()
    if not stdout:
        raise RuntimeError(f"JS harness produced empty stdout. STDERR:\n{proc.stderr.strip()}")
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"JS harness produced invalid JSON: {exc}\nSTDOUT:\n{stdout}\nSTDERR:\n{proc.stderr}"
        ) from exc

    if not result.get("ok", False):
        raise AssertionError(
            f"JS scenario error: {result.get('error', 'unknown error')}\n"
            f"Stack: {result.get('stack', '')}"
        )
    return result


def inspect_vite_config(mode: str = "production", timeout_s: int = 20) -> dict[str, Any]:
    """Inspect vite.config.js resolved config & VitePWA options without writing dist/."""
    proc = subprocess.run(
        ["node", str(VITE_INSPECT_PATH), mode],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
        timeout=timeout_s,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"vite_config_inspect.mjs failed (exit {proc.returncode}).\n"
            f"STDERR:\n{proc.stderr.strip()}\nSTDOUT:\n{proc.stdout.strip()}"
        )
    stdout = proc.stdout.strip()
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"vite_config_inspect.mjs produced invalid JSON: {exc}\nSTDOUT:\n{stdout}"
        ) from exc
