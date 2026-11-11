import { BaseDeviceController } from '../BaseDeviceController.js';
import { WEBOS_COMMANDS } from './webos_commands.js';
import { TVScreenRenderer } from './TVScreenRenderer.js';
import { TVModal } from './TVModal.js';

/**
 * TVController
 * 
 * Controller per LG webOS Smart TV e il relativo pulsante Wake-on-LAN.
 * Gestisce la logica di business, il display 3D dinamico e il telecomando.
 */
export class TVController extends BaseDeviceController {
  constructor(options = {}) {
    super('tv', {
      name: 'LG webOS Smart TV',
      primaryEntityId: options.primaryEntityId || 'media_player.lg_webos_smart_tv',
      associatedEntityIds: [
        'button.wake_on_lan_58_fd_b1_ae_99_79',
        'media_player.smart_tv_lg_oled_2',
        ...(options.associatedEntityIds || []),
      ],
    });

    this.wolEntityId = 'button.wake_on_lan_58_fd_b1_ae_99_79';
    this.haClient = options.haClient || null;
    this.latestStateObj = null; // Cache dell'ultimo stato reale ricevuto via WebSocket da HA
    this.screenRenderer = new TVScreenRenderer();
    this.modalView = new TVModal(this);
    this.tvMeshes = [];
    this.isScreenTurnedOffManually = false;
  }

  setHAClient(haClient) {
    this.haClient = haClient;
  }

  getEntity() {
    // 1. Priorità all'ultimo stato ricevuto in tempo reale da Home Assistant
    if (this.latestStateObj) {
      return this.latestStateObj;
    }

    if (!this.haClient) {
      return {
        entity_id: this.primaryEntityId,
        state: 'off',
        attributes: { friendly_name: this.name },
      };
    }

    // 2. Cerca nel client HA l'entità primaria reale o l'alias
    const liveEntity =
      this.haClient.getEntity(this.primaryEntityId) ||
      this.haClient.getEntity('media_player.smart_tv_lg_oled_2');

    if (liveEntity) {
      return liveEntity;
    }

    return {
      entity_id: this.primaryEntityId,
      state: 'off',
      attributes: { friendly_name: this.name },
    };
  }

  /**
   * Determina in modo rigoroso se la TV è accesa o spenta.
   * Su Home Assistant le LG webOS spente riportano 'off', 'unavailable' o 'standby'.
   */
  isPoweredOn() {
    const ent = this.getEntity();
    if (!ent || !ent.state) return false;
    const s = String(ent.state).toLowerCase().trim();

    // Stati considerati chiaramente spenta / disconnessa
    if (s === 'off' || s === 'unavailable' || s === 'standby' || s === 'unknown') {
      return false;
    }

    // Stati di effettiva accensione
    return s === 'playing' || s === 'on' || s === 'idle' || s === 'paused' || s === 'buffering';
  }

  /**
   * Accende la TV utilizzando il pulsante Wake-on-LAN
   */
  turnOn() {
    console.log(`[TVController] Accensione TV via Wake-on-LAN: ${this.wolEntityId}`);
    if (!this.haClient) return;

    // Chiama il servizio button.press sul pulsante WoL reale
    this.haClient.callService('button', 'press', {
      entity_id: this.wolEntityId,
    });

    // Per completezza/ridondanza invia anche il comando turn_on sul media_player
    this.haClient.callService('media_player', 'turn_on', {
      entity_id: this.primaryEntityId,
    });
  }

  /**
   * Spegne la TV tramite media_player.turn_off o comando nativo system/turnOff
   */
  turnOff() {
    console.log(`[TVController] Spegnimento TV: ${this.primaryEntityId}`);
    if (!this.haClient) return;

    this.haClient.callService('media_player', 'turn_off', {
      entity_id: this.primaryEntityId,
    });
  }

  togglePower() {
    if (this.isPoweredOn()) {
      this.turnOff();
    } else {
      this.turnOn();
    }
  }

  /**
   * Esegue un comando nativo webOS (tramite servizio webostv.command di Home Assistant)
   * { entity_id: "media_player.lg_webos_smart_tv", command: ..., payload: ... }
   */
  sendWebOSCommand(command, payload = {}) {
    console.log(`[TVController] webostv.command -> ${command}`, payload);
    if (!this.haClient) return;

    this.haClient.callService('webostv', 'command', {
      entity_id: this.primaryEntityId,
      command,
      payload,
    });
  }

  /**
   * Esegue un pulsante telecomando webOS (tramite webostv.button o comando compatibile)
   */
  sendButton(button) {
    console.log(`[TVController] webostv.button -> ${button}`);
    if (!this.haClient) return;

    this.haClient.callService('webostv', 'button', {
      entity_id: this.primaryEntityId,
      button,
    });
  }

  /**
   * Seleziona la sorgente o lancia un'app (Netflix, Live TV, Prime Video, ecc.)
   */
  selectSource(source) {
    console.log(`[TVController] Selezione sorgente: ${source}`);
    if (!this.haClient) return;

    this.haClient.callService('media_player', 'select_source', {
      entity_id: this.primaryEntityId,
      source,
    });
  }

