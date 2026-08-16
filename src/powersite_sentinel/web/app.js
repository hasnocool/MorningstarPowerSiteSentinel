const sitesRoot = document.querySelector('#sites');
const banner = document.querySelector('#banner');
const template = document.querySelector('#site-template');
const refreshButton = document.querySelector('#refresh');
const forensicCache = new Map();
const FORENSIC_CACHE_MS = 5 * 60 * 1000;

const watts = (value) => Number.isFinite(value) ? `${Math.round(value)} W` : 'unknown';
const metricValue = (value) => (
  value && typeof value === 'object' && Number.isFinite(value.value) ? value.value : null
);

async function json(path) {
  const response = await fetch(path, { headers: { Accept: 'application/json' } });
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
  return response.json();
}

async function getForensics(uid, force) {
  const cached = forensicCache.get(uid);
  if (!force && cached && Date.now() - cached.fetchedAt < FORENSIC_CACHE_MS) {
    return cached.payload;
  }
  const payload = await json(`/v1/sites/${uid}/forensics?days=30`);
  forensicCache.set(uid, { fetchedAt: Date.now(), payload });
  return payload;
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

function renderTimelineEvent(item) {
  const row = document.createElement('div');
  row.className = `timeline-event ${item.severity ?? 'info'}`;

  const top = document.createElement('div');
  top.className = 'timeline-event-heading';
  const title = document.createElement('strong');
  title.textContent = String(item.title ?? item.event_type ?? 'Event');
  const time = document.createElement('span');
  time.className = 'mono';
  time.textContent = item.observed_at
    ? String(item.observed_at).replace('T', ' ').slice(0, 19)
    : 'unknown time';
  top.append(title, time);

  const detail = document.createElement('span');
  detail.textContent = String(item.message ?? item.event_type ?? '');
  row.append(top, detail);
  return row;
}

function renderForensics(fragment, forensic) {
  const period = forensic?.period ?? {};
  const summary = forensic?.summary ?? {};
  const status = fragment.querySelector('.forensic-status');
  fragment.querySelector('.forensic-period').textContent = (
    period.from && period.to ? `${period.from} → ${period.to}` : 'history unavailable'
  );

  if (forensic?.error) {
    status.textContent = 'unavailable';
    status.className = 'forensic-status bad';
    fragment.querySelector('.history-coverage').textContent = '—';
    fragment.querySelector('.history-missing').textContent = '—';
    fragment.querySelector('.history-recovered').textContent = '—';
    fragment.querySelector('.energy-discrepancies').textContent = '—';
    const row = document.createElement('div');
    row.className = 'timeline-event warning';
    row.textContent = `Historical diagnostics unavailable: ${forensic.error}`;
    fragment.querySelector('.timeline-preview').append(row);
    return;
  }

  const missing = summary.missing_controller_days ?? 0;
  const discrepancies = summary.energy_discrepancy_controller_days ?? 0;
  status.textContent = missing || discrepancies ? 'attention' : 'continuous';
  status.className = `forensic-status ${missing || discrepancies ? 'warn' : 'good'}`;
  const coverage = summary.minimum_daily_evidence_percent;
  fragment.querySelector('.history-coverage').textContent = (
    Number.isFinite(coverage) ? `${coverage}%` : 'unknown'
  );
  fragment.querySelector('.history-missing').textContent = missing;
  fragment.querySelector('.history-recovered').textContent = summary.recovered_controller_days ?? 0;
  fragment.querySelector('.energy-discrepancies').textContent = discrepancies;

  const timelineRoot = fragment.querySelector('.timeline-preview');
  const events = (forensic?.timeline?.events ?? []).slice(0, 5);
  if (!events.length) {
    const clear = document.createElement('div');
    clear.className = 'timeline-event clear';
    clear.textContent = 'No forensic timeline events in this window.';
    timelineRoot.append(clear);
  } else {
    events.forEach((item) => timelineRoot.append(renderTimelineEvent(item)));
  }
}

function renderSite(site, assessment, explanation, forensic) {
  const fragment = template.content.cloneNode(true);
  const card = fragment.querySelector('.site-card');
  const health = assessment.health?.overall ?? {};
  card.dataset.status = health.status ?? 'unknown';
  fragment.querySelector('.site-name').textContent = site.name || site.system_uid;
  fragment.querySelector('.site-id').textContent = site.system_uid;
  fragment.querySelector('.score').textContent = health.value ?? '—';
  fragment.querySelector('.observability').textContent = `${assessment.health?.observability?.value ?? 0}%`;
  fragment.querySelector('.controllers').textContent = (
    site.controller_count ?? assessment.snapshot?.controllers?.length ?? 0
  );
  fragment.querySelector('.incidents').textContent = assessment.open_incidents?.length ?? 0;

  const flow = assessment.snapshot?.power_flow ?? {};
  fragment.querySelector('.solar').textContent = watts(metricValue(flow.sources?.solar_input_power_w));
  fragment.querySelector('.battery').textContent = watts(metricValue(flow.battery?.net_power_w));
  fragment.querySelector('.loads').textContent = watts(metricValue(flow.loads?.dc_power_w));
  fragment.querySelector('.explanation').textContent = explanation.headline;

  const findingRoot = fragment.querySelector('.findings');
  const findings = (assessment.findings ?? []).filter((item) => item.severity !== 'info').slice(0, 4);
  if (!findings.length) {
    const clear = document.createElement('div');
    clear.className = 'finding clear';
    clear.textContent = 'No evidence-backed warning or critical finding is active.';
    findingRoot.append(clear);
  } else {
    findings.forEach((item) => findingRoot.append(renderFinding(item)));
  }

  renderForensics(fragment, forensic);
  sitesRoot.append(fragment);
}

async function refresh(forceForensics = false) {
  refreshButton.disabled = true;
  banner.textContent = 'Refreshing site assessments…';
  banner.className = 'banner';
  sitesRoot.replaceChildren();
  try {
    const sites = await json('/v1/sites');
    if (!sites.length) {
      banner.textContent = 'No Morningstar systems are currently reported by the upstream API.';
      return;
    }
    for (const site of sites) {
      const uid = encodeURIComponent(site.system_uid || site.name);
      const assessment = await json(`/v1/sites/${uid}/assessment`);
      const explanation = await json(`/v1/sites/${uid}/explain`);
      let forensic;
      try {
        forensic = await getForensics(uid, forceForensics);
      } catch (error) {
        forensic = { error: error.message };
      }
      renderSite(site, assessment, explanation, forensic);
    }
    banner.textContent = `Monitoring ${sites.length} site${sites.length === 1 ? '' : 's'}.`;
    banner.className = 'banner ok';
  } catch (error) {
    banner.textContent = `Sentinel could not read the upstream site model: ${error.message}`;
    banner.className = 'banner error';
  } finally {
    refreshButton.disabled = false;
  }
}

refreshButton.addEventListener('click', () => refresh(true));
refresh();
setInterval(() => refresh(false), 15000);
