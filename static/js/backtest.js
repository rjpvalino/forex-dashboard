'use strict';

let _btChart = null;

const PAIR_COLORS = [
  '#00d4ff', '#00ff88', '#ff3366', '#ffd700',
  '#7b2ff7', '#ff6b35', '#00e5cc', '#ff9500',
];

/* ── Entry point ──────────────────────────────────────────────────── */
async function runBacktest() {
  const btn   = document.getElementById('run-btn');
  const icon  = document.getElementById('run-icon');
  const msg   = document.getElementById('bt-status-msg');

  btn.disabled = true;
  icon.textContent = '⟳';
  icon.style.display = 'inline-block';
  icon.classList.add('spinning');
  msg.textContent = 'Running backtest — computing ADX across ~500 bars per pair…';
  msg.className = 'bt-status-running';

  try {
    const res = await fetch('/api/backtest', { method: 'POST' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
      throw new Error(err.error || `HTTP ${res.status}`);
    }
    const data = await res.json();
    if (data.error) throw new Error(data.error);

    msg.textContent = `Backtest complete — ${data.results.length} pairs, ${data.results.reduce((s, r) => s + r.total_trades, 0)} total trades`;
    msg.className = 'bt-status-done';

    if (data.is_demo) {
      document.getElementById('demo-notice').classList.remove('hidden');
    }

    renderResults(data);
  } catch (e) {
    msg.textContent = 'Error: ' + e.message;
    msg.className = 'bt-status-error';
  } finally {
    btn.disabled = false;
    icon.textContent = '▶';
    icon.classList.remove('spinning');
  }
}

/* ── Render all results ───────────────────────────────────────────── */
function renderResults(data) {
  const { results } = data;
  document.getElementById('bt-results').classList.remove('hidden');

  renderSummary(results);
  renderPairTable(results);
  renderEquityCurve(results);
  renderTradeLog(results);
}

/* ── Portfolio summary stats ──────────────────────────────────────── */
function renderSummary(results) {
  const totalTrades = results.reduce((s, r) => s + r.total_trades, 0);
  const totalWins   = results.reduce((s, r) => s + r.wins, 0);
  const wr          = totalTrades > 0 ? (totalWins / totalTrades * 100).toFixed(1) : 0;

  const validPf = results.filter(r => r.profit_factor > 0 && r.profit_factor < 999);
  const avgPf   = validPf.length ? (validPf.reduce((s, r) => s + r.profit_factor, 0) / validPf.length).toFixed(2) : '—';

  const avgRet  = results.length ? (results.reduce((s, r) => s + r.total_return, 0) / results.length).toFixed(2) : 0;
  const avgDd   = results.length ? (results.reduce((s, r) => s + r.max_drawdown, 0) / results.length).toFixed(2) : 0;
  const avgExp  = results.length ? (results.reduce((s, r) => s + r.expectancy, 0) / results.length).toFixed(2) : 0;

  document.getElementById('sum-trades').textContent = totalTrades;
  document.getElementById('sum-wr').textContent     = wr + '%';
  document.getElementById('sum-pf').textContent     = avgPf;
  document.getElementById('sum-ret').textContent    = (avgRet > 0 ? '+' : '') + avgRet + '%';
  document.getElementById('sum-dd').textContent     = avgDd + '%';
  document.getElementById('sum-exp').textContent    = '$' + avgExp;

  // Color the return and PF
  const retEl = document.getElementById('sum-ret');
  retEl.className = 'bt-stat-val ' + (avgRet >= 0 ? 'col-up' : 'col-dn');
  const pfEl = document.getElementById('sum-pf');
  pfEl.className = 'bt-stat-val ' + (parseFloat(avgPf) >= 1.0 ? 'col-up' : 'col-dn');
}

/* ── Per-pair results table ───────────────────────────────────────── */
function renderPairTable(results) {
  const tbody = document.getElementById('bt-pair-body');
  tbody.innerHTML = '';

  results.forEach((r, i) => {
    const color = PAIR_COLORS[i % PAIR_COLORS.length];
    const tr = document.createElement('tr');

    const retCls   = r.total_return >= 0 ? 'col-up' : 'col-dn';
    const pfCls    = r.profit_factor >= 1.0 ? 'col-up' : 'col-dn';
    const pnlCls   = r.net_pnl >= 0 ? 'col-up' : 'col-dn';
    const pfDisplay = r.profit_factor >= 999 ? '∞' : r.profit_factor.toFixed(2);
    const noTrades  = r.total_trades === 0;

    tr.innerHTML = `
      <td><span class="pair-name" style="color:${color}">${r.instrument}</span></td>
      <td class="mono">${r.total_trades}</td>
      <td class="mono col-up">${r.wins}</td>
      <td class="mono col-dn">${r.losses}</td>
      <td class="mono ${noTrades ? '' : (r.win_rate >= 50 ? 'col-up' : 'col-dn')}">${noTrades ? '—' : r.win_rate + '%'}</td>
      <td class="mono ${noTrades ? '' : pfCls}">${noTrades ? '—' : pfDisplay}</td>
      <td class="mono col-up">${r.avg_win ? '$' + r.avg_win.toFixed(2) : '—'}</td>
      <td class="mono col-dn">${r.avg_loss ? '$' + r.avg_loss.toFixed(2) : '—'}</td>
      <td class="mono ${noTrades ? '' : (r.expectancy >= 0 ? 'col-up' : 'col-dn')}">${noTrades ? '—' : '$' + r.expectancy.toFixed(2)}</td>
      <td class="mono ${pnlCls}">${r.net_pnl >= 0 ? '+' : ''}$${r.net_pnl.toFixed(2)}</td>
      <td class="mono ${retCls}">${r.total_return >= 0 ? '+' : ''}${r.total_return.toFixed(2)}%</td>
      <td class="mono ${r.max_drawdown > 15 ? 'col-dn' : ''}">${r.max_drawdown.toFixed(2)}%</td>
      <td><span class="mini-curve" id="mini-${i}"></span></td>
    `;
    tbody.appendChild(tr);

    // Mini sparkline for each row
    renderSparkline('mini-' + i, r.equity_curve, color);
  });
}

/* ── Mini sparkline SVG ───────────────────────────────────────────── */
function renderSparkline(id, curve, color) {
  const el = document.getElementById(id);
  if (!el || curve.length < 2) return;
  const W = 80, H = 28;
  const min = Math.min(...curve);
  const max = Math.max(...curve);
  const range = max - min || 1;
  const pts = curve.map((v, i) => {
    const x = (i / (curve.length - 1)) * W;
    const y = H - ((v - min) / range) * H;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  el.innerHTML = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
    <polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linejoin="round"/>
  </svg>`;
}

/* ── Equity curve Chart.js ────────────────────────────────────────── */
function renderEquityCurve(results) {
  const canvas = document.getElementById('equity-chart');
  if (_btChart) { _btChart.destroy(); _btChart = null; }

  const datasets = results.map((r, i) => ({
    label: r.instrument,
    data: r.equity_curve.map((v, idx) => ({ x: idx, y: v })),
    borderColor: PAIR_COLORS[i % PAIR_COLORS.length],
    backgroundColor: 'transparent',
    borderWidth: 1.8,
    pointRadius: 0,
    tension: 0.3,
  }));

  _btChart = new Chart(canvas, {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: {
          type: 'linear',
          title: { display: true, text: 'Trade #', color: '#6b8099' },
          ticks: { color: '#6b8099', font: { family: 'Share Tech Mono', size: 11 } },
          grid:  { color: 'rgba(0,212,255,0.06)' },
        },
        y: {
          title: { display: true, text: 'Equity  ($)', color: '#6b8099' },
          ticks: {
            color: '#6b8099',
            font: { family: 'Share Tech Mono', size: 11 },
            callback: v => '$' + v.toLocaleString(),
          },
          grid: { color: 'rgba(0,212,255,0.06)' },
        },
      },
      plugins: {
        legend: {
          labels: {
            color: '#c8d6e5',
            font: { family: 'Rajdhani', size: 13 },
            boxWidth: 18,
          }
        },
        tooltip: {
          backgroundColor: 'rgba(5,11,26,0.92)',
          borderColor: 'rgba(0,212,255,0.3)',
          borderWidth: 1,
          titleColor: '#00d4ff',
          bodyColor: '#c8d6e5',
          callbacks: {
            label: ctx => ` ${ctx.dataset.label}: $${ctx.parsed.y.toFixed(2)}`,
          }
        }
      }
    }
  });
}

/* ── Trade log ────────────────────────────────────────────────────── */
function renderTradeLog(results) {
  const tbody = document.getElementById('trade-log-body');
  tbody.innerHTML = '';

  const allTrades = [];
  results.forEach(r => allTrades.push(...(r.trade_log || [])));

  if (!allTrades.length) {
    tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--txt2)">No trades generated</td></tr>';
    return;
  }

  allTrades.forEach(t => {
    const tr = document.createElement('tr');
    const isWin = t.pnl > 0;
    const dirCls = t.direction === 'long' ? 'col-up' : 'col-dn';
    const dirLabel = t.direction === 'long' ? '↑ LONG' : '↓ SHORT';
    const reasonCls = t.exit_reason === 'TP' ? 'col-up' : (t.exit_reason === 'SL' ? 'col-dn' : '');

    tr.innerHTML = `
      <td><span class="pair-name" style="font-size:12px">${t.instrument}</span></td>
      <td class="${dirCls}" style="font-family:var(--mono)">${dirLabel}</td>
      <td class="mono">${t.entry_px}</td>
      <td class="mono">${t.exit_px}</td>
      <td class="${reasonCls}" style="font-family:var(--mono)">${t.exit_reason}</td>
      <td class="mono">${t.bars_held}</td>
      <td class="mono ${isWin ? 'col-up' : 'col-dn'}">${isWin ? '+' : ''}$${t.pnl.toFixed(2)}</td>
      <td class="mono">${t.daily_adx}</td>
      <td class="mono">${t.weekly_adx}</td>
    `;
    tbody.appendChild(tr);
  });
}

/* ── Toggle trade log ─────────────────────────────────────────────── */
function toggleLog() {
  const wrap = document.getElementById('trade-log-wrap');
  wrap.classList.toggle('hidden');
}
