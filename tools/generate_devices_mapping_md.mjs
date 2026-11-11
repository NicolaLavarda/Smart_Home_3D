import fs from 'node:fs';
import path from 'node:path';
import { createConnection, subscribeEntities, createLongLivedTokenAuth } from 'home-assistant-js-websocket';

// 1. Leggi .env
const envContent = fs.readFileSync(path.resolve('.env'), 'utf8');
let haUrl = 'http://192.168.86.24:8123';
let haToken = '';

for (const line of envContent.split('\n')) {
  const trimmed = line.trim();
  if (trimmed.startsWith('VITE_HA_URL=')) {
    haUrl = trimmed.replace('VITE_HA_URL=', '').trim();
  } else if (trimmed.startsWith('VITE_HA_TOKEN=')) {
    haToken = trimmed.replace('VITE_HA_TOKEN=', '').trim();
  }
}

// Pulizia URL
let cleanUrl = haUrl
  .replace(/^ws:\/\//i, 'http://')
  .replace(/^wss:\/\//i, 'https://')
  .replace(/\/api\/websocket\/?$/i, '')
  .replace(/\/+$/, '');

if (!cleanUrl) cleanUrl = 'http://192.168.86.24:8123';

console.log(`[Mapping Generator] Connessione a: ${cleanUrl}`);

// Mappe di entità già collegate nel progetto 3D
const ALREADY_MAPPED = {
  'light.bancone': 'Isola_Lampada_Cono_1, Isola_Lampada_Cono_2 (Luci sopra il bancone cucina)',
  'light.forno': 'Lampadario_Coppa_1..4, Lampadario_Pranzo_Asta (Lampadario sopra tavolo pranzo)',
  'light.portico': 'Pillar_Portico_1 (Illuminazione portico)',
  'switch.switch_casa_interruttore_1': 'Gate_Leaf_L, Gate_Leaf_R (Ante cancello carraio animato)',
  'media_player.smart_tv_lg_oled_2': 'TV_Salotto_Screen, TV_Salotto_Bezel (Smart TV salotto)',
  'camera.carraio_scorrevole': 'Cam_Carraio (Telecamera reale montata su palo pilastrino a Z=2.10m)',
};

// Domini rilevanti per la domotica e il gemello 3D
const TARGET_DOMAINS = [
  'light',
  'switch',
  'cover',
  'climate',
  'media_player',
  'camera',
  'binary_sensor',
  'sensor',
  'siren',
  'button'
];

// Filtri per escludere entità di sistema/diagnostica irrilevanti
const IGNORED_PREFIXES = [
  'sensor.date',
  'sensor.time',
  'sensor.sun',
  'sensor.uptime',
  'sensor.memory',
  'sensor.processor',
  'binary_sensor.remote_ui',
  'binary_sensor.updater'
];

async function run() {
  const candidateUrls = ['http://192.168.86.24:8123', cleanUrl];
  let conn = null;

  for (const url of candidateUrls) {
    try {
      console.log(`[Mapping Generator] Tentativo connessione a ${url}...`);
      const auth = createLongLivedTokenAuth(url, haToken);
      conn = await createConnection({ auth });
      console.log(`[Mapping Generator] Connesso con successo a ${url}!`);
      break;
    } catch (e) {
      console.warn(`[Mapping Generator] Connessione a ${url} fallita: ${e.message}`);
    }
  }

  if (!conn) {
    console.error('[Mapping Generator] Impossibile connettersi ad Home Assistant con le candidate URL fornite.');
    process.exit(1);
  }

  subscribeEntities(conn, (entities) => {
    console.log(`[Mapping Generator] Ricevute ${Object.keys(entities).length} entità. Generazione file Markdown...`);

    const categorized = {};
    for (const d of TARGET_DOMAINS) categorized[d] = [];
    categorized['other'] = [];

    for (const [id, ent] of Object.entries(entities)) {
      const domain = id.split('.')[0];
      const friendlyName = ent.attributes.friendly_name || id;
      const state = ent.state;

      // Filtra entità rumorose
      if (IGNORED_PREFIXES.some((p) => id.startsWith(p))) continue;

      const item = {
        id,
        domain,
        name: friendlyName,
        state,
        unit: ent.attributes.unit_of_measurement || '',
        device_class: ent.attributes.device_class || '',
        is_mapped: id in ALREADY_MAPPED,
        mapped_to: ALREADY_MAPPED[id] || '',
      };

      if (categorized[domain]) {
        categorized[domain].push(item);
      } else if (['scene', 'automation', 'script', 'input_boolean', 'select', 'number'].includes(domain)) {
        // Raccogliamo solo quelli potenzialmente utili
        categorized['other'].push(item);
      }
    }

    // Costruzione contenuto Markdown
    let md = '';
    md += `# 📋 Mappatura Dispositivi ed Entità Home Assistant $\\to$ 3D Digital Twin\n\n`;
    md += `> **Istruzioni per l'utente:**\n`;
    md += `> Questo file contiene tutte le entità fisiche e i sensori presenti nel tuo Home Assistant.\n`;
    md += `> 1. Per ogni entità che vuoi posizionare nel 3D, cambia **\`Azione:\`** da **\`ignora\`** a **\`mappa\`**.\n`;
    md += `> 2. Compila **\`Posizione 3D:\`** descrivendo dove si trova l'oggetto (es. *"Parete nord del salotto a 1.2m"*, *"Soffitto centro cucina"*, *"Tavolino vicino al divano"*).\n`;
    md += `> 3. Compila **\`Funzionamento / Note:\`** indicando cosa deve fare quando interagisci (es. *"Click per accendere/spegnere"*, *"Mostra badge temperatura in tempo reale"*, *"Apri modal per scegliere sorgente/volume"*).\n`;
    md += `> 4. Quando hai finito, salva il file e dimmi di procedere: leggerò questo file e applicherò i collegamenti e i modelli 3D corrispondenti!\n\n`;
    md += `---\n\n`;

    md += `## 🟢 Entità Già Mappate nel 3D (Riferimento Attivo)\n\n`;
    for (const [entId, meshInfo] of Object.entries(ALREADY_MAPPED)) {
      const ent = entities[entId];
      const name = ent ? ent.attributes.friendly_name || entId : entId;
      const state = ent ? ent.state : 'sconosciuto';
      md += `* **\`${entId}\`** — *${name}* (Stato live: \`${state}\`)\n`;
      md += `  - **Oggetto 3D / Ruolo:** ${meshInfo}\n`;
      md += `  - **Azione:** \`GIA_MAPPATO\`\n\n`;
    }
    md += `---\n\n`;

    const domainTitles = {
      light: '💡 1. Luci (light.*)',
      switch: '🔌 2. Interruttori, Prese e Relè (switch.*)',
      media_player: '📺 3. Smart TV, Casse e Media Player (media_player.*)',
      camera: '📹 4. Telecamere di Sicurezza (camera.*)',
      cover: '🚪 5. Cancelli, Tende e Tapparelle (cover.*)',
      climate: '❄️ 6. Termostati e Climatizzazione (climate.*)',
      binary_sensor: '🚨 7. Sensori di Presenza, Movimento e Apertura (binary_sensor.*)',
      sensor: '📊 8. Sensori Ambientali, Consumi ed Energetici (sensor.*)',
      siren: '🔔 9. Sirene e Notificatori (siren.*)',
      button: '🔘 10. Pulsanti e Comandi Rapidi (button.*)',
      other: '⚙️ 11. Altri Dispositivi e Scene (select, number, scene, automation)',
    };

    for (const [domain, items] of Object.entries(categorized)) {
      if (items.length === 0) continue;
      const title = domainTitles[domain] || `Dispositivi (${domain})`;
      md += `## ${title} (${items.length} entità)\n\n`;

      for (const item of items) {
        const actionDefault = item.is_mapped ? 'GIA_MAPPATO' : 'ignora';
        const mappedBadge = item.is_mapped ? ' `[COLLEGATO]`' : '';

        md += `### \`${item.id}\`${mappedBadge}\n`;
        md += `- **Nome HA:** ${item.name}\n`;
        md += `- **Stato Live:** \`${item.state}\`${item.unit ? ' ' + item.unit : ''}${item.device_class ? ' (classe: ' + item.device_class + ')' : ''}\n`;
        md += `- **Azione:** \`${actionDefault}\` <!-- Scrivi "mappa" per includerlo nel 3D, oppure lascia "ignora" -->\n`;
        md += `- **Posizione 3D:** ${item.is_mapped ? item.mapped_to : ''}\n`;
        md += `- **Funzionamento / Note:** ${item.is_mapped ? 'Già funzionante' : ''}\n\n`;
      }

      md += `---\n\n`;
    }

    const outputPath = path.resolve('HA_DEVICES_MAPPING.md');
    fs.writeFileSync(outputPath, md, 'utf8');
    console.log(`[Mapping Generator] File generato con successo: ${outputPath}`);
    process.exit(0);
  });
}

run();

