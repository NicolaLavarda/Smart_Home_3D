Voglio aggiungere una nuova telecamera al progetto **Smart_Home_3D** seguendo rigorosamente la pipeline descritta in `docs/PIPELINE_AGGIUNTA_TELECAMERA.md`.

Assicurati di ricercare online le specifiche ufficiali del modello (FOV orizzontale/verticale, lunghezza focale, aspect ratio, risoluzione, codec, URL RTSP/ONVIF, dimensioni fisiche) e di integrare tutto senza rompere `Cam_Carraio`, la sicurezza o i test esistenti.

### 1. Identificazione e Home Assistant
- **Modello esatto:** <es. Reolink RLC-810A / Reolink Duo 3 PoE>
- **Nome da mostrare in UI (italiano):** <es. Telecamera Portico Sud>
- **Zona inquadrata (descrizione breve):** <es. Portico, ingresso pedonale e vialetto>
- **Entity ID Home Assistant:** <es. camera.portico_fluente — oppure: leggilo da HA usando .env.local>

### 2. Posizione fisica e misure rispetto alla casa
- **Elemento di montaggio:** <es. Muro ovest della casa principale / Muro sud del garage / Palo vicino alla lavanderia>
- **Distanza lungo il muro (da uno spigolo noto):** <es. a 2,40 m dallo spigolo sud-ovest verso est>
- **Altezza di installazione:** <es. a 2,85 m dal pavimento del portico / dal terreno>
- **Sporgenza staffa dal muro (se nota):** <es. 12 cm / standard da datasheet>
- **Direzione e punto inquadrato (dove guarda):** <es. guarda verso Sud-Ovest, centrata sull'ingresso del cancello carraio a circa 1 m da terra — oppure: inclinata verso il basso di ~25° verso il centro del prato>
- **Ostacoli vicini da considerare in Blender (opzionale):** <es. sporgenza tetto/grondaia a 3,10 m / nessuna ostruzione>

### 3. Rete e Streaming video
- **IP LAN statico della telecamera:** <es. 192.168.86.XXX>
- **Porte/protocolli abilitati sulla camera:** RTSP 554 e ONVIF abilitati
- **Codec configurato sulla camera:** Main H.264 + Sub H.264
- **Credenziali / `.env`:** variabili RTSP in `.env` le compilo io manualmente appena mi dici i nomi

### 4. Preferenze e ambiente
- **Tracking / AI OpenVINO (`spatial_server`):** Sì, includi anche rilevamento AI con gestione già implementata intelligente per aree viste da più telecamere contemporaneamente
- **Preset vista rapida dedicato nella TopBar:** No, basta cliccabile in 3D e nel pannello telecamere
- **Target finale richiesto:** Aggiorna Blender, export GLB, codice multi-camera, test e build produzione