  setVolume(volumeLevel) {
    if (!this.haClient) return;
    this.haClient.callService('media_player', 'volume_set', {
      entity_id: this.primaryEntityId,
      volume_level: Math.max(0, Math.min(1, volumeLevel)),
    });
  }

  volumeUp() {
    if (!this.haClient) return;
    this.haClient.callService('media_player', 'volume_up', {
      entity_id: this.primaryEntityId,
    });
  }

  volumeDown() {
    if (!this.haClient) return;
    this.haClient.callService('media_player', 'volume_down', {
      entity_id: this.primaryEntityId,
    });
  }

  toggleMute() {
    if (!this.haClient) return;
    const ent = this.getEntity();
    const isMuted = ent.attributes?.is_volume_muted || false;
    this.haClient.callService('media_player', 'volume_mute', {
      entity_id: this.primaryEntityId,
      is_volume_muted: !isMuted,
    });
  }

  channelUp() {
    this.sendWebOSCommand(WEBOS_COMMANDS.TV_CHANNEL_UP);
  }

  channelDown() {
    this.sendWebOSCommand(WEBOS_COMMANDS.TV_CHANNEL_DOWN);
  }

  sendKeyInput(key) {
    this.sendButton(key);
  }

  togglePlayPause() {
    if (!this.haClient) return;
    this.haClient.callService('media_player', 'media_play_pause', {
      entity_id: this.primaryEntityId,
    });
  }

  stopMedia() {
    if (!this.haClient) return;
    this.haClient.callService('media_player', 'media_stop', {
      entity_id: this.primaryEntityId,
    });
  }

  /**
   * Invia una notifica popup Toast sullo schermo della TV
   */
  showToast(message) {
    console.log(`[TVController] Invia notifica Toast TV: "${message}"`);
    this.sendWebOSCommand(WEBOS_COMMANDS.SHOW_MESSAGE, {
      message,
      iconData: null,
    });
  }

  /**
   * Apre una pagina web nel browser della TV (es. https://www.google.com)
   */
  openUrl(targetUrl) {
    console.log(`[TVController] Apertura browser web su TV: ${targetUrl}`);
    this.sendWebOSCommand(WEBOS_COMMANDS.OPEN, {
      target: targetUrl,
    });
  }

  /**
   * Spegne o accende solo il pannello OLED per risparmio energetico
   */
  toggleScreenDisplay() {
    this.isScreenTurnedOffManually = !this.isScreenTurnedOffManually;
    if (this.isScreenTurnedOffManually) {
      this.sendWebOSCommand(WEBOS_COMMANDS.TURN_OFF_SCREEN);
      this.screenRenderer.renderStandby();
    } else {
      this.sendWebOSCommand(WEBOS_COMMANDS.TURN_ON_SCREEN);
      this.screenRenderer.render();
    }
  }

  /**
   * Associa le mesh 3D del salotto
   */
  bind3D(meshes, scene, context) {
    this.tvMeshes = meshes || [];
    if (context && context.haClient) {
      this.haClient = context.haClient;
    }

    let screenMesh = this.tvMeshes.find((m) => m.name === 'TV_Salotto_Screen');
    if (!screenMesh) {
      for (const m of this.tvMeshes) {
        if (m.name && m.name.includes('Screen')) {
          screenMesh = m;
          break;
        }
        m.traverse((child) => {
          if (child.isMesh && child.name.includes('Screen')) {
            screenMesh = child;
          }
        });
        if (screenMesh) break;
      }
    }
    if (!screenMesh && scene) {
      scene.traverse((node) => {
        if (node.isMesh && (node.name === 'TV_Salotto_Screen' || (node.name.includes('TV') && node.name.includes('Screen')))) {
          screenMesh = node;
        }
      });
    }

    if (screenMesh) {
      console.log(`[TVController] Screen mesh trovata e associata: ${screenMesh.name}`);
      this.screenRenderer.attachToMesh(screenMesh);
    } else {
      console.warn('[TVController] ATTENZIONE: Screen mesh TV_Salotto_Screen non trovata nella scena!');
    }

    // Inizializza con lo stato corrente dell'entità
    const ent = this.getEntity();
    if (ent) {
      this.update3D(ent);
    }
  }

  /**
   * Aggiorna lo stato 3D e il modale se aperto
   */
  update3D(stateObj, allEntities) {
    if (!stateObj) return;
    // Ignora entità che non sono un media_player (es. pulsante Wake-on-LAN)
    if (stateObj.entity_id && !stateObj.entity_id.startsWith('media_player.')) {
      return;
    }
    this.latestStateObj = stateObj;
    this.screenRenderer.updateState(stateObj);
    this.modalView.updateLive();
  }

  /**
   * Renderizza il pannello modale quando l'utente clicca sulla TV
   */
  renderModal(container, entity, context) {
    if (context && context.haClient) {
      this.haClient = context.haClient;
    }
    this.modalView.render(container);
  }

  onTick(delta) {
    this.screenRenderer.onTick(delta);
  }

  dispose() {
    this.tvMeshes = [];
  }
}

