const sitesRoot = document.querySelector('#sites');
const banner = document.querySelector('#banner');
const template = document.querySelector('#site-template');
const refreshButton = document.querySelector('#refresh');

const openSites = new Set();
const openControllers = new Set();
const controllerDetailCache = new Map();

const metricValue = (metric) => (
  metric && typeof metric === 'object' && Number.isFinite(metric.value) ? metric.value : null
);

const formatNumber = (value, unit, digits = 1, missing = 'unmeasured') => {
  if (!Number.isFinite(value)) return missing;
  const rounded = Math.abs(value) >= 100 ? Math.round(value).toString() : value.toFixed(digits);
  return unit ? `${rounded} ${unit}` : rounded;
};

const formatMetric = (metric, fallbackUnit = '', digits = 1, missing = 'unmeasured') => (
  formatNumber(metricValue(metric), metric?.unit || fallbackUnit, digits, missing)
);

const formatStateMetric = (metric, missing = 'unmeasured') => {
  const value = metric?.value;
  if (Array.isArray(value)) return value.length ? value.join(', ') : 'clear';
  if (value === null || value === undefined || value === '') return missing;
  return String(value);
};

const relativeAge = (timestamp) => {
  if (!timestamp) return 'no timestamp';
  const time = Date.parse(timestamp);
  if (!Number.isFinite(time)) return 'unknown age';
  const seconds = Math.max(0, Math.round((Date.now() - time) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  return `${(seconds / 3600).toFixed(1)}h ago`;
};

const labelize = (value) => String(value)
  .replaceAll('_', ' ')
  .replace(/\b\w/g, (letter) => letter.toUpperCase());

const displayValue = (value) => {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(3).replace(/0+$/, '').replace(/\.$/, '');
  if (Array.isArray(value)) {
    if (!value.length) return 'none';
    if (value.every((item) => ['string', 'number', 'boolean'].includes(typeof item))) return value.join(', ');
    return `${value.length} record${value.length === 1 ? '' : 's'}`;
  }
  if (typeof value === 'object') return 'available';
  return String(value);
};

async function json(path) {
  const response = await fetch(path, { headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
  return response.json();
}

function renderFinding(item) {
  const row = document.createElement('div');
  row.className = `finding ${item.severity}`;

  const title = document.createElement('strong');
  title.textContent = String(item.title ?? 'Finding');
  const summary = document.createElement('span');
  summary.textContent = String(item.summary ?? '');
  row.append(title, summary);
  return row;
}

function controllerStatus(controllers) {
  if (!Array.isArray(controllers) || !controllers.length) return 'No controller inventory';
  const online = controllers.filter((item) => String(item?.status || '').toLowerCase() === 'online').length;
  if (online === controllers.length) return `${online}/${controllers.length} controller${controllers.length === 1 ? '' : 's'} online`;
  return `${online}/${controllers.length} controllers online`;
}

function accountingGapText(flow) {
  const missing = [];
  if (metricValue(flow.battery?.net_power_w) === null) missing.push('battery net flow');
  if (metricValue(flow.loads?.dc_power_w) === null) missing.push('DC load power');
  if (metricValue(flow.battery?.soc_percent) === null) missing.push('battery SOC');
  if (!missing.length) {
    return 'Core whole-site measurements are source-backed and currently available.';
  }
  return `${missing.join(', ')} ${missing.length === 1 ? 'is' : 'are'} not directly measured by the current instrumentation. This reduces whole-site accounting coverage but is not an active controller fault.`;
}

function appendFact(root, label, value) {
  const item = document.createElement('div');
  item.className = 'fact';
  const name = document.createElement('span');
  name.textContent = label;
  const content = document.createElement('strong');
  content.textContent = displayValue(value);
  item.append(name, content);
  root.append(item);
}

function flattenRecord(record, prefix = '', depth = 0) {
  if (!record || typeof record !== 'object' || Array.isArray(record)) return [];
  const output = [];
  for (const [key, value] of Object.entries(record)) {
    const label = prefix ? `${prefix} · ${labelize(key)}` : labelize(key);
    if (value && typeof value === 'object' && !Array.isArray(value) && depth < 1) {
      output.push(...flattenRecord(value, label, depth + 1));
    } else {
      output.push([label, value]);
    }
  }
  return output;
}

function renderFacts(root, record, preferred = []) {
  root.replaceChildren();
  if (!record || typeof record !== 'object') {
    appendFact(root, 'State', 'unavailable');
    return;
  }

  const used = new Set();
  for (const key of preferred) {
    if (!(key in record)) continue;
    appendFact(root, labelize(key), record[key]);
    used.add(key);
  }
  for (const [key, value] of Object.entries(record)) {
    if (used.has(key) || (value && typeof value === 'object')) continue;
    appendFact(root, labelize(key), value);
  }
}

function renderFlatFacts(root, record, limit = 24) {
  root.replaceChildren();
  const entries = flattenRecord(record).slice(0, limit);
  if (!entries.length) {
    appendFact(root, 'State', 'No data reported');
    return;
  }
  entries.forEach(([label, value]) => appendFact(root, label, value));
}

function formatNormalizedMetric(metric) {
  if (!metric || typeof metric !== 'object') return '—';
  if (Array.isArray(metric.value)) return metric.value.length ? metric.value.join(', ') : 'clear';
  if (Number.isFinite(metric.value)) return formatNumber(metric.value, metric.unit || '', 2);
  if (metric.value !== null && metric.value !== undefined) return displayValue(metric.value);
  return 'unmeasured';
}

function renderSiteMetrics(root, metrics) {
  root.replaceChildren();
  for (const [name, metric] of Object.entries(metrics || {})) {
    const row = document.createElement('tr');
    const sources = Array.isArray(metric?.sources) ? metric.sources.length : Number(metric?.contributors ?? 0);
    const expected = Number(metric?.expected_contributors ?? 0);
    const sourceText = expected > 0 ? `${sources}/${expected}` : String(sources || '—');
    [labelize(name), formatNormalizedMetric(metric), metric?.quality || metric?.status || '—', sourceText]
      .forEach((value) => {
        const cell = document.createElement('td');
        cell.textContent = String(value);
        row.append(cell);
      });
    root.append(row);
  }
  if (!root.children.length) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 4;
    cell.textContent = 'No normalized site metrics are available.';
    row.append(cell);
    root.append(row);
  }
}

function renderEvents(root, payload) {
  root.replaceChildren();
  const events = Array.isArray(payload) ? payload : Array.isArray(payload?.events) ? payload.events : [];
  if (!events.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-detail';
    empty.textContent = 'No recent site events were reported.';
    root.append(empty);
    return;
  }

  events.slice(0, 10).forEach((event) => {
    const item = document.createElement('div');
    item.className = 'event-item';
    const title = document.createElement('strong');
    title.textContent = String(event.title || event.code || event.type || event.event || 'Site event');
    const meta = document.createElement('span');
    const timestamp = event.observed_at || event.created_at || event.timestamp || event.at;
    meta.textContent = timestamp ? `${relativeAge(timestamp)} · ${timestamp}` : 'Timestamp unavailable';
    const summary = document.createElement('p');
    summary.textContent = String(event.summary || event.message || event.detail || event.status || '');
    item.append(title, meta);
    if (summary.textContent) item.append(summary);
    root.append(item);
  });
}

function controllerUid(controller) {
  return String(controller?.controller_uid || controller?.controller_id || '');
}

function renderConnections(root, connections) {
  root.replaceChildren();
  if (!Array.isArray(connections) || !connections.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-detail';
    empty.textContent = 'No connection history reported.';
    root.append(empty);
    return;
  }

  const wrapper = document.createElement('div');
  wrapper.className = 'table-scroll';
  const table = document.createElement('table');
  table.className = 'detail-table';
  table.innerHTML = '<thead><tr><th>Role</th><th>Transport</th><th>Target</th><th>Unit</th><th>Status</th><th>Last seen</th></tr></thead>';
  const body = document.createElement('tbody');
  connections.forEach((connection) => {
    const row = document.createElement('tr');
    [
      connection.role || (connection.active ? 'current' : 'previous'),
      connection.transport,
      connection.target,
      connection.unit_id,
      connection.status || (connection.active ? 'online' : 'inactive'),
      connection.last_seen,
    ].forEach((value) => {
      const cell = document.createElement('td');
      cell.textContent = displayValue(value);
      row.append(cell);
    });
    body.append(row);
  });
  table.append(body);
  wrapper.append(table);
  root.append(wrapper);
}

function renderRegisters(root, latest) {
  root.replaceChildren();
  const values = Array.isArray(latest?.values) ? latest.values : [];
  if (!values.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-detail';
    empty.textContent = latest?.error || 'No latest register sample is available.';
    root.append(empty);
    return;
  }

  const wrapper = document.createElement('div');
  wrapper.className = 'table-scroll register-table';
  const table = document.createElement('table');
  table.className = 'detail-table';
  table.innerHTML = '<thead><tr><th>Register</th><th>Value</th><th>Unit</th><th>Raw</th><th>Address</th></tr></thead>';
  const body = document.createElement('tbody');
  values.forEach((register) => {
    const row = document.createElement('tr');
    [
      register.register_name || register.name,
      register.value,
      register.unit,
      register.raw,
      register.address,
    ].forEach((value) => {
      const cell = document.createElement('td');
      cell.textContent = displayValue(value);
      row.append(cell);
    });
    body.append(row);
  });
  table.append(body);
  wrapper.append(table);
  root.append(wrapper);
}

function makeDetailSection(titleText) {
  const section = document.createElement('section');
  section.className = 'controller-detail-section';
  const title = document.createElement('h4');
  title.textContent = titleText;
  section.append(title);
  return section;
}

function renderControllerDetail(panel, detail) {
  panel.replaceChildren();
  const snapshot = detail?.snapshot || {};
  const controller = snapshot.controller || {};

  if (detail?.upstream?.stale) {
    const stale = document.createElement('p');
    stale.className = 'detail-warning';
    stale.textContent = 'Showing last-known-good controller detail while the upstream API reconnects.';
    panel.append(stale);
  }

  const identitySection = makeDetailSection('Controller identity');
  const identityFacts = document.createElement('div');
  identityFacts.className = 'fact-grid compact-facts';
  renderFacts(identityFacts, controller, [
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
  identitySection.append(identityFacts);
  panel.append(identitySection);

  const currentSection = makeDetailSection('Current connection');
  const currentFacts = document.createElement('div');
  currentFacts.className = 'fact-grid compact-facts';
  renderFlatFacts(currentFacts, controller.current_connection || {}, 20);
  currentSection.append(currentFacts);
  panel.append(currentSection);

  const connectionSection = makeDetailSection('Connection history');
  const connections = document.createElement('div');
  renderConnections(connections, controller.connections);
  connectionSection.append(connections);
  panel.append(connectionSection);

  const latestSection = makeDetailSection('Latest raw register sample');
  const sampleMeta = document.createElement('p');
  sampleMeta.className = 'detail-meta';
  sampleMeta.textContent = snapshot.latest?.observed_at
    ? `Observed ${relativeAge(snapshot.latest.observed_at)} · ${snapshot.latest.observed_at}`
    : 'Latest sample timestamp unavailable.';
  const registers = document.createElement('div');
  renderRegisters(registers, snapshot.latest);
  latestSection.append(sampleMeta, registers);
  panel.append(latestSection);

  const historySection = makeDetailSection('History & collection quality');
  const historyColumns = document.createElement('div');
  historyColumns.className = 'detail-columns controller-history-columns';
  [
    ['History summary', snapshot.history_summary],
    ['Daily summary', snapshot.daily_summary],
    ['History coverage', snapshot.history_coverage],
    ['Polling performance', snapshot.polling_performance],
  ].forEach(([titleText, record]) => {
    const block = document.createElement('div');
    block.className = 'subdetail-card';
    const title = document.createElement('strong');
    title.textContent = titleText;
    const facts = document.createElement('div');
    facts.className = 'fact-grid mini-facts';
    renderFlatFacts(facts, record, 18);
    block.append(title, facts);
    historyColumns.append(block);
  });
  historySection.append(historyColumns);
  panel.append(historySection);
}

async function loadControllerDetail(controllerUidValue, panel) {
  if (controllerDetailCache.has(controllerUidValue)) {
    renderControllerDetail(panel, controllerDetailCache.get(controllerUidValue));
    return;
  }
  panel.replaceChildren();
  const loading = document.createElement('p');
  loading.className = 'empty-detail';
  loading.textContent = 'Loading controller identity, registers, history and polling details…';
  panel.append(loading);
  try {
    const detail = await json(`/v1/controllers/${encodeURIComponent(controllerUidValue)}/detail`);
    controllerDetailCache.set(controllerUidValue, detail);
    if (openControllers.has(controllerUidValue)) renderControllerDetail(panel, detail);
  } catch (error) {
    panel.replaceChildren();
    const failure = document.createElement('p');
    failure.className = 'detail-warning';
    failure.textContent = `Could not load controller detail: ${error.message}`;
    panel.append(failure);
  }
}

function renderControllerList(root, controllers) {
  root.replaceChildren();
  if (!Array.isArray(controllers) || !controllers.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-detail';
    empty.textContent = 'No controllers are enrolled in this site.';
    root.append(empty);
    return;
  }

  controllers.forEach((controller) => {
    const uid = controllerUid(controller);
    const item = document.createElement('article');
    item.className = 'controller-inspector';
    const toggle = document.createElement('button');
    toggle.className = 'controller-toggle';
    toggle.type = 'button';
    const expanded = openControllers.has(uid);
    toggle.setAttribute('aria-expanded', String(expanded));

    const identity = document.createElement('span');
    identity.className = 'controller-identity';
    const name = document.createElement('strong');
    name.textContent = String(controller.model || controller.family || controller.profile || uid || 'Controller');
    const meta = document.createElement('span');
    const parts = [controller.serial_number, controller.profile, uid].filter(Boolean);
    meta.textContent = parts.join(' · ');
    identity.append(name, meta);

    const state = document.createElement('span');
    state.className = `status-pill ${String(controller.status || 'unknown').toLowerCase()}`;
    state.textContent = String(controller.status || 'unknown');
    const chevron = document.createElement('span');
    chevron.className = 'controller-chevron';
    chevron.textContent = expanded ? '⌃' : '⌄';
    const action = document.createElement('span');
    action.className = 'controller-action';
    action.append(state, chevron);
    toggle.append(identity, action);

    const panel = document.createElement('div');
    panel.className = 'controller-detail';
    panel.hidden = !expanded;

    toggle.addEventListener('click', () => {
      const next = panel.hidden;
      panel.hidden = !next;
      toggle.setAttribute('aria-expanded', String(next));
      chevron.textContent = next ? '⌃' : '⌄';
      if (next) {
        openControllers.add(uid);
        loadControllerDetail(uid, panel);
      } else {
        openControllers.delete(uid);
      }
    });

    item.append(toggle, panel);
    root.append(item);
    if (expanded) loadControllerDetail(uid, panel);
  });
}

function renderSiteDetails(fragment, site, assessment) {
  const snapshot = assessment.snapshot || {};
  const siteRecord = snapshot.site || site || {};
  const latest = snapshot.latest || {};
  const detailRoot = fragment.querySelector('.site-details');
  fragment.querySelector('.assessed-at').textContent = assessment.assessed_at
    ? `Assessed ${relativeAge(assessment.assessed_at)}`
    : 'Assessment time unavailable';

  const siteFacts = fragment.querySelector('.site-facts');
  renderFacts(siteFacts, siteRecord, [
    'name',
    'system_uid',
    'controller_count',
    'status',
    'created_at',
    'updated_at',
  ]);
  appendFact(siteFacts, 'Upstream', assessment.upstream?.stale ? 'stale / reconnecting' : 'reachable');
  appendFact(siteFacts, 'Latest telemetry', latest.observed_at || 'unavailable');

  renderControllerList(fragment.querySelector('.controller-list'), snapshot.controllers || []);
  renderSiteMetrics(fragment.querySelector('.site-metrics'), latest.metrics || {});
  renderFlatFacts(fragment.querySelector('.energy-ledger'), snapshot.energy_ledger || {}, 28);
  renderEvents(fragment.querySelector('.recent-events'), snapshot.events);

  return detailRoot;
}

function renderSite(site, assessment, explanation) {
  const fragment = template.content.cloneNode(true);
  const card = fragment.querySelector('.site-card');
  const health = assessment.health?.overall ?? {};
  const observability = assessment.health?.observability ?? {};
  const accounting = assessment.health?.power_accounting ?? {};
  const snapshot = assessment.snapshot ?? {};
  const latest = snapshot.latest ?? {};
  const metrics = latest.metrics ?? {};
  const flow = snapshot.power_flow ?? {};
  const controllers = snapshot.controllers ?? [];
  const siteUid = String(site.system_uid || site.name || assessment.site_uid || 'site');

  card.dataset.status = health.status ?? 'unknown';
  fragment.querySelector('.site-name').textContent = site.name || site.system_uid;
  fragment.querySelector('.site-id').textContent = site.system_uid;
  fragment.querySelector('.site-status').textContent = controllerStatus(controllers);
  fragment.querySelector('.score').textContent = health.value ?? '—';
  fragment.querySelector('.observability').textContent = `${observability.value ?? 0}%`;
  fragment.querySelector('.accounting').textContent = `${accounting.value ?? 0}%`;
  fragment.querySelector('.controllers').textContent = site.controller_count ?? controllers.length ?? 0;
  fragment.querySelector('.incidents').textContent = assessment.open_incidents?.length ?? 0;

  fragment.querySelector('.telemetry-age').textContent = relativeAge(latest.observed_at);
  fragment.querySelector('.solar').textContent = formatMetric(metrics.solar_input_power_w, 'W', 0);
  fragment.querySelector('.charge-output').textContent = formatMetric(metrics.charge_output_power_w, 'W', 0);
  fragment.querySelector('.battery-voltage').textContent = formatMetric(metrics.battery_voltage_v, 'V', 2);
  fragment.querySelector('.charge-current').textContent = formatMetric(metrics.battery_charge_current_a, 'A', 2);
  fragment.querySelector('.array-voltage').textContent = formatMetric(metrics.array_voltage_v, 'V', 1);
  fragment.querySelector('.charge-stage').textContent = formatStateMetric(metrics.charge_state);

  const dailyWh = metricValue(metrics.daily_charge_wh);
  const dailyKwh = metricValue(metrics.daily_charge_kwh);
  fragment.querySelector('.daily-energy').textContent = Number.isFinite(dailyWh)
    ? formatNumber(dailyWh, 'Wh', 0)
    : formatNumber(dailyKwh, 'kWh', 2);
  fragment.querySelector('.battery-temperature').textContent = formatMetric(
    metrics.battery_temperature_c,
    '°C',
    1,
  );

  fragment.querySelector('.battery').textContent = formatMetric(flow.battery?.net_power_w, 'W', 0);
  fragment.querySelector('.loads').textContent = formatMetric(flow.loads?.dc_power_w, 'W', 0);
  fragment.querySelector('.battery-soc').textContent = formatMetric(flow.battery?.soc_percent, '%', 0);
  fragment.querySelector('.accounting-status').textContent = accounting.status || 'unknown';
  fragment.querySelector('.coverage-note').textContent = accountingGapText(flow);

  const accountingLimited = Number(accounting.value ?? 0) < 80;
  const healthCaveat = accountingLimited
    ? ' No active problem was detected in the observed telemetry, but whole-site electrical state is only partially measured.'
    : '';
  fragment.querySelector('.explanation').textContent = `${explanation.headline}${healthCaveat}`;

  const findingRoot = fragment.querySelector('.findings');
  const findings = (assessment.findings ?? []).filter((item) => item.severity !== 'info').slice(0, 4);
  if (!findings.length) {
    const clear = document.createElement('div');
    clear.className = 'finding clear';
    clear.textContent = accountingLimited
      ? 'No evidence-backed warning or critical finding is active in the telemetry currently observed.'
      : 'No evidence-backed warning or critical finding is active.';
    findingRoot.append(clear);
  } else {
    findings.forEach((item) => findingRoot.append(renderFinding(item)));
  }

  const detailRoot = renderSiteDetails(fragment, site, assessment);
  const siteToggle = fragment.querySelector('.site-toggle');
  const inspectLabel = fragment.querySelector('.inspect-label');
  const expanded = openSites.has(siteUid);
  detailRoot.hidden = !expanded;
  siteToggle.setAttribute('aria-expanded', String(expanded));
  inspectLabel.innerHTML = expanded
    ? 'Close site <span class="chevron">⌃</span>'
    : 'Inspect site <span class="chevron">⌄</span>';

  siteToggle.addEventListener('click', () => {
    const next = detailRoot.hidden;
    detailRoot.hidden = !next;
    siteToggle.setAttribute('aria-expanded', String(next));
    inspectLabel.innerHTML = next
      ? 'Close site <span class="chevron">⌃</span>'
      : 'Inspect site <span class="chevron">⌄</span>';
    if (next) openSites.add(siteUid);
    else openSites.delete(siteUid);
  });

  sitesRoot.append(fragment);
}

async function refresh() {
  refreshButton.disabled = true;
  banner.textContent = 'Refreshing site assessments…';
  banner.className = 'banner';
  sitesRoot.replaceChildren();
  try {
    const [sentinelHealth, sites] = await Promise.all([
      json('/health'),
      json('/v1/sites'),
    ]);
    if (!sites.length) {
      banner.textContent = 'No Morningstar systems are currently reported by the upstream API.';
      return;
    }

    let stale = sentinelHealth.upstream !== 'reachable';
    for (const site of sites) {
      const uid = encodeURIComponent(site.system_uid || site.name);
      const assessment = await json(`/v1/sites/${uid}/assessment`);
      const explanation = await json(`/v1/sites/${uid}/explain`);
      stale = stale || assessment.upstream?.stale === true;
      renderSite(site, assessment, explanation);
    }

    if (stale) {
      banner.textContent = `Showing last-known-good data for ${sites.length} site${sites.length === 1 ? '' : 's'} while MorningstarModbusAPI reconnects.`;
      banner.className = 'banner';
    } else {
      banner.textContent = `Monitoring ${sites.length} site${sites.length === 1 ? '' : 's'}.`;
      banner.className = 'banner ok';
    }
  } catch (error) {
    banner.textContent = `Sentinel could not read the upstream site model: ${error.message}`;
    banner.className = 'banner error';
  } finally {
    refreshButton.disabled = false;
  }
}

refreshButton.addEventListener('click', () => {
  controllerDetailCache.clear();
  refresh();
});
refresh();
setInterval(refresh, 15000);
