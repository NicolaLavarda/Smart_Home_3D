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
        onRegisteredSW: (_swUrl, registration) => {
          if (!registration || typeof registration.update !== 'function') return;
          this._registration = registration;
          // Controlla subito aggiornamenti al rientro in foreground della PWA
          if (typeof document !== 'undefined' && typeof document.addEventListener === 'function' && !this._visListenerAttached) {
            this._visListenerAttached = true;
            document.addEventListener('visibilitychange', () => {
              if (!document.hidden) {
                this._registration?.update?.().catch(() => {});
              }
            });
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
      toast.className = 'pwa-update-toast';
      toast.setAttribute('role', 'alertdialog');
      toast.setAttribute('aria-modal', 'true');
      toast.setAttribute('aria-live', 'assertive');
      toast.innerHTML = `
        <div class="sw-update-card">
          <div class="sw-update-icon" aria-hidden="true">
            <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path>
              <path d="M3 3v5h5"></path>
              <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"></path>
              <path d="M16 16h5v5"></path>
            </svg>
          </div>
          <h2 class="sw-update-label">Nuova versione disponibile</h2>
          <p class="sw-update-subtitle">
            È disponibile un aggiornamento importante di <strong>Smart Home 3D</strong>. Tocca il pulsante qui sotto per ricaricare subito l'app aggiornata.
          </p>
          <div class="sw-update-actions">
            <button type="button" class="btn-pwa-update" id="btn-pwa-update">Aggiorna ora</button>
            <button type="button" class="btn-pwa-dismiss" id="btn-pwa-dismiss" aria-label="Chiudi">Più tardi</button>
          </div>
        </div>
      `;

      const updateBtn = toast.querySelector('#btn-pwa-update');
      const dismissBtn = toast.querySelector('#btn-pwa-dismiss');

      updateBtn?.addEventListener('click', async () => {
        updateBtn.disabled = true;
        updateBtn.textContent = 'Aggiornamento in corso...';
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
