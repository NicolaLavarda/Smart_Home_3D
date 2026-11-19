from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

_MARKER = "__SH3D_TIER34_RESULT__:"

_BROWSER_SHIM_JS = r"""
export function installBrowserShims(opts = {}) {
  const origin = opts.origin || 'https://pc-fisso.tail123.ts.net';
  const url = new URL(opts.href || (origin + '/'));
  const storageMap = new Map(Object.entries(opts.localStorage || {}));
  const listeners = new Map();
  const docListeners = new Map();

  function makeElement(tag = 'div', id = '') {
    const classes = new Set();
    const attrs = new Map();
    const children = [];
    const elListeners = new Map();
    let _innerHTML = '';
    let _textContent = '';
    const el = {
      tagName: String(tag).toUpperCase(),
      id,
      style: {},
      dataset: {},
      children,
      disabled: false,
      hidden: false,
      muted: false,
      autoplay: false,
      playsInline: false,
      crossOrigin: '',
      disableRemotePlayback: false,
      src: '',
      srcObject: null,
      width: 640,
      height: 360,
      classList: {
        add: (...cs) => cs.forEach((c) => classes.add(c)),
        remove: (...cs) => cs.forEach((c) => classes.delete(c)),
        toggle: (c, force) => {
          if (force === undefined) {
            if (classes.has(c)) { classes.delete(c); return false; }
            classes.add(c); return true;
          }
          if (force) classes.add(c); else classes.delete(c);
          return Boolean(force);
        },
        contains: (c) => classes.has(c),
        toString: () => Array.from(classes).join(' '),
      },
      setAttribute: (k, v) => attrs.set(k, String(v)),
      getAttribute: (k) => (attrs.has(k) ? attrs.get(k) : null),
      removeAttribute: (k) => attrs.delete(k),
      hasAttribute: (k) => attrs.has(k),
      appendChild: (c) => { children.push(c); return c; },
      removeChild: (c) => {
        const idx = children.indexOf(c);
        if (idx >= 0) children.splice(idx, 1);
        return c;
      },
      remove: () => {},
      addEventListener: (ev, fn) => {
        if (!elListeners.has(ev)) elListeners.set(ev, []);
        elListeners.get(ev).push(fn);
      },
      removeEventListener: (ev, fn) => {
        if (!elListeners.has(ev)) return;
        elListeners.set(ev, elListeners.get(ev).filter((f) => f !== fn));
      },
      dispatchEvent: (ev) => {
        const list = elListeners.get(ev?.type || ev) || [];
        list.forEach((fn) => fn(ev));
        return true;
      },
      click: () => {
        const list = elListeners.get('click') || [];
        list.forEach((fn) => fn({ preventDefault() {}, stopPropagation() {}, target: el, currentTarget: el }));
      },
      getContext: () => ({
        fillStyle: '',
        strokeStyle: '',
        lineWidth: 1,
        font: '',
        textAlign: '',
        fillRect() {},
        strokeRect() {},
        clearRect() {},
        beginPath() {},
        closePath() {},
        moveTo() {},
        lineTo() {},
        stroke() {},
        arc() {},
        fill() {},
        fillText() {},
        drawImage() {},
        save() {},
        restore() {},
        createLinearGradient: () => ({ addColorStop() {} }),
        createRadialGradient: () => ({ addColorStop() {} }),
      }),
      captureStream: () => ({ getTracks: () => [] }),
      play: async () => {},
      pause: () => {},
      getBoundingClientRect: () => ({ left: 0, top: 0, width: 800, height: 600 }),
      querySelector: (sel) => el._findBySelector(sel),
      querySelectorAll: (sel) => el._findAllBySelector(sel),
      _findBySelector: (sel) => {
        const all = el._findAllBySelector(sel);
        return all.length ? all[0] : null;
      },
      _findAllBySelector: (sel) => {
        const out = [];
        const walk = (node) => {
          for (const c of node.children || []) {
            if (matchesSelector(c, sel)) out.push(c);
            walk(c);
          }
        };
        walk(el);
        return out;
      },
      get innerHTML() {
        const childContent = children.map((c) => (c._rawInner || '') + (c.textContent || '')).join('');
        return _innerHTML + (childContent && !_innerHTML.includes(childContent) ? childContent : '');
      },
      get _rawInner() { return _innerHTML; },
      get outerHTML() {
        const t = String(tag || 'div').toLowerCase();
        return `<${t}>${_innerHTML}</${t}>`;
      },
      set innerHTML(val) {
        _innerHTML = String(val || '');
        children.length = 0;
        // Parse id="..." and class="..." tokens into synthetic child elements for querySelector
        const tagRegex = /<([a-zA-Z0-9-]+)([^>]*)>/g;
        let m;
        while ((m = tagRegex.exec(_innerHTML)) !== null) {
          const tName = m[1];
          const attrStr = m[2] || '';
          const idMatch = attrStr.match(/\bid=["']([^"']+)["']/);
          const classMatch = attrStr.match(/\bclass=["']([^"']+)["']/);
          const child = makeElement(tName, idMatch ? idMatch[1] : '');
          if (classMatch) {
            classMatch[1].split(/\s+/).filter(Boolean).forEach((c) => child.classList.add(c));
          }
          const dsRegex = /\bdata-([a-zA-Z0-9-]+)=["']([^"']+)["']/g;
          let dm;
          while ((dm = dsRegex.exec(attrStr)) !== null) {
            child.dataset[dm[1]] = dm[2];
          }
          if (/\bhidden\b/.test(attrStr)) child.hidden = true;
          if (/\bdisabled\b/.test(attrStr)) child.disabled = true;
          children.push(child);
        }
      },
      get textContent() { return _textContent; },
      set textContent(v) { _textContent = String(v ?? ''); },
    };
    return el;
  }

  function matchesSelector(node, sel) {
    if (!sel) return false;
    if (sel.startsWith('#')) return node.id === sel.slice(1);
    if (sel.startsWith('.')) return node.classList.contains(sel.slice(1));
    return node.tagName === sel.toUpperCase();
  }

  const rootBody = makeElement('body', 'body');
  const docElements = new Map();
  if (Array.isArray(opts.domIds)) {
    for (const id of opts.domIds) {
      const e = makeElement('div', id);
      docElements.set(id, e);
      rootBody.appendChild(e);
    }
  }

  const localStorage = {
    getItem: (k) => (storageMap.has(k) ? storageMap.get(k) : null),
    setItem: (k, v) => storageMap.set(k, String(v)),
    removeItem: (k) => storageMap.delete(k),
    clear: () => storageMap.clear(),
  };

  const windowObj = {
    location: {
      href: url.href,
      origin: url.origin,
      protocol: url.protocol,
      host: url.host,
      hostname: url.hostname,
      port: url.port,
      pathname: url.pathname,
      search: url.search,
      hash: url.hash,
      assign(next) { windowObj._navigatedTo = next; },
      replace(next) { windowObj._navigatedTo = next; },
    },
    history: {
      replaceState(_state, _title, nextUrl) {
        windowObj._replacedHistoryUrl = nextUrl;
      },
    },
    localStorage,
    innerWidth: opts.innerWidth ?? 1280,
    innerHeight: opts.innerHeight ?? 720,
    devicePixelRatio: opts.devicePixelRatio ?? 1,
    matchMedia: (q) => ({
      matches: typeof opts.matchMedia === 'function' ? Boolean(opts.matchMedia(q)) : Boolean(opts.isCoarsePointer && q.includes('coarse')),
      media: q,
      addEventListener() {},
      removeEventListener() {},
    }),
    addEventListener: (ev, fn) => {
      if (!listeners.has(ev)) listeners.set(ev, []);
      listeners.get(ev).push(fn);
    },
    removeEventListener: (ev, fn) => {
      if (!listeners.has(ev)) return;
      listeners.set(ev, listeners.get(ev).filter((f) => f !== fn));
    },
    dispatchEvent: (ev) => {
      const list = listeners.get(ev?.type || ev) || [];
      list.forEach((fn) => fn(ev));
    },
  };

  const documentObj = {
    hidden: Boolean(opts.documentHidden),
    visibilityState: opts.documentHidden ? 'hidden' : 'visible',
    body: rootBody,
    createElement: (tag) => makeElement(tag),
    createElementNS: (_ns, tag) => documentObj.createElement(tag),
    getElementById: (id) => {
      if (docElements.has(id)) return docElements.get(id);
      return rootBody._findBySelector('#' + id);
    },
    querySelector: (sel) => {
      if (sel.startsWith('#') && docElements.has(sel.slice(1))) return docElements.get(sel.slice(1));
      return rootBody._findBySelector(sel);
    },
    querySelectorAll: (sel) => rootBody._findAllBySelector(sel),
    addEventListener: (ev, fn) => {
      if (!docListeners.has(ev)) docListeners.set(ev, []);
      docListeners.get(ev).push(fn);
    },
    removeEventListener: (ev, fn) => {
      if (!docListeners.has(ev)) return;
      docListeners.set(ev, docListeners.get(ev).filter((f) => f !== fn));
    },
    dispatchEvent: (ev) => {
      const list = docListeners.get(ev?.type || ev) || [];
      list.forEach((fn) => fn(ev));
    },
  };

  const rafQueue = [];
  let rafId = 1;
  const navObj = {
    userAgent: opts.userAgent || 'Mozilla/5.0',
    maxTouchPoints: opts.maxTouchPoints ?? 0,
  };
  windowObj.navigator = navObj;
  windowObj.document = documentObj;
  windowObj.Event = class Event { constructor(t) { this.type = t; } };
  globalThis.Event = windowObj.Event;
  globalThis.window = windowObj;
  globalThis.self = windowObj;
  globalThis.document = documentObj;
  globalThis.localStorage = localStorage;
  Object.defineProperty(globalThis, 'navigator', {
    value: navObj,
    configurable: true,
    writable: true,
  });
  globalThis.requestAnimationFrame = (cb) => {
    const id = rafId++;
    rafQueue.push({ id, cb });
    return id;
  };
  globalThis.cancelAnimationFrame = (id) => {
    const idx = rafQueue.findIndex((x) => x.id === id);
    if (idx >= 0) rafQueue.splice(idx, 1);
  };
  globalThis.URL.createObjectURL = globalThis.URL.createObjectURL || (() => 'blob:mock-url');
  globalThis.URL.revokeObjectURL = globalThis.URL.revokeObjectURL || (() => {});

  return { windowObj, documentObj, storageMap, rafQueue, makeElement };
}
"""


