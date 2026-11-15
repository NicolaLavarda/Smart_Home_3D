/**
 * IVideoStreamProvider
 *
 * Contratto base OOP (Strategy Pattern) per i provider di streaming video live.
 * Ogni implementazione deve fornire un flusso riproducibile su un elemento HTMLVideoElement,
 * utilizzabile sia nei modali DOM sia come sorgente per THREE.VideoTexture.
 */
export class IVideoStreamProvider {
  constructor(streamName, options = {}) {
    if (new.target === IVideoStreamProvider) {
      throw new TypeError('IVideoStreamProvider è una classe astratta e non può essere istanziata direttamente.');
    }
    this.streamName = streamName;
    this.options = options;
    this.videoElement = null;
    this.connected = false;
    this.mode = 'unknown';
    this.latencyMs = 0;
    this.lastError = null;
    this.statusListeners = new Set();
  }

  /**
   * Connette lo stream video all'elemento <video> fornito.
   * @param {HTMLVideoElement} videoElement
   * @returns {Promise<boolean>}
   */
  async connect(videoElement) {
    throw new Error('Metodo astratto connect(videoElement) non implementato.');
  }

  /**
   * Disconnette e rilascia tutte le risorse di rete/media.
   */
  disconnect() {
    throw new Error('Metodo astratto disconnect() non implementato.');
  }

  /**
   * Restituisce lo stato corrente del provider.
   * @returns {{ connected: boolean, mode: string, latencyMs: number, streamName: string, lastError: string|null }}
   */
  getStatus() {
    return {
      connected: this.connected,
      mode: this.mode,
      latencyMs: this.latencyMs,
      streamName: this.streamName,
      lastError: this.lastError,
    };
  }

  onStatusChange(listener) {
    if (typeof listener === 'function') {
      this.statusListeners.add(listener);
    }
    return () => this.statusListeners.delete(listener);
  }

  notifyStatus() {
    const status = this.getStatus();
    this.statusListeners.forEach((fn) => {
      try {
        fn(status);
      } catch (err) {
        console.warn('[IVideoStreamProvider] Errore listener stato:', err);
      }
    });
  }
}

