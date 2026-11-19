import { defineConfig, loadEnv } from 'vite';
import { VitePWA } from 'vite-plugin-pwa';

function normalizeHaUrl(raw) {
  if (!raw || typeof raw !== 'string') return '';
  return raw
    .trim()
    .replace(/^ws:\/\//i, 'http://')
    .replace(/^wss:\/\//i, 'https://')
    .replace(/\/api\/websocket\/?$/i, '')
    .replace(/\/+$/, '');
}

function haCameraBridgePlugin(env) {
  const attachMiddleware = (middlewares) => {
    middlewares.use('/api/ha-camera/snapshot', async (req, res) => {
      try {
        const reqUrl = new URL(req.url || '/', 'http://localhost');
        const entityId = (reqUrl.searchParams.get('entity_id') || 'camera.carraio_scorrevole').trim();
        if (!/^[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+$/.test(entityId)) {
          res.statusCode = 400;
          res.setHeader('Content-Type', 'application/json');
          res.end(JSON.stringify({ error: 'entity_id non valido' }));
          return;
        }

        const token = (env.VITE_HA_TOKEN || '').trim();
        if (!token) {
          res.statusCode = 503;
          res.setHeader('Content-Type', 'application/json');
          res.end(JSON.stringify({ error: 'VITE_HA_TOKEN non configurato' }));
          return;
        }

        const requestedHaUrl = normalizeHaUrl(reqUrl.searchParams.get('ha_url') || '');
        const rawCandidates = [
          requestedHaUrl && /^https?:\/\//i.test(requestedHaUrl) ? requestedHaUrl : '',
          normalizeHaUrl(env.VITE_HA_TAILSCALE_URL),
          normalizeHaUrl(env.VITE_HA_REMOTE_URL),
          normalizeHaUrl(env.VITE_HA_LOCAL_URL),
          normalizeHaUrl(env.VITE_HA_URL),
        ];

        const candidates = [];
        for (const c of rawCandidates) {
          if (c && !candidates.includes(c)) candidates.push(c);
        }

        let lastStatus = 502;
        let lastError = 'Nessun endpoint Home Assistant configurato o raggiungibile';

        for (const baseUrl of candidates) {
          const controller = new AbortController();
          const timer = setTimeout(() => controller.abort(), 3500);
          try {
            const upstream = await fetch(
              `${baseUrl}/api/camera_proxy/${encodeURIComponent(entityId)}`,
              {
                headers: { Authorization: `Bearer ${token}` },
                signal: controller.signal,
              }
            );
            clearTimeout(timer);

            if (upstream.ok) {
              const buffer = Buffer.from(await upstream.arrayBuffer());
              res.statusCode = 200;
              res.setHeader('Content-Type', upstream.headers.get('content-type') || 'image/jpeg');
              res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate');
              res.setHeader('Access-Control-Allow-Origin', '*');
              res.end(buffer);
              return;
            }

            lastStatus = upstream.status;
            lastError = `Home Assistant HTTP ${upstream.status} su ${baseUrl}`;
          } catch (err) {
            clearTimeout(timer);
            lastError = err?.message || `Timeout/errore su ${baseUrl}`;
          }
        }

        res.statusCode = lastStatus;
        res.setHeader('Content-Type', 'application/json');
        res.setHeader('Access-Control-Allow-Origin', '*');
        res.end(JSON.stringify({ error: lastError, entity_id: entityId }));
      } catch (err) {
        res.statusCode = 500;
        res.setHeader('Content-Type', 'application/json');
        res.end(JSON.stringify({ error: err?.message || 'Errore interno proxy camera HA' }));
      }
    });
  };

  return {
    name: 'ha-camera-bridge-proxy',
    configureServer(server) {
      attachMiddleware(server.middlewares);
    },
    configurePreviewServer(server) {
      attachMiddleware(server.middlewares);
    },
  };
}

export function createPwaOptions() {
  return {
    registerType: 'prompt',
    injectRegister: 'auto',
    includeAssets: [
      'pwa/icon.svg',
      'pwa/icon-192.png',
      'pwa/icon-512.png',
      'pwa/icon-maskable-512.png',
      'pwa/icon-monochrome-512.png',
      'pwa/apple-touch-icon.png',
    ],
    manifest: {
      name: 'Smart Home 3D - Digital Twin & Spatial CV Engine',
      short_name: 'SmartHome 3D',
      description: 'Digital Twin 3D interattivo e motore Spatial CV con integrazione Home Assistant',
      lang: 'it',
      start_url: '/',
      scope: '/',
      display: 'standalone',
      orientation: 'any',
      background_color: '#09111e',
      theme_color: '#0f172a',
      icons: [
        {
          src: '/pwa/icon-192.png',
          sizes: '192x192',
          type: 'image/png',
          purpose: 'any',
        },
        {
          src: '/pwa/icon-512.png',
          sizes: '512x512',
          type: 'image/png',
          purpose: 'any',
        },
        {
          src: '/pwa/icon-maskable-512.png',
          sizes: '512x512',
          type: 'image/png',
          purpose: 'maskable',
        },
        {
          src: '/pwa/icon-monochrome-512.png',
          sizes: '512x512',
          type: 'image/png',
          purpose: 'monochrome',
        },
      ],
    },
    workbox: {
      globPatterns: ['**/*.{js,css,html,svg,png,ico,woff2}'],
      globIgnores: ['**/models/*.glb', '**/*.glb', '**/node_modules/**/*'],
      navigateFallback: '/index.html',
      navigateFallbackDenylist: [
        /^\/api\//,
        /^\/ws\//,
        /^\/go2rtc\//,
        /[?&]auth_callback=/,
      ],
      runtimeCaching: [
        {
          urlPattern: /(\/api\/|\/ws\/|\/go2rtc\/|[?&]auth_callback=)/,
          handler: 'NetworkOnly',
        },
        {
          urlPattern: /\/models\/scene_manifest\.json(\?.*)?$/i,
          handler: 'NetworkFirst',
          options: {
            cacheName: 'sh3d-scene-manifest',
            networkTimeoutSeconds: 3,
            expiration: {
              maxEntries: 4,
              maxAgeSeconds: 7 * 24 * 60 * 60,
            },
            cacheableResponse: {
              statuses: [0, 200],
            },
          },
        },
        {
          urlPattern: /\/models\/.*\.glb(\?.*)?$/i,
          handler: 'CacheFirst',
          options: {
            cacheName: 'sh3d-3d-models',
            expiration: {
              maxEntries: 4,
              maxAgeSeconds: 30 * 24 * 60 * 60,
            },
            cacheableResponse: {
              statuses: [0, 200],
            },
          },
        },
        {
          urlPattern: /^https:\/\/www\.gstatic\.com\/draco\/.*/i,
          handler: 'CacheFirst',
          options: {
            cacheName: 'sh3d-draco-decoder',
            expiration: {
              maxEntries: 10,
              maxAgeSeconds: 365 * 24 * 60 * 60,
            },
            cacheableResponse: {
              statuses: [0, 200],
            },
          },
        },
      ],
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const isProd = mode === 'production';
  const pwaOptions = createPwaOptions();
  const rawPwaPlugins = VitePWA(pwaOptions);
  const pwaPlugins = (Array.isArray(rawPwaPlugins) ? rawPwaPlugins : [rawPwaPlugins]).map((plugin) => {
    if (plugin && typeof plugin === 'object' && plugin.api) {
      plugin.api.userOptions = pwaOptions;
      if (!plugin.api.options) {
        plugin.api.options = pwaOptions;
      }
    }
    return plugin;
  });

  return {
    root: '.',
    publicDir: 'public',
    define: isProd
      ? {
          'import.meta.env.VITE_HA_TOKEN': JSON.stringify(''),
        }
      : {},
    plugins: [haCameraBridgePlugin(env), ...pwaPlugins],
    server: {
      port: 3000,
      open: false,
      host: true,
    },
    build: {
      outDir: 'dist',
      assetsDir: 'assets',
      sourcemap: true,
    },
  };
});
