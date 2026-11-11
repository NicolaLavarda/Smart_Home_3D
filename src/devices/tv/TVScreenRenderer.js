import * as THREE from 'three';

/**
 * TVScreenRenderer
 * 
 * Genera e aggiorna dinamicamente una texture WebGL fotorealistica ad alta risoluzione (1024x576)
 * per lo schermo 3D della TV nel salotto (TV_Salotto_Screen).
 * Mostra grafiche fedeli e curate in base a ciò che è in riproduzione:
 * - Canali TV del digitale terrestre (Rai, Mediaset, Sky con info programma e badge DIRETTA)
 * - Piattaforme streaming (Netflix, Prime Video, YouTube, Disney+, Spotify con equalizer animato)
 * - Browser Web (Google / URL personalizzato)
 * - Modalità Spenta / Standby (Vetro antiriflesso scuro con led standby rosso)
 */
export class TVScreenRenderer {
  constructor() {
    this.canvas = document.createElement('canvas');
    this.canvas.width = 1024;
    this.canvas.height = 576;
    this.ctx = this.canvas.getContext('2d');

    this.texture = new THREE.CanvasTexture(this.canvas);
    this.texture.colorSpace = THREE.SRGBColorSpace;
    this.texture.minFilter = THREE.LinearFilter;
    this.texture.magFilter = THREE.LinearFilter;

    this.screenMesh = null;
    this.currentState = null;
    this.animationTimer = 0;

    // Carica tutti i loghi ufficiali vettoriali in memoria
    this.initLogoAssets();

    // Disegna stato iniziale standby
    this.renderStandby();
  }

  initLogoAssets() {
    this.logos = {};
    const logoSources = {
      netflix: '/logos/netflix.svg',
      netflix_n: '/logos/netflix-n.svg',
      prime: '/logos/prime-video.svg',
      youtube: '/logos/youtube.svg',
      disney: '/logos/disney-plus.svg',
      spotify: '/logos/spotify.svg',
      raiplay: '/logos/raiplay.svg',
      rai1: '/logos/rai1.svg',
      mediaset: '/logos/mediaset.svg',
      google: '/logos/google.svg',
      livetv: '/logos/livetv.svg',
      hdmi: '/logos/hdmi.svg',
      lg: '/logos/lg-webos.svg',
    };

    for (const [key, src] of Object.entries(logoSources)) {
      const img = new Image();
      img.src = src;
      img.onload = () => {
        this.logos[key] = img;
        if (this.currentState) {
          this.render();
        }
      };
    }
  }

  attachToMesh(mesh) {
    this.screenMesh = mesh;
    if (!this.screenMesh) return;

    // 1. Configura UV planari corrette 16:9 verticali per il display
    this.setupScreenUVs(this.screenMesh);

    // 2. Assegna un materiale PBR dedicato, luminoso e non alterato da tinte scure pregresse del GLB
    this.screenMaterial = new THREE.MeshStandardMaterial({
      name: 'Mat_TV_Active_Display',
      color: new THREE.Color(0xffffff),
      map: this.texture,
      emissive: new THREE.Color(0xffffff),
      emissiveMap: this.texture,
      emissiveIntensity: 1.0,
      roughness: 0.15,
      metalness: 0.02,
      side: THREE.DoubleSide,
    });
    this.screenMesh.material = this.screenMaterial;

    const state = this.currentState?.state;
    const isOn = state === 'playing' || state === 'on' || state === 'idle' || state === 'paused';
    this.applyMeshLighting(isOn);
    this.render();
  }

