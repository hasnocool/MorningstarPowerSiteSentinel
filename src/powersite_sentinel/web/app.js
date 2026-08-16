const sitesRoot = document.querySelector('#sites');
const banner = document.querySelector('#banner');
const template = document.querySelector('#site-template');
const refreshButton = document.querySelector('#refresh');

const siteViews = new Map();
const forensicCache = new Map();
const FORENSIC_CACHE_MS = 5 * 60 * 1000;
const LIVE_REFRESH_MS = 15 * 1000;
let refreshInFlight = null;

const metricValue = (metric) => (
  metric && typeof metric === 'object' && Number.isFinite(metric.value) ? metric.value : null
);

function setText(node, value) {
  if (!node) return;
  const next = value === null || value === undefined ? '—' : String(value);
  if (node.textContent === next) return;
  node.textContent = next;
  node.classList.remove('live-update-flash');
  void node.offsetWidth;
  node.classList.add('live-update-flash');
}

function formatNumber(value, unit = '', digits = 1, missing = 'unmeasured') {
  if (!Number.isFinite(value)) return missing;
  const rounded = Math.abs(value) >= 100 ? Math.round(value).toString() : value.toFixed(digits);
  return unit ? `${rounded} ${unit}` : rounded;
}

function formatPower(metric, missing = 'unmeasured') {
  const value = metricValue(metric);
  if (value === null) return missing;
  const magnitude = Math.abs(value);
  const digits = magnitude > 0 && magnitude < 1 ? 2 : magnitude < 10 ? 1 : 0;
  return formatNumber(value, metric?.unit || 'W', digits, missing);
}

function formatMetric(metric, fallbackUnit = '', digits = 1, missing = 'unmeasured') {
  return formatNumber(metricValue(metric), metric?.unit || fallbackUnit, digits, missing);
}

function formatStateMetric(metric, missing = 'unmeasured') {
  const value = metric?.value;
  if (Array.isArray(value)) return value.length ? value.join(', ') : 'clear';
  if (value === null || value === undefined || value === '') return missing;
  return String(value);
}

