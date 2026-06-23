'use strict';

const filters = { type: 'all', trend: 'all', agreement: 'all' };
let _data = null;
const CURRENCY_ORDER = ['USD','EUR','GBP','JPY','AUD','CAD','CHF','NZD'];

/* ── Bootstrap ──────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', initDashboard);

async function initDashboard() {
  try {
    await fetchData();
  } catch (e) {
    showError('Failed to load data: ' + e.message);
  } finally {
    hideLoader();
  }
}

async function fetchData() {
  const res = await fetch('/api/data');
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  _data = await res.json();

  if (_data.error) showError(_data.error);
  else hideError();

  renderAll(_data);
}

async function refreshData() {
  const icon = document.getElementById('refresh-icon');
  icon.classList.add('spinning');
  document.getElementById('refresh-btn').disabled = true;

  try {
    const res = await fetch('/api/refresh', { method: 'POST' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const result = await res.json();
    if (result.error) showError(result.error);
    await fetchData();
  } catch (e) {
    showError('Refresh failed: ' + e.message);
  } finally {
    icon.classList.remove('spinning');
    document.getElementById('refresh-btn').disabled = false;
  }
}

/* ── Main render ────────────────────────────────────────────────────── */
function renderAll(data) {
  updateTimestamp(data.last_updated);
  renderTable('major', data.pairs.filter(p => (data.major_pairs || []).includes(p.display)), data.news);
  renderTable('minor', data.pairs.filter(p => (data.minor_pairs || []).includes(p.display)), data.news);
  renderNews(data.news);
  updateStats(data.pairs, data.major_pairs, data.minor_pairs);
  applyFilters();
}

/* ── Tables ─────────────────────────────────────────────────────────── */
function renderTable(type, pairs, newsData) {
  const tbody = document.getElementById(`body-${type}`);
  tbody.innerHTML = '';
  pairs.forEach(p => tbody.appendChild(makeRow(p, newsData)));
}

function makeRow(p, newsData) {
  const tr = document.createElement('tr');
  tr.dataset.type     = p.display;
  tr.dataset.dailyTrend  = trendKey(p.daily_trend);
  tr.dataset.weeklyTrend = trendKey(p.weekly_trend);
  tr.dataset.agreement   = (p.agreement || 'No').toLowerCase();

  const newsImpact = getNewsImpact(p.base, p.quote, newsData);

  tr.innerHTML = `
    <td><span class="pair-name">${p.display}</span></td>
    <td><span class="price">${p.bid ?? '—'}</span></td>
    <td><span class="price">${p.ask ?? '—'}</span></td>
    <td>${formatChange(p.daily_change)}</td>
    <td>${trendBadge(p.daily_trend, p.daily_strength, p.daily_adx)}</td>
    <td>${trendBadge(p.weekly_trend, p.weekly_strength, p.weekly_adx)}</td>
    <td>${agreementBadge(p.agreement)}</td>
    <td>${newsImpactCell(newsImpact)}</td>
  `;
  return tr;
}

function trendBadge(trend, strength, adx) {
  if (!trend || trend === 'Ranging') {
    return '<span class="badge badge-rng">↔ RANGING</span>';
  }
  const adxStr = adx != null ? ` <span class="adx-val">ADX ${adx}</span>` : '';
  if (trend === 'Trending Up') {
    if (strength === 'Strong')   return `<span class="badge badge-up-strong">↑ STRONG BULL${adxStr}</span>`;
    if (strength === 'Moderate') return `<span class="badge badge-up">↑ BULLISH${adxStr}</span>`;
    return `<span class="badge badge-up-weak">↑ WEAK BULL${adxStr}</span>`;
  }
  if (trend === 'Trending Down') {
    if (strength === 'Strong')   return `<span class="badge badge-dn-strong">↓ STRONG BEAR${adxStr}</span>`;
    if (strength === 'Moderate') return `<span class="badge badge-dn">↓ BEARISH${adxStr}</span>`;
    return `<span class="badge badge-dn-weak">↓ WEAK BEAR${adxStr}</span>`;
  }
  return '<span class="badge badge-rng">↔ RANGING</span>';
}

function agreementBadge(agr) {
  if (!agr) return '<span class="badge agr-no">✗ N/A</span>';
  if (agr === 'Yes')     return '<span class="badge agr-yes">✓ CONFIRMED</span>';
  if (agr === 'Partial') return '<span class="badge agr-part">~ PARTIAL</span>';
  return '<span class="badge agr-no">✗ CONFLICT</span>';
}