  /**
   * Genera coordinate UV normalizzate [0..1] per la faccia frontale rivolta verso il salotto (+X).
   */
  setupScreenUVs(mesh) {
    if (!mesh || !mesh.geometry || !mesh.geometry.attributes.position) return;
    const geom = mesh.geometry;
    const pos = geom.attributes.position;
    const norm = geom.attributes.normal;
    const count = pos.count;
    const uvs = new Float32Array(count * 2);

    let yMin = Infinity, yMax = -Infinity;
    let zMin = Infinity, zMax = -Infinity;
    let xMax = -Infinity;

    for (let i = 0; i < count; i++) {
      const x = pos.getX(i);
      const y = pos.getY(i);
      const z = pos.getZ(i);
      if (x > xMax) xMax = x;
      if (y < yMin) yMin = y;
      if (y > yMax) yMax = y;
      if (z < zMin) zMin = z;
      if (z > zMax) zMax = z;
    }

    const ySpan = (yMax - yMin) || 1;
    const zSpan = (zMax - zMin) || 1;

    for (let i = 0; i < count; i++) {
      const x = pos.getX(i);
      const nx = norm ? norm.getX(i) : 0;
      // Faccia frontale dello schermo (+X > 0.5 o vertici a xMax)
      if (nx > 0.5 || x >= xMax - 0.005) {
        const y = pos.getY(i);
        const z = pos.getZ(i);
        // Vista dal salotto guardando verso la parete Ovest (-X):
        // zMax (4.70m, sud) è il bordo SINISTRO dello schermo (U=0)
        // zMin (3.30m, nord) è il bordo DESTRO dello schermo (U=1)
        // yMin (0.85m) è il bordo INFERIORE (V=0)
        // yMax (1.65m) è il bordo SUPERIORE (V=1)
        uvs[i * 2] = (zMax - z) / zSpan;
        uvs[i * 2 + 1] = (y - yMin) / ySpan;
      } else {
        // Altre facce (retro, bordi) mappate a zero
        uvs[i * 2] = 0.0;
        uvs[i * 2 + 1] = 0.0;
      }
    }

    geom.setAttribute('uv', new THREE.BufferAttribute(uvs, 2));
    geom.attributes.uv.needsUpdate = true;
    console.log(`[TVScreenRenderer] Coordinate UV generate con successo per ${mesh.name}: ${count} vertici, Y=[${yMin.toFixed(2)}..${yMax.toFixed(2)}], Z=[${zMin.toFixed(2)}..${zMax.toFixed(2)}].`);
  }

  applyMeshLighting(isOn) {
    if (!this.screenMesh || !this.screenMesh.material) return;
    const mat = this.screenMesh.material;
    if (isOn) {
      mat.color.setHex(0xffffff);
      mat.emissive.setHex(0xffffff);
      mat.emissiveIntensity = 1.0;
      mat.roughness = 0.15;
    } else {
      mat.color.setHex(0x181818);
      mat.emissive.setHex(0x060606);
      mat.emissiveIntensity = 0.08;
      mat.roughness = 0.1;
    }
    mat.needsUpdate = true;
  }

  updateState(stateObj) {
    this.currentState = stateObj;
    this.render();
  }

  onTick(delta) {
    this.animationTimer += delta;
    // Aggiorna animazioni procedurali su schermo attivo (es. equalizer Spotify o badge live)
    if (this.currentState) {
      const state = this.currentState.state;
      const isLive = state === 'playing' || state === 'on';
      if (isLive) {
        const source = (this.currentState.attributes?.source || this.currentState.attributes?.app_name || '').toLowerCase();
        if (source.includes('spotify') || source.includes('musica') || source.includes('tv') || source.includes('live')) {
          this.render();
        }
      }
    }
  }

  render() {
    if (!this.ctx) return;
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;

    const state = this.currentState?.state || 'off';
    const attrs = this.currentState?.attributes || {};
    const isOn = state === 'playing' || state === 'on' || state === 'idle' || state === 'paused';

    this.applyMeshLighting(isOn);

    if (!isOn || state === 'off' || state === 'standby' || state === 'unavailable') {
      this.renderStandby();
      return;
    }

    const source = (attrs.source || attrs.app_name || 'Live TV').toLowerCase();
    const title = attrs.media_title || attrs.friendly_name || 'LG webOS Smart TV';
    const channel = attrs.media_channel || attrs.source || title || 'Live TV';

    if (source.includes('netflix')) {
      this.renderNetflix(title, attrs);
    } else if (source.includes('prime') || source.includes('amazon')) {
      this.renderPrimeVideo(title, attrs);
    } else if (source.includes('youtube')) {
      this.renderYouTube(title, attrs);
    } else if (source.includes('disney')) {
      this.renderDisneyPlus(title, attrs);
    } else if (source.includes('spotify') || source.includes('musica')) {
      this.renderSpotify(title, attrs);
    } else if (source.includes('browser') || source.includes('google')) {
      this.renderBrowser(title, attrs);
    } else if (source.includes('hdmi')) {
      this.renderHDMI(attrs.source || 'HDMI 1', attrs);
    } else {
      // Default: Live TV / Canali televisivi
      this.renderLiveTV(channel || attrs.source || 'Live TV', title, attrs);
    }

    this.texture.needsUpdate = true;
  }

