const sitesRoot = document.querySelector('#sites');
const banner = document.querySelector('#banner');
const template = document.querySelector('#site-template');
const refreshButton = document.querySelector('#refresh');

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

refreshButton.addEventListener('click', refresh);
refresh();
setInterval(refresh, 15000);
