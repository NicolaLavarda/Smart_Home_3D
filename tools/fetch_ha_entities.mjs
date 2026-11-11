import fs from 'node:fs';
import path from 'node:path';
import { createConnection, subscribeEntities, createLongLivedTokenAuth } from 'home-assistant-js-websocket';

// Leggi .env senza esporre il token
const envContent = fs.readFileSync(path.resolve('.env'), 'utf8');
let haUrl = 'ws://homeassistant.local:8123/api/websocket';
let haToken = '';

for (const line of envContent.split('\n')) {
  const trimmed = line.trim();
  if (trimmed.startsWith('VITE_HA_URL=')) {
    haUrl = trimmed.replace('VITE_HA_URL=', '').trim();
  } else if (trimmed.startsWith('VITE_HA_TOKEN=')) {
    haToken = trimmed.replace('VITE_HA_TOKEN=', '').trim();
  }
}

// Normalizza URL per home-assistant-js-websocket: deve essere http(s)://host:port senza /api/websocket
let authUrl = haUrl.replace(/^ws:\/\//, 'http://').replace(/^wss:\/\//, 'https://').replace(/\/api\/websocket\/?$/, '');
console.log(`[HA Entity Explorer] Auth URL normalizzato: ${authUrl}`);
if (!haToken) {
  console.error('[HA Entity Explorer] Nessun VITE_HA_TOKEN trovato in .env');
  process.exit(1);
}

async function run() {
  try {
    const auth = createLongLivedTokenAuth(authUrl, haToken);
    const conn = await createConnection({ auth });
    console.log('[HA Entity Explorer] Connessione WebSocket stabilita!');

    subscribeEntities(conn, (entities) => {
      console.log(`\n=== ENTITÀ DISPONIBILI SU HOME ASSISTANT (${Object.keys(entities).length} totali) ===\n`);

      console.log('--- LUCI (domain: light) ---');
      for (const [id, ent] of Object.entries(entities)) {
        if (id.startsWith('light.')) {
          console.log(`  ${id.padEnd(35)} -> "${ent.attributes.friendly_name || ''}" [state: ${ent.state}]`);
        }
      }

      console.log('\n--- TELECAMERE (domain: camera) ---');
      for (const [id, ent] of Object.entries(entities)) {
        if (id.startsWith('camera.')) {
          console.log(`  ${id.padEnd(35)} -> "${ent.attributes.friendly_name || ''}" [state: ${ent.state}]`);
        }
      }

      console.log('\n--- CANCELLI / COVER (domain: cover) ---');
      for (const [id, ent] of Object.entries(entities)) {
        if (id.startsWith('cover.')) {
          console.log(`  ${id.padEnd(35)} -> "${ent.attributes.friendly_name || ''}" [state: ${ent.state}]`);
        }
      }

      console.log('\n--- MEDIA PLAYER (domain: media_player) ---');
      for (const [id, ent] of Object.entries(entities)) {
        if (id.startsWith('media_player.')) {
          console.log(`  ${id.padEnd(35)} -> "${ent.attributes.friendly_name || ''}" [state: ${ent.state}]`);
        }
      }

      console.log('\n--- ENTITÀ CON NOMI CHIAVE (bancone, forno, carraio, cancello, tavolo, cucina) ---');
      for (const [id, ent] of Object.entries(entities)) {
        const name = (ent.attributes.friendly_name || '').toLowerCase();
        const lowId = id.toLowerCase();
        if (['bancone', 'forno', 'carraio', 'cancello', 'tavolo', 'cucina'].some(k => name.includes(k) || lowId.includes(k))) {
          console.log(`  ${id.padEnd(35)} -> "${ent.attributes.friendly_name || ''}"`);
        }
      }

      process.exit(0);
    });
  } catch (err) {
    console.error('[HA Entity Explorer] Errore connessione:', err.message);
    process.exit(1);
  }
}

run();
