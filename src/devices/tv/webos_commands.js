/**
 * WebOS Commands & Endpoints per LG Smart TV
 * Documentati e supportati dall'integrazione webostv di Home Assistant.
 */

export const WEBOS_COMMANDS = {
  GET_SERVICES: 'api/getServiceList',
  SET_MUTE: 'audio/setMute',
  GET_AUDIO_STATUS: 'audio/getStatus',
  GET_VOLUME: 'audio/getVolume',
  SET_VOLUME: 'audio/setVolume',
  VOLUME_UP: 'audio/volumeUp',
  VOLUME_DOWN: 'audio/volumeDown',
  GET_CURRENT_APP_INFO: 'com.webos.applicationManager/getForegroundAppInfo',
  LAUNCH_APP: 'com.webos.applicationManager/launch',
  GET_APPS: 'com.webos.applicationManager/listLaunchPoints',
  GET_APP_STATUS: 'com.webos.service.appstatus/getAppStatus',
  SEND_ENTER: 'com.webos.service.ime/sendEnterKey',
  SEND_DELETE: 'com.webos.service.ime/deleteCharacters',
  INSERT_TEXT: 'com.webos.service.ime/insertText',
  SET_3D_ON: 'com.webos.service.tv.display/set3DOn',
  SET_3D_OFF: 'com.webos.service.tv.display/set3DOff',
  GET_SOFTWARE_INFO: 'com.webos.service.update/getCurrentSWInformation',
  MEDIA_PLAY: 'media.controls/play',
  MEDIA_STOP: 'media.controls/stop',
  MEDIA_PAUSE: 'media.controls/pause',
  MEDIA_REWIND: 'media.controls/rewind',
  MEDIA_FAST_FORWARD: 'media.controls/fastForward',
  MEDIA_CLOSE: 'media.viewer/close',
  POWER_OFF: 'system/turnOff',
  POWER_ON: 'system/turnOn',
  SHOW_MESSAGE: 'system.notifications/createToast',
  CLOSE_TOAST: 'system.notifications/closeToast',
  CREATE_ALERT: 'system.notifications/createAlert',
  CLOSE_ALERT: 'system.notifications/closeAlert',
  LAUNCHER_CLOSE: 'system.launcher/close',
  GET_APP_STATE: 'system.launcher/getAppState',
  GET_SYSTEM_INFO: 'system/getSystemInfo',
  LAUNCH: 'system.launcher/launch',
  OPEN: 'system.launcher/open',
  GET_SYSTEM_SETTINGS: 'settings/getSystemSettings',
  TV_CHANNEL_DOWN: 'tv/channelDown',
  TV_CHANNEL_UP: 'tv/channelUp',
  GET_TV_CHANNELS: 'tv/getChannelList',
  GET_CHANNEL_INFO: 'tv/getChannelProgramInfo',
  GET_CURRENT_CHANNEL: 'tv/getCurrentChannel',
  GET_INPUTS: 'tv/getExternalInputList',
  SET_CHANNEL: 'tv/openChannel',
  SET_INPUT: 'tv/switchInput',
  CLOSE_WEB_APP: 'webapp/closeWebApp',
  INPUT_SOCKET: 'com.webos.service.networkinput/getPointerInputSocket',
  CALIBRATION: 'externalpq/setExternalPqData',
  GET_CALIBRATION: 'externalpq/getExternalPqData',
  GET_SOUND_OUTPUT: 'com.webos.service.apiadapter/audio/getSoundOutput',
  CHANGE_SOUND_OUTPUT: 'com.webos.service.apiadapter/audio/changeSoundOutput',
  GET_POWER_STATE: 'com.webos.service.tvpower/power/getPowerState',
  TURN_OFF_SCREEN: 'com.webos.service.tvpower/power/turnOffScreen',
  TURN_ON_SCREEN: 'com.webos.service.tvpower/power/turnOnScreen',
};

/**
 * Fonti e applicazioni disponibili sull'LG webOS Smart TV
 * (estratte dagli attributi reali di Home Assistant dell'utente)
 */
export const AVAILABLE_SOURCES = [
  'Live TV',
  'Netflix',
  'Prime Video',
  'YouTube',
  'Disney+',
  'RaiPlay',
  'Mediaset Infinity',
  'Spotify - Musica e podcast',
  'Browser Web',
  'Apple TV',
  'NOW',
  'Plex',
  'Pluto TV',
  'Rakuten TV',
  'LG Channels',
  'HDMI 1',
  'HDMI 2',
  'HDMI 3',
  'HDMI 4',
  'Home Dashboard',
  'TIMVISION',
  'Musica',
  'Foto e video',
  'Art Gallery',
];

/**
 * Canali TV Italiani predefiniti / popolari per il telecomando
 */
export const POPULAR_TV_CHANNELS = [
  { number: '1', name: 'Rai 1 HD', badge: 'RAI 1' },
  { number: '2', name: 'Rai 2 HD', badge: 'RAI 2' },
  { number: '3', name: 'Rai 3 HD', badge: 'RAI 3' },
  { number: '4', name: 'Rete 4 HD', badge: 'RETE 4' },
  { number: '5', name: 'Canale 5 HD', badge: 'CANALE 5' },
  { number: '6', name: 'Italia 1 HD', badge: 'ITALIA 1' },
  { number: '7', name: 'LA7 HD', badge: 'LA7' },
  { number: '8', name: 'TV8 HD', badge: 'TV8' },
  { number: '9', name: 'NOVE', badge: 'NOVE' },
];