  /**
   * Schermo spento / Standby con riflesso vetro scuro e LED rosso
   */
  renderStandby() {
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;

    // Sfondo nero profondo OLED con sfumatura riflesso ambiente
    const grad = ctx.createLinearGradient(0, 0, w, h);
    grad.addColorStop(0, '#020305');
    grad.addColorStop(0.5, '#07090e');
    grad.addColorStop(1, '#020305');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);

    // Riflesso diagonale sottilissimo e realistico del pannello in vetro
    const glassGrad = ctx.createLinearGradient(0, 0, w, h);
    glassGrad.addColorStop(0, 'rgba(255, 255, 255, 0.025)');
    glassGrad.addColorStop(0.3, 'rgba(255, 255, 255, 0.04)');
    glassGrad.addColorStop(0.32, 'rgba(255, 255, 255, 0.0)');
    glassGrad.addColorStop(1, 'rgba(255, 255, 255, 0.0)');
    ctx.fillStyle = glassGrad;
    ctx.fillRect(0, 0, w, h);

    // Piccolo LED Standby rosso in basso a destra
    ctx.fillStyle = '#ef4444';
    ctx.beginPath();
    ctx.arc(w - 24, h - 20, 3.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowColor = '#ef4444';
    ctx.shadowBlur = 8;
    ctx.stroke();
    ctx.shadowBlur = 0;

    this.texture.needsUpdate = true;
  }

  /**
   * Grafica Canali TV Live (Rai 1, Canale 5, Italia 1, ecc.)
   */
  renderLiveTV(channelName, programTitle, attrs) {
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;

    // Sfondo scenografico trasmissione HD
    const bgGrad = ctx.createLinearGradient(0, 0, w, h);
    bgGrad.addColorStop(0, '#0c1a30');
    bgGrad.addColorStop(0.4, '#172554');
    bgGrad.addColorStop(0.8, '#1e1b4b');
    bgGrad.addColorStop(1, '#0a0f1d');
    ctx.fillStyle = bgGrad;
    ctx.fillRect(0, 0, w, h);

    // Effetto illuminazione studio televisivo
    ctx.fillStyle = 'rgba(56, 189, 248, 0.12)';
    ctx.beginPath();
    ctx.ellipse(w * 0.7, h * 0.45, 380, 200, 0.2, 0, Math.PI * 2);
    ctx.fill();

    // Linee scenografiche digitali
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    ctx.lineWidth = 1.5;
    for (let y = 100; y < h; y += 40) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
    }

