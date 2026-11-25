/**
 * RuleDraftModel.js
 *
 * Pure data model helpers for Automation Studio:
 * - Clean blank-slate rule/trigger/condition/action/zone/entity factories (zero fake examples)
 * - Normalizers & floating-point rounding
 * - Dirty-state JSON snapshot & diff helpers
 * - Readable Italian rule summary generator
 * - Entity & Home Assistant service discovery helpers
 */

export function uid(prefix = 'id') {
  return `${prefix}_${Math.random().toString(36).slice(2, 9)}`;
}

export function escapeHtml(val) {
  return String(val ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function roundClean(val, decimals = 2) {
  const num = Number(val);
  if (!Number.isFinite(num)) return 0;
  const factor = 10 ** decimals;
  return Math.round(num * factor) / factor;
}

export function sanitizeControlId(raw) {
  return String(raw || 'ctrl')
    .replace(/[^a-zA-Z0-9_-]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

export const ZONE_PALETTE = [
  '#38bdf8',
  '#34d399',
  '#f59e0b',
  '#a78bfa',
  '#fb7185',
  '#2dd4bf',
  '#fbbf24',
  '#60a5fa',
];

export function pickDistinctZoneColor(existingZones = [], geometryType = 'polygon') {
  const used = new Set(
    (Array.isArray(existingZones) ? existingZones : [])
      .map((z) => String(z?.color || '').toLowerCase())
      .filter(Boolean)
  );
  const ordered =
    geometryType === 'perimeter'
      ? ['#fb7185', '#f59e0b', '#38bdf8', '#a78bfa', '#34d399', '#2dd4bf', '#fbbf24', '#60a5fa']
      : ZONE_PALETTE;
  for (const hex of ordered) {
    if (!used.has(hex.toLowerCase())) return hex;
  }
  return ordered[(existingZones?.length || 0) % ordered.length];
}

export const TRIGGER_TYPE_LABELS = {
  zone_presence: 'Presenza in area 3D',
  perimeter_crossing: 'Attraversamento perimetro',
  zone_transition: 'Passaggio tra due aree',
  kinematic_vector: 'Direzione e velocità media',
  time_schedule: 'Orario, alba o tramonto',
  entity_state_change: 'Cambio stato entità',
  biometric_detection: 'Riconoscimento volto o targa',
  proximity_3d: 'Prossimità a punto 3D',
  scene_event: 'Episodio scena',
};

export const CONDITION_TYPE_LABELS = {
  entity_state: 'Stato entità',
  time_window: 'Fascia oraria o sole',
  zone_occupancy: 'Occupazione area 3D',
  track_kinematics: 'Velocità o direzione soggetto',
  subject_filter: 'Filtro soggetto o biometria',
  scene_event: 'Stato episodio scena',
  recent_zone_visit: 'Passaggio recente in area 3D',
};

export const ACTION_TYPE_LABELS = {
  send_notification: 'Notifica dispositivo (Push / TTS / TV)',
  call_ha_service: 'Servizio Home Assistant',
  set_virtual_entity: 'Stato entità interna (sh3d.*)',
  ui_alert: 'Avviso e sirena 3D',
  delay: 'Attesa (secondi)',
  if_then_else: 'Condizione Se / Altrimenti',
  webhook: 'Webhook HTTP',
};

export const NOTIFICATION_TEMPLATE_VARS = [
  { token: '{{ scene.summary }}', label: 'Riassunto scena' },
  { token: '{{ track.identity }}', label: 'Persona' },
  { token: '{{ track.plate }}', label: 'Targa' },
  { token: '{{ trigger.zone_name }}', label: 'Area 3D' },
  { token: '{{ track.speed_kmh }}', label: 'Velocità km/h' },
  { token: '{{ trigger.summary }}', label: 'Dettaglio trigger' },
];

export const DEFAULT_SELECT_OPTIONS_TEXT = 'Spento, Silenzioso, Acceso';

export function getAvailableEntities({ virtualEntities = [], haEntities = {} } = {}) {
  const virtual = (Array.isArray(virtualEntities) ? virtualEntities : []).map((ve) => ({
    entity_id: String(ve.entity_id || ''),
    name: String(ve.name || ve.entity_id || ''),
    state: String(ve.state ?? ''),
    domain: String(ve.domain || 'switch'),
    options: Array.isArray(ve.options) ? ve.options : [],
    source: 'sh3d',
  }));
  const ha = Object.entries(haEntities || {}).map(([eid, st]) => ({
    entity_id: eid,
    name: String(st?.attributes?.friendly_name || eid),
    state: String(st?.state ?? ''),
    domain: String(eid.split('.')[0] || ''),
    options: [],
    source: 'ha',
  }));
  return { virtual, ha, all: [...virtual, ...ha] };
}

export function getHaServiceSuggestions(haEntities = {}) {
  const base = [
    'light.turn_on',
    'light.turn_off',
    'switch.turn_on',
    'switch.turn_off',
    'cover.open_cover',
    'cover.close_cover',
    'lock.lock',
    'lock.unlock',
    'scene.turn_on',
    'script.turn_on',
    'siren.turn_on',
    'siren.turn_off',
    'media_player.media_play',
    'media_player.media_stop',
  ];
  const domains = new Set(Object.keys(haEntities || {}).map((eid) => eid.split('.')[0]).filter(Boolean));
  return base.filter((svc) => domains.size === 0 || domains.has(svc.split('.')[0]) || svc.startsWith('light.') || svc.startsWith('switch.'));
}

export function defaultTriggerParamsForType(tType, ctx = {}) {
  const firstVirtual = ctx.virtualEntities?.[0]?.entity_id || '';
  if (tType === 'zone_presence') return { zone_id: '', event: 'enter', min_dwell_s: 0 };
  if (tType === 'perimeter_crossing') return { perimeter_id: '', direction: 'a_to_b' };
  if (tType === 'zone_transition') return { from_zone_id: '', to_zone_id: '', max_transit_s: 20, min_speed_mps: 0 };
  if (tType === 'kinematic_vector') return { zone_id: '', target_azimuth_deg: null, azimuth_tolerance_deg: 35, min_duration_s: 1.0, min_speed_mps: 0.5 };
  if (tType === 'time_schedule') return { mode: 'fixed_time', at: '22:00', offset_minutes: 0 };
  if (tType === 'entity_state_change') return { entity_id: firstVirtual, from_state: '', to_state: 'on', for_duration_s: 0 };
  if (tType === 'biometric_detection') return { modality: 'any', camera_id: '', zone_id: '', require_locked: true };
  if (tType === 'proximity_3d') return { target_x: 0, target_z: 0, radius_m: 2.0, min_dwell_s: 1.0 };
  if (tType === 'scene_event') return { event: 'started', importance: 'any', zone_id: '', min_subjects: 0 };
  return {};
}

export function defaultConditionParamsForType(cType, ctx = {}) {
  const firstVirtual = ctx.virtualEntities?.[0]?.entity_id || '';
  if (cType === 'entity_state') return { entity_id: firstVirtual, operator: '==', value: 'on' };
  if (cType === 'time_window') return { after_hhmm: '', before_hhmm: '', sun_state: 'any' };
  if (cType === 'zone_occupancy') return { zone_id: '', operator: '>=', count: 1 };
  if (cType === 'track_kinematics') return { evaluation_mode: 'peak_in_window', window_s: 10.0, min_speed_mps: 0.5, target_azimuth_deg: null, azimuth_tolerance_deg: 35 };
  if (cType === 'subject_filter') return { target: 'trigger_track', classes: ['any'], face_mode: 'any', identities: [], plate_mode: 'any', plates: [] };
  if (cType === 'scene_event') return { importance: 'any', has_unknown_person: 'any', has_whitelisted_plate: 'any' };
  if (cType === 'recent_zone_visit') return { zone_id: '', within_s: 10.0, min_dwell_s: 0.0 };
  return {};
}

export function defaultActionForType(aType, ctx = {}) {
  const firstVirtual = ctx.virtualEntities?.[0]?.entity_id || '';
  const firstHaId = Object.keys(ctx.haEntities || {})[0] || '';
  const firstTts = ctx.haDiscovery?.tts_entities?.[0]?.entity_id || '';
  const base = {
    action_id: uid('act'),
    type: aType,
    params: {},
    then_actions: [],
    else_actions: [],
  };

  if (aType === 'set_virtual_entity') {
    base.params = { entity_id: firstVirtual, operation: 'turn_on', state: 'on' };
  } else if (aType === 'call_ha_service') {
    base.params = { service: 'light.turn_on', entity_id: firstHaId };
  } else if (aType === 'send_notification') {
    base.params = {
      mobile_targets: [],
      tv_targets: [],
      tts_targets: [],
      tts_entity: firstTts,
      priority: 'normal',
      image_mode: 'annotated',
      message_mode: 'auto_scene',
      message: '',
      title: 'Smart Home 3D',
      location_label: '',
      tag: '',
      update_on_biometrics: true,
      display_show_image: true,
      display_duration_s: 25,
      tv_only_when_on: true,
      actions: [],
    };
  } else if (aType === 'ui_alert') {
    base.params = { title: '', message: '', severity: 'warning', sound: true };
  } else if (aType === 'delay') {
    base.params = { seconds: 10 };
  } else if (aType === 'webhook') {
    base.params = { url: '' };
  } else if (aType === 'if_then_else') {
    base.if_condition = {
      condition_id: uid('cnd'),
      type: 'entity_state',
      children: [],
      params: defaultConditionParamsForType('entity_state', ctx),
    };
  }
  return base;
}

export function createBlankTrigger(type = 'zone_presence', ctx = {}) {
  return {
    trigger_id: uid('trg'),
    type,
    enabled: true,
    subject_filter: {
      classes: ['any'],
      face_mode: 'any',
      identities: [],
      plate_mode: 'any',
      plates: [],
      biometric_grace_s: 1.2,
    },
    params: defaultTriggerParamsForType(type, ctx),
  };
}

export function createBlankPreTriggerStage(index = 0) {
  return {
    stage_id: uid('pre'),
    name: `Pre-trigger ${index + 1}`,
    enabled: true,
    match_mode: 'any',
    max_wait_s: 10,
    min_delay_s: 0,
    stage_window_s: 10,
    correlation_scope: 'same_subject',
    consume_on_fire: true,
    refresh_on_rearm: true,
    condition: null,
    triggers: [
      {
        trigger_id: uid('trg'),
        type: 'kinematic_vector',
        enabled: true,
        subject_filter: {
          classes: ['vehicle'],
          face_mode: 'any',
          identities: [],
          plate_mode: 'any',
          plates: [],
          biometric_grace_s: 1.2,
        },
        params: {
          zone_id: '',
          target_azimuth_deg: null,
          azimuth_tolerance_deg: 35,
          min_duration_s: 0.5,
          min_speed_mps: 0.5,
        },
      },
    ],
  };
}

export function createBlankRuleDraft() {
  return {
    rule_id: uid('rule'),
    name: '',
    description: '',
    enabled: true,
    execution_mode: 'single',
    cooldown_s: 3,
    pre_triggers: [],
    triggers: [createBlankTrigger('zone_presence')],
    trigger_logic: 'or',
    trigger_window_s: 10,
    trigger_correlation_scope: 'same_subject',
    condition: {
      condition_id: uid('cnd'),
      type: 'and',
      children: [],
      params: {},
    },
    actions: [],
    log_blocked_evaluations: false,
  };
}

function normalizeSubjectFilter(sf) {
  const out = sf && typeof sf === 'object' ? sf : {};
  if (!Array.isArray(out.classes) || out.classes.length === 0) out.classes = ['any'];
  if (!out.face_mode) out.face_mode = 'any';
  if (!Array.isArray(out.identities)) out.identities = [];
  if (!out.plate_mode) out.plate_mode = 'any';
  if (!Array.isArray(out.plates)) out.plates = [];
  out.biometric_grace_s = roundClean(out.biometric_grace_s ?? 1.2, 2);
  return out;
}

function normalizeTrigger(trig) {
  if (!trig || typeof trig !== 'object') return createBlankTrigger('zone_presence');
  if (!trig.trigger_id) trig.trigger_id = uid('trg');
  if (!trig.type) trig.type = 'zone_presence';
  if (trig.enabled === undefined) trig.enabled = true;
  trig.subject_filter = normalizeSubjectFilter(trig.subject_filter);
  trig.params = trig.params && typeof trig.params === 'object' ? trig.params : {};
  return trig;
}

export function normalizeRule(rule) {
  if (!rule || typeof rule !== 'object') return createBlankRuleDraft();
  if (!rule.rule_id) rule.rule_id = uid('rule');
  if (typeof rule.name !== 'string') rule.name = '';
  if (typeof rule.description !== 'string') rule.description = '';
  if (rule.enabled === undefined) rule.enabled = true;
  if (!rule.execution_mode) rule.execution_mode = 'single';
  rule.cooldown_s = Number.isFinite(Number(rule.cooldown_s)) ? roundClean(rule.cooldown_s, 2) : 3;
  rule.pre_triggers = Array.isArray(rule.pre_triggers) ? rule.pre_triggers : [];
  for (const stg of rule.pre_triggers) {
    if (!stg.stage_id) stg.stage_id = uid('pre');
    stg.triggers = Array.isArray(stg.triggers) ? stg.triggers.map(normalizeTrigger) : [];
    if (!stg.match_mode) stg.match_mode = 'any';
    if (!stg.correlation_scope) stg.correlation_scope = 'same_subject';
    stg.max_wait_s = Number.isFinite(Number(stg.max_wait_s)) ? roundClean(stg.max_wait_s, 2) : 10;
    stg.min_delay_s = Number.isFinite(Number(stg.min_delay_s)) ? roundClean(stg.min_delay_s, 2) : 0;
    stg.stage_window_s = Number.isFinite(Number(stg.stage_window_s)) ? roundClean(stg.stage_window_s, 2) : 10;
  }
  rule.triggers = Array.isArray(rule.triggers) ? rule.triggers.map(normalizeTrigger) : [];
  if (!rule.trigger_logic) rule.trigger_logic = 'or';
  if (!Number.isFinite(Number(rule.trigger_window_s))) rule.trigger_window_s = 10;
  if (!rule.trigger_correlation_scope) rule.trigger_correlation_scope = 'same_subject';
  rule.log_blocked_evaluations = Boolean(rule.log_blocked_evaluations);
  if (!rule.condition || typeof rule.condition !== 'object') {
    rule.condition = {
      condition_id: uid('cnd'),
      type: 'and',
      children: [],
      params: {},
    };
  }
  if (!Array.isArray(rule.actions)) rule.actions = [];
  return rule;
}

export function normalizeZone(zone, existingZones = []) {
  const isPerim = zone?.geometry_type === 'perimeter';
  const yMinNum = Number(zone?.y_min);
  const yMaxNum = Number(zone?.y_max);
  const hystNum = Number(zone?.hysteresis_m);
  return {
    zone_id: zone?.zone_id || uid(isPerim ? 'perim' : 'zone'),
    name: typeof zone?.name === 'string' ? zone.name : (isPerim ? 'Nuovo perimetro' : 'Nuova area'),
    geometry_type: isPerim ? 'perimeter' : 'polygon',
    vertices: Array.isArray(zone?.vertices) ? zone.vertices.map((v) => ({ x: Number(v.x), z: Number(v.z) })) : [],
    y_min: Number.isFinite(yMinNum) ? yMinNum : -1.5,
    y_max: Number.isFinite(yMaxNum) ? yMaxNum : 4.0,
    normal_flipped: Boolean(zone?.normal_flipped),
    hysteresis_m: Number.isFinite(hystNum) ? Math.max(0, hystNum) : 0.12,
    color: zone?.color || pickDistinctZoneColor(existingZones, isPerim ? 'perimeter' : 'polygon'),
    enabled: zone?.enabled !== false,
  };
}

export function buildSnapshot(obj) {
  try {
    return JSON.stringify(obj ?? null);
  } catch {
    return '';
  }
}

export function isDirtySnapshot(snapshotStr, currentObj) {
  if (!snapshotStr) return false;
  return snapshotStr !== buildSnapshot(currentObj);
}

const SUBJECT_IT = {
  any: 'Qualsiasi soggetto',
  person: 'Una persona',
  vehicle: 'Un veicolo',
  dog: 'Un animale',
  bicycle: 'Una bicicletta',
};

const EVENT_IT = {
  enter: 'entra in',
  present: 'è presente in',
  exit: 'esce da',
  dwell: 'sosta in',
};

function describeTriggerItalian(trig, zoneNameById) {
  if (!trig) return 'evento';
  const p = trig.params || {};
  const sf = trig.subject_filter || {};
  const cls = Array.isArray(sf.classes) && sf.classes[0] ? sf.classes[0] : 'any';
  const subj = SUBJECT_IT[cls] || 'Un soggetto';

  if (trig.type === 'zone_presence') {
    const zName = zoneNameById.get(p.zone_id) || 'area da scegliere';
    const verb = EVENT_IT[p.event || 'enter'] || 'entra in';
    return `${subj} ${verb} ${zName}`;
  }
  if (trig.type === 'perimeter_crossing') {
    const zName = zoneNameById.get(p.perimeter_id) || 'perimetro da scegliere';
    return `${subj} attraversa ${zName}`;
  }
  if (trig.type === 'zone_transition') {
    const fromN = zoneNameById.get(p.from_zone_id) || 'Area A';
    const toN = zoneNameById.get(p.to_zone_id) || 'Area B';
    return `${subj} passa da ${fromN} a ${toN}`;
  }
  if (trig.type === 'kinematic_vector') {
    const minV = Number(p.min_speed_mps ?? 0);
    return `${subj} si muove (≥ ${minV} m/s)`;
  }
  if (trig.type === 'time_schedule') {
    if (p.mode === 'sunrise') return 'All’alba';
    if (p.mode === 'sunset') return 'Al tramonto';
    if (p.mode === 'interval') return `Ogni ${Number(p.interval_seconds ?? 60)}s`;
    return `Alle ${p.at || '22:00'}`;
  }
  if (trig.type === 'entity_state_change') {
    return `${p.entity_id || 'entità'} passa a ${p.to_state || 'on'}`;
  }
  if (trig.type === 'biometric_detection') {
    const zName = p.zone_id ? ` in ${zoneNameById.get(p.zone_id) || p.zone_id}` : '';
    return `Riconoscimento volto/targa${zName}`;
  }
  if (trig.type === 'proximity_3d') {
    return `${subj} vicino a punto 3D`;
  }
  if (trig.type === 'scene_event') {
    return 'Episodio scena';
  }
  return TRIGGER_TYPE_LABELS[trig.type] || trig.type;
}

function describeActionItalian(act) {
  if (!act) return '';
  const p = act.params || {};
  if (act.type === 'send_notification') {
    const nTargets = (p.mobile_targets?.length || 0) + (p.tts_targets?.length || 0) + (p.tv_targets?.length || 0);
    return nTargets > 0 ? `invia notifica (${nTargets})` : 'invia notifica';
  }
  if (act.type === 'call_ha_service') {
    return p.service ? `esegue ${p.service}` : 'chiama servizio HA';
  }
  if (act.type === 'set_virtual_entity') {
    return p.entity_id ? `aggiorna ${p.entity_id}` : 'aggiorna entità';
  }
  if (act.type === 'ui_alert') return 'mostra avviso 3D';
  if (act.type === 'delay') return `attende ${Number(p.seconds ?? 10)}s`;
  if (act.type === 'if_then_else') return 'esegue Se/Altrimenti';
  if (act.type === 'webhook') return 'invia webhook';
  return ACTION_TYPE_LABELS[act.type] || act.type;
}

export function buildRuleSummaryItalian(rule, { zones = [] } = {}) {
  if (!rule) return '';
  const zoneNameById = new Map((Array.isArray(zones) ? zones : []).map((z) => [z.zone_id, z.name]));
  const triggers = Array.isArray(rule.triggers) ? rule.triggers : [];
  const actions = Array.isArray(rule.actions) ? rule.actions : [];
  const preCount = Array.isArray(rule.pre_triggers) ? rule.pre_triggers.length : 0;
  const condCount = Array.isArray(rule.condition?.children) ? rule.condition.children.length : 0;

  const whenPart = triggers.length
    ? triggers.slice(0, 2).map((t) => describeTriggerItalian(t, zoneNameById)).join(rule.trigger_logic === 'and_within' ? ' e ' : ' o ')
    : 'nessun trigger';
  const prePart = preCount > 0 ? `Dopo ${preCount} pre-trigger: ` : '';
  const condPart = condCount > 0 ? ` (con ${condCount} ${condCount === 1 ? 'condizione' : 'condizioni'})` : '';
  const thenPart = actions.length
    ? actions.slice(0, 2).map(describeActionItalian).join(', ')
    : 'nessuna azione';

  return `${prePart}Quando ${whenPart}${condPart}, ${thenPart}.`;
}
