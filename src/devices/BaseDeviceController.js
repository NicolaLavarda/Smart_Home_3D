/**
 * BaseDeviceController
 * 
 * Classe base astratta per tutti i controller decentralizzati di dispositivi smart
 * (Smart TV, Lavastoviglie, Telecamere, Robot Aspirapolvere, ecc.).
 * Fornisce il ciclo di vita unificato:
 * - Matching delle entità HA associate
 * - Binding e gestione grafica 3D nella scena Three.js
 * - Render del pannello modale di controllo e interazione
 * - Aggiornamento continuo nel render loop (onTick)
 */
export class BaseDeviceController {
  constructor(id, options = {}) {
    // Supporta sia constructor('tv', { ... }) che constructor({ id: 'tv', ... })
    if (typeof id === 'object' && id !== null) {
      options = id;
      id = options.id;
    }
    this.id = id;
    this.name = options.name || id;
    this.primaryEntityId = options.primaryEntityId || null;
    this.associatedEntityIds = new Set(options.associatedEntityIds || options.monitoredEntities || []);
    if (this.primaryEntityId) {
      this.associatedEntityIds.add(this.primaryEntityId);
    }
    this.haClient = options.haClient || null;
    this.latestEntities = {};
    this.latestStateObj = null;
  }

  setHAClient(haClient) {
    this.haClient = haClient;
  }

  /**
   * Restituisce l'entità HA per un entity_id dato (o per la primaryEntityId di default)
   */
  getEntity(entityId = null) {
    const id = entityId || this.primaryEntityId;
    if (!id) return null;

    if (id === this.primaryEntityId && this.latestStateObj) {
      return this.latestStateObj;
    }

    if (this.latestEntities && this.latestEntities[id]) {
      return this.latestEntities[id];
    }

    if (this.haClient && typeof this.haClient.getEntity === 'function') {
      const ent = this.haClient.getEntity(id);
      if (ent) return ent;
    }

    return null;
  }

  /**
   * Verifica se un entity_id di Home Assistant appartiene a questo dispositivo
   */
  matchesEntity(entityId) {
    if (!entityId) return false;
    return this.primaryEntityId === entityId || this.associatedEntityIds.has(entityId);
  }

  /**
   * Restituisce tutti gli entity_id monitorati da questo controller
   */
  getMonitoredEntityIds() {
    return Array.from(this.associatedEntityIds);
  }

  /**
   * Inizializza nodi 3D, materiali, texture dinamiche o animazioni
   * @param {Array<THREE.Mesh>} meshes - Mesh 3D associate da Blender
   * @param {THREE.Scene} scene - Scena Three.js principale
   * @param {Object} context - Oggetti di sistema (haClient, entityBinder, assetLoader)
   */
  bind3D(meshes, scene, context) {
    if (context && context.haClient) {
      this.haClient = context.haClient;
    }
  }

  /**
   * Aggiorna lo stato 3D del dispositivo (es. schermo TV, sportello aperto, luci led)
   * @param {Object} stateObj - Stato HA dell'entità primaria
   * @param {Object} allEntities - Mappa completa di tutte le entità HA
   */
  update3D(stateObj, allEntities) {
    this.latestStateObj = stateObj;
    if (allEntities) {
      this.latestEntities = allEntities;
    }
  }

  /**
   * Renderizza il contenuto del pannello modale quando l'utente clicca sul dispositivo
   * @param {HTMLElement} container - Contenitore DOM per i controlli
   * @param {Object} entity - Oggetto entità HA corrente
   * @param {Object} context - Contesto UI (haClient, cameraController, modal)
   */
  renderModal(container, entity, context) {
    // Override nelle sottoclassi
  }

  /**
   * Callback di chiusura modale
   */
  onModalClose() {
    // Override nelle sottoclassi se necessario
  }

  /**
   * Eseguito ad ogni frame nel render loop di Three.js
   * @param {number} delta - Delta time in secondi
   */
  onTick(delta) {
    // Override nelle sottoclassi se necessario
  }

  /**
   * Pulizia risorse WebGL / texture / listener
   */
  dispose() {
    // Override nelle sottoclassi se necessario
  }
}
