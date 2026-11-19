import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const mode = process.argv[2] || 'production';
const repoRoot = process.cwd();
const viteConfigPath = path.join(repoRoot, 'vite.config.js');

function serializeValue(val, seen = new WeakSet()) {
  if (val === null || val === undefined) return val;
  if (typeof val === 'string' || typeof val === 'number' || typeof val === 'boolean') return val;
  if (val instanceof RegExp) {
    return {
      __type: 'RegExp',
      source: val.source,
      flags: val.flags,
      string: val.toString(),
    };
  }
  if (typeof val === 'function') {
    return {
      __type: 'Function',
      name: val.name || 'anonymous',
      source: val.toString().slice(0, 400),
    };
  }
  if (Array.isArray(val)) {
    return val.map((item) => serializeValue(item, seen));
  }
  if (typeof val === 'object') {
    if (seen.has(val)) return '[Circular]';
    seen.add(val);
    if (val instanceof Set) {
      return Array.from(val).map((item) => serializeValue(item, seen));
    }
    if (val instanceof Map) {
      return Object.fromEntries(
        Array.from(val.entries()).map(([k, v]) => [String(k), serializeValue(v, seen)])
      );
    }
    const out = {};
    for (const key of Object.keys(val)) {
      if (key === 'ctx' || key === '_viteConfig') continue;
      try {
        out[key] = serializeValue(val[key], seen);
      } catch {
        out[key] = '[Unserializable]';
      }
    }
    return out;
  }
  return String(val);
}

function flattenPlugins(plugins, out = []) {
  if (!plugins) return out;
  for (const p of plugins) {
    if (!p) continue;
    if (Array.isArray(p)) {
      flattenPlugins(p, out);
    } else {
      out.push(p);
    }
  }
  return out;
}

async function main() {
  const emptyDir = fs.mkdtempSync(path.join(os.tmpdir(), 'sh3d-vite-inspect-'));
  let rawConfig;
  try {
    const mod = await import(pathToFileURL(viteConfigPath).href);
    const exported = mod.default;

    // Temporarily chdir into an empty directory so loadEnv(mode, process.cwd(), '')
    // inside vite.config.js NEVER reads the repository's .env secrets.
    process.chdir(emptyDir);
    try {
      rawConfig = typeof exported === 'function'
        ? await exported({ mode, command: 'build', isSsrBuild: false, isPreview: false })
        : exported;
    } finally {
      process.chdir(repoRoot);
    }

    const flatPlugins = flattenPlugins(rawConfig?.plugins || []);
    const resolvedEnv = { mode, command: 'build', isSsrBuild: false, isPreview: false };

    // Trigger config() / configResolved() hooks on PWA plugins if needed so api.options populates.
    const mergedConfig = {
      root: repoRoot,
      base: rawConfig?.base || '/',
      mode,
      command: 'build',
      publicDir: path.join(repoRoot, rawConfig?.publicDir || 'public'),
      build: {
        outDir: path.join(repoRoot, rawConfig?.build?.outDir || 'dist'),
        assetsDir: rawConfig?.build?.assetsDir || 'assets',
        ...(rawConfig?.build || {}),
      },
      plugins: flatPlugins,
    };

    for (const plugin of flatPlugins) {
      if (plugin?.name && plugin.name.includes('pwa')) {
        if (typeof plugin.config === 'function') {
          try {
            await plugin.config(mergedConfig, resolvedEnv);
          } catch {}
        }
      }
    }
    for (const plugin of flatPlugins) {
      if (plugin?.name && plugin.name.includes('pwa')) {
        if (typeof plugin.configResolved === 'function') {
          try {
            await plugin.configResolved(mergedConfig);
          } catch {}
        }
      }
    }

    let pwaOptions = null;
    const pluginSummaries = [];
    for (const plugin of flatPlugins) {
      const name = plugin?.name || 'unnamed';
      const summary = { name };
      if (plugin?.api) {
        summary.apiKeys = Object.keys(plugin.api);
        if (plugin.api.options && !pwaOptions) {
          pwaOptions = serializeValue(plugin.api.options);
        }
        if (plugin.api.userOptions && !pwaOptions) {
          pwaOptions = serializeValue(plugin.api.userOptions);
        }
      }
      if (name.includes('pwa') && !pwaOptions && plugin?.options) {
        pwaOptions = serializeValue(plugin.options);
      }
      pluginSummaries.push(summary);
    }

    // Fallback: if vite-plugin-pwa keeps options inside a closure without exposing api.options,
    // read public getters on plugin.api (like extendManifest) or check vite.config.js options.
    let pwaPluginPresent = flatPlugins.some((p) => String(p?.name || '').includes('pwa'));

    const output = {
      ok: true,
      mode,
      hasPwaPlugin: pwaPluginPresent,
      pluginNames: flatPlugins.map((p) => p?.name || 'unnamed'),
      plugins: pluginSummaries,
      pwaOptions,
      build: serializeValue(rawConfig?.build || {}),
      server: serializeValue(rawConfig?.server || {}),
    };

    process.stdout.write(JSON.stringify(output));
  } finally {
    try {
      process.chdir(repoRoot);
    } catch {}
    try {
      fs.rmSync(emptyDir, { recursive: true, force: true });
    } catch {}
  }
}

main().catch((err) => {
  process.stderr.write(err?.stack || String(err));
  process.exit(1);
});
