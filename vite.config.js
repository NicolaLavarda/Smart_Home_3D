import { defineConfig, loadEnv } from 'vite';

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

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  return {
    root: '.',
    publicDir: 'public',
    plugins: [haCameraBridgePlugin(env)],
    server: {
      port: 3000,
      open: false,
      host: true
    },
    build: {
      outDir: 'dist',
      assetsDir: 'assets',
      sourcemap: true
    }
  };
});

