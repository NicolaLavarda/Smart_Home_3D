/**
 * IRecordingProvider
 *
 * Interfaccia astratta (Strategy Pattern) per qualsiasi backend di registrazione video:
 * - Opzione A: Hard Disk dedicato alla videosorveglianza collegato al PC (SpatialServerNvrProvider / Frigate / go2rtc VOD)
 * - Opzione B: SSD / MicroSD a bordo di ciascuna telecamera (EdgeCameraSdProvider via HA Media Source / Reolink API)
 *
 * Implementando questa interfaccia, l'intera UI di Sicurezza e il Replay sincronizzato 3D
 * funzionano senza modifiche indipendentemente dall'hardware di archiviazione scelto.
 */
export class IRecordingProvider {
  constructor(name, options = {}) {
    if (new.target === IRecordingProvider) {
      throw new TypeError('IRecordingProvider è una classe astratta e non può essere istanziata direttamente.');
    }
    this.name = name || new.target.name;
    this.storageType = options.storageType || 'unknown';
    this.options = options;
  }

  /**
   * Restituisce metadati di stato e disponibilità dello storage di registrazione.
   * @returns {Promise<{configured: boolean, online: boolean, storageType: string, cameras?: string[], detail?: string}>}
   */
  async getHealthStatus() {
    return {
      configured: false,
      online: false,
      storageType: this.storageType,
      detail: 'Provider non configurato',
    };
  }

  /**
   * Interroga i segmenti video registrati per una telecamera nell'intervallo [startUnix, endUnix].
   * @param {string} _cameraId
   * @param {number} _startUnix
   * @param {number} _endUnix
   * @returns {Promise<Array<import('./RecordingModels.js').RecordingSegment>>}
   */
  async querySegments(_cameraId, _startUnix, _endUnix) {
    throw new Error(`${this.name}.querySegments() non implementato`);
  }

  /**
   * Risolve il sorgente video e l'offset esatto (in secondi) per riprodurre la telecamera al timestamp richiesto.
   * @param {string} _cameraId
   * @param {number} _timestampUnix
   * @returns {Promise<import('./RecordingModels.js').PlaybackResolution>}
   */
  async resolvePlayback(_cameraId, _timestampUnix) {
    throw new Error(`${this.name}.resolvePlayback() non implementato`);
  }

  /**
   * Collega (o esegue il seek su) un elemento <video> HTML5 alla registrazione corrispondente a timestampUnix.
   * @param {string} _cameraId
   * @param {HTMLVideoElement} _videoElement
   * @param {number} _timestampUnix
   * @param {{autoplay?: boolean, playbackRate?: number}} [_opts]
   * @returns {Promise<import('./RecordingModels.js').PlaybackResolution>}
   */
  async attachHistoricalVideo(_cameraId, _videoElement, _timestampUnix, _opts = {}) {
    throw new Error(`${this.name}.attachHistoricalVideo() non implementato`);
  }

  /**
   * Imposta la velocità di riproduzione storica (1x, 2x, 5x).
   */
  setPlaybackRate(videoElement, rate = 1.0) {
    if (!videoElement) return;
    const safeRate = Math.max(0.25, Math.min(8.0, Number(rate) || 1.0));
    try {
      videoElement.playbackRate = safeRate;
    } catch {}
  }

  /**
   * Mette in pausa o riprende la riproduzione sul tag <video>.
   */
  setPaused(videoElement, paused) {
    if (!videoElement) return;
    try {
      if (paused) {
        videoElement.pause();
      } else if (videoElement.src || videoElement.srcObject) {
        videoElement.play().catch(() => {});
      }
    } catch {}
  }

  /**
   * Rilascia in modo pulito il media associato al tag <video>.
   */
  detach(videoElement) {
    if (!videoElement) return;
    try {
      videoElement.pause();
      videoElement.removeAttribute('src');
      if (videoElement.srcObject) {
        videoElement.srcObject = null;
      }
      if (typeof videoElement.load === 'function') {
        videoElement.load();
      }
    } catch {}
  }
}
