import {
  createConnection,
  subscribeEntities,
  callService,
  createLongLivedTokenAuth,
} from 'home-assistant-js-websocket';

export class HAClient {
  constructor(options = {}) {
    this.tailscaleUrl = options.tailscaleUrl || import.meta.env.VITE_HA_TAILSCALE_URL || import.meta.env.VITE_HA_REMOTE_URL || '';
    this.localUrl = options.localUrl || import.meta.env.VITE_HA_LOCAL_URL || '';
    this.url = options.url || import.meta.env.VITE_HA_URL || this.tailscaleUrl || this.localUrl || '';
    this.token = options.token || import.meta.env.VITE_HA_TOKEN || '';
    this.connection = null;
    this.activeUrl = '';
    this.isTailscale = false;
    this.isMockMode = false;
    this.subscribers = new Set();
    this.statusListeners = new Set();
    this.mqttSubscribers = new Map(); // topic -> Set<callback>
    this.entities = {}; // Cache delle entità in tempo reale ricevute da Home Assistant WebSocket

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
          friendly_name: 'Luci Portico (2 Applique)',
          brightness: 255,
          rgb_color: [255, 245, 225],
        },
      },
      'light.smart_plug_in_unit_switch_3': {
        entity_id: 'light.smart_plug_in_unit_switch_3',
        state: 'on',
        attributes: {
          friendly_name: 'Faretti Soffitto Salotto (6 Faretti)',
          brightness: 255,
          rgb_color: [255, 248, 230],
        },
      },
      'light.luci_esterne': {
        entity_id: 'light.luci_esterne',
        state: 'on',
        attributes: {
          friendly_name: 'Luci Esterne (4 Lampioncini + 4 Muro)',
          brightness: 255,
          rgb_color: [255, 240, 200],
        },
      },
      'light.1': {
        entity_id: 'light.1',
        state: 'off',
        attributes: {
          friendly_name: 'Applique Salotto Est',
          brightness: 200,
          rgb_color: [255, 235, 210],
        },
      },
      'light.2': {
        entity_id: 'light.2',
        state: 'off',
        attributes: {
          friendly_name: 'Applique Salotto Nord',
          brightness: 200,
          rgb_color: [255, 235, 210],
        },
      },
      'switch.switch_casa_interruttore_1': {
        entity_id: 'switch.switch_casa_interruttore_1',
        state: 'off',
        attributes: {
          friendly_name: 'Cancello Carraio',
        },
      },
      'switch.switch_casa_interruttore_2': {
        entity_id: 'switch.switch_casa_interruttore_2',
        state: 'off',
        attributes: {
          friendly_name: 'Serratura Cancelletto Pedonale',
        },
      },
      'switch.switch_casa_interruttore_3': {
        entity_id: 'switch.switch_casa_interruttore_3',
        state: 'off',
        attributes: {
          friendly_name: 'Serranda Garage',
        },
      },
      'switch.smart_switch_caldaia': {
        entity_id: 'switch.smart_switch_caldaia',
        state: 'on',
        attributes: {
          friendly_name: 'Interruttore Caldaia',
        },
      },
      // Impianto Irrigazione Smart Giardino (3 Aree, 11 Gettini pop-up)
      'switch.smart_switch_area1': {
        entity_id: 'switch.smart_switch_area1',
        state: 'off',
        attributes: {
          friendly_name: 'Irrigazione Area 1 (Prato Sud)',
          device_class: 'switch',
          icon: 'mdi:sprinkler',
        },
      },
      'switch.smart_switch_area2': {
        entity_id: 'switch.smart_switch_area2',
        state: 'off',
        attributes: {
          friendly_name: 'Irrigazione Area 2 (Corte Est)',
          device_class: 'switch',
          icon: 'mdi:sprinkler',
        },
      },
      'switch.smart_switch_area3': {
        entity_id: 'switch.smart_switch_area3',
        state: 'off',
        attributes: {
          friendly_name: 'Irrigazione Area 3 (Prato Nord & Viale)',
          device_class: 'switch',
          icon: 'mdi:sprinkler',
        },
      },
      // Entità card di controllo irrigazione (Home Assistant)
      'input_boolean.irrigazione_attiva': {
        entity_id: 'input_boolean.irrigazione_attiva',
        state: 'off',
        attributes: {
          friendly_name: 'Irrigazione Attiva',
          icon: 'mdi:water',
        },
      },
      'input_boolean.area_1': {
        entity_id: 'input_boolean.area_1',
        state: 'on',
        attributes: {
          friendly_name: 'Abilita Area 1',
          icon: 'mdi:valve',
        },
      },
      'input_number.tempo_area_1': {
        entity_id: 'input_number.tempo_area_1',
        state: '10',
        attributes: {
          friendly_name: 'Tempo Area 1',
          unit_of_measurement: 'min',
          min: 1,
          max: 120,
          step: 1,
        },
      },
      'input_boolean.area_2': {
        entity_id: 'input_boolean.area_2',
        state: 'on',
        attributes: {
          friendly_name: 'Abilita Area 2',
          icon: 'mdi:valve',
        },
      },
      'input_number.tempo_area_2': {
        entity_id: 'input_number.tempo_area_2',
        state: '5',
        attributes: {
          friendly_name: 'Tempo Area 2',
          unit_of_measurement: 'min',
          min: 1,
          max: 120,
          step: 1,
        },
      },
      'input_boolean.area_3': {
        entity_id: 'input_boolean.area_3',
        state: 'on',
        attributes: {
          friendly_name: 'Abilita Area 3',
          icon: 'mdi:valve',
        },
      },
      'input_number.tempo_area_3': {
        entity_id: 'input_number.tempo_area_3',
        state: '15',
        attributes: {
          friendly_name: 'Tempo Area 3',
          unit_of_measurement: 'min',
          min: 1,
          max: 120,
          step: 1,
        },
      },
      'sensor.temperatura_accumulo_alto': {
        entity_id: 'sensor.temperatura_accumulo_alto',
        state: '57.9',
        attributes: {
          friendly_name: 'Temp. Accumulo Alto',
          unit_of_measurement: '°C',
          device_class: 'temperature',
        },
      },
      'sensor.temperatura_accumulo_basso': {
        entity_id: 'sensor.temperatura_accumulo_basso',
        state: '14.2',
        attributes: {
          friendly_name: 'Temp. Accumulo Basso',
          unit_of_measurement: '°C',
          device_class: 'temperature',
        },
      },
      'sensor.temperatura_caldaia': {
        entity_id: 'sensor.temperatura_caldaia',
        state: '43.8',
        attributes: {
          friendly_name: 'Temp. Caldaia',
          unit_of_measurement: '°C',
          device_class: 'temperature',
        },
      },
      'sensor.variazione_temperatura_caldaia': {
        entity_id: 'sensor.variazione_temperatura_caldaia',
        state: '43.8',
        attributes: {
          friendly_name: 'Temp. Caldaia',
          unit_of_measurement: '°C',
          device_class: 'temperature',
        },
      },
      // Lavastoviglie Smart
      'sensor.lavastoviglie_stato_di_funzionamento': {
        entity_id: 'sensor.lavastoviglie_stato_di_funzionamento',
        state: 'In funzione',
        attributes: {
          friendly_name: 'Lavastoviglie Cucina',
        },
      },
      'switch.lavastoviglie_potenza': {
        entity_id: 'switch.lavastoviglie_potenza',
        state: 'on',
        attributes: { friendly_name: 'Alimentazione Lavastoviglie' },
      },
      'select.lavastoviglie_programma_selezionato': {
        entity_id: 'select.lavastoviglie_programma_selezionato',
        state: 'Dishcare.Dishwasher.Program.Auto2',
        attributes: {
          friendly_name: 'Programma Selezionato',
          options: [
            'Dishcare.Dishwasher.Program.Auto2',
            'Dishcare.Dishwasher.Program.Eco50',
            'Dishcare.Dishwasher.Program.Intensiv70',
            'Dishcare.Dishwasher.Program.Quick65',
            'Dishcare.Dishwasher.Program.NightWash',
            'Dishcare.Dishwasher.Program.Glass40',
          ],
        },
      },
      'sensor.lavastoviglie_orario_di_fine_del_programma': {
        entity_id: 'sensor.lavastoviglie_orario_di_fine_del_programma',
        state: new Date(Date.now() + 42 * 60000).toISOString(),
        attributes: { friendly_name: 'Fine Programma' },
      },
      'sensor.lavastoviglie_avanzamento_del_programma': {
        entity_id: 'sensor.lavastoviglie_avanzamento_del_programma',
        state: '64',
        attributes: { friendly_name: 'Avanzamento Programma', unit_of_measurement: '%' },
      },
      'switch.lavastoviglie_extra_dry': {
        entity_id: 'switch.lavastoviglie_extra_dry',
        state: 'on',
        attributes: { friendly_name: 'Asciugatura Extra' },
      },
      'switch.lavastoviglie_half_load': {
        entity_id: 'switch.lavastoviglie_half_load',
        state: 'off',
        attributes: { friendly_name: 'Mezzo Carico' },
      },
      'switch.lavastoviglie_hygiene': {
        entity_id: 'switch.lavastoviglie_hygiene',
        state: 'on',
        attributes: { friendly_name: 'Igiene+' },
      },
      'switch.lavastoviglie_vario_speed': {
        entity_id: 'switch.lavastoviglie_vario_speed',
        state: 'on',
        attributes: { friendly_name: 'Velocità+' },
      },
      'switch.lavastoviglie_silence_on_demand': {
        entity_id: 'switch.lavastoviglie_silence_on_demand',
        state: 'off',
        attributes: { friendly_name: 'Silence on Demand' },
      },
      'sensor.lavastoviglie_sale_quasi_vuoto': {
        entity_id: 'sensor.lavastoviglie_sale_quasi_vuoto',
        state: 'off',
        attributes: { friendly_name: 'Livello Sale' },
      },
      'sensor.lavastoviglie_brillantante_quasi_vuoto': {
        entity_id: 'sensor.lavastoviglie_brillantante_quasi_vuoto',
        state: 'off',
        attributes: { friendly_name: 'Livello Brillantante' },
      },
      'sensor.lavastoviglie_porta': {
        entity_id: 'sensor.lavastoviglie_porta',
        state: 'off',
        attributes: { friendly_name: 'Sportello Lavastoviglie' },
      },
      'button.lavastoviglie_stop_program': {
        entity_id: 'button.lavastoviglie_stop_program',
        state: 'idle',
        attributes: { friendly_name: 'Arresta Programma' },
      },
      'camera.carraio_scorrevole': {
        entity_id: 'camera.carraio_scorrevole',
        state: 'idle',
        attributes: {
          friendly_name: 'Telecamera Carraio (Cancelli)',
          brand: 'Security AI 4K',
        },
      },
      'camera.carraio_trasparente': {
        entity_id: 'camera.carraio_trasparente',
        state: 'idle',
        attributes: {
          friendly_name: 'Telecamera Carraio (Trasparente)',
          brand: 'Security AI 4K',
        },
      },
      'button.wake_on_lan_58_fd_b1_ae_99_79': {
        entity_id: 'button.wake_on_lan_58_fd_b1_ae_99_79',
        state: '2026-11-11T12:00:00Z',
        attributes: {
          friendly_name: 'Wake on LAN TV',
        },
      },
      'media_player.lg_webos_smart_tv': {
        entity_id: 'media_player.lg_webos_smart_tv',
        state: 'off',
        attributes: {
          friendly_name: 'LG webOS Smart TV',
          device_class: 'tv',
          source: 'Live TV',
          media_title: 'TV Spenta',
          app_name: 'Live TV',
          volume_level: 0.45,
          is_volume_muted: false,
          source_list: [
            'Allarme Sport', 'Amazon Alexa', 'Apple TV', 'Art Gallery', 'Browser Web',
            'Disney+', 'Facebook Watch', 'Foto e video', 'HDMI 1', 'HDMI 2', 'HDMI 3', 'HDMI 4',
            'Home Dashboard', 'LG Channels', 'LG Content Store', 'Live TV', 'Mediaset Infinity',
            'Musica', 'NOW', 'Netflix', 'Plex', 'Pluto TV', 'Prime Video', 'RaiPlay',
            'Rakuten TV', 'Smart STB', 'Spotify - Musica e podcast', 'TIMVISION', 'YouTube'
          ],
        },
      },
      'media_player.smart_tv_lg_oled_2': {
        entity_id: 'media_player.smart_tv_lg_oled_2',
        state: 'off',
        attributes: {
          friendly_name: 'Smart TV LG OLED',
          device_class: 'tv',
          media_title: 'TV Spenta',
          app_name: 'Live TV',
          source: 'Live TV',
          volume_level: 0.45,
          is_volume_muted: false,
        },
      },
      // Robot Aspirapolvere Ecovacs Deebot
      'vacuum.deebot': {
        entity_id: 'vacuum.deebot',
        state: 'docked',
        attributes: {
          friendly_name: 'Deebot',
          battery_level: 100,
          fan_speed: 'normal',
          fan_speed_list: ['quiet', 'normal', 'max', 'max_plus'],
          rooms: {
            cucina1: 0,
            living_room: 1,
            guardaroba1: 3,
            bagno1: 4,
          },
          supported_features: 29500,
        },
      },
      'sensor.deebot_batteria': {
        entity_id: 'sensor.deebot_batteria',
        state: '100',
        attributes: { unit_of_measurement: '%', device_class: 'battery', friendly_name: 'Deebot Batteria' },
      },
      'sensor.deebot_area_cleaned': {
        entity_id: 'sensor.deebot_area_cleaned',
        state: '69',
        attributes: { unit_of_measurement: 'm²', device_class: 'area', friendly_name: 'Deebot Area pulita' },
      },
      'sensor.deebot_cleaning_duration': {
        entity_id: 'sensor.deebot_cleaning_duration',
        state: '54.0',
        attributes: { unit_of_measurement: 'min', device_class: 'duration', friendly_name: 'Deebot Durata pulizia' },
      },
      'sensor.deebot_total_area_cleaned': {
        entity_id: 'sensor.deebot_total_area_cleaned',
        state: '20088',
        attributes: { unit_of_measurement: 'm²', device_class: 'area', friendly_name: 'Deebot Area totale pulita' },
      },
      'sensor.deebot_total_cleaning_duration': {
        entity_id: 'sensor.deebot_total_cleaning_duration',
        state: '363.7',
        attributes: { unit_of_measurement: 'h', device_class: 'duration', friendly_name: 'Deebot Total cleaning duration' },
      },
      'sensor.deebot_total_cleanings': {
        entity_id: 'sensor.deebot_total_cleanings',
        state: '516',
        attributes: { friendly_name: 'Deebot Pulizie totali' },
      },
      'select.deebot_water_flow_level': {
        entity_id: 'select.deebot_water_flow_level',
        state: 'medium',
        attributes: { options: ['low', 'medium', 'high'], friendly_name: 'Deebot Water flow level' },
      },
      'select.deebot_active_map': {
        entity_id: 'select.deebot_active_map',
        state: 'Piano terra',
        attributes: { options: ['Piano terra', 'Primo piano'], friendly_name: 'Deebot Active map' },
      },
      'switch.deebot_advanced_mode': {
        entity_id: 'switch.deebot_advanced_mode',
        state: 'on',
        attributes: { friendly_name: 'Deebot Modalità avanzata' },
      },
      'switch.deebot_carpet_auto_boost_suction': {
        entity_id: 'switch.deebot_carpet_auto_boost_suction',
        state: 'on',
        attributes: { friendly_name: 'Deebot Aspirazione automatica potenziata del tappeto' },
      },
      'binary_sensor.deebot_mop_attached': {
        entity_id: 'binary_sensor.deebot_mop_attached',
        state: 'off',
        attributes: { friendly_name: 'Deebot Mocio montato' },
      },
      'button.deebot_relocate': {
        entity_id: 'button.deebot_relocate',
        state: 'unknown',
        attributes: { friendly_name: 'Deebot Trasferire' },
      },
      'sensor.deebot_main_brush_lifespan': {
        entity_id: 'sensor.deebot_main_brush_lifespan',
        state: '56.7',
        attributes: { unit_of_measurement: '%', friendly_name: 'Deebot Durata spazzola principale' },
      },
      'sensor.deebot_filter_lifespan': {
        entity_id: 'sensor.deebot_filter_lifespan',
        state: '96.5',
        attributes: { unit_of_measurement: '%', friendly_name: 'Deebot Durata filtro' },
      },
      'sensor.deebot_round_mop_lifespan': {
        entity_id: 'sensor.deebot_round_mop_lifespan',
        state: '99.9',
        attributes: { unit_of_measurement: '%', friendly_name: 'Deebot Durata del mocio rotondo' },
      },
      'sensor.deebot_side_brush_lifespan': {
        entity_id: 'sensor.deebot_side_brush_lifespan',
        state: '97.1',
        attributes: { unit_of_measurement: '%', friendly_name: 'Deebot Durata spazzola laterale' },
      },
      'sensor.deebot_unit_care_lifespan': {
        entity_id: 'sensor.deebot_unit_care_lifespan',
        state: '85.9',
        attributes: { unit_of_measurement: '%', friendly_name: 'Deebot Unit care lifespan' },
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

    // Lista ordinata di candidati URL (Zero IP privati cablati nel codice!):
    // 1. Tailscale / VPN da .env (prioritario: consente l'accesso continuo ovunque ti trovi)
    // 2. URL principale / LAN da .env (VITE_HA_LOCAL_URL o VITE_HA_URL)
    // 3. Fallback mDNS standard 'http://homeassistant.local:8123'
    const rawCandidates = [
      this.tailscaleUrl,
      this.localUrl,
      this.url,
      'http://homeassistant.local:8123',
    ];

    const candidateUrls = [];
    for (const raw of rawCandidates) {
      if (!raw || typeof raw !== 'string' || !raw.trim()) continue;
      const clean = raw
        .trim()
        .replace(/^ws:\/\//i, 'http://')
        .replace(/^wss:\/\//i, 'https://')
        .replace(/\/api\/websocket\/?$/i, '')
        .replace(/\/+$/, '');
      if (clean && !candidateUrls.includes(clean)) {
        candidateUrls.push(clean);
      }
    }

    for (const authUrl of candidateUrls) {
      try {
        const isTailscale = authUrl.includes('100.') || authUrl.includes('.ts.net') || authUrl === this.tailscaleUrl;
        const tag = isTailscale ? 'Tailscale' : 'LAN/Locale';
        this.notifyStatus('connecting', `Connessione a ${authUrl} (${tag})...`);
        console.log(`[HAClient] Tentativo connessione WebSocket (${tag}) a: ${authUrl}`);

        const auth = createLongLivedTokenAuth(authUrl, this.token);
        const connectionPromise = createConnection({ auth });
        const timeoutPromise = new Promise((_, reject) =>
          setTimeout(() => reject(new Error(`Timeout connessione a ${authUrl} (${tag})`)), 4500)
        );

        this.connection = await Promise.race([connectionPromise, timeoutPromise]);
        this.isMockMode = false;
        this.activeUrl = authUrl;
        this.url = authUrl;
        this.isTailscale = isTailscale;
        const hostDisplay = authUrl.replace(/^https?:\/\//, '');
        this.notifyStatus('online', `Live HA (${tag}: ${hostDisplay})`);
        console.log(`[HAClient] Connessione WebSocket HA riuscita con successo tramite ${tag} (${authUrl})!`);

        subscribeEntities(this.connection, (entities) => {
          this.notifyEntities(entities);
        });

        // Sottoscrivi eventuali topic MQTT registrati dai controller
        if (this.mqttSubscribers && this.mqttSubscribers.size > 0) {
          for (const [topic, cbs] of this.mqttSubscribers.entries()) {
            this.connection.subscribeMessage(
              (msg) => {
                let data = msg.payload ?? msg;
                if (typeof data === 'string') {
                  try { data = JSON.parse(data); } catch { }
                }
                cbs.forEach((cb) => cb(data, msg.topic || topic));
              },
              { type: 'mqtt/subscribe', topic }
            ).catch((err) => console.warn(`[HAClient] MQTT sub error for ${topic}:`, err.message));
          }
        }

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
    this.activeUrl = '';
    this.isTailscale = false;
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

  async subscribeMqtt(topic, callback) {
    if (!topic || typeof callback !== 'function') return () => { };

    if (!this.mqttSubscribers.has(topic)) {
      this.mqttSubscribers.set(topic, new Set());
    }
    this.mqttSubscribers.get(topic).add(callback);

    if (this.connection && !this.isMockMode) {
      try {
        const unsub = await this.connection.subscribeMessage(
          (msg) => {
            let data = msg.payload ?? msg;
            if (typeof data === 'string') {
              try { data = JSON.parse(data); } catch { }
            }
            callback(data, msg.topic || topic);
          },
          { type: 'mqtt/subscribe', topic }
        );
        return () => {
          this.mqttSubscribers.get(topic)?.delete(callback);
          if (typeof unsub === 'function') unsub();
        };
      } catch (err) {
        console.warn(`[HAClient] Sottoscrizione MQTT fallita per topic '${topic}':`, err.message);
      }
    }

    return () => {
      this.mqttSubscribers.get(topic)?.delete(callback);
    };
  }

  publishMockMqtt(topic, payload) {
    if (this.mqttSubscribers && this.mqttSubscribers.has(topic)) {
      this.mqttSubscribers.get(topic).forEach((cb) => {
        try {
          cb(payload, topic);
        } catch (e) {
          console.error('[HAClient] Errore nel callback MQTT mock:', e);
        }
      });
    }
  }

  notifyEntities(entities) {
    this.entities = entities || {};
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
    const tv = this.mockEntities['media_player.lg_webos_smart_tv'] || this.mockEntities['media_player.smart_tv_lg_oled_2'];

    // 1. Accensione via Wake-on-LAN
    if (domain === 'button' && service === 'press') {
      if (entityId === 'button.wake_on_lan_58_fd_b1_ae_99_79' || entityId?.includes('wake_on_lan')) {
        console.log('[Mock HA] ⚡ Eseguito Wake-on-LAN: Accensione TV completata!');
        if (tv) tv.state = 'playing';
        if (this.mockEntities['media_player.smart_tv_lg_oled_2']) {
          this.mockEntities['media_player.smart_tv_lg_oled_2'].state = 'playing';
        }
        this.notifyEntities({ ...this.mockEntities });
        return;
      }
    }

    // 2. Comandi nativi WebOS (webostv.command e webostv.button)
    if (domain === 'webostv') {
      if (service === 'command') {
        const cmd = serviceData.command;
        const payload = serviceData.payload || {};
        console.log(`[Mock HA] Ricevuto webostv.command: '${cmd}'`, payload);

        if (cmd === 'system/turnOff') {
          if (tv) tv.state = 'off';
        } else if (cmd === 'system/turnOn') {
          if (tv) tv.state = 'playing';
        } else if (cmd === 'audio/volumeUp') {
          if (tv) tv.attributes.volume_level = Math.min(1.0, (tv.attributes.volume_level || 0) + 0.05);
        } else if (cmd === 'audio/volumeDown') {
          if (tv) tv.attributes.volume_level = Math.max(0.0, (tv.attributes.volume_level || 0) - 0.05);
        } else if (cmd === 'audio/setMute') {
          if (tv) tv.attributes.is_volume_muted = !tv.attributes.is_volume_muted;
        } else if (cmd === 'system.notifications/createToast') {
          console.log(`[Mock HA] 📺 [POPUP TOAST SU SCHERMO TV]: "${payload.message || 'Notifica webOS'}"`);
        } else if (cmd === 'system.launcher/open' || cmd === 'system.launcher/launch') {
          const target = payload.target || 'https://www.google.com';
          if (tv) {
            tv.state = 'playing';
            tv.attributes.source = 'Browser Web';
            tv.attributes.media_title = `Browser: ${target}`;
          }
        } else if (cmd === 'tv/channelUp') {
          if (tv) {
            tv.attributes.source = 'Live TV';
            tv.attributes.media_channel = 'Canale Successivo HD';
            tv.attributes.media_title = 'Programma Live DVB-T2';
          }
        } else if (cmd === 'tv/channelDown') {
          if (tv) {
            tv.attributes.source = 'Live TV';
            tv.attributes.media_channel = 'Canale Precedente HD';
            tv.attributes.media_title = 'Programma Live DVB-T2';
          }
        }
        this.notifyEntities({ ...this.mockEntities });
        return;
      } else if (service === 'button') {
        console.log(`[Mock HA] webostv.button premuto: '${serviceData.button}'`);
        return;
      }
    }

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
    } else if (domain === 'cover' || domain === 'switch' || domain === 'input_boolean') {
      if (service === 'toggle') {
        ent.state = (ent.state === 'open' || ent.state === 'on') ? 'off' : 'on';
      } else if (service === 'turn_on' || service === 'open_cover') {
        ent.state = 'on';
      } else if (service === 'turn_off' || service === 'close_cover') {
        ent.state = 'off';
      }

      // Logica automatica per il ciclo di irrigazione mock
      if (entityId === 'input_boolean.irrigazione_attiva') {
        const isCycleOn = ent.state === 'on';
        if (isCycleOn) {
          // Attiva le valvole fisiche per le aree abilitate
          if (this.mockEntities['input_boolean.area_1']?.state === 'on') {
            if (this.mockEntities['switch.smart_switch_area1']) this.mockEntities['switch.smart_switch_area1'].state = 'on';
          }
          if (this.mockEntities['input_boolean.area_2']?.state === 'on') {
            if (this.mockEntities['switch.smart_switch_area2']) this.mockEntities['switch.smart_switch_area2'].state = 'on';
          }
          if (this.mockEntities['input_boolean.area_3']?.state === 'on') {
            if (this.mockEntities['switch.smart_switch_area3']) this.mockEntities['switch.smart_switch_area3'].state = 'on';
          }
        } else {
          // Spegne tutte le valvole fisiche
          if (this.mockEntities['switch.smart_switch_area1']) this.mockEntities['switch.smart_switch_area1'].state = 'off';
          if (this.mockEntities['switch.smart_switch_area2']) this.mockEntities['switch.smart_switch_area2'].state = 'off';
          if (this.mockEntities['switch.smart_switch_area3']) this.mockEntities['switch.smart_switch_area3'].state = 'off';
        }
      }
    } else if (domain === 'input_number') {
      if (service === 'set_value' && serviceData.value !== undefined) {
        ent.state = String(serviceData.value);
      }
    } else if (domain === 'media_player') {
      if (service === 'toggle') {
        ent.state = ent.state === 'playing' ? 'off' : 'playing';
      } else if (service === 'media_play_pause') {
        ent.state = ent.state === 'playing' ? 'paused' : 'playing';
      } else if (service === 'media_stop') {
        ent.state = 'idle';
      } else if (service === 'turn_off') {
        ent.state = 'off';
      } else if (service === 'turn_on') {
        ent.state = 'playing';
      } else if (service === 'volume_set' && serviceData.volume_level !== undefined) {
        ent.attributes.volume_level = serviceData.volume_level;
      } else if (service === 'volume_up') {
        ent.attributes.volume_level = Math.min(1.0, (ent.attributes.volume_level || 0) + 0.05);
      } else if (service === 'volume_down') {
        ent.attributes.volume_level = Math.max(0.0, (ent.attributes.volume_level || 0) - 0.05);
      } else if (service === 'volume_mute') {
        ent.attributes.is_volume_muted = !ent.attributes.is_volume_muted;
      } else if (service === 'select_source' && serviceData.source) {
        ent.state = 'playing';
        ent.attributes.source = serviceData.source;
        ent.attributes.app_name = serviceData.source;

        // Titoli e descrizioni scenografiche realistiche in base all'app scelta
        const s = serviceData.source.toLowerCase();
        if (s.includes('netflix')) {
          ent.attributes.media_title = '...';
          ent.attributes.media_channel = 'Netflix Original';
        } else if (s.includes('prime')) {
          ent.attributes.media_title = 'Il Signore degli Anelli: Gli Anelli del Potere';
          ent.attributes.media_channel = 'Amazon MGM Studios';
        } else if (s.includes('youtube')) {
          ent.attributes.media_title = '3D Digital Twin Smart Home Architecture';
          ent.attributes.media_channel = 'Google Deepmind Channel';
        } else if (s.includes('disney')) {
          ent.attributes.media_title = 'The Mandalorian (Stagione 3)';
          ent.attributes.media_channel = 'Lucasfilm 4K';
        } else if (s.includes('spotify') || s.includes('musica')) {
          ent.attributes.media_title = 'Italian Chill Lounge & Jazz';
          ent.attributes.media_channel = 'Spotify Hi-Fi Salotto';
        } else if (s.includes('raiplay')) {
          ent.attributes.media_title = 'RaiPlay On Demand - Doc';
          ent.attributes.media_channel = 'Rai Play';
        } else if (s.includes('browser')) {
          ent.attributes.media_title = 'Google Search & Web';
          ent.attributes.media_channel = 'Browser Web LG';
        } else if (s.includes('live') || s.includes('tv')) {
          ent.attributes.media_title = 'TG1 - Notiziario Principale HD';
          ent.attributes.media_channel = 'Rai 1 HD';
        }
      }
    } else if (domain === 'select') {
      if (service === 'select_option' && serviceData.option) {
        ent.state = serviceData.option;
      }
    } else if (domain === 'vacuum') {
      const vac = this.mockEntities['vacuum.deebot'];
      if (vac) {
        if (service === 'start' || service === 'turn_on') {
          vac.state = 'cleaning';
        } else if (service === 'pause') {
          vac.state = 'paused';
        } else if (service === 'stop') {
          vac.state = 'idle';
        } else if (service === 'return_to_base') {
          vac.state = 'returning';
        } else if (service === 'locate') {
          console.log('[Mock HA] 🔊 Deebot: Segnale sonoro di localizzazione inviato!');
        } else if (service === 'set_fan_speed' && serviceData.fan_speed) {
          vac.attributes.fan_speed = serviceData.fan_speed;
        }
      }
    } else if (domain === 'button') {
      if (service === 'press') {
        ent.state = new Date().toISOString();
        if (entityId === 'button.lavastoviglie_stop_program') {
          if (this.mockEntities['sensor.lavastoviglie_stato_di_funzionamento']) {
            this.mockEntities['sensor.lavastoviglie_stato_di_funzionamento'].state = 'Pronto';
          }
          if (this.mockEntities['sensor.lavastoviglie_avanzamento_del_programma']) {
            this.mockEntities['sensor.lavastoviglie_avanzamento_del_programma'].state = '0';
          }
        }
      }
    } else if (domain === 'script') {
      if (service === 'avvio_programma' || entityId === 'script.avvio_programma') {
        if (this.mockEntities['sensor.lavastoviglie_stato_di_funzionamento']) {
          this.mockEntities['sensor.lavastoviglie_stato_di_funzionamento'].state = 'In funzione';
        }
        if (this.mockEntities['switch.lavastoviglie_potenza']) {
          this.mockEntities['switch.lavastoviglie_potenza'].state = 'on';
        }
        if (this.mockEntities['sensor.lavastoviglie_avanzamento_del_programma']) {
          this.mockEntities['sensor.lavastoviglie_avanzamento_del_programma'].state = '15';
        }
      }
    }

    this.notifyEntities({ ...this.mockEntities });
  }

  setMockEntityState(entityId, state, attributes = {}) {
    if (this.mockEntities && this.mockEntities[entityId]) {
      this.mockEntities[entityId].state = state;
      if (attributes && Object.keys(attributes).length > 0) {
        this.mockEntities[entityId].attributes = {
          ...this.mockEntities[entityId].attributes,
          ...attributes,
        };
      }
      this.notifyEntities({ ...this.mockEntities });
    }
  }

  getActiveUrl() {
    return this.activeUrl || this.tailscaleUrl || this.localUrl || this.url || '';
  }

  resolveCameraEntityId(preferredId = 'camera.carraio_scorrevole') {
    const entities = this.entities || {};
    if (preferredId && entities[preferredId]) {
      return preferredId;
    }

    const cameraIds = Object.keys(entities).filter((id) => id.startsWith('camera.'));
    if (cameraIds.length === 0) {
      return preferredId;
    }

    const keywords = ['carraio', 'cancello', 'reolink', 'rlc', 'ingresso', 'estern'];
    const matched = cameraIds.find((id) => {
      const lowerId = id.toLowerCase();
      const friendly = String(entities[id]?.attributes?.friendly_name || '').toLowerCase();
      return keywords.some((kw) => lowerId.includes(kw) || friendly.includes(kw));
    });

    return matched || cameraIds[0];
  }

  getEntity(entityId) {
    if (this.entities && this.entities[entityId]) {
      return this.entities[entityId];
    }
    if (this.isMockMode && this.mockEntities[entityId]) {
      return this.mockEntities[entityId];
    }
    return this.entities?.[entityId] || this.mockEntities?.[entityId] || null;
  }
}
