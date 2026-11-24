/**
 * DualVideoBufferController
 *
 * Gestore OOP a doppio buffer (<video> primario + <video> standby sovrapposto) per garantire
 * transizioni istantanee senza schermo nero tra segmenti Sub H24 e clip Main HD.
 */
export class DualVideoBufferController {
  constructor({ primaryVideoEl, bufferVideoEl = null, onActiveVideoChange = null } = {}) {
    this.primaryVideoEl = primaryVideoEl || null;
    this.bufferVideoEl = bufferVideoEl || null;
    this.onActiveVideoChange = typeof onActiveVideoChange === 'function' ? onActiveVideoChange : null;

    this._activeRole = 'primary'; // 'primary' | 'buffer'
    this._standbyState = {
      status: 'idle', // 'idle' | 'loading' | 'ready' | 'error'
      segmentId: null,
      streamUrl: null,
      targetOffsetSec: 0,
    };
    this._preloadCancel = null;
  }

  static detectBrowserHevcSupport(videoEl = null) {
    let checkedAny = false;
    const probes = [
      'video/mp4; codecs="hvc1.1.6.L153.B0"',
      'video/mp4; codecs="hev1.1.6.L153.B0"',
      'video/mp4; codecs="hvc1.1.6.L180.B0"',
    ];

    if (videoEl && typeof videoEl.canPlayType === 'function') {
      checkedAny = true;
      for (const mime of probes) {
        const res = String(videoEl.canPlayType(mime) || '').toLowerCase();
        if (res === 'probably' || res === 'maybe') {
          return true;
        }
      }
    }

    const MS = typeof window !== 'undefined'
      ? (window.MediaSource || window.ManagedMediaSource || null)
      : null;
    if (MS && typeof MS.isTypeSupported === 'function') {
      checkedAny = true;
      for (const mime of probes) {
        try {
          if (MS.isTypeSupported(mime)) return true;
        } catch {}
      }
    }

    // In ambienti headless/mock senza API multimediali browser lasciamo true per non bloccare i test
    return checkedAny ? false : true;
  }

  hasDualBuffer() {
    return Boolean(this.primaryVideoEl && this.bufferVideoEl && this.primaryVideoEl !== this.bufferVideoEl);
  }

  getActiveVideo() {
    if (this._activeRole === 'buffer' && this.bufferVideoEl) {
      return this.bufferVideoEl;
    }
    return this.primaryVideoEl;
  }

  getStandbyVideo() {
    if (!this.hasDualBuffer()) return null;
    return this._activeRole === 'primary' ? this.bufferVideoEl : this.primaryVideoEl;
  }

  isStandbyReadyFor(segmentId, streamUrl) {
    return (
      this._standbyState.status === 'ready' &&
      this._standbyState.segmentId === segmentId &&
      this._standbyState.streamUrl === streamUrl
    );
  }

  _cancelPendingPreload() {
    if (this._preloadCancel) {
      this._preloadCancel();
      this._preloadCancel = null;
    }
  }

  _clearVideoElement(videoEl) {
    if (!videoEl) return;
    try {
      videoEl.pause?.();
      if (typeof videoEl.removeAttribute === 'function') {
        videoEl.removeAttribute('src');
      } else {
        videoEl.src = '';
      }
      if (videoEl.srcObject) {
        videoEl.srcObject = null;
      }
      if (typeof videoEl.load === 'function') {
        videoEl.load();
      }
    } catch {}
  }

  _applyVisibilityClasses() {
    if (!this.primaryVideoEl || !this.bufferVideoEl) return;
    const isBufferActive = this._activeRole === 'buffer';
    this.primaryVideoEl.classList?.toggle('is-buffer-hidden', isBufferActive);
    this.bufferVideoEl.classList?.toggle('is-buffer-visible', isBufferActive);
  }

