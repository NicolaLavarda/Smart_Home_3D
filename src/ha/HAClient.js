import {
  createConnection,
  subscribeEntities,
  callService,
  createLongLivedTokenAuth,
} from 'home-assistant-js-websocket';

export class HAClient {
  constructor(options = {}) {
    this.url = options.url || import.meta.env.VITE_HA_URL || '';
    this.token = options.token || import.meta.env.VITE_HA_TOKEN || '';
    this.connection = null;
    this.isMockMode = false;
    this.subscribers = new Set();
    this.statusListeners = new Set();

    // Inizializza stato Mock reattivo (allineato con le entità reali di Home Assistant dell'utente)
    this.mockEntities = {
      'light.forno': {
        entity_id: 'light.forno',
        state: 'on',
        attributes: {
          friendly_name: 'Lampadario Tavolo (HA: Forno)',
          brightness: 220,
          rgb_color: [255, 230, 190],
        },
      },
      'light.bancone': {
        entity_id: 'light.bancone',
        state: 'on',
        attributes: {
          friendly_name: 'Luci Bancone',
          brightness: 190,
          rgb_color: [255, 240, 215],
        },
      },
      'light.portico': {
        entity_id: 'light.portico',
        state: 'on',
        attributes: {
          friendly_name: 'Luce Portico',
          brightness: 255,
          rgb_color: [255, 245, 225],
        },
      },
      'switch.switch_casa_interruttore_1': {
        entity_id: 'switch.switch_casa_interruttore_1',
        state: 'off',
        attributes: {
          friendly_name: 'Cancello Carraio',
        },
      },
      'camera.carraio_scorrevole': {
        entity_id: 'camera.carraio_scorrevole',
        state: 'idle',
        attributes: {
          friendly_name: 'Telecamera Carraio (Cancelli)',
          brand: 'Security AI 4K',
        },
      },
      'media_player.smart_tv_lg_oled_2': {
        entity_id: 'media_player.smart_tv_lg_oled_2',
        state: 'idle',
        attributes: {
          friendly_name: 'Smart TV LG OLED',
          media_title: 'Cinema 4K',
          app_name: 'Netflix',
          volume_level: 0.45,
          is_volume_muted: false,
        },
      },
    };
  }

  onStatusChange(fn) {
    this.statusListeners.add(fn);
  }

  notifyStatus(status, details = '') {
    this.statusListeners.forEach((fn) => fn(status, details));
  }

  async connect() {
    if (!this.token) {
      console.info('[HAClient] Nessun VITE_HA_TOKEN configurato in .env: avvio in MODALITÀ MOCK/DEMO.');
      this.initMockMode();
      return;
    }

    // Lista ordinata di candidate URL:
    // Su Windows Chrome/Edge la risoluzione mDNS (.local) spesso fallisce o va in timeout a causa del DNS-over-HTTPS.
    // Pertanto testiamo prima l'IP diretto verificato 192.168.86.24:8123 e poi l'URL fornito in .env.
    const rawCandidates = [
      'http://192.168.86.24:8123',
      this.url,
      'http://homeassistant.local:8123'
    ];

    const candidateUrls = [];
    for (const raw of rawCandidates) {
      if (!raw) continue;
      const clean = raw
        .replace(/^ws:\/\//i, 'http://')
        .replace(/^wss:\/\//i, 'https://')
        .replace(/\/api\/websocket\/?$/i, '')
        .replace(/\/+$/, '');
      if (!candidateUrls.includes(clean)) {
        candidateUrls.push(clean);
      }
    }

    for (const authUrl of candidateUrls) {
      try {
        this.notifyStatus('connecting', `Connessione a ${authUrl}...`);
        console.log(`[HAClient] Tentativo connessione WebSocket a: ${authUrl}`);

        const auth = createLongLivedTokenAuth(authUrl, this.token);
        const connectionPromise = createConnection({ auth });
        const timeoutPromise = new Promise((_, reject) =>
          setTimeout(() => reject(new Error(`Timeout connessione a ${authUrl}`)), 6000)
        );

        this.connection = await Promise.race([connectionPromise, timeoutPromise]);
        this.isMockMode = false;
        const hostDisplay = authUrl.replace(/^https?:\/\//, '');
        this.notifyStatus('online', `Live HA (${hostDisplay})`);
        console.log(`[HAClient] Connessione WebSocket HA riuscita con successo su ${authUrl}!`);

        subscribeEntities(this.connection, (entities) => {
          this.notifyEntities(entities);
        });
        return; // Connesso con successo
      } catch (err) {
        console.warn(`[HAClient] Tentativo su ${authUrl} fallito (${err.message}), provo endpoint successivo...`);
      }
    }

    console.warn('[HAClient] Tutti i tentativi WebSocket verso Home Assistant sono falliti. Fallback su Demo Mock.');
    this.initMockMode();
  }

  initMockMode() {
    this.isMockMode = true;
    this.notifyStatus('mock', 'Modalità Demo Offline (Mock HA)');
    setTimeout(() => {
      this.notifyEntities(this.mockEntities);
    }, 100);
  }

  subscribeEntities(callback) {
    this.subscribers.add(callback);
    if (this.isMockMode) {
      callback(this.mockEntities);
    }
    return () => this.subscribers.delete(callback);
  }

  notifyEntities(entities) {
    this.subscribers.forEach((cb) => {
      try {
        cb(entities);
      } catch (e) {
        console.error('[HAClient] Errore nel callback entità:', e);
      }
    });
  }

  async callService(domain, service, serviceData = {}) {
    console.log(`[HAClient] Call Service: ${domain}.${service}`, serviceData);

    if (this.isMockMode) {
      this.handleMockService(domain, service, serviceData);
      return;
    }

    if (this.connection) {
      try {
        await callService(this.connection, domain, service, serviceData);
      } catch (err) {
        console.error(`[HAClient] Errore chiamata servizio ${domain}.${service}:`, err);
      }
    }
  }

  handleMockService(domain, service, serviceData) {
    const entityId = serviceData.entity_id;
    if (!entityId || !this.mockEntities[entityId]) return;

    const ent = this.mockEntities[entityId];

    if (domain === 'light') {
      if (service === 'toggle') {
        ent.state = ent.state === 'on' ? 'off' : 'on';
      } else if (service === 'turn_on') {
        ent.state = 'on';
        if (serviceData.brightness !== undefined) ent.attributes.brightness = serviceData.brightness;
        if (serviceData.rgb_color) ent.attributes.rgb_color = serviceData.rgb_color;
      } else if (service === 'turn_off') {
        ent.state = 'off';
      }
    } else if (domain === 'cover' || domain === 'switch') {
      if (service === 'toggle') {
        ent.state = (ent.state === 'open' || ent.state === 'on') ? 'off' : 'on';
      } else if (service === 'turn_on' || service === 'open_cover') {
        ent.state = 'on';
      } else if (service === 'turn_off' || service === 'close_cover') {
        ent.state = 'off';
      }
    } else if (domain === 'media_player') {
      if (service === 'toggle' || service === 'media_play_pause') {
        ent.state = ent.state === 'playing' ? 'paused' : 'playing';
      } else if (service === 'turn_off') {
        ent.state = 'off';
      } else if (service === 'turn_on') {
        ent.state = 'playing';
      } else if (service === 'volume_set' && serviceData.volume_level !== undefined) {
        ent.attributes.volume_level = serviceData.volume_level;
      }
    }

    this.notifyEntities({ ...this.mockEntities });
  }

  getEntity(entityId) {
    return this.mockEntities[entityId] || null;
  }
}
