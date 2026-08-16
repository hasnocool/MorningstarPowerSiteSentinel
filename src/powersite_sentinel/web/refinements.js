const sitesRoot = document.querySelector('#sites');

function actualControllerCount(card) {
  const status = card.querySelector('.site-status')?.textContent || '';
  const match = status.match(/\b\d+\/(\d+)\s+controllers?\s+online\b/i);
  if (match) return Number(match[1]);

  const controllerList = card.querySelector('.controller-list');
  if (controllerList) {
    const items = controllerList.querySelectorAll('.controller-inspector');
    if (items.length) return items.length;
  }
  return null;
}

function reconcileControllerCount(card) {
  const count = actualControllerCount(card);
  if (!Number.isFinite(count)) return;

  const summary = card.querySelector('.controllers');
  if (summary && summary.textContent !== String(count)) {
    summary.textContent = String(count);
    summary.title = 'Count reconciled from the current physical-controller inventory.';
  }

  for (const fact of card.querySelectorAll('.site-facts .fact')) {
    const label = fact.querySelector('span')?.textContent?.trim().toLowerCase();
    if (label !== 'controller count') continue;
    const value = fact.querySelector('strong');
    if (value && value.textContent !== String(count)) {
      value.textContent = String(count);
      value.title = 'Count reconciled from the current physical-controller inventory.';
    }
  }
}

function supportedMetricCoverage(card) {
  let supported = 0;
  let reporting = 0;
  for (const row of card.querySelectorAll('.site-metrics tr')) {
    const cells = row.querySelectorAll('td');
    if (cells.length < 4) continue;
    const match = cells[3].textContent?.trim().match(/^(\d+)\/(\d+)$/);
    if (!match) continue;
    const contributors = Number(match[1]);
    const expected = Number(match[2]);
    if (!Number.isFinite(expected) || expected <= 0) continue;
    supported += 1;
    if (contributors >= expected) reporting += 1;
  }
  if (!supported) return null;
  return { reporting, supported, percent: Math.round((reporting / supported) * 100) };
}

function reconcileTelemetryCoverage(card) {
  const coverage = supportedMetricCoverage(card);
  if (!coverage) return;
  const target = card.querySelector('.observability');
  if (!target) return;
  const text = `${coverage.percent}%`;
  if (target.textContent !== text) target.textContent = text;
  target.title = `${coverage.reporting}/${coverage.supported} supported normalized metrics are reporting from their expected controller contributors.`;
}

function isUnmeasuredMetricRow(row) {
  const cells = row.querySelectorAll('td');
  if (cells.length < 2) return false;
  const value = cells[1].textContent?.trim().toLowerCase();
  const quality = cells[2]?.textContent?.trim().toLowerCase();
  return value === 'unmeasured' || value === '—' || quality === 'empty';
}

function updateMetricVisibility(section, showUnmeasured) {
  const body = section.querySelector('.site-metrics');
  if (!body) return;

  const rows = [...body.querySelectorAll('tr')];
  let measured = 0;
  let unmeasured = 0;
  for (const row of rows) {
    if (isUnmeasuredMetricRow(row)) {
      unmeasured += 1;
      row.classList.add('unmeasured-row');
      row.hidden = !showUnmeasured;
    } else {
      measured += 1;
      row.classList.remove('unmeasured-row');
      row.hidden = false;
    }
  }

  let control = section.querySelector('.metric-visibility');
  if (!control) {
    control = document.createElement('div');
    control.className = 'metric-visibility';
    const table = section.querySelector('.table-scroll');
    table?.before(control);
  }

  const state = `${measured}:${unmeasured}:${showUnmeasured}`;
  if (control.dataset.state === state) return;
  control.dataset.state = state;
  control.replaceChildren();

  const summary = document.createElement('span');
  summary.textContent = unmeasured
    ? `${measured} measured/observed metrics shown · ${unmeasured} unsupported or unmeasured hidden`
    : `${measured} measured/observed metrics shown`;
  control.append(summary);

  if (unmeasured) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'secondary-button';
    button.textContent = showUnmeasured
      ? 'Hide unmeasured'
      : `Show ${unmeasured} unmeasured`;
    button.addEventListener('click', () => {
      section.dataset.showUnmeasured = showUnmeasured ? 'false' : 'true';
      updateMetricVisibility(section, !showUnmeasured);
    });
    control.append(button);
  }
}

function cleanEnergyLedger(card) {
  const ledger = card.querySelector('.energy-ledger');
  if (!ledger) return;

  let hidden = 0;
  for (const fact of ledger.querySelectorAll('.fact')) {
    const value = fact.querySelector('strong')?.textContent?.trim().toLowerCase();
    const shouldHide = value === 'available' || value === 'unmeasured' || value === '—';
    fact.hidden = shouldHide;
    if (shouldHide) hidden += 1;
  }

  const existing = ledger.querySelector('.ledger-note');
  if (!hidden) {
    existing?.remove();
    return;
  }
  if (existing) {
    existing.textContent = `${hidden} empty or structural ledger fields are hidden. The inspector prioritizes numeric/source-backed values.`;
    return;
  }

  const note = document.createElement('p');
  note.className = 'ledger-note';
  note.textContent = `${hidden} empty or structural ledger fields are hidden. The inspector prioritizes numeric/source-backed values.`;
  ledger.append(note);
}

function compactUninstrumentedAccounting(card) {
  const grid = card.querySelector('.accounting-grid');
  if (!grid) return;
  const values = [...grid.querySelectorAll('strong')].map((item) => item.textContent?.trim().toLowerCase());
  const allMissing = values.length > 0 && values.every((value) => value === 'unmeasured' || value === '—');
  grid.classList.toggle('all-unmeasured', allMissing);

  const note = card.querySelector('.coverage-note');
  if (allMissing && note) {
    note.dataset.originalText ||= note.textContent || '';
    note.textContent = 'Whole-site battery/load accounting is not instrumented. Add source-backed shunt/load measurements to populate battery net flow, DC loads, and SOC. Controller telemetry above remains valid.';
  } else if (note?.dataset.originalText) {
    note.textContent = note.dataset.originalText;
  }
}

function refineCard(card) {
  reconcileControllerCount(card);
  reconcileTelemetryCoverage(card);

  const metricsBody = card.querySelector('.site-metrics');
  const metricsSection = metricsBody?.closest('.detail-section');
  if (metricsSection && metricsBody.children.length) {
    const showUnmeasured = metricsSection.dataset.showUnmeasured === 'true';
    updateMetricVisibility(metricsSection, showUnmeasured);
  }

  compactUninstrumentedAccounting(card);
  cleanEnergyLedger(card);
}

let observer;
let scheduled = false;

function observe() {
  observer.observe(sitesRoot, { childList: true, subtree: true, characterData: true });
}

function refineAll() {
  observer.disconnect();
  for (const card of sitesRoot.querySelectorAll('.site-card')) refineCard(card);
  observe();
}

function scheduleRefinement() {
  if (scheduled) return;
  scheduled = true;
  queueMicrotask(() => {
    scheduled = false;
    refineAll();
  });
}

observer = new MutationObserver(scheduleRefinement);
observe();
refineAll();