  preloadStandby(streamUrl, targetOffsetSec = 0, segmentId = '', { playbackRate = 1.0 } = {}) {
    const standby = this.getStandbyVideo();
    if (!standby || !streamUrl || !segmentId) return false;

    if (
      (this._standbyState.status === 'loading' || this._standbyState.status === 'ready') &&
      this._standbyState.segmentId === segmentId &&
      this._standbyState.streamUrl === streamUrl
    ) {
      return true;
    }

    this._cancelPendingPreload();
    const safeOffset = Math.max(0, Number(targetOffsetSec) || 0);
    this._standbyState = {
      status: 'loading',
      segmentId,
      streamUrl,
      targetOffsetSec: safeOffset,
    };

    standby.muted = true;
    standby.playsInline = true;
    standby.crossOrigin = 'use-credentials';
    standby.preload = 'auto';

    let settled = false;
    let timer = null;
    const cleanup = () => {
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
      standby.removeEventListener?.('loadedmetadata', onLoaded);
      standby.removeEventListener?.('canplay', onLoaded);
      standby.removeEventListener?.('error', onError);
    };

    const onLoaded = () => {
      if (settled) return;
      settled = true;
      cleanup();
      if (this._standbyState.segmentId !== segmentId || this._standbyState.streamUrl !== streamUrl) {
        return;
      }
      try {
        standby.currentTime = safeOffset;
        standby.playbackRate = Math.max(0.25, Math.min(8.0, Number(playbackRate) || 1.0));
      } catch {}
      this._standbyState.status = 'ready';
    };

    const onError = () => {
      if (settled) return;
      settled = true;
      cleanup();
      if (this._standbyState.segmentId === segmentId) {
        this._standbyState.status = 'error';
      }
    };

    this._preloadCancel = () => {
      if (settled) return;
      settled = true;
      cleanup();
    };

    standby.addEventListener?.('loadedmetadata', onLoaded);
    standby.addEventListener?.('canplay', onLoaded);
    standby.addEventListener?.('error', onError);
    timer = setTimeout(onLoaded, 1800);

    standby.src = streamUrl;
    if (typeof standby.load === 'function') {
      try {
        standby.load();
      } catch {}
    }
    return true;
  }

  commitStandbySwap(exactOffsetSec = 0, { autoplay = true, playbackRate = 1.0 } = {}) {
    const oldActive = this.getActiveVideo();
    const standby = this.getStandbyVideo();
    if (!standby || this._standbyState.status !== 'ready') {
      return null;
    }

    const safeOffset = Math.max(0, Number(exactOffsetSec) || 0);
    const safeRate = Math.max(0.25, Math.min(8.0, Number(playbackRate) || 1.0));
    try {
      if (Math.abs((standby.currentTime || 0) - safeOffset) > 0.18) {
        standby.currentTime = safeOffset;
      }
      standby.playbackRate = safeRate;
    } catch {}

    if (autoplay) {
      standby.play?.().catch(() => {});
    } else {
      standby.pause?.();
    }

    this._activeRole = this._activeRole === 'primary' ? 'buffer' : 'primary';
    this._applyVisibilityClasses();

    this._standbyState = {
      status: 'idle',
      segmentId: null,
      streamUrl: null,
      targetOffsetSec: 0,
    };

    if (oldActive && oldActive !== standby) {
      this._clearVideoElement(oldActive);
    }

    if (this.onActiveVideoChange) {
      try {
        this.onActiveVideoChange(standby, this._activeRole);
      } catch {}
    }
    return standby;
  }

  resetToPrimary() {
    this._cancelPendingPreload();
    this._standbyState = {
      status: 'idle',
      segmentId: null,
      streamUrl: null,
      targetOffsetSec: 0,
    };
    if (this.bufferVideoEl) {
      this._clearVideoElement(this.bufferVideoEl);
    }
    const prevRole = this._activeRole;
    this._activeRole = 'primary';
    this._applyVisibilityClasses();
    if (prevRole !== 'primary' && this.onActiveVideoChange && this.primaryVideoEl) {
      try {
        this.onActiveVideoChange(this.primaryVideoEl, 'primary');
      } catch {}
    }
  }

  detachAll() {
    this.resetToPrimary();
    if (this.primaryVideoEl) {
      this._clearVideoElement(this.primaryVideoEl);
    }
  }
}
