const sitesRoot = document.querySelector('#sites');
const banner = document.querySelector('#banner');
const template = document.querySelector('#site-template');
const refreshButton = document.querySelector('#refresh');

const watts = (value) => Number.isFinite(value) ? `${Math.round(value)} W` : 'unknown';
const metricValue = (value) => value && typeof value === 'object' && Number.isFinite(value.value) ? value.value : null;

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

function renderSite(site, assessment, explanation) {
  const fragment = template.content.cloneNode(true);
  const card = fragment.querySelector('.site-card');
  const health = assessment.health?.overall ?? {};
  card.dataset.status = health.status ?? 'unknown';
  fragment.querySelector('.site-name').textContent = site.name || site.system_uid;
  fragment.querySelector('.site-id').textContent = site.system_uid;
  fragment.querySelector('.score').textContent = health.value ?? '—';
  fragment.querySelector('.observability').textContent = `${assessment.health?.observability?.value ?? 0}%`;
  fragment.querySelector('.controllers').textContent = site.controller_count ?? assessment.snapshot?.controllers?.length ?? 0;
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