function formatChange(val) {
  if (val == null || val === 0) return '<span class="chg-neu">0.000%</span>';
  const sign = val > 0 ? '+' : '';
  const cls = val > 0 ? 'chg-pos' : 'chg-neg';
  return `<span class="${cls}">${sign}${val.toFixed(3)}%</span>`;
}

function trendKey(trend) {
  if (trend === 'Trending Up')   return 'up';
  if (trend === 'Trending Down') return 'down';
  return 'ranging';
}

function getNewsImpact(base, quote, newsData) {
  if (!newsData) return null;
  const baseBias  = newsData[base]?.bias;
  const quoteBias = newsData[quote]?.bias;
  if (!baseBias && !quoteBias) return null;
  if (baseBias === 'Bullish' && quoteBias !== 'Bullish') return 'Bullish';
  if (baseBias === 'Bearish' && quoteBias !== 'Bearish') return 'Bearish';
  if (quoteBias === 'Bullish' && baseBias !== 'Bullish') return 'Bearish'; // quote bullish = pair bearish
  if (quoteBias === 'Bearish' && baseBias !== 'Bearish') return 'Bullish';
  return 'Mixed';
}

function newsImpactCell(impact) {
  if (!impact) return '<span class="ni ni-none">—</span>';
  if (impact === 'Bullish') return '<span class="ni ni-bull">↑ BULLISH</span>';
  if (impact === 'Bearish') return '<span class="ni ni-bear">↓ BEARISH</span>';
  return '<span class="ni ni-mix">~ MIXED</span>';
}

/* ── News Section ───────────────────────────────────────────────────── */
function renderNews(newsData) {
  const tabsEl   = document.getElementById('ctabs');
  const panelsEl = document.getElementById('npanels');
  tabsEl.innerHTML   = '';
  panelsEl.innerHTML = '';

  if (!newsData || !Object.keys(newsData).length) {
    panelsEl.innerHTML = '<div class="news-empty">No high-impact events found for this period.</div>';
    return;
  }

  const currencies = sortCurrencies(Object.keys(newsData));
  let first = true;

  currencies.forEach(cur => {
    const { events, bias } = newsData[cur];

    // Tab button
    const btn = document.createElement('button');
    btn.className = 'ctab' + (first ? ' active' : '');
    btn.textContent = cur;
    btn.onclick = () => switchTab(cur);
    tabsEl.appendChild(btn);

    // Panel
    const panel = document.createElement('div');
    panel.id = `np-${cur}`;
    panel.className = 'news-panel' + (first ? ' active' : '');

    panel.innerHTML = `
      ${biasBadge(bias, cur)}
      ${makeNewsTable(events)}
    `;
    panelsEl.appendChild(panel);
    first = false;
  });
}

function switchTab(cur) {
  document.querySelectorAll('.ctab').forEach(b => {
    b.classList.toggle('active', b.textContent === cur);
  });
  document.querySelectorAll('.news-panel').forEach(p => {
    p.classList.toggle('active', p.id === `np-${cur}`);
  });
}

function biasBadge(bias, cur) {
  const map = {
    'Bullish': `<div class="news-bias nb-bull">↑ ${cur} OVERALL BIAS: BULLISH — Price likely to rise</div>`,
    'Bearish': `<div class="news-bias nb-bear">↓ ${cur} OVERALL BIAS: BEARISH — Price likely to fall</div>`,
    'Mixed':   `<div class="news-bias nb-mix">~ ${cur} OVERALL BIAS: MIXED SIGNALS</div>`
  };
  return map[bias] || '';
}