def run_vite_module_script(
    repo_root: Path,
    script_body: str,
    *,
    define_env: Optional[dict[str, Any]] = None,
    timeout_s: int = 30,
) -> dict[str, Any]:
    """Execute an async ESM script against repo_root via Vite SSR (no .env loading)."""
    defines: dict[str, str] = {
        "import.meta.env.PROD": "true",
        "import.meta.env.DEV": "false",
        "import.meta.env.VITE_HA_TOKEN": json.dumps(""),
    }
    if define_env:
        for k, v in define_env.items():
            key = k if k.startswith("import.meta.env.") else f"import.meta.env.{k}"
            defines[key] = json.dumps(v)

    with tempfile.TemporaryDirectory(prefix="sh3d_tier34_js_") as td:
        td_path = Path(td)
        shim_path = td_path / "browser_shim.mjs"
        shim_path.write_text(_BROWSER_SHIM_JS, encoding="utf-8")

        runner_path = td_path / "runner.mjs"
        runner_code = f"""
import {{ createServer }} from {json.dumps((repo_root / 'node_modules' / 'vite' / 'dist' / 'node' / 'index.js').as_uri())};
import {{ installBrowserShims }} from {json.dumps(shim_path.as_uri())};

const virtualPwaPlugin = {{
  name: 'sh3d-tier34-virtual-pwa',
  enforce: 'pre',
  configResolved(resolvedConfig) {{
    resolvedConfig.env.PROD = {json.dumps(defines.get("import.meta.env.PROD") == "true")};
    resolvedConfig.env.DEV = {json.dumps(defines.get("import.meta.env.DEV") == "true")};
    resolvedConfig.env.MODE = resolvedConfig.env.PROD ? 'production' : 'development';
    resolvedConfig.env.VITE_HA_TOKEN = {defines.get("import.meta.env.VITE_HA_TOKEN", '""')};
  }},
  resolveId(id) {{
    if (id === 'virtual:pwa-register' || id === 'virtual:pwa-register/vanilla') return '\\0' + id;
  }},
  load(id) {{
    if (id === '\\0virtual:pwa-register' || id === '\\0virtual:pwa-register/vanilla') {{
      return 'export function registerSW(opts = {{}}) {{ if (typeof globalThis.__SH3D_TEST_REGISTER_SW__ === "function") return globalThis.__SH3D_TEST_REGISTER_SW__(opts); return async () => {{}}; }}';
    }}
  }},
}};

const server = await createServer({{
  configFile: false,
  envFile: false,
  mode: {json.dumps("production" if defines.get("import.meta.env.PROD") == "true" else "development")},
  root: {json.dumps(str(repo_root))},
  define: {json.dumps(defines)},
  optimizeDeps: {{ noDiscovery: true, include: [] }},
  ssr: {{ external: ['lucide'], noExternal: ['home-assistant-js-websocket'] }},
  plugins: [virtualPwaPlugin],
  server: {{ middlewareMode: true, hmr: false, ws: false, watch: null }},
  appType: 'custom',
  logLevel: 'silent',
}});

try {{
  const __run = async (server, installBrowserShims) => {{
{script_body}
  }};
  const result = await __run(server, installBrowserShims);
  console.log({json.dumps(_MARKER)} + JSON.stringify({{ ok: true, result }}));
}} catch (err) {{
  console.log({json.dumps(_MARKER)} + JSON.stringify({{
    ok: false,
    error: err?.message || String(err),
    stack: err?.stack || '',
  }}));
  process.exitCode = 1;
}} finally {{
  server.close().catch(() => {{}});
  setImmediate(() => process.exit(process.exitCode || 0));
}}
"""
        runner_path.write_text(runner_code, encoding="utf-8")

        env = os.environ.copy()
        # Ensure no VITE_* env vars leak from parent shell
        for key in list(env.keys()):
            if key.startswith("VITE_"):
                env.pop(key, None)

        proc = subprocess.run(
            ["node", str(runner_path)],
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )

        for line in reversed(proc.stdout.splitlines()):
            if line.startswith(_MARKER):
                payload = json.loads(line[len(_MARKER):])
                if not payload.get("ok"):
                    raise AssertionError(
                        f"Vite JS scenario failed: {payload.get('error')}\n{payload.get('stack')}"
                    )
                return payload["result"]

        raise RuntimeError(
            f"Vite JS runner produced no result marker (rc={proc.returncode}).\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )


def resolve_vite_config_json(repo_root: Path, mode: str = "production") -> dict[str, Any]:
    """Load vite.config.js via Vite's resolveConfig in Node without mutating repo or reading .env secrets."""
    with tempfile.TemporaryDirectory(prefix="sh3d_vite_cfg_") as td:
        runner_path = Path(td) / "inspect_cfg.mjs"
        runner_code = f"""
import {{ resolveConfig }} from {json.dumps((repo_root / 'node_modules' / 'vite' / 'dist' / 'node' / 'index.js').as_uri())};

const cfg = await resolveConfig({{ configFile: {json.dumps(str(repo_root / 'vite.config.js'))} }}, 'build', {json.dumps(mode)});
const pluginNames = (cfg.plugins || []).map((p) => p?.name).filter(Boolean);
const pwaPlugin = (cfg.plugins || []).find((p) => p?.name && p.name.includes('vite-plugin-pwa'));
const pwaApi = pwaPlugin?.api || null;
const pwaOptions = pwaApi?.options || null;

console.log({json.dumps(_MARKER)} + JSON.stringify({{
  mode: cfg.mode,
  pluginNames,
  build: {{
    outDir: cfg.build?.outDir,
    assetsDir: cfg.build?.assetsDir,
  }},
  pwaOptions: pwaOptions ? {{
    registerType: pwaOptions.registerType,
    manifest: pwaOptions.manifest,
    workbox: pwaOptions.workbox ? {{
      globPatterns: pwaOptions.workbox.globPatterns,
      globIgnores: pwaOptions.workbox.globIgnores,
      navigateFallbackDenylist: (pwaOptions.workbox.navigateFallbackDenylist || []).map(String),
      runtimeCaching: (pwaOptions.workbox.runtimeCaching || []).map((rc) => ({{
        urlPattern: String(rc.urlPattern),
        handler: rc.handler,
        cacheName: rc.options?.cacheName || null,
      }})),
    }} : null,
  }} : null,
}}));
"""
        runner_path.write_text(runner_code, encoding="utf-8")
        env = os.environ.copy()
        for key in list(env.keys()):
            if key.startswith("VITE_"):
                env.pop(key, None)
        proc = subprocess.run(
            ["node", str(runner_path)],
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
            timeout=25,
        )
        for line in reversed(proc.stdout.splitlines()):
            if line.startswith(_MARKER):
                return json.loads(line[len(_MARKER):])
        raise RuntimeError(f"resolveConfig failed (rc={proc.returncode}):\n{proc.stdout}\n{proc.stderr}")