function relativeAge(timestamp) {
  if (!timestamp) return 'no timestamp';
  const time = Date.parse(timestamp);
  if (!Number.isFinite(time)) return 'unknown age';
  const seconds = Math.max(0, Math.round((Date.now() - time) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h ago`;
  return `${(seconds / 86400).toFixed(1)}d ago`;
}

function labelize(value) {
  return String(value)
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function displayValue(value) {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  if (typeof value === 'number') {
    return Number.isInteger(value)
      ? String(value)
      : value.toFixed(3).replace(/0+$/, '').replace(/\.$/, '');
  }
  if (Array.isArray(value)) {
    if (!value.length) return 'none';
    if (value.every((item) => ['string', 'number', 'boolean'].includes(typeof item))) {
      return value.join(', ');
    }
    return `${value.length} record${value.length === 1 ? '' : 's'}`;
  }
  if (typeof value === 'object') return 'structured data';
  return String(value);
}

async function json(path) {
  const response = await fetch(path, {
    cache: 'no-store',
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
  return response.json();
}

async function getForensics(uid, force = false) {
  const cached = forensicCache.get(uid);
  if (!force && cached && Date.now() - cached.fetchedAt < FORENSIC_CACHE_MS) {
    return cached.payload;
  }
  const payload = await json(`/v1/sites/${encodeURIComponent(uid)}/forensics?days=30`);
  forensicCache.set(uid, { fetchedAt: Date.now(), payload });
  return payload;
}

function controllerUid(controller) {
  return String(controller?.controller_uid || controller?.controller_id || '');
}

function controllerIdentityKey(controller) {
  const serial = String(controller?.serial_number || '').trim().toLowerCase();
  const profile = String(controller?.profile || controller?.family || '').trim().toLowerCase();
  if (serial) return `serial:${profile}:${serial}`;

  const currentDeviceId = String(controller?.current_device_id || '').trim();
  if (currentDeviceId) return `device:${currentDeviceId}`;

  const connection = controller?.current_connection;
  if (connection && typeof connection === 'object') {
    const transport = String(connection.transport || '').trim();
    const target = String(connection.target || '').trim();
    const unit = String(connection.unit_id ?? '').trim();
    if (transport || target || unit) return `connection:${transport}:${target}:${unit}`;
  }

  const uid = controllerUid(controller);
  return uid ? `uid:${uid}` : `anonymous:${JSON.stringify(controller)}`;
}

function controllerPreference(controller) {
  const online = String(controller?.status || '').toLowerCase() === 'online' ? 1 : 0;
  const seen = Date.parse(controller?.last_seen || controller?.updated_at || '') || 0;
  const identified = controller?.serial_number ? 1 : 0;
  return [online, identified, seen];
}

function preferController(candidate, current) {
  if (!current) return candidate;
  const left = controllerPreference(candidate);
  const right = controllerPreference(current);
  for (let index = 0; index < left.length; index += 1) {
    if (left[index] > right[index]) return candidate;
    if (left[index] < right[index]) return current;
  }
  return current;
}

function dedupeControllers(controllers) {
  const unique = new Map();
  for (const controller of Array.isArray(controllers) ? controllers : []) {
    if (!controller || typeof controller !== 'object') continue;
    const key = controllerIdentityKey(controller);
    unique.set(key, preferController(controller, unique.get(key)));
  }
  return [...unique.values()];
}

function controllerStatus(controllers) {
  if (!controllers.length) return 'No controller inventory';
  const online = controllers.filter(
    (item) => String(item?.status || '').toLowerCase() === 'online',
  ).length;
  if (online === controllers.length) {
    return `${online}/${controllers.length} controller${controllers.length === 1 ? '' : 's'} online`;
  }
  return `${online}/${controllers.length} controllers online`;
}

function syncFacts(root, entries) {
  const wanted = new Set();
  for (const [key, label, value] of entries) {
    wanted.add(key);
    let item = [...root.children].find((child) => child.dataset.factKey === key);
    if (!item) {
      item = document.createElement('div');
      item.className = 'fact';
      item.dataset.factKey = key;
      const name = document.createElement('span');
      const content = document.createElement('strong');
      item.append(name, content);
    }
    setText(item.querySelector('span'), label);
    setText(item.querySelector('strong'), displayValue(value));
    root.append(item);
  }
  for (const child of [...root.children]) {
    if (child.dataset.factKey && !wanted.has(child.dataset.factKey)) child.remove();
  }
}

function primitiveFactEntries(record, preferred = []) {
  if (!record || typeof record !== 'object') return [];
  const entries = [];
  const used = new Set();
  for (const key of preferred) {
    if (!(key in record)) continue;
    entries.push([key, labelize(key), record[key]]);
    used.add(key);
  }
  for (const [key, value] of Object.entries(record)) {
    if (used.has(key) || (value && typeof value === 'object')) continue;
    entries.push([key, labelize(key), value]);
  }
  return entries;
}

function normalizedMetricObserved(metric) {
  if (!metric || typeof metric !== 'object') return false;
  if (metric.value !== null && metric.value !== undefined) return true;
  if (Number(metric.contributors || 0) > 0) return true;
  return ['complete', 'partial', 'derived'].includes(String(metric.quality || '').toLowerCase());
}

function formatNormalizedMetric(metric) {
  if (!metric || typeof metric !== 'object') return '—';
  if (Array.isArray(metric.value)) return metric.value.length ? metric.value.join(', ') : 'clear';
  if (Number.isFinite(metric.value)) return formatNumber(metric.value, metric.unit || '', 2);
  if (metric.value !== null && metric.value !== undefined) return displayValue(metric.value);
  return 'unmeasured';
}

function ensureMetricRow(view, name) {
  let row = view.metricRows.get(name);
  if (row) return row;
  row = document.createElement('tr');
  row.dataset.metricName = name;
  for (let index = 0; index < 4; index += 1) row.append(document.createElement('td'));
  view.refs.siteMetrics.append(row);
  view.metricRows.set(name, row);
  return row;
}

function syncMetrics(view, metrics) {
  const entries = Object.entries(metrics || {});
  const measured = entries.filter(([, metric]) => normalizedMetricObserved(metric));
  const unmeasured = entries.filter(([, metric]) => !normalizedMetricObserved(metric));
  const wanted = new Set(entries.map(([name]) => name));

  for (const [name, metric] of [...measured, ...unmeasured]) {
    const row = ensureMetricRow(view, name);
    const sources = Array.isArray(metric?.sources)
      ? metric.sources.length
      : Number(metric?.contributors ?? 0);
    const expected = Number(metric?.expected_contributors ?? 0);
    const sourceText = expected > 0 ? `${sources}/${expected}` : String(sources || '—');
    const values = [
      labelize(name),
      formatNormalizedMetric(metric),
      metric?.quality || metric?.status || '—',
      sourceText,
    ];
    [...row.children].forEach((cell, index) => setText(cell, values[index]));
    const hidden = !normalizedMetricObserved(metric) && !view.showUnmeasured;
    row.hidden = hidden;
    row.classList.toggle('unmeasured-row', !normalizedMetricObserved(metric));
    view.refs.siteMetrics.append(row);
  }

  for (const [name, row] of [...view.metricRows.entries()]) {
    if (wanted.has(name)) continue;
    row.remove();
    view.metricRows.delete(name);
  }

  setText(
    view.refs.metricVisibilitySummary,
    unmeasured.length
      ? `${measured.length} measured/observed metrics shown · ${unmeasured.length} unsupported or unmeasured ${view.showUnmeasured ? 'shown' : 'hidden'}`
      : `${measured.length} measured/observed metrics shown`,
  );
  view.refs.metricVisibilityToggle.hidden = unmeasured.length === 0;
  setText(
    view.refs.metricVisibilityToggle,
    view.showUnmeasured ? 'Hide unmeasured' : `Show ${unmeasured.length} unmeasured`,
  );
}

function ledgerEntries(ledger) {
  if (!ledger || typeof ledger !== 'object') return [];
  const entries = [
    ['period', 'Period', ledger.period || 'unknown'],
    ['quality', 'Quality', ledger.quality || 'unknown'],
  ];
  for (const [groupName, group] of Object.entries({
    flows: ledger.flows || {},
    counters: ledger.counters || {},
  })) {
    for (const [name, field] of Object.entries(group)) {
      if (!field || typeof field !== 'object' || !Number.isFinite(field.value)) continue;
      const digits = Math.abs(field.value) >= 100 ? 0 : 2;
      entries.push([
        `${groupName}.${name}`,
        `${labelize(groupName)} · ${labelize(name)}`,
        formatNumber(field.value, field.unit || '', digits, ''),
      ]);
    }
  }
  return entries;
}

function syncEnergyLedger(view, ledger) {
  syncFacts(view.refs.energyLedger, ledgerEntries(ledger));
  const missing = [];
  for (const group of [ledger?.flows || {}, ledger?.counters || {}]) {
    for (const [name, field] of Object.entries(group)) {
      if (field && typeof field === 'object' && Number.isFinite(field.value)) continue;
      missing.push(field?.reason ? `${labelize(name)}: ${field.reason}` : labelize(name));
    }
  }

  let note = view.refs.energyLedger.querySelector('.ledger-note');
  if (!missing.length) {
    note?.remove();
    return;
  }
  if (!note) {
    note = document.createElement('details');
    note.className = 'ledger-note';
    note.append(document.createElement('summary'), document.createElement('ul'));
    view.refs.energyLedger.append(note);
  }
  setText(note.querySelector('summary'), `${missing.length} unavailable ledger field${missing.length === 1 ? '' : 's'} hidden`);
  const list = note.querySelector('ul');
  const signature = JSON.stringify(missing.slice(0, 12));
  if (list.dataset.signature !== signature) {
    list.dataset.signature = signature;
    list.replaceChildren();
    for (const reason of missing.slice(0, 12)) {
      const item = document.createElement('li');
      item.textContent = reason;
      list.append(item);
    }
  }
}

function syncEvents(root, events) {
  const rows = Array.isArray(events) ? events.slice(0, 10) : [];
  const wanted = new Set();
  for (const event of rows) {
    const key = String(
      event.id
      ?? event.dedupe_key
      ?? `${event.observed_at || event.created_at || ''}:${event.event_type || event.type || ''}:${event.message || ''}`,
    );
    wanted.add(key);
    let item = [...root.children].find((child) => child.dataset.eventKey === key);
    if (!item) {
      item = document.createElement('div');
      item.className = 'event-item';
      item.dataset.eventKey = key;
      item.append(document.createElement('strong'), document.createElement('span'), document.createElement('p'));
    }
    const title = event.title || event.code || event.event_type || event.type || event.event || 'Site event';
    const timestamp = event.observed_at || event.created_at || event.timestamp || event.at;
    const severity = event.severity ? `${String(event.severity).toUpperCase()} · ` : '';
    setText(item.querySelector('strong'), labelize(title));
    setText(item.querySelector('span'), timestamp ? `${severity}${relativeAge(timestamp)} · ${timestamp}` : `${severity}Timestamp unavailable`);
    const summary = item.querySelector('p');
    setText(summary, event.summary || event.message || event.detail || event.status || '');
    summary.hidden = !summary.textContent;
    root.append(item);
  }

  for (const child of [...root.children]) {
    if (child.dataset.eventKey && !wanted.has(child.dataset.eventKey)) child.remove();
  }
  if (!rows.length) {
    let empty = root.querySelector('.empty-detail');
    if (!empty) {
      empty = document.createElement('p');
      empty.className = 'empty-detail';
      root.append(empty);
    }
    setText(empty, 'No recent site events were reported.');
  } else {
    root.querySelector('.empty-detail')?.remove();
  }
}

function controllerFactEntries(controller) {
  const entries = primitiveFactEntries(controller, [
    'controller_uid',
    'controller_id',
    'model',
    'family',
    'serial_number',
    'profile',
    'status',
    'identity_source',
    'first_seen',
    'last_seen',
    'connection_count',
    'active_connection_count',
  ]);
  const connection = controller?.current_connection;
  if (connection && typeof connection === 'object') {
    for (const [key, value] of Object.entries(connection)) {
      if (value && typeof value === 'object') continue;
      entries.push([`connection.${key}`, `Connection · ${labelize(key)}`, value]);
    }
  }
  return entries;
}

function ensureControllerView(siteView, key) {
  let controllerView = siteView.controllerViews.get(key);
  if (controllerView) return controllerView;

  const item = document.createElement('article');
  item.className = 'controller-inspector';
  item.dataset.controllerKey = key;
  const toggle = document.createElement('button');
  toggle.className = 'controller-toggle';
  toggle.type = 'button';
  toggle.setAttribute('aria-expanded', 'false');
  const identity = document.createElement('span');
  identity.className = 'controller-identity';
  identity.append(document.createElement('strong'), document.createElement('span'));
  const action = document.createElement('span');
  action.className = 'controller-action';
  const state = document.createElement('span');
  state.className = 'status-pill';
  const chevron = document.createElement('span');
  chevron.className = 'controller-chevron';
  chevron.textContent = '⌄';
  action.append(state, chevron);
  toggle.append(identity, action);

  const detail = document.createElement('div');
  detail.className = 'controller-detail';
  detail.hidden = true;
  const title = document.createElement('h4');
  title.textContent = 'Controller identity & connection';
  const facts = document.createElement('div');
  facts.className = 'fact-grid';
  detail.append(title, facts);

  toggle.addEventListener('click', () => {
    detail.hidden = !detail.hidden;
    toggle.setAttribute('aria-expanded', String(!detail.hidden));
    chevron.textContent = detail.hidden ? '⌄' : '⌃';
  });

  item.append(toggle, detail);
  siteView.refs.controllerList.append(item);
  controllerView = { item, toggle, identity, state, chevron, detail, facts };
  siteView.controllerViews.set(key, controllerView);
  return controllerView;
}

function syncControllers(siteView, controllers) {
  const wanted = new Set();
  for (const controller of controllers) {
    const key = controllerIdentityKey(controller);
    wanted.add(key);
    const controllerView = ensureControllerView(siteView, key);
    const uid = controllerUid(controller);
    const name = controller.model || controller.family || controller.profile || uid || 'Controller';
    setText(controllerView.identity.querySelector('strong'), name);
    setText(
      controllerView.identity.querySelector('span'),
      [controller.serial_number, controller.profile, uid].filter(Boolean).join(' · '),
    );
    const state = String(controller.status || 'unknown').toLowerCase();
    controllerView.state.className = `status-pill ${state}`;
    setText(controllerView.state, state);
    syncFacts(controllerView.facts, controllerFactEntries(controller));
    siteView.refs.controllerList.append(controllerView.item);
  }

  for (const [key, controllerView] of [...siteView.controllerViews.entries()]) {
    if (wanted.has(key)) continue;
    controllerView.item.remove();
    siteView.controllerViews.delete(key);
  }

  if (!controllers.length) {
    let empty = siteView.refs.controllerList.querySelector('.empty-detail');
    if (!empty) {
      empty = document.createElement('p');
      empty.className = 'empty-detail';
      siteView.refs.controllerList.append(empty);
    }
    setText(empty, 'No controllers are currently enrolled in this site.');
  } else {
    siteView.refs.controllerList.querySelector('.empty-detail')?.remove();
  }
}

function findingKey(item, index) {
  return String(item.fingerprint || `${item.code || item.title || 'finding'}:${index}`);
}

function syncFindings(root, findings, accountingLimited) {
  const visible = (findings || []).filter((item) => item.severity !== 'info').slice(0, 4);
  const wanted = new Set();

  visible.forEach((finding, index) => {
    const key = findingKey(finding, index);
    wanted.add(key);
    let row = [...root.children].find((child) => child.dataset.findingKey === key);
    if (!row) {
      row = document.createElement('div');
      row.dataset.findingKey = key;
      row.append(document.createElement('strong'), document.createElement('span'));
    }
    row.className = `finding ${finding.severity || 'info'}`;
    setText(row.querySelector('strong'), finding.title || 'Finding');
    setText(row.querySelector('span'), finding.summary || '');
    root.append(row);
  });

  if (!visible.length) {
    const key = 'clear';
    wanted.add(key);
    let clear = [...root.children].find((child) => child.dataset.findingKey === key);
    if (!clear) {
      clear = document.createElement('div');
      clear.dataset.findingKey = key;
      clear.className = 'finding clear';
    }
    setText(
      clear,
      accountingLimited
        ? 'No evidence-backed warning or critical finding is active in controller telemetry; whole-site accounting remains partially instrumented.'
        : 'No evidence-backed warning or critical finding is active.',
    );
    root.append(clear);
  }

  for (const child of [...root.children]) {
    if (child.dataset.findingKey && !wanted.has(child.dataset.findingKey)) child.remove();
  }
}

function ensureForensicTimelineEvent(root, key) {
  let row = [...root.children].find((child) => child.dataset.timelineKey === key);
  if (row) return row;
  row = document.createElement('div');
  row.className = 'timeline-event';
  row.dataset.timelineKey = key;
  const top = document.createElement('div');
  top.className = 'timeline-event-heading';
  top.append(document.createElement('strong'), document.createElement('span'));
  top.querySelector('span').className = 'mono';
  row.append(top, document.createElement('span'));
  root.append(row);
  return row;
}

function syncForensics(view, forensic) {
  const period = forensic?.period ?? {};
  const summary = forensic?.summary ?? {};
  setText(
    view.refs.forensicPeriod,
    period.from && period.to ? `${period.from} → ${period.to}` : 'history unavailable',
  );

  if (forensic?.error) {
    setText(view.refs.forensicStatus, 'unavailable');
    view.refs.forensicStatus.className = 'forensic-status bad';
    setText(view.refs.historyCoverage, '—');
    setText(view.refs.historyMissing, '—');
    setText(view.refs.historyRecovered, '—');
    setText(view.refs.energyDiscrepancies, '—');
    const key = 'forensic-error';
    const row = ensureForensicTimelineEvent(view.refs.timelinePreview, key);
    row.className = 'timeline-event warning';
    setText(row.querySelector('strong'), 'Historical diagnostics unavailable');
    setText(row.querySelector('.mono'), '');
    setText(row.lastElementChild, forensic.error);
    for (const child of [...view.refs.timelinePreview.children]) {
      if (child.dataset.timelineKey && child.dataset.timelineKey !== key) child.remove();
    }
    return;
  }

  const missing = summary.missing_controller_days ?? 0;
  const discrepancies = summary.energy_discrepancy_controller_days ?? 0;
  setText(view.refs.forensicStatus, missing || discrepancies ? 'attention' : 'continuous');
  view.refs.forensicStatus.className = `forensic-status ${missing || discrepancies ? 'warn' : 'good'}`;
  const coverage = summary.minimum_daily_evidence_percent;
  setText(view.refs.historyCoverage, Number.isFinite(coverage) ? `${coverage}%` : 'unknown');
  setText(view.refs.historyMissing, missing);
  setText(view.refs.historyRecovered, summary.recovered_controller_days ?? 0);
  setText(view.refs.energyDiscrepancies, discrepancies);

  const events = (forensic?.timeline?.events ?? []).slice(0, 5);
  const wanted = new Set();
  events.forEach((item, index) => {
    const key = String(item.id ?? `${item.observed_at || ''}:${item.event_type || item.title || index}`);
    wanted.add(key);
    const row = ensureForensicTimelineEvent(view.refs.timelinePreview, key);
    row.className = `timeline-event ${item.severity ?? 'info'}`;
    setText(row.querySelector('strong'), item.title ?? item.event_type ?? 'Event');
    setText(
      row.querySelector('.mono'),
      item.observed_at ? String(item.observed_at).replace('T', ' ').slice(0, 19) : 'unknown time',
    );
    setText(row.lastElementChild, item.message ?? item.event_type ?? '');
    view.refs.timelinePreview.append(row);
  });

  if (!events.length) {
    const key = 'forensic-clear';
    wanted.add(key);
    const row = ensureForensicTimelineEvent(view.refs.timelinePreview, key);
    row.className = 'timeline-event clear';
    setText(row.querySelector('strong'), 'No forensic timeline events in this window.');
    setText(row.querySelector('.mono'), '');
    setText(row.lastElementChild, '');
  }

  for (const child of [...view.refs.timelinePreview.children]) {
    if (child.dataset.timelineKey && !wanted.has(child.dataset.timelineKey)) child.remove();
  }
}

function createSiteView(siteUid) {
  const fragment = template.content.cloneNode(true);
  const card = fragment.querySelector('.site-card');
  card.dataset.siteUid = siteUid;
  const refs = {
    siteToggle: fragment.querySelector('.site-toggle'),
    siteName: fragment.querySelector('.site-name'),
    siteId: fragment.querySelector('.site-id'),
    siteStatus: fragment.querySelector('.site-status'),
    score: fragment.querySelector('.score'),
    observability: fragment.querySelector('.observability'),
    controllers: fragment.querySelector('.controllers'),
    incidents: fragment.querySelector('.incidents'),
    solar: fragment.querySelector('.solar'),
    battery: fragment.querySelector('.battery'),
    loads: fragment.querySelector('.loads'),
    explanation: fragment.querySelector('.explanation'),
    findings: fragment.querySelector('.findings'),
    siteDetails: fragment.querySelector('.site-details'),
    inspectLabel: fragment.querySelector('.inspect-label'),
    assessedAt: fragment.querySelector('.assessed-at'),
    siteFacts: fragment.querySelector('.site-facts'),
    controllerList: fragment.querySelector('.controller-list'),
    siteMetrics: fragment.querySelector('.site-metrics'),
    metricVisibilitySummary: fragment.querySelector('.metric-visibility-summary'),
    metricVisibilityToggle: fragment.querySelector('.metric-visibility-toggle'),
    energyLedger: fragment.querySelector('.energy-ledger'),
    recentEvents: fragment.querySelector('.recent-events'),
    forensicPeriod: fragment.querySelector('.forensic-period'),
    forensicStatus: fragment.querySelector('.forensic-status'),
    historyCoverage: fragment.querySelector('.history-coverage'),
    historyMissing: fragment.querySelector('.history-missing'),
    historyRecovered: fragment.querySelector('.history-recovered'),
    energyDiscrepancies: fragment.querySelector('.energy-discrepancies'),
    timelinePreview: fragment.querySelector('.timeline-preview'),
  };

  const view = {
    siteUid,
    card,
    refs,
    metricRows: new Map(),
    controllerViews: new Map(),
    showUnmeasured: false,
    assessedAt: null,
    latestObservedAt: null,
  };

  refs.siteToggle.addEventListener('click', () => {
    refs.siteDetails.hidden = !refs.siteDetails.hidden;
    const expanded = !refs.siteDetails.hidden;
    refs.siteToggle.setAttribute('aria-expanded', String(expanded));
    refs.inspectLabel.innerHTML = expanded
      ? 'Close site <span class="chevron">⌃</span>'
      : 'Inspect site <span class="chevron">⌄</span>';
  });

  refs.metricVisibilityToggle.addEventListener('click', () => {
    view.showUnmeasured = !view.showUnmeasured;
    if (view.latestMetrics) syncMetrics(view, view.latestMetrics);
  });

  sitesRoot.append(fragment);
  siteViews.set(siteUid, view);
  return view;
}

function updateSiteView(view, site, assessment, explanation, forensic) {
  const health = assessment.health?.overall ?? {};
  const snapshot = assessment.snapshot ?? {};
  const controllers = dedupeControllers(snapshot.controllers);
  const latest = snapshot.latest ?? {};
  const metrics = latest.metrics ?? {};
  const flow = snapshot.power_flow ?? {};
  const accounting = assessment.health?.power_accounting ?? {};
  const accountingLimited = Number(accounting.value ?? 0) < 80;

  view.card.dataset.status = health.status ?? 'unknown';
  setText(view.refs.siteName, site.name || site.system_uid || view.siteUid);
  setText(view.refs.siteId, site.system_uid || view.siteUid);
  setText(view.refs.siteStatus, controllerStatus(controllers));
  setText(view.refs.score, health.value ?? '—');
  setText(view.refs.observability, `${assessment.health?.observability?.value ?? 0}%`);
  setText(view.refs.controllers, controllers.length);
  setText(view.refs.incidents, assessment.open_incidents?.length ?? 0);
  setText(view.refs.solar, formatPower(metrics.solar_input_power_w || flow.sources?.solar_input_power_w));
  setText(view.refs.battery, formatPower(flow.battery?.net_power_w));
  setText(view.refs.loads, formatPower(flow.loads?.dc_power_w));
  setText(view.refs.explanation, explanation.headline || 'No explanation is currently available.');
  syncFindings(view.refs.findings, assessment.findings, accountingLimited);

  view.assessedAt = assessment.assessed_at || null;
  view.latestObservedAt = latest.observed_at || flow.observed_at || null;
  setText(view.refs.assessedAt, view.assessedAt ? `Assessed ${relativeAge(view.assessedAt)}` : 'Assessment time unavailable');

  const siteRecord = {
    ...(snapshot.site || site || {}),
    controller_count: controllers.length,
  };
  const siteFacts = primitiveFactEntries(siteRecord, [
    'name',
    'system_uid',
    'controller_count',
    'status',
    'created_at',
    'updated_at',
    'description',
    'auto_discover',
  ]);
  siteFacts.push(['upstream', 'Upstream', assessment.upstream?.stale ? 'stale / reconnecting' : 'reachable']);
  siteFacts.push(['latest_telemetry', 'Latest telemetry', view.latestObservedAt || 'unavailable']);
  syncFacts(view.refs.siteFacts, siteFacts);
  syncControllers(view, controllers);
  view.latestMetrics = metrics;
  syncMetrics(view, metrics);
  syncEnergyLedger(view, snapshot.energy_ledger || {});
  syncEvents(view.refs.recentEvents, snapshot.events);
  syncForensics(view, forensic);
}

function updateRelativeAges() {
  for (const view of siteViews.values()) {
    if (view.assessedAt) setText(view.refs.assessedAt, `Assessed ${relativeAge(view.assessedAt)}`);
    for (const event of view.refs.recentEvents.querySelectorAll('.event-item')) {
      // Event timestamps are refreshed from the network payload; avoid rewriting them here.
      event.classList.remove('live-update-flash');
    }
  }
}

async function refresh(forceForensics = false) {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    refreshButton.disabled = true;
    if (!siteViews.size) {
      banner.textContent = 'Connecting to Sentinel…';
      banner.className = 'banner';
    }

    try {
      const sites = await json('/v1/sites');
      const seen = new Set();
      if (!sites.length) {
        banner.textContent = 'No Morningstar systems are currently reported by the upstream API.';
        banner.className = 'banner';
        for (const view of siteViews.values()) view.card.remove();
        siteViews.clear();
        return;
      }

      const results = await Promise.all(sites.map(async (site) => {
        const siteUid = String(site.system_uid || site.name);
        const encodedUid = encodeURIComponent(siteUid);
        const [assessment, explanation] = await Promise.all([
          json(`/v1/sites/${encodedUid}/assessment`),
          json(`/v1/sites/${encodedUid}/explain`),
        ]);
        let forensic;
        try {
          forensic = await getForensics(siteUid, forceForensics);
        } catch (error) {
          forensic = { error: error.message };
        }
        return { siteUid, site, assessment, explanation, forensic };
      }));

      for (const result of results) {
        seen.add(result.siteUid);
        const view = siteViews.get(result.siteUid) || createSiteView(result.siteUid);
        updateSiteView(view, result.site, result.assessment, result.explanation, result.forensic);
      }

      for (const [siteUid, view] of [...siteViews.entries()]) {
        if (seen.has(siteUid)) continue;
        view.card.remove();
        siteViews.delete(siteUid);
        forensicCache.delete(siteUid);
      }

      setText(banner, `Monitoring ${sites.length} site${sites.length === 1 ? '' : 's'}. Live values update in place.`);
      banner.className = 'banner ok';
    } catch (error) {
      setText(banner, `Sentinel could not read the upstream site model: ${error.message}`);
      banner.className = 'banner error';
    } finally {
      refreshButton.disabled = false;
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

refreshButton.addEventListener('click', () => refresh(true));
refresh();
setInterval(() => refresh(false), LIVE_REFRESH_MS);
setInterval(updateRelativeAges, 1000);
