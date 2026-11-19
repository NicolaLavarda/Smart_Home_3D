import { registerSW } from 'virtual:pwa-register';

/**
 * PwaUpdatePrompt
 *
 * Gestisce la registrazione del Service Worker Workbox in modalità 'prompt'
 * e mostra un toast discreto in italiano ("Nuova versione disponibile — Aggiorna")
 * quando una nuova release della PWA è pronta per l'attivazione (skipWaiting).
 */
export class PwaUpdatePrompt {
  constructor(options = {}) {
    this.options = options;
    this.container = options.container || null;
    this.onUpdateCallback = typeof options.onUpdate === 'function' ? options.onUpdate : null;
    this.updateSW = null;
    this.el = null;
    this._registered = false;

    if (options.autoRegister !== false) {
      this.register();
    }
  }

  init() {
    return this.register();
  }

  mount() {
    return this.register();
  }

  register() {
    if (this._registered) return this.updateSW;
    this._registered = true;

    const hasSwSupport =
      typeof navigator !== 'undefined' &&
      'serviceWorker' in navigator &&
      Boolean(navigator.serviceWorker);

    if (!hasSwSupport && typeof globalThis.__SH3D_TEST_REGISTER_SW__ !== 'function') {
      return null;
    }

    try {
      const regFn =
        typeof registerSW === 'function'
          ? registerSW
          : typeof globalThis.__SH3D_TEST_REGISTER_SW__ === 'function'
            ? globalThis.__SH3D_TEST_REGISTER_SW__
            : null;

      if (!regFn) return null;

      this.updateSW = regFn({
        immediate: true,
        onNeedRefresh: () => {
          this.show();
        },
        onOfflineReady: () => {
          if (typeof this.options.onOfflineReady === 'function') {
            this.options.onOfflineReady();
          }
        },
      });
    } catch (err) {
      console.warn('[PwaUpdatePrompt] Registrazione Service Worker non disponibile:', err?.message || err);
      this.updateSW = null;
    }

    return this.updateSW;
  }

  _resolveHost() {
    if (this.container) return this.container;
    if (typeof document === 'undefined') return null;
    return document.querySelector('.ui-layer') || document.body;
  }

  show() {
    if (typeof document === 'undefined') return null;
    const host = this._resolveHost();
    if (!host) return null;

    let toast = document.getElementById('pwa-update-toast') || this.el;
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'pwa-update-toast';
      toast.className = 'pwa-update-toast glass';
      toast.setAttribute('role', 'alert');
      toast.setAttribute('aria-live', 'polite');
      toast.innerHTML = `
        <span class="sw-update-label">Nuova versione disponibile — Aggiorna</span>
        <div class="sw-update-actions">
          <button type="button" class="btn-pwa-update" id="btn-pwa-update">Aggiorna</button>
          <button type="button" class="btn-pwa-dismiss" id="btn-pwa-dismiss" aria-label="Chiudi">Più tardi</button>
        </div>
      `;

      const updateBtn = toast.querySelector('#btn-pwa-update');
      const dismissBtn = toast.querySelector('#btn-pwa-dismiss');

      updateBtn?.addEventListener('click', async () => {
        await this.confirmUpdate();
      });

      dismissBtn?.addEventListener('click', () => {
        this.hide();
      });

      host.appendChild(toast);
    } else if (!toast.parentNode) {
      host.appendChild(toast);
    }

    toast.hidden = false;
    toast.style.display = 'flex';
    this.el = toast;
    return toast;
  }

  async confirmUpdate() {
    try {
      if (typeof this.updateSW === 'function') {
        await this.updateSW(true);
      }
      if (this.onUpdateCallback) {
        await this.onUpdateCallback(true);
      }
    } catch (err) {
      console.warn('[PwaUpdatePrompt] Errore durante aggiornamento Service Worker:', err);
    } finally {
      this.hide();
    }
  }

  hide() {
    const toast = (typeof document !== 'undefined' && document.getElementById('pwa-update-toast')) || this.el;
    if (toast) {
      toast.hidden = true;
      toast.style.display = 'none';
      if (typeof toast.remove === 'function') {
        toast.remove();
      }
    }
    this.el = null;
  }
}

export function initPwaUpdatePrompt(options = {}) {
  return new PwaUpdatePrompt(options);
}

export default PwaUpdatePrompt;