    // Top Bar: Badge DIRETTA + Ora locale
    const pulse = Math.sin(this.animationTimer * 4) * 0.3 + 0.7;
    ctx.fillStyle = `rgba(239, 68, 68, ${pulse})`;
    ctx.beginPath();
    ctx.arc(60, 50, 7, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 20px "Inter", sans-serif';
    ctx.fillText('DIRETTA', 76, 56);

    const now = new Date();
    const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
    ctx.fillStyle = '#94a3b8';
    ctx.font = '600 22px monospace';
    ctx.fillText(timeStr, w - 120, 56);

    // Logo / Emblema Canale in alto a destra
    const chLower = (channelName + ' ' + (programTitle || '')).toLowerCase();
    let badgeText = 'TV HD';
    let badgeColor = '#0284c7';
    let drawnLogo = false;

    if (chLower.includes('rai 1') || chLower.includes('rai1')) {
      badgeText = 'RAI 1 HD'; badgeColor = '#0284c7';
      if (this.logos.rai1) {
        ctx.drawImage(this.logos.rai1, w - 200, 28, 140, 54.7);
        drawnLogo = true;
      }
    } else if (chLower.includes('rai') || chLower.includes('raiplay')) {
      badgeText = 'RAIPLAY HD'; badgeColor = '#0284c7';
      if (this.logos.raiplay) {
        ctx.drawImage(this.logos.raiplay, w - 200, 28, 140, 54.7);
        drawnLogo = true;
      }
    } else if (chLower.includes('canale 5') || chLower.includes('italia 1') || chLower.includes('mediaset')) {
      badgeText = 'MEDIASET HD'; badgeColor = '#ea580c';
      if (this.logos.mediaset) {
        ctx.drawImage(this.logos.mediaset, w - 210, 28, 150, 58.6);
        drawnLogo = true;
      }
    } else if (chLower.includes('rai 2') || chLower.includes('rai2')) {
      badgeText = 'RAI 2 HD'; badgeColor = '#dc2626';
    } else if (chLower.includes('rai 3') || chLower.includes('rai3')) {
      badgeText = 'RAI 3 HD'; badgeColor = '#16a34a';
    } else if (chLower.includes('la7')) {
      badgeText = 'LA7 HD'; badgeColor = '#f59e0b';
    } else {
      badgeText = channelName.length < 15 ? channelName.toUpperCase() : 'LIVE TV';
      if (this.logos.livetv) {
        ctx.drawImage(this.logos.livetv, w - 240, 32, 48, 48);
        this.drawChannelLogoBadge(ctx, w - 180, 36, badgeText, badgeColor);
        drawnLogo = true;
      }
    }

    if (!drawnLogo) {
      this.drawChannelLogoBadge(ctx, w - 240, 36, badgeText, badgeColor);
    }

    // Titolo programma principale in sovraimpressione centrale/bassa
    const displayProgram = (programTitle && programTitle !== 'LG webOS Smart TV') ? programTitle : (channelName || 'TG1 - Notiziario Principale HD');

    // Banner OSD semitrasparente stile Smart TV webOS
    ctx.fillStyle = 'rgba(15, 23, 42, 0.88)';
    this.roundRect(ctx, 40, h - 170, w - 80, 130, 16);
    ctx.fill();
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
    ctx.lineWidth = 1;
    ctx.stroke();

    // Testi programma e canale OSD
    ctx.fillStyle = '#38bdf8';
    ctx.font = 'bold 16px "Inter", sans-serif';
    ctx.fillText(`CANALE • ${badgeText}`, 65, h - 130);

    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 30px "Inter", sans-serif';
    const truncatedTitle = displayProgram.length > 40 ? displayProgram.substring(0, 40) + '...' : displayProgram;
    ctx.fillText(truncatedTitle, 65, h - 90);

    // Badge risoluzione e audio
    this.drawTagBadge(ctx, w - 260, h - 135, '4K DVB-T2', '#0284c7');
    this.drawTagBadge(ctx, w - 140, h - 135, 'DOLBY 5.1', '#64748b');

    // Barra progresso trasmissione
    ctx.fillStyle = 'rgba(255, 255, 255, 0.15)';
    this.roundRect(ctx, 65, h - 65, w - 130, 6, 3);
    ctx.fill();

    const progressWidth = (w - 130) * 0.65;
    ctx.fillStyle = '#38bdf8';
    this.roundRect(ctx, 65, h - 65, progressWidth, 6, 3);
    ctx.fill();
  }

  /**
   * Grafica Netflix con Logo Ufficiale e Ribbon 'N'
   */
  renderNetflix(title, attrs) {
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;

    // Sfondo scuro cinematografico con riflesso rosso alla base
    const bg = ctx.createRadialGradient(w / 2, h + 100, 50, w / 2, h / 2, 700);
    bg.addColorStop(0, '#450a0a');
    bg.addColorStop(0.5, '#180303');
    bg.addColorStop(1, '#050505');
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, w, h);

    // Ribbon 'N' Netflix gigante in semitrasparenza sullo sfondo
    if (this.logos.netflix_n) {
      ctx.save();
      ctx.globalAlpha = 0.09;
      ctx.drawImage(this.logos.netflix_n, w - 280, 70, 200, 360);
      ctx.restore();
    }

    // Logo ufficiale NETFLIX
    if (this.logos.netflix) {
      ctx.drawImage(this.logos.netflix, 60, 42, 175, 47.3);
    } else {
      ctx.fillStyle = '#e50914';
      ctx.font = '900 38px "Impact", "Arial Black", sans-serif';
      ctx.fillText('NETFLIX', 60, 75);
    }

