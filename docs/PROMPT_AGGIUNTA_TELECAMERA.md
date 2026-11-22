Voglio aggiungere una nuova telecamera al progetto **Smart_Home_3D** seguendo rigorosamente la pipeline descritta in `docs/PIPELINE_AGGIUNTA_TELECAMERA.md`.

Assicurati di ricercare online le specifiche ufficiali del modello (FOV orizzontale/verticale, lunghezza focale, aspect ratio, risoluzione, codec, URL RTSP/ONVIF, dimensioni fisiche) e di integrare tutto senza rompere `Cam_Carraio`, la sicurezza o i test esistenti.

### 1. Identificazione e Home Assistant
- **Modello esatto:** Reolink Duo 3 PoE
- **Nome da mostrare in UI (italiano):** Ingresso
- **Zona inquadrata (descrizione breve):** zona ovest della casa
- **Entity ID Home Assistant:** ingresso

### 2. Posizione fisica e misure rispetto alla casa
- **Posizione:** L'obiettivo della telecamera si trova a 350cm da terra, a 48cm verso nord dalla colonna più a nord tra le due sulla facciata ovest del portico che misurando invece dallo spigolo nord-ovest della casa dovrebbe essere a 5936cm (controlla se le due cose circa coincidono). La distanza dal muro è quella data dalla staffa (se trovi le specifiche online altrimenti 15cm).

- **Direzione e punto inquadrato (dove guarda):** guarda verso ovest perpendicolarmente al muro inclinata di 25° verso il basso (rispetto all'orizzontale)

### 3. Rete e Streaming video
- **IP LAN statico della telecamera:** 192.168.86.53
- **Porte/protocolli abilitati sulla camera:** RTSP 554 e ONVIF abilitati
- **Codec configurato sulla camera:** Main H.264 + Sub H.264
- **Credenziali / `.env`:** variabili RTSP in `.env` le compilo io manualmente appena mi dici i nomi

### 4. Preferenze e ambiente
- **Tracking / AI OpenVINO (`spatial_server`):** Sì, includi anche rilevamento AI con gestione già implementata intelligente per aree viste da più telecamere contemporaneamente
- **Preset vista rapida dedicato nella TopBar:** No, basta cliccabile in 3D e nel pannello telecamere
- **Target finale richiesto:** Aggiorna Blender, export GLB, codice multi-camera, test e build produzione