function makeNewsTable(events) {
  if (!events || !events.length) return '<div class="news-empty">No events for this currency.</div>';

  const rows = events.map(e => `
    <tr>
      <td class="mono">${e.date || '—'}</td>
      <td class="mono">${e.time || '—'}</td>
      <td>${e.event}</td>
      <td><span class="${impactClass(e.impact)}">${e.impact}</span></td>
      <td class="mono">${e.actual  || '—'}</td>
      <td class="mono">${e.forecast || '—'}</td>
      <td class="mono">${e.previous || '—'}</td>
      <td>${dirBadge(e.direction)}</td>
    </tr>
  `).join('');

  return `
    <table class="news-tbl">
      <thead><tr>
        <th>DATE</th><th>TIME</th><th>EVENT</th><th>IMPACT</th>
        <th>ACTUAL</th><th>FORECAST</th><th>PREVIOUS</th><th>DIRECTION</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

function impactClass(impact) {
  if (impact === 'High')    return 'imp-high';
  if (impact === 'Holiday') return 'imp-hol';
  if (impact === 'Speech')  return 'imp-sp';
  return '';
}

function dirBadge(dir) {
  const map = {
    'Bullish': '<span class="dir dir-bull">↑ BULLISH</span>',
    'Bearish': '<span class="dir dir-bear">↓ BEARISH</span>',
    'Neutral': '<span class="dir dir-neu">→ NEUTRAL</span>',
    'Watch':   '<span class="dir dir-watch">👁 WATCH</span>',
    'Pending': '<span class="dir dir-pend">⏳ PENDING</span>',
  };
  return map[dir] || `<span class="dir dir-neu">${dir || '—'}</span>`;
}

/* ── Filters ────────────────────────────────────────────────────────── */
function setFilter(key, val, el) {
  filters[key] = val;
  el.closest('.pills').querySelectorAll('.pill').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
  applyFilters();
}

function applyFilters() {
  if (!_data) return;
  const { type, trend, agreement } = filters;

  let shown = 0;
  document.querySelectorAll('.ptbl tbody tr').forEach(tr => {
    const isMajor = (_data.major_pairs || []).includes(tr.dataset.type);
    const isMinor = (_data.minor_pairs || []).includes(tr.dataset.type);
    const passType = type === 'all' || (type === 'major' && isMajor) || (type === 'minor' && isMinor);
    const passTrend = trend === 'all' || tr.dataset.dailyTrend === trend;
    const passAgr = agreement === 'all' || tr.dataset.agreement === agreement;
    const hide = !(passType && passTrend && passAgr);
    tr.classList.toggle('filtered-out', hide);
    if (!hide) shown++;
  });

  // Show/hide whole sections
  const majorSection = document.getElementById('sec-major');
  const minorSection = document.getElementById('sec-minor');
  if (type === 'minor') majorSection.style.display = 'none';
  else majorSection.style.display = '';
  if (type === 'major') minorSection.style.display = 'none';
  else minorSection.style.display = '';

  document.getElementById('s-total').textContent = shown;
}

/* ── Stats Bar ──────────────────────────────────────────────────────── */
function updateStats(pairs, majorPairs, minorPairs) {
  let up = 0, dn = 0, rng = 0, conf = 0;
  pairs.forEach(p => {
    if (p.daily_trend === 'Trending Up')   up++;
    if (p.daily_trend === 'Trending Down') dn++;
    if (p.daily_trend === 'Ranging')       rng++;
    if (p.agreement === 'Yes')             conf++;
  });
  document.getElementById('s-up').textContent   = up;
  document.getElementById('s-dn').textContent   = dn;
  document.getElementById('s-rng').textContent  = rng;
  document.getElementById('s-conf').textContent = conf;
  document.getElementById('s-total').textContent = pairs.length;

  const mc = (majorPairs || []).filter(d => pairs.find(p => p.display === d)).length;
  const nc = (minorPairs || []).filter(d => pairs.find(p => p.display === d)).length;
  document.getElementById('cnt-major').textContent = `${mc} pair${mc !== 1 ? 's' : ''}`;
  document.getElementById('cnt-minor').textContent = `${nc} pair${nc !== 1 ? 's' : ''}`;
}

/* ── Helpers ────────────────────────────────────────────────────────── */
function updateTimestamp(iso) {
  if (!iso) return;
  const d = new Date(iso);
  document.getElementById('last-updated').textContent =
    d.toLocaleString('en-US', { timeZone: 'America/Chicago', month:'short', day:'2-digit', hour:'2-digit', minute:'2-digit', hour12:true }) + ' CT';
}

function sortCurrencies(keys) {
  return [...keys].sort((a, b) => {
    const ia = CURRENCY_ORDER.indexOf(a);
    const ib = CURRENCY_ORDER.indexOf(b);
    if (ia === -1 && ib === -1) return a.localeCompare(b);
    if (ia === -1) return 1;
    if (ib === -1) return -1;
    return ia - ib;
  });
}

function showError(msg) {
  const el = document.getElementById('error-banner');
  document.getElementById('error-msg').textContent = msg;
  el.classList.remove('hidden');
}
function hideError() { document.getElementById('error-banner').classList.add('hidden'); }

function hideLoader() {
  const ov = document.getElementById('loading-overlay');
  ov.classList.add('fade-out');
  setTimeout(() => ov.remove(), 600);
}
