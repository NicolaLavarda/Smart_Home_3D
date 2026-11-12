/**
 * Script di test per ascoltare in tempo reale le coordinate del Deebot da terminale
 * =================================================================================
 * Compatibile con Node 18, 20, 22, 24+ (standard WHATWG WebSocket e libreria ws)
 *
 * Utilizzo:
 *   node tools/listen_deebot_pose.mjs
 */

import { readFileSync, existsSync } from 'fs';
import { resolve } from 'path';

// Carica variabili d'ambiente da .env
let haUrl = process.env.VITE_HA_URL || 'ws://homeassistant.local:8123/api/websocket';
let haToken = process.env.VITE_HA_TOKEN || '';

const envPath = resolve(process.cwd(), '.env');
if (existsSync(envPath)) {
  const content = readFileSync(envPath, 'utf8');
  content.split('\n').forEach((line) => {
    const trimmed = line.trim();
    if (trimmed.startsWith('VITE_HA_URL=')) {
      haUrl = trimmed.substring('VITE_HA_URL='.length).trim();
    } else if (trimmed.startsWith('VITE_HA_TOKEN=')) {
      haToken = trimmed.substring('VITE_HA_TOKEN='.length).trim();
    }
  });
}

// Verifica token
if (!haToken) {
  console.warn('⚠️  Attenzione: VITE_HA_TOKEN non trovato nel file .env.');
}

console.log('='.repeat(70));
console.log('🛰️  ECOVACS DEEBOT - LISTENER TELEMETRIA MQTT IN TEMPO REALE');
console.log('='.repeat(70));
console.log(`📡 Connessione WebSocket a Home Assistant: ${haUrl}`);
console.log(`🎯 In ascolto su topic: 'homeassistant/deebot/pose'`);
console.log('Premi Ctrl+C per terminare.\n');

// Supporto per WebSocket (WHATWG standard in Node 22+ oppure fallback 'ws')
let WSClient = globalThis.WebSocket;
if (!WSClient) {
  try {
    const wsModule = await import('ws');
    WSClient = wsModule.default || wsModule;
  } catch (e) {
    console.error('❌ Libreria WebSocket non disponibile.');
    process.exit(1);
  }
}

let messageId = 1;
const ws = new WSClient(haUrl);

function send(payload) {
  ws.send(JSON.stringify(payload));
}

// Gestione eventi universale (supporta sia addEventListener che on('event'))
function addListener(eventName, handler) {
  if (typeof ws.addEventListener === 'function') {
    ws.addEventListener(eventName, (e) => handler(e.data !== undefined ? e.data : e));
  } else if (typeof ws.on === 'function') {
    ws.on(eventName, handler);
  }
}

addListener('open', () => {
  // Connesso a HA, attende 'auth_required'
});

addListener('message', (raw) => {
  try {
    const str = typeof raw === 'string' ? raw : (raw.toString ? raw.toString() : String(raw));
    const msg = JSON.parse(str);

    if (msg.type === 'auth_required') {
      send({ type: 'auth', access_token: haToken });
    } else if (msg.type === 'auth_ok') {
      console.log('✅ Autenticato con successo su Home Assistant!');
      // Sottoscrivi al topic MQTT tramite il WebSocket nativo di HA
      send({
        id: messageId++,
        type: 'mqtt/subscribe',
        topic: 'homeassistant/deebot/pose',
      });
      console.log('👂 Sottoscrizione MQTT attiva. Muovi o avvia il Deebot per vedere i dati...\n');
    } else if (msg.type === 'auth_invalid') {
      console.error('❌ Autenticazione fallita: verifica VITE_HA_TOKEN in .env');
    } else if (msg.type === 'event' && msg.event) {
      const payload = typeof msg.event.payload === 'string' ? JSON.parse(msg.event.payload) : msg.event.payload;
      const robot = payload.robot || payload;
      const t = new Date().toLocaleTimeString();

      console.log(
        `[${t}] 📍 Robot Pose -> X: ${Number(robot.x)?.toFixed(1) ?? '?'} mm | Y: ${Number(robot.y)?.toFixed(1) ?? '?'} mm | Angolo: ${Number(robot.angle)?.toFixed(1) ?? '?'}° | Stato: ${payload.state || 'N/A'}`
      );
    }
  } catch (err) {
    // Messaggi secondari non JSON
  }
});

addListener('error', (err) => {
  console.error('❌ Errore WebSocket:', err?.message || err);
});

addListener('close', () => {
  console.log('🔌 Connessione chiusa.');
});
