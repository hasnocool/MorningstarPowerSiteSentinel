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
  if (summary) {
    summary.textContent = String(count);
    summary.title = 'Count reconciled from the current physical-controller inventory.';
  }

  for (const fact of card.querySelectorAll('.site-facts .fact')) {
    const label = fact.querySelector('span')?.textContent?.trim().toLowerCase();
    if (label !== 'controller count') continue;
    const value = fact.querySelector('strong');
    if (value) {
      value.textContent = String(count);
      value.title = 'Count reconciled from the current physical-controller inventory.';
    }
  }
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
    if (value === 'available' || value === 'unmeasured' || value === '—') {
      fact.hidden = true;
      hidden += 1;
    } else {
      fact.hidden = false;
    }
  }

  if (!hidden || ledger.querySelector('.ledger-note')) return;
  const note = document.createElement('p');
  note.className = 'ledger-note';
  note.textContent = `${hidden} empty or structural ledger fields are hidden. The inspector prioritizes numeric/source-backed values.`;
  ledger.append(note);
}

function refineCard(card) {
  reconcileControllerCount(card);

  const metricsBody = card.querySelector('.site-metrics');
  const metricsSection = metricsBody?.closest('.detail-section');
  if (metricsSection && metricsBody.children.length) {
    const showUnmeasured = metricsSection.dataset.showUnmeasured === 'true';
    updateMetricVisibility(metricsSection, showUnmeasured);
  }

  cleanEnergyLedger(card);
}

function refineAll() {
  for (const card of sitesRoot.querySelectorAll('.site-card')) refineCard(card);
}

const observer = new MutationObserver(() => queueMicrotask(refineAll));
observer.observe(sitesRoot, { childList: true, subtree: true, characterData: true });
refineAll();
