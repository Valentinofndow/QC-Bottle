// static/analysis.js — ANALYSIS PAGE
// menampilkan chart & breakdown defect

const $ = (s) => document.querySelector(s);
const el = (id) => document.getElementById(id);
const bust = () => `&_=${Date.now()}`;

let pollingActive = true;
document.addEventListener('visibilitychange', () => { pollingActive = !document.hidden; });

const ctl = { stats: null, detail: null };

function setText(id, v) { const n = el(id); if (n) n.textContent = v; }
function fmtPct(x) { return (Math.round((x ?? 0) * 100) / 100).toFixed(2); }
function ts() {
  const d = new Date(); const two = (n) => String(n).padStart(2, '0');
  return `${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}`;
}

/* === CHART SETUP === */
let pieOverall = null;
let barDefects = null;

function initCharts() {
  const ctxPie = el('pieOverall');
  const ctxBar = el('barDefects');

  if (ctxPie) {
    pieOverall = new Chart(ctxPie, {
      type: 'doughnut',
      data: {
        labels: ['Good', 'Defect'],
        datasets: [{
          data: [0, 0],
          backgroundColor: ['#66BB6A', '#EF5350'],
          borderWidth: 1
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '70%',
        plugins: {
          legend: { position: 'bottom', labels: { color: '#ddd' } }
        }
      }
    });
  }

  if (ctxBar) {
    barDefects = new Chart(ctxBar, {
      type: 'bar',
      data: {
        labels: ['Touching Characters', 'Double Print', 'Missing Text'],
        datasets: [{
          label: 'Count',
          data: [0, 0, 0],
          backgroundColor: ['#64B5F6', '#FFB74D', '#EF9A9A'],
          borderWidth: 1
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: {
            ticks: { color: '#ddd', font: { size: 11 } },
            grid: { color: 'rgba(255,255,255,0.05)' }
          },
          y: {
            ticks: { color: '#ddd' },
            grid: { color: 'rgba(255,255,255,0.05)' },
            beginAtZero: true,
            precision: 0
          }
        },
        plugins: { legend: { display: false } }
      }
    });
  }
}
initCharts();

/* === /stats endpoint === */
async function pollStats() {
  if (!pollingActive) return;
  try {
    if (ctl.stats) ctl.stats.abort();
    ctl.stats = new AbortController();

    const r = await fetch(`/stats?t=${Date.now()}${bust()}`, { signal: ctl.stats.signal });
    if (!r.ok) return;
    const d = await r.json();

    const good = d.good ?? 0;
    const defect = d.defect ?? 0;

    setText('kpi_good', good);
    setText('kpi_defect', defect);
    setText('kpi_pct_good', `${fmtPct(d.percent_good ?? 0)}%`);
    setText('kpi_pct_def', `${fmtPct(d.percent_defect ?? 0)}%`);

    if (pieOverall) {
      pieOverall.data.datasets[0].data = [good, defect];
      pieOverall.update();
    }

    setText('last_update', ts());
  } catch (err) {
    console.warn("pollStats error:", err);
  } finally {
    ctl.stats = null;
  }
}

/* === /stats_detail endpoint === */
async function pollDetail() {
  if (!pollingActive) return;
  try {
    if (ctl.detail) ctl.detail.abort();
    ctl.detail = new AbortController();

    const r = await fetch(`/stats_detail?t=${Date.now()}${bust()}`, { signal: ctl.detail.signal });
    if (!r.ok) return;
    const d = await r.json();

    const touching = d['Touching_Characters'] ?? 0;
    const doubles  = d['Double_Print'] ?? 0;
    const missing  = d['Missing_Text'] ?? 0;

    setText('bd_touching', touching);
    setText('bd_double', doubles);
    setText('bd_missing', missing);

    if (barDefects) {
      barDefects.data.datasets[0].data = [touching, doubles, missing];
      barDefects.update();
    }

    setText('last_update', ts());
  } catch (err) {
    console.warn("pollDetail error:", err);
  } finally {
    ctl.detail = null;
  }
}

/* === Start polling === */
pollStats();
pollDetail();
setInterval(pollStats, 2000);
setInterval(pollDetail, 2000);