    // Titolo serie / film
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 44px "Inter", sans-serif';
    const displayTitle = title !== 'LG webOS Smart TV' ? title : 'Stranger Things';
    ctx.fillText(displayTitle, 60, h / 2 + 10);

    // Tag e specifiche
    this.drawTagBadge(ctx, 60, h / 2 + 35, 'TOP 10', '#e50914');
    this.drawTagBadge(ctx, 150, h / 2 + 35, '4K Ultra HD', 'rgba(255,255,255,0.2)');
    this.drawTagBadge(ctx, 280, h / 2 + 35, 'HDR', 'rgba(255,255,255,0.2)');
    this.drawTagBadge(ctx, 350, h / 2 + 35, 'Dolby Atmos', 'rgba(255,255,255,0.2)');

    // Stato player e barra rossa
    const isPlaying = attrs.state === 'playing';
    ctx.fillStyle = '#94a3b8';
    ctx.font = '600 16px "Inter", sans-serif';
    ctx.fillText(isPlaying ? 'In riproduzione' : 'In pausa', 60, h - 90);

    ctx.fillStyle = 'rgba(255, 255, 255, 0.2)';
    this.roundRect(ctx, 60, h - 60, w - 120, 8, 4);
    ctx.fill();

    ctx.fillStyle = '#e50914';
    this.roundRect(ctx, 60, h - 60, (w - 120) * 0.42, 8, 4);
    ctx.fill();
  }

  /**
   * Grafica Prime Video con Logo Ufficiale e freccia sorriso
   */
  renderPrimeVideo(title, attrs) {
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;

    const bg = ctx.createLinearGradient(0, 0, w, h);
    bg.addColorStop(0, '#00050d');
    bg.addColorStop(0.5, '#04172a');
    bg.addColorStop(1, '#000814');
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, w, h);

    // Logo ufficiale Prime Video
    if (this.logos.prime) {
      ctx.drawImage(this.logos.prime, 60, 38, 165, 55);
    } else {
      ctx.fillStyle = '#00a8e1';
      ctx.font = 'bold 36px "Inter", sans-serif';
      ctx.fillText('prime video', 60, 75);
    }

    // Titolo
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 44px "Inter", sans-serif';
    const displayTitle = title !== 'LG webOS Smart TV' ? title : 'Il Signore degli Anelli';
    ctx.fillText(displayTitle, 60, h / 2 + 10);

    this.drawTagBadge(ctx, 60, h / 2 + 35, 'INCLUSO CON PRIME', '#00a8e1');
    this.drawTagBadge(ctx, 245, h / 2 + 35, 'UHD HDR', 'rgba(255,255,255,0.2)');

    // Scrubber
    ctx.fillStyle = 'rgba(255, 255, 255, 0.2)';
    this.roundRect(ctx, 60, h - 60, w - 120, 8, 4);
    ctx.fill();
    ctx.fillStyle = '#00a8e1';
    this.roundRect(ctx, 60, h - 60, (w - 120) * 0.58, 8, 4);
    ctx.fill();
  }

  /**
   * Grafica YouTube con Logo Ufficiale
   */
  renderYouTube(title, attrs) {
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;

    ctx.fillStyle = '#0f0f0f';
    ctx.fillRect(0, 0, w, h);

    // Logo ufficiale YouTube
    if (this.logos.youtube) {
      ctx.drawImage(this.logos.youtube, 60, 38, 156, 55);
    } else {
      ctx.fillStyle = '#ff0000';
      this.roundRect(ctx, 60, 45, 52, 36, 10);
      ctx.fill();
      ctx.fillStyle = '#ffffff';
      ctx.beginPath();
      ctx.moveTo(80, 54); ctx.lineTo(96, 63); ctx.lineTo(80, 72);
      ctx.fill();
      ctx.font = 'bold 30px "Inter", sans-serif';
      ctx.fillText('YouTube', 125, 72);
    }

    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 38px "Inter", sans-serif';
    const displayTitle = title !== 'LG webOS Smart TV' ? title : 'Smart Home 3D Digital Twin - Live Feed';
    ctx.fillText(displayTitle, 60, h / 2);

    ctx.fillStyle = '#aaaaaa';
    ctx.font = '20px "Inter", sans-serif';
    ctx.fillText('Digital Twin 3D • 4K 60fps', 60, h / 2 + 45);

    // Barra rossa
    ctx.fillStyle = 'rgba(255, 255, 255, 0.2)';
    this.roundRect(ctx, 60, h - 60, w - 120, 6, 3);
    ctx.fill();
    ctx.fillStyle = '#ff0000';
    this.roundRect(ctx, 60, h - 60, (w - 120) * 0.72, 6, 3);
    ctx.fill();
  }

  /**
   * Grafica Disney+ con Logo Ufficiale
   */
  renderDisneyPlus(title, attrs) {
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;

    const bg = ctx.createLinearGradient(0, 0, w, h);
    bg.addColorStop(0, '#040714');
    bg.addColorStop(0.5, '#0c1b3a');
    bg.addColorStop(1, '#02050e');
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, w, h);

    // Logo ufficiale Disney+
    if (this.logos.disney) {
      ctx.drawImage(this.logos.disney, 60, 34, 160, 62.5);
    } else {
      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 38px "Inter", sans-serif';
      ctx.fillText('Disney+', 60, 75);
    }

    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 44px "Inter", sans-serif';
    const displayTitle = title !== 'LG webOS Smart TV' ? title : 'The Mandalorian';
    ctx.fillText(displayTitle, 60, h / 2);

    this.drawTagBadge(ctx, 60, h / 2 + 30, 'DISNEY+ ORIGINAL', '#38bdf8');
    this.drawTagBadge(ctx, 235, h / 2 + 30, 'IMAX Enhanced', 'rgba(255,255,255,0.2)');

    ctx.fillStyle = 'rgba(255, 255, 255, 0.2)';
    this.roundRect(ctx, 60, h - 60, w - 120, 8, 4);
    ctx.fill();
    ctx.fillStyle = '#38bdf8';
    this.roundRect(ctx, 60, h - 60, (w - 120) * 0.35, 8, 4);
    ctx.fill();
  }

  /**
   * Grafica Spotify con Logo Ufficiale ed Equalizer audio animato
   */
  renderSpotify(title, attrs) {
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;

    const bg = ctx.createLinearGradient(0, 0, w, h);
    bg.addColorStop(0, '#121212');
    bg.addColorStop(0.5, '#0a2216');
    bg.addColorStop(1, '#07130c');
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, w, h);

    // Spotify Logo
    if (this.logos.spotify) {
      ctx.drawImage(this.logos.spotify, 60, 38, 48, 48);
      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 32px "Inter", sans-serif';
      ctx.fillText('Spotify', 120, 73);
    } else {
      ctx.fillStyle = '#1db954';
      ctx.beginPath();
      ctx.arc(80, 65, 22, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = '#ffffff';
      ctx.font = 'bold 30px "Inter", sans-serif';
      ctx.fillText('Spotify', 115, 75);
    }

    // Equalizer animato
    const numBars = 28;
    const barWidth = 14;
    const startX = 60;
    const baseY = h - 140;

    for (let i = 0; i < numBars; i++) {
      const height = Math.abs(Math.sin(this.animationTimer * 6 + i * 0.45)) * 90 + 15;
      const x = startX + i * (barWidth + 8);
      ctx.fillStyle = '#1db954';
      this.roundRect(ctx, x, baseY - height, barWidth, height, 6);
      ctx.fill();
    }

    // Info brano
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 40px "Inter", sans-serif';
    const displayTitle = title !== 'LG webOS Smart TV' ? title : 'Musica Salotto HD';
    ctx.fillText(displayTitle, 60, h / 2 - 30);

    ctx.fillStyle = '#1db954';
    ctx.font = '600 22px "Inter", sans-serif';
    ctx.fillText('LG webOS Hi-Fi Sound System • In Riproduzione', 60, h / 2 + 10);

    // Scrubber
    ctx.fillStyle = 'rgba(255, 255, 255, 0.2)';
    this.roundRect(ctx, 60, h - 50, w - 120, 6, 3);
    ctx.fill();
    ctx.fillStyle = '#1db954';
    this.roundRect(ctx, 60, h - 50, (w - 120) * 0.62, 6, 3);
    ctx.fill();
  }

  /**
   * Grafica Browser Web con Logo Google Ufficiale a 4 colori
   */
  renderBrowser(title, attrs) {
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;

    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, w, h);

    // Barra del browser webOS
    ctx.fillStyle = '#1e293b';
    ctx.fillRect(0, 0, w, 70);

    ctx.fillStyle = '#0f172a';
    this.roundRect(ctx, 160, 15, w - 320, 40, 10);
    ctx.fill();

    ctx.fillStyle = '#94a3b8';
    ctx.font = '16px monospace';
    ctx.fillText('https://www.google.com', 185, 41);

    // Google Logo al centro
    if (this.logos.google) {
      ctx.drawImage(this.logos.google, w / 2 - 45, h / 2 - 95, 90, 90);
      ctx.fillStyle = '#4285f4';
      ctx.font = 'bold 36px "Inter", sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Google', w / 2, h / 2 + 25);
      ctx.textAlign = 'start';
    } else {
      ctx.font = 'bold 74px "Inter", sans-serif';
      const letters = [
        { t: 'G', c: '#4285f4' },
        { t: 'o', c: '#ea4335' },
        { t: 'o', c: '#fbbc05' },
        { t: 'g', c: '#4285f4' },
        { t: 'l', c: '#34a853' },
        { t: 'e', c: '#ea4335' },
      ];
      let gx = w / 2 - 140;
      letters.forEach((l) => {
        ctx.fillStyle = l.c;
        ctx.fillText(l.t, gx, h / 2 - 40);
        gx += 46;
      });
    }

    // Barra ricerca
    ctx.strokeStyle = '#cbd5e1';
    ctx.lineWidth = 2;
    this.roundRect(ctx, w / 2 - 280, h / 2 + 50, 560, 50, 25);
    ctx.stroke();

    ctx.fillStyle = '#94a3b8';
    ctx.font = '18px "Inter", sans-serif';
    ctx.fillText('Cerca con Google o digita un URL...', w / 2 - 240, h / 2 + 82);
  }

  /**
   * Grafica HDMI con Logo Ufficiale HDMI
   */
  renderHDMI(sourceName, attrs) {
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;

    ctx.fillStyle = '#0a0d14';
    ctx.fillRect(0, 0, w, h);

    if (this.logos.hdmi) {
      ctx.drawImage(this.logos.hdmi, 60, 38, 140, 54.7);
    } else {
      ctx.fillStyle = '#38bdf8';
      ctx.font = 'bold 36px "Inter", sans-serif';
      ctx.fillText(sourceName.toUpperCase(), 60, 80);
    }

    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 44px "Inter", sans-serif';
    ctx.fillText('Sorgente Esterna Connessa (' + sourceName + ')', 60, h / 2);

    this.drawTagBadge(ctx, 60, h / 2 + 35, '3840x2160 @ 120Hz', '#38bdf8');
    this.drawTagBadge(ctx, 260, h / 2 + 35, 'VRR • HDR10 • eARC', 'rgba(255,255,255,0.2)');
  }

  drawChannelLogoBadge(ctx, x, y, text, color) {
    ctx.fillStyle = color;
    this.roundRect(ctx, x, y, 160, 36, 8);
    ctx.fill();
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 15px "Inter", sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(text, x + 80, y + 24);
    ctx.textAlign = 'start';
  }

  drawTagBadge(ctx, x, y, text, bg) {
    ctx.font = 'bold 14px "Inter", sans-serif';
    const textW = ctx.measureText(text).width;
    ctx.fillStyle = bg;
    this.roundRect(ctx, x, y, textW + 24, 28, 6);
    ctx.fill();
    ctx.fillStyle = '#ffffff';
    ctx.fillText(text, x + 12, y + 19);
  }

  roundRect(ctx, x, y, width, height, radius) {
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.lineTo(x + width - radius, y);
    ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
    ctx.lineTo(x + width, y + height - radius);
    ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
    ctx.lineTo(x + radius, y + height);
    ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
    ctx.lineTo(x, y + radius);
    ctx.quadraticCurveTo(x, y, x + radius, y);
    ctx.closePath();
  }
}

