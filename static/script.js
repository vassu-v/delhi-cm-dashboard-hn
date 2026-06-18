// ── Counter animation ────────────────────────────────────────────
function animateCounter(el, target, suffix = '') {
  if (!el) return;
  const duration = 700;
  const start    = performance.now();
  function tick(now) {
    const progress = Math.min((now - start) / duration, 1);
    const eased    = 1 - Math.pow(1 - progress, 3);
    el.textContent = Math.round(eased * target).toLocaleString() + suffix;
    if (progress < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

// ── Utilities ────────────────────────────────────────────────────
function esc(t) { const d = document.createElement('div'); d.textContent = t || ''; return d.innerHTML; }
function fmt(n) { return (n || 0).toLocaleString(); }
function fmtDate(s) {
  if (!s) return '—';
  const d = new Date(s);
  return isNaN(d) ? s : d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

function statusTag(s) {
  const cls = { 'Received': 'tag-received', 'Assigned': 'tag-assigned', 'In Progress': 'tag-progress', 'Resolved': 'tag-resolved' };
  return `<span class="tag ${cls[s] || 'tag-received'}">${esc(s)}</span>`;
}
function priorityTag(p) {
  const cls = { low: 'tag-low', medium: 'tag-medium', high: 'tag-high', critical: 'tag-critical' };
  return `<span class="tag ${cls[p] || 'tag-medium'}">${esc(p || 'medium')}</span>`;
}
function perfClass(r) {
  if (!r) return 'avg';
  const l = r.toLowerCase();
  if (l === 'good' || l === 'excellent') return 'good';
  if (l === 'poor') return 'poor';
  return 'avg';
}

// ── Navigation ───────────────────────────────────────────────────
let currentPage    = 'overview';
let advisorAutoRun = false;
let advisorCache   = null;

function goPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(n => n.classList.remove('active'));
  const page = document.getElementById('page-' + name);
  if (page) page.classList.add('active');
  const tab = document.querySelector(`.nav-tab[data-page="${name}"]`);
  if (tab) tab.classList.add('active');
  currentPage = name;
  const loaders = {
    overview:    loadOverview,
    districts:   loadDistricts,
    departments: loadDepartments,
    issues:      loadClusters,
    submit:      () => {},
  };
  if (loaders[name]) loaders[name]();
  const fab = document.getElementById('fab-log-complaint');
  if (fab) fab.style.display = name === 'submit' ? 'none' : '';
}

// ── API ──────────────────────────────────────────────────────────
async function api(path, opts = {}) {
  const r = await fetch('/api' + path, { headers: { 'Content-Type': 'application/json' }, ...opts });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// ── OVERVIEW ─────────────────────────────────────────────────────
async function loadOverview() {
  try {
    const now = new Date();
    document.getElementById('overview-date-sub').textContent = now.toLocaleDateString('en-IN', {
      weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'
    });

    const [city, surges, depts, recentClusters, staleClusters] = await Promise.all([
      api('/patterns/city'),
      api('/patterns/surges'),
      api('/patterns/departments'),
      api('/recent-clusters?limit=10'),
      api('/stale-clusters?limit=5'),
    ]);

    animateCounter(document.getElementById('stat-total'),    city.total || 0);
    animateCounter(document.getElementById('stat-open'),     city.open || 0);
    animateCounter(document.getElementById('stat-critical'), city.critical || 0);
    animateCounter(document.getElementById('stat-rate'),     city.resolution_rate || 0, '%');
    document.getElementById('topbar-open').textContent = fmt(city.open) + ' active issues';

    const sl = document.getElementById('overview-status-line');
    if (sl) sl.textContent = `${fmt(city.stale)} stale · avg ${city.avg_resolution_days}d to resolve · ${fmt(city.total)} total`;

    const surgeChip = document.getElementById('topbar-surge');
    if (city.surge_count > 0) {
      surgeChip.classList.add('active');
      document.getElementById('topbar-surge-text').textContent =
        city.surge_count + (city.surge_count === 1 ? ' surge' : ' surges');
    } else {
      surgeChip.classList.remove('active');
    }

    renderSurgeBanner(surges);
    renderNeedsAttention(surges, staleClusters);
    await loadHeatmap();
    renderDeptTable(depts, 'dept-table-body');
    renderClusterFeed(recentClusters, 'recent-feed');
  } catch (e) { console.error('Overview error:', e); }
}

// ── NEEDS ATTENTION ───────────────────────────────────────────────
function renderNeedsAttention(surges, staleClusters) {
  const bar = document.getElementById('needs-attention-bar');
  if (!bar) return;

  let html = '';

  if (surges && surges.length > 0) {
    const s = surges[0];
    html += `<span class="na-badge na-surge">SURGE</span>
      <span class="na-text">
        <b>${esc(s.district)} / ${esc(s.category)}</b> — ${s.recent_count} complaints this week
        ${s.label ? `(${esc(s.label)})` : ''}
        <span class="na-link" onclick="filterIssuesByDistrictCat('${esc(s.district)}','${esc(s.category)}')">View issues →</span>
      </span>`;
  }

  if (staleClusters && staleClusters.length > 0) {
    const c = staleClusters[0];
    if (html) html += `<span style="margin:0 10px;color:var(--line)">|</span>`;
    html += `<span class="na-badge na-stale">STALE</span>
      <span class="na-text">
        <b>${esc(c.district)}</b> — ${esc((c.summary || '').slice(0, 55))}
        (${c.weight} citizens · ${c.days_since_update}d)
        <span class="na-link" onclick="openClusterModal(${parseInt(c.id, 10)})">View →</span>
      </span>`;
  }

  if (html) {
    bar.innerHTML = html;
    bar.style.display = 'flex';
  } else {
    bar.style.display = 'none';
  }
}

// ── SURGE BANNER ─────────────────────────────────────────────────
function renderSurgeBanner(surges) {
  const banner = document.getElementById('surge-banner');
  const items  = document.getElementById('surge-banner-items');
  if (!surges || surges.length === 0) { banner.classList.remove('active'); return; }
  banner.classList.add('active');
  items.innerHTML = surges.slice(0, 6).map(s => {
    const mult = s.surge_ratio ? Math.round(s.surge_ratio) + '×' : (s.recent_count + ' this week');
    return `<div class="surge-inline" style="cursor:pointer" title="Click to filter issues"
        onclick="filterIssuesByDistrictCat('${esc(s.district)}','${esc(s.category)}')">
      <span class="surge-inline-mult">${esc(mult)}</span>
      <span class="surge-inline-loc">${esc(s.district)} · ${esc(s.category)}</span>
    </div>`;
  }).join('');
}

function filterIssuesByDistrictCat(district, category) {
  goPage('issues');
  setTimeout(() => {
    const d = document.getElementById('if-district');
    const c = document.getElementById('if-category');
    if (d) d.value = district;
    if (c) c.value = category;
    loadClusters();
  }, 80);
}

// ── HEATMAP ──────────────────────────────────────────────────────
async function loadHeatmap() {
  const data = await api('/patterns/heatmap');
  const { districts, categories, matrix, max_value } = data;

  document.getElementById('heatmap-labels').innerHTML =
    categories.map(c => `<div class="heatmap-cat-label">${esc(c)}</div>`).join('');

  document.getElementById('heatmap-grid').innerHTML = districts.map(d => {
    const cells = categories.map(cat => {
      const val = (matrix[d] && matrix[d][cat]) || 0;
      const { bg, text, border } = heatColor(val === 0 ? 0 : val / (max_value || 1));
      const zeroClass = val === 0 ? ' zero' : '';
      return `<div class="heatmap-cell${zeroClass}"
        style="background:${bg};color:${text};border-color:${border}"
        title="${esc(d)} · ${esc(cat)}: ${val} complaints"
        onclick="heatmapClick('${esc(d)}','${esc(cat)}')">${val > 0 ? val : ''}</div>`;
    }).join('');
    return `<div class="heatmap-row"><div class="heatmap-district-label">${esc(d)}</div>${cells}</div>`;
  }).join('');

  const legend = document.getElementById('heatmap-legend');
  if (legend) {
    legend.innerHTML = `
      <span>Low</span>
      <div class="hm-swatch" style="background:rgba(217,119,6,0.2)"></div>
      <div class="hm-swatch" style="background:rgba(217,119,6,0.5)"></div>
      <div class="hm-swatch" style="background:rgba(220,38,38,0.4)"></div>
      <div class="hm-swatch" style="background:rgba(220,38,38,0.7)"></div>
      <div class="hm-swatch" style="background:rgba(220,38,38,1.0)"></div>
      <span>High</span>`;
  }
}

function heatColor(intensity) {
  if (intensity < 0.01) return { bg: 'var(--raised)', text: 'transparent', border: 'var(--border)' };
  if (intensity < 0.4) {
    const a     = intensity / 0.4;
    const alpha = 0.15 + a * 0.45;
    return {
      bg:     `rgba(217, 119, 6, ${alpha})`,
      text:   alpha > 0.38 ? '#92400e' : 'var(--muted)',
      border: `rgba(217, 119, 6, ${alpha + 0.12})`
    };
  }
  const a     = (intensity - 0.4) / 0.6;
  const alpha = 0.35 + a * 0.65;
  return {
    bg:     `rgba(220, 38, 38, ${alpha})`,
    text:   alpha > 0.55 ? 'white' : '#991b1b',
    border: `rgba(220, 38, 38, ${alpha + 0.08})`
  };
}

function heatmapClick(district, category) {
  filterIssuesByDistrictCat(district, category);
}

// ── DEPT TABLE (overview) ─────────────────────────────────────────
function renderDeptTable(depts, tbodyId) {
  const el = document.getElementById(tbodyId);
  if (!depts || depts.length === 0) {
    el.innerHTML = '<tr><td colspan="6" style="padding:20px;text-align:center;color:var(--muted)">No data</td></tr>';
    return;
  }
  el.innerHTML = depts.map(d => {
    const rate = d.resolution_rate || 0;
    const pc   = perfClass(d.performance_rating);
    const bar  = `<div class="res-bar-wrap">
      <div class="res-bar"><div class="res-bar-fill ${pc}" style="width:${rate}%"></div></div>
      <span class="res-pct perf-${pc}">${rate}%</span>
    </div>`;
    return `<tr>
      <td><b>${esc(d.department)}</b></td>
      <td style="font-family:'IBM Plex Mono',monospace;font-weight:700;color:var(--amber)">${fmt(d.open_count)}</td>
      <td style="min-width:140px">${bar}</td>
      <td style="font-family:'IBM Plex Mono',monospace;color:var(--muted)">${d.avg_resolution_days}d</td>
      <td style="font-family:'IBM Plex Mono',monospace;${d.stale_count > 0 ? 'color:var(--red);font-weight:700' : 'color:var(--muted)'}">${fmt(d.stale_count)}</td>
      <td class="perf-${pc}">${esc(d.performance_rating)}</td>
    </tr>`;
  }).join('');
}

// ── CLUSTER FEED (overview recent-feed) ───────────────────────────
function renderClusterFeed(clusters, containerId) {
  const el = document.getElementById(containerId);
  if (!clusters || clusters.length === 0) {
    el.innerHTML = '<div class="empty" style="padding:32px 0"><div class="empty-text">No active issue clusters</div></div>';
    return;
  }
  el.innerHTML = clusters.map(c => {
    const cls = c.priority === 'critical' ? 'critical' : c.priority === 'high' ? 'high' : '';
    const stale = c.stale_flag ? `<span class="tag tag-stale" style="margin-left:4px">Stale</span>` : '';
    return `<div class="feed-item ${cls}" onclick="openClusterModal(${parseInt(c.id,10)})">
      <div style="flex:1;min-width:0">
        <div class="feed-title" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
          ${esc((c.summary || '').slice(0, 60))}${stale}
        </div>
        <div class="feed-meta">${esc(c.district)} · ${esc(c.category || '—')} · ${c.weight} citizens · ${statusTag(c.status)}</div>
      </div>
    </div>`;
  }).join('');
}

// ── DISTRICTS ────────────────────────────────────────────────────
let districtData = [];

async function loadDistricts() {
  try {
    const data = await api('/patterns/districts');
    districtData = data;
    const sel = document.getElementById('district-select');
    sel.innerHTML = '<option value="">— Select a district to see its breakdown —</option>' +
      data.map(d => `<option value="${esc(d.district)}">${esc(d.district)}</option>`).join('');
    renderDistrictList(data);
  } catch (e) { console.error(e); }
}

function renderDistrictList(data) {
  document.getElementById('district-list').innerHTML = data.map(d => {
    const level = d.critical_count > 5 ? 'critical' : d.critical_count > 0 ? 'high' : 'low';
    return `<div class="district-card" onclick="selectDistrict('${esc(d.district)}')">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
        <b style="font-family:'IBM Plex Serif',serif;font-size:15px">${esc(d.district)}</b>
        <span class="tag tag-${level}">${level}</span>
      </div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;text-align:center">
        <div>
          <div style="font-family:'IBM Plex Serif',serif;font-size:20px;font-weight:600;color:var(--blue)">${fmt(d.total)}</div>
          <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px">Total</div>
        </div>
        <div>
          <div style="font-family:'IBM Plex Serif',serif;font-size:20px;font-weight:600;color:var(--amber)">${fmt(d.open_count)}</div>
          <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px">Open</div>
        </div>
        <div>
          <div style="font-family:'IBM Plex Serif',serif;font-size:20px;font-weight:600;color:var(--green)">${d.resolution_rate}%</div>
          <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px">Resolved</div>
        </div>
      </div>
      <div style="margin-top:8px;font-size:11px;color:var(--muted)">
        ${(d.top_categories || []).slice(0, 3).map(c => `${esc(c.category)} (${c.cnt})`).join(' · ')}
      </div>
    </div>`;
  }).join('');
}

function selectDistrict(name) {
  document.getElementById('district-select').value = name;
  document.querySelectorAll('.district-card').forEach(c => c.classList.remove('active'));
  onDistrictSelect();
}

async function onDistrictSelect() {
  const name = document.getElementById('district-select').value;
  if (!name) return;
  const d = districtData.find(x => x.district === name);
  if (!d) return;

  document.getElementById('district-detail').innerHTML = `
    <div class="card" style="margin-bottom:14px">
      <div style="font-size:9px;letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);margin-bottom:14px">${esc(name).toUpperCase()}</div>
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;text-align:center">
        <div>
          <div style="font-family:'IBM Plex Serif',serif;font-size:28px;font-weight:600;color:var(--blue)">${fmt(d.total)}</div>
          <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px">Total</div>
        </div>
        <div>
          <div style="font-family:'IBM Plex Serif',serif;font-size:28px;font-weight:600;color:var(--amber)">${fmt(d.open_count)}</div>
          <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px">Open</div>
        </div>
        <div>
          <div style="font-family:'IBM Plex Serif',serif;font-size:28px;font-weight:600;color:var(--red)">${fmt(d.critical_count)}</div>
          <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px">Critical</div>
        </div>
        <div>
          <div style="font-family:'IBM Plex Serif',serif;font-size:28px;font-weight:600;color:var(--green)">${d.resolution_rate}%</div>
          <div style="font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:0.5px">Resolved</div>
        </div>
      </div>
    </div>
    <div class="card" style="margin-bottom:14px">
      <div class="card-title">Top Issue Categories</div>
      ${(d.top_categories || []).map(c => `
        <div style="display:flex;align-items:center;justify-content:space-between;padding:9px 0;border-bottom:1px solid var(--raised)">
          <span style="font-size:13px">${esc(c.category)}</span>
          <span style="font-family:'IBM Plex Mono',monospace;font-weight:700;color:var(--blue-mid)">${c.cnt}</span>
        </div>`).join('')}
    </div>
    <div class="card">
      <div class="card-title">Recent Grievances</div>
      ${(d.recent_grievances || []).map(g => `
        <div class="feed-item ${g.priority === 'critical' ? 'critical' : g.priority === 'high' ? 'high' : ''}" onclick="openGrievanceModal(${parseInt(g.id,10)})">
          <div>
            <div class="feed-title">${esc((g.title || g.description || '').slice(0, 60))}</div>
            <div class="feed-meta">${esc(g.category)} · ${statusTag(g.status)} · ${fmtDate(g.date_received)}</div>
          </div>
        </div>`).join('')}
    </div>`;
}

// ── DEPARTMENTS ───────────────────────────────────────────────────
async function loadDepartments() {
  try {
    const depts = await api('/patterns/departments');
    document.getElementById('dept-cards').innerHTML = depts.map(d => {
      const rate = d.resolution_rate || 0;
      const pc   = perfClass(d.performance_rating);
      const staleHtml = d.stale_grievances && d.stale_grievances.length > 0
        ? `<div class="dept-stale-label">Stale / Overdue Grievances</div>
           ${d.stale_grievances.map(g => `
             <div class="dept-stale-item">
               <span class="tag tag-stale">Stale</span>
               <span style="flex:1;font-size:12px">${esc(g.title)}</span>
               <span style="font-size:11px;color:var(--muted)">${esc(g.district)}</span>
               <span class="dept-stale-days">${g.days_since_update}d</span>
             </div>`).join('')}` : '';
      return `<div class="dept-card">
        <div class="dept-card-header">
          <div class="dept-card-name">${esc(d.department)}</div>
          <span class="perf-${pc}">${esc(d.performance_rating)}</span>
        </div>
        <div class="dept-metrics">
          <div>
            <div class="dept-metric-val" style="color:var(--amber)">${fmt(d.open_count)}</div>
            <div class="dept-metric-lbl">Open Reports</div>
          </div>
          <div>
            <div class="dept-metric-val" style="color:var(--green)">${rate}%</div>
            <div class="dept-metric-lbl">Resolved</div>
          </div>
          <div>
            <div class="dept-metric-val" style="color:var(--blue)">${d.avg_resolution_days}d</div>
            <div class="dept-metric-lbl">Avg Days</div>
          </div>
          <div>
            <div class="dept-metric-val" style="color:var(--red)">${fmt(d.stale_count)}</div>
            <div class="dept-metric-lbl">Stale Reports</div>
          </div>
        </div>
        <div class="dept-res-row">
          <div class="dept-res-label">Resolution rate</div>
          <div class="res-bar" style="flex:1"><div class="res-bar-fill ${pc}" style="width:${rate}%"></div></div>
          <span class="res-pct perf-${pc}">${rate}%</span>
        </div>
        ${staleHtml ? `<div style="margin-top:14px;border-top:1px solid var(--line);padding-top:12px">${staleHtml}</div>` : ''}
      </div>`;
    }).join('');
  } catch (e) { console.error(e); }
}

// ── ISSUES (CLUSTERS) ─────────────────────────────────────────────
async function loadClusters() {
  const params = new URLSearchParams();
  ['district', 'department', 'status', 'priority', 'category'].forEach(k => {
    const el = document.getElementById('if-' + k);
    if (el && el.value) params.append(k, el.value);
  });

  const tbody = document.getElementById('cluster-tbody');
  tbody.innerHTML = '<tr><td colspan="7" style="padding:28px;text-align:center"><span class="loading"></span></td></tr>';

  try {
    const data = await api('/clusters?' + params.toString());
    const countBar = document.getElementById('issues-count-bar');
    if (countBar) {
      const statusFilter = document.getElementById('if-status');
      const label = (statusFilter && statusFilter.value) ? statusFilter.value : 'active';
      countBar.textContent = data.length > 0
        ? `${data.length} ${label} issue cluster${data.length !== 1 ? 's' : ''}`
        : '';
    }

    if (data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="padding:48px;text-align:center">
        <div class="empty-icon" style="font-size:20px;opacity:0.3;margin-bottom:8px">📋</div>
        <div style="color:var(--muted);font-family:'IBM Plex Serif',serif">No issue clusters match these filters</div>
      </td></tr>`;
      return;
    }

    tbody.innerHTML = data.map(c => {
      const pRow  = c.priority === 'critical' ? 'p-critical' : c.priority === 'high' ? 'p-high' : '';
      const stale = c.stale_flag
        ? `<span class="tag tag-stale" style="margin-left:4px;font-size:9px">Stale&nbsp;${c.days_since_update}d</span>`
        : '';
      const dept  = c.department_assigned || '<span style="color:var(--dim)">—</span>';
      return `<tr class="clickable ${pRow}${c.stale_flag ? ' stale-row' : ''}" onclick="openClusterModal(${parseInt(c.id,10)})">
        <td>
          <span style="font-size:13px;font-weight:500">${esc((c.summary || '').slice(0, 60))}</span>${stale}
        </td>
        <td>${esc(c.district || '—')}</td>
        <td>${esc(c.category || '—')}</td>
        <td>${esc(c.department_assigned || '—')}</td>
        <td>
          <span style="font-family:'IBM Plex Mono',monospace;font-weight:700;color:var(--blue-mid)">${c.weight}</span>
          <span style="font-size:11px;color:var(--muted)"> citizens</span>
        </td>
        <td>${statusTag(c.status)}</td>
        <td>${priorityTag(c.priority)}</td>
      </tr>`;
    }).join('');
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" style="color:var(--red);padding:16px">${esc(e.message)}</td></tr>`;
  }
}

// ── CLUSTER MODAL ─────────────────────────────────────────────────
async function openClusterModal(id) {
  const modal = document.getElementById('cluster-modal');
  modal.classList.add('open');
  document.getElementById('cluster-modal-body').innerHTML =
    '<div style="text-align:center;padding:48px"><span class="loading"></span></div>';

  try {
    const c = await api('/clusters/' + id);
    document.getElementById('cluster-modal-title').textContent =
      `Issue Cluster · ${c.district || '—'} · ${c.category || '—'}`;

    const statuses = ['Received', 'Assigned', 'In Progress', 'Resolved'];
    const curIdx   = statuses.indexOf(c.status);
    const timeline = statuses.map((s, i) => {
      let cls = '';
      if (i < curIdx)      cls = 'done';
      else if (i === curIdx) cls = c.status === 'Resolved' ? 'done-final' : 'current';
      const tick = i < curIdx ? '✓' : i + 1;
      return `<div class="status-step ${cls}">
        <div class="status-dot">${tick}</div>
        <div class="status-name">${s}</div>
      </div>`;
    }).join('');

    const priorityHint = c.weight >= 5
      ? '<span class="priority-auto-hint"> · auto-escalated: 5+ citizens</span>'
      : c.weight >= 3
      ? '<span class="priority-auto-hint"> · auto-escalated: 3+ citizens</span>'
      : '';

    const grievances = c.grievances || [];
    const gList = grievances.length > 0
      ? grievances.map(g => `
        <div class="linked-grievance" onclick="openGrievanceModal(${parseInt(g.id,10)})">
          <div class="linked-g-desc">${esc((g.title || g.description || '').slice(0, 80))}</div>
          <div class="linked-g-meta">
            ${esc(g.citizen_name || 'Unknown citizen')}
            · ${fmtDate(g.date_received)}
            · ${esc(g.source || '—')}
            · ${statusTag(g.status)}
          </div>
        </div>`).join('')
      : '<div style="padding:16px;text-align:center;color:var(--muted);font-size:13px">No linked reports yet</div>';

    const DEPTS_ALL = ['MCD','PWD','DJB','DUSIB','Delhi Police','Transport Department',
                       'Health Department','Education Department','Revenue Department','BSES'];

    document.getElementById('cluster-modal-body').innerHTML = `
      <div class="status-timeline" style="margin-bottom:20px">${timeline}</div>

      <div class="detail-desc">${esc((c.summary || '').slice(0, 200))}</div>

      <div class="detail-row">
        <div class="detail-label">District</div>
        <div class="detail-value">${esc(c.district || '—')}</div>
      </div>
      <div class="detail-row">
        <div class="detail-label">Category</div>
        <div class="detail-value">${esc(c.category || '—')}</div>
      </div>
      <div class="detail-row">
        <div class="detail-label">Department</div>
        <div class="detail-value">${esc(c.department_assigned || 'Unassigned')}</div>
      </div>
      <div class="detail-row">
        <div class="detail-label">Citizens Affected</div>
        <div class="detail-value">
          <b style="font-family:'IBM Plex Serif',serif;font-size:18px;color:var(--blue)">${c.weight}</b>
          <span style="color:var(--muted);font-size:12px"> citizens in this cluster</span>
        </div>
      </div>
      <div class="detail-row">
        <div class="detail-label">Priority</div>
        <div class="detail-value">${priorityTag(c.priority)}${priorityHint}</div>
      </div>
      ${c.stale_flag ? `
      <div class="detail-row">
        <div class="detail-label">Attention</div>
        <div class="detail-value"><span class="tag tag-stale">Stale · ${c.days_since_update} days without update</span></div>
      </div>` : ''}
      <div class="detail-row">
        <div class="detail-label">Received</div>
        <div class="detail-value">${fmtDate(c.date_received)}</div>
      </div>
      ${c.date_assigned ? `<div class="detail-row"><div class="detail-label">Assigned</div><div class="detail-value">${fmtDate(c.date_assigned)}</div></div>` : ''}
      ${c.date_resolved ? `<div class="detail-row"><div class="detail-label">Resolved</div><div class="detail-value" style="color:var(--green)">${fmtDate(c.date_resolved)}</div></div>` : ''}

      <div class="modal-actions">
        <select class="form-select" id="cluster-status-sel" style="flex:1;padding:7px 10px">
          ${statuses.map(s => `<option ${s === c.status ? 'selected' : ''}>${s}</option>`).join('')}
        </select>
        <button class="btn btn-primary btn-sm" onclick="updateClusterStatus(${parseInt(c.id,10)})">Update Status</button>
      </div>
      <div id="cluster-update-msg" style="font-size:12px;color:var(--green);margin-top:6px;min-height:16px"></div>

      <div style="margin-top:20px;border-top:1px solid var(--line);padding-top:16px">
        <div class="card-title" style="margin-bottom:12px">
          ${grievances.length} citizen report${grievances.length !== 1 ? 's' : ''} in this cluster
          <span style="font-size:11px;color:var(--dim);font-weight:400">click a report to view details</span>
        </div>
        <div class="linked-grievances-list">${gList}</div>
      </div>`;
  } catch (e) {
    document.getElementById('cluster-modal-body').innerHTML =
      `<div style="color:var(--red);padding:20px">${esc(e.message)}</div>`;
  }
}

async function updateClusterStatus(id) {
  const sel = document.getElementById('cluster-status-sel');
  const msg = document.getElementById('cluster-update-msg');
  try {
    const res = await api('/clusters/' + id + '/status', {
      method: 'POST', body: JSON.stringify({ status: sel.value })
    });
    msg.textContent = `Updated cluster and ${res.affected_grievances} linked report${res.affected_grievances !== 1 ? 's' : ''} to "${sel.value}"`;
    setTimeout(() => {
      closeClusterModal();
      if (currentPage === 'issues')    loadClusters();
      if (currentPage === 'overview')  loadOverview();
    }, 1600);
  } catch (e) {
    msg.style.color = 'var(--red)';
    msg.textContent = 'Error: ' + e.message;
  }
}

function closeClusterModal() {
  document.getElementById('cluster-modal').classList.remove('open');
}

// ── AI SIDE PANEL ─────────────────────────────────────────────────
function toggleAIPanel() {
  const panel   = document.getElementById('ai-panel');
  const overlay = document.getElementById('ai-overlay');
  const btn     = document.getElementById('topbar-ai-toggle');
  const isOpen  = panel.classList.contains('open');
  if (isOpen) {
    panel.classList.remove('open');
    overlay.classList.remove('open');
    if (btn) btn.classList.remove('active');
  } else {
    panel.classList.add('open');
    overlay.classList.add('open');
    if (btn) btn.classList.add('active');
  }
}

function switchAIPanelTab(name) {
  document.querySelectorAll('.ai-panel-tab').forEach(t =>
    t.classList.toggle('active', t.dataset.panel === name)
  );
  document.querySelectorAll('.ai-panel-section').forEach(s =>
    s.classList.toggle('active', s.id === 'aip-' + name)
  );
  if (name === 'advisor' && !advisorAutoRun) {
    advisorAutoRun = true;
    runAdvisor();
  }
}

// ── GRIEVANCE MODAL (district drill-down) ─────────────────────────
async function openGrievanceModal(id) {
  const modal = document.getElementById('grievance-modal');
  modal.classList.add('open');
  document.getElementById('modal-body').innerHTML =
    '<div style="text-align:center;padding:48px"><span class="loading"></span></div>';
  try {
    const g = await api('/grievances/' + id);
    document.getElementById('modal-title').textContent = `Grievance #${g.id}`;
    const statuses = ['Received', 'Assigned', 'In Progress', 'Resolved'];
    const curIdx   = statuses.indexOf(g.status);
    const timeline = statuses.map((s, i) => {
      let cls = '';
      if (i < curIdx)      cls = 'done';
      else if (i === curIdx) cls = g.status === 'Resolved' ? 'done-final' : 'current';
      const tick = i < curIdx ? '✓' : i + 1;
      return `<div class="status-step ${cls}">
        <div class="status-dot">${tick}</div>
        <div class="status-name">${s}</div>
      </div>`;
    }).join('');

    document.getElementById('modal-body').innerHTML = `
      <div class="status-timeline">${timeline}</div>
      ${g.description ? `<div class="detail-desc">${esc(g.description)}</div>` : ''}
      <div class="detail-row"><div class="detail-label">District</div><div class="detail-value">${esc(g.district || '—')}</div></div>
      <div class="detail-row"><div class="detail-label">Category</div><div class="detail-value">${esc(g.category || '—')}</div></div>
      <div class="detail-row"><div class="detail-label">Department</div><div class="detail-value">${esc(g.department_assigned || '—')}</div></div>
      <div class="detail-row"><div class="detail-label">Priority</div><div class="detail-value">${priorityTag(g.priority)}</div></div>
      <div class="detail-row"><div class="detail-label">Citizen</div><div class="detail-value">${esc(g.citizen_name || '—')}${g.citizen_contact ? ' · ' + esc(g.citizen_contact) : ''}</div></div>
      <div class="detail-row"><div class="detail-label">Received via</div><div class="detail-value">${esc(g.source || '—')}</div></div>
      <div class="detail-row"><div class="detail-label">Date Received</div><div class="detail-value">${fmtDate(g.date_received)}</div></div>
      <div class="detail-row"><div class="detail-label">Date Assigned</div><div class="detail-value">${fmtDate(g.date_assigned)}</div></div>
      ${g.date_resolved ? `<div class="detail-row"><div class="detail-label">Date Resolved</div><div class="detail-value" style="color:var(--green)">${fmtDate(g.date_resolved)}</div></div>` : ''}
      ${g.stale_flag ? `<div class="detail-row"><div class="detail-label">Attention</div><div class="detail-value"><span class="tag tag-stale">Stale · ${g.days_since_update} days without update</span></div></div>` : ''}
      ${g.cluster_id ? `<div class="detail-row"><div class="detail-label">Cluster</div><div class="detail-value"><a href="#" onclick="closeModal();openClusterModal(${parseInt(g.cluster_id,10)});return false" style="color:var(--blue);text-decoration:underline">View issue cluster #${g.cluster_id} →</a></div></div>` : ''}
      <div class="modal-actions">
        ${g.cluster_id
          ? `<span style="font-size:12px;color:var(--muted);flex:1">Status is managed at the cluster level.</span>`
          : `<span style="font-size:12px;color:var(--muted);flex:1">This report has not been assigned to a cluster yet.</span>`}
        <button class="btn btn-ghost btn-sm" onclick="closeModal()">Close</button>
      </div>`;
  } catch (e) {
    document.getElementById('modal-body').innerHTML =
      `<div style="color:var(--red);padding:20px">${esc(e.message)}</div>`;
  }
}

function closeModal() {
  document.getElementById('grievance-modal').classList.remove('open');
}

// ── SUBMIT ────────────────────────────────────────────────────────
async function submitGrievance(e) {
  e.preventDefault();
  const btn        = document.getElementById('submit-btn');
  const clusterDiv = document.getElementById('cluster-match');
  const successDiv = document.getElementById('submit-success');
  const successSub = document.getElementById('submit-success-sub');
  btn.disabled = true; btn.textContent = 'Submitting…';
  clusterDiv.style.display = 'none';

  const data = {
    description:     document.getElementById('s-description').value,
    district:        document.getElementById('s-district').value,
    category:        document.getElementById('s-category').value,
    priority:        document.getElementById('s-priority').value,
    citizen_name:    document.getElementById('s-name').value,
    citizen_contact: document.getElementById('s-contact').value,
    citizen_email:   document.getElementById('s-email').value,
    source:          document.getElementById('s-source').value,
  };

  try {
    const res = await api('/grievances', { method: 'POST', body: JSON.stringify(data) });
    if (res.cluster_match) {
      clusterDiv.style.display = 'block';
      clusterDiv.innerHTML = `<b>Similar complaints found in your area.</b> ${esc(res.cluster_summary)} — ${res.cluster_weight} related complaint${res.cluster_weight !== 1 ? 's' : ''} grouped together.`;
    }
    let subText = 'The complaint has been recorded and routed to the appropriate department.';
    if (res.cluster_match) subText += ` Grouped with ${res.cluster_weight} similar complaint(s) in the same area.`;
    successSub.textContent = subText;
    successDiv.classList.add('active');
    document.getElementById('submit-form').style.display = 'none';
    setTimeout(() => {
      successDiv.classList.remove('active');
      document.getElementById('submit-form').style.display = '';
      document.getElementById('submit-form').reset();
      clusterDiv.style.display = 'none';
      btn.disabled = false; btn.textContent = 'Submit Complaint';
    }, 5000);
  } catch (e) {
    btn.disabled = false; btn.textContent = 'Submit Complaint';
    alert('Error: ' + e.message);
  }
}

// ── CHAT ──────────────────────────────────────────────────────────
let chatHistory       = [];
let chatWorkingMemory = [];

function useStarter(el) {
  document.getElementById('chat-input').value = el.textContent;
  sendChat();
}

async function sendChat() {
  const input = document.getElementById('chat-input');
  const query = input.value.trim();
  if (!query) return;
  input.value = '';

  appendBubble('you', esc(query));
  chatHistory.push({ role: 'user', content: query });
  const thinking = appendBubbleRaw('ai', '<span class="loading"></span>');

  try {
    const res = await api('/chat', {
      method: 'POST',
      body: JSON.stringify({ query, history: chatHistory.slice(-10), working_memory: chatWorkingMemory })
    });
    chatWorkingMemory = res.working_memory || [];
    let html = esc(res.response);
    if (res.sources && res.sources.length > 0) {
      html += `<div class="sources">Sources: ${res.sources.map(s => esc(s.domain) + ' · ' + esc(s.title)).join(', ')}</div>`;
    }
    thinking.querySelector('.bubble').innerHTML = html;
    chatHistory.push({ role: 'ai', content: res.response });
  } catch (e) {
    thinking.querySelector('.bubble').innerHTML = `<span style="color:var(--red)">Error: ${esc(e.message)}</span>`;
  }
}

function appendBubble(role, html) {
  const wrap = document.getElementById('chat-messages');
  const el   = document.createElement('div');
  el.className = 'msg';
  if (role === 'you') {
    el.style.alignSelf = 'flex-end';
    el.innerHTML = `<div class="bubble you">${html}</div>`;
  } else {
    el.innerHTML = `<div class="msg-from">Delhi CM Advisor</div><div class="bubble ai">${html}</div>`;
  }
  wrap.appendChild(el);
  wrap.scrollTop = wrap.scrollHeight;
  return el;
}
function appendBubbleRaw(role, html) { return appendBubble(role, html); }

function clearChat() {
  chatHistory = []; chatWorkingMemory = [];
  document.getElementById('chat-messages').innerHTML = `
    <div class="msg">
      <div class="msg-from">Delhi CM Advisor</div>
      <div class="bubble ai">I can answer questions about complaints across all 14 Delhi districts — district breakdowns, department performance, surge alerts, stale issues, and more. What would you like to know?</div>
    </div>`;
}

// ── ADVISOR ───────────────────────────────────────────────────────
let advisorHistory = [];

async function runAdvisor() {
  const query  = document.getElementById('advisor-query').value.trim();
  const btn    = document.getElementById('advisor-btn');
  const thread = document.getElementById('advisor-thread');
  btn.disabled = true; btn.textContent = 'Analysing…';
  thread.innerHTML = '<div style="padding:32px;text-align:center"><span class="loading"></span></div>';

  try {
    const res = await api('/suggestions', {
      method: 'POST',
      body: JSON.stringify({ query: query || null, history: advisorHistory })
    });
    advisorHistory = res.thinking_trace || [];
    renderAdvisorThread(res, thread);
    advisorCache = thread.innerHTML;
  } catch (e) {
    thread.innerHTML = `<div style="color:var(--red);padding:20px">${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false; btn.textContent = 'Run Analysis';
  }
}

function renderAdvisorThread(res, container) {
  let html = '';
  (res.thinking_trace || []).forEach(t => {
    const typeLabel = t.type === 'tool_call'   ? `Round ${t.round} · Tool called`
                    : t.type === 'tool_result' ? `Round ${t.round} · Data retrieved`
                    : `Round ${t.round} · Analysis`;
    const content = `${esc((t.content || '').slice(0, 700))}${(t.content || '').length > 700 ? '\n…' : ''}`;
    if (t.type === 'tool_call' || t.type === 'tool_result') {
      html += `<details class="trace-entry trace-collapsible">
        <summary class="trace-meta type-${esc(t.type)}">${typeLabel}</summary>
        <div class="trace-text">${content}</div>
      </details>`;
    } else {
      html += `<div class="trace-entry">
        <div class="trace-meta type-${esc(t.type)}">${typeLabel}</div>
        <div class="trace-text">${content}</div>
      </div>`;
    }
  });
  if ((res.suggestions || []).length > 0) {
    if (res.thinking_trace && res.thinking_trace.length > 0) html += '<hr class="trace-divider">';
    html += `<div class="trace-recs-title">Strategic Recommendations</div>`;
    html += res.suggestions.map(s => `
      <div class="rec-card ${esc(s.priority)}">
        <div class="rec-priority">${esc(s.priority)} priority</div>
        <div class="rec-title">${esc(s.title)}</div>
        <div class="rec-body">${esc(s.body)}</div>
      </div>`).join('');
  }
  if (!html) html = '<div class="advisor-empty"><div class="advisor-empty-title">No results</div></div>';
  if (res.context_summary) {
    html += `<div style="font-size:11px;color:var(--muted);margin-top:16px;padding-top:12px;border-top:1px solid var(--line)">${esc(res.context_summary)}</div>`;
  }
  container.innerHTML = html;
}

function clearAdvisor() {
  advisorHistory = []; advisorAutoRun = false; advisorCache = null;
  document.getElementById('advisor-query').value = '';
  document.getElementById('advisor-thread').innerHTML = `
    <div class="advisor-empty">
      <div class="advisor-empty-title">No analysis yet</div>
      <div class="advisor-empty-hint">Click "Run" to generate strategic recommendations</div>
    </div>`;
}

// ── INIT ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const now = new Date();
  document.getElementById('topbar-date').textContent = now.toLocaleDateString('en-IN', {
    weekday: 'short', day: 'numeric', month: 'short', year: 'numeric'
  });

  document.querySelectorAll('.nav-tab').forEach(el => {
    el.addEventListener('click', () => goPage(el.dataset.page));
  });

  document.querySelectorAll('.ai-panel-tab').forEach(el => {
    el.addEventListener('click', () => switchAIPanelTab(el.dataset.panel));
  });

  document.getElementById('chat-input').addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
  });
  document.getElementById('advisor-query').addEventListener('keydown', e => {
    if (e.key === 'Enter') runAdvisor();
  });
  document.getElementById('submit-form').addEventListener('submit', submitGrievance);
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      closeModal(); closeClusterModal();
      const panel = document.getElementById('ai-panel');
      if (panel && panel.classList.contains('open')) toggleAIPanel();
    }
  });

  const DISTRICTS = ['Central','East','New Delhi','North','North East','North West',
                     'Shahdara','South','South East','South West','Dwarka','West','Rohini','Outer'];
  const DEPTS     = ['MCD','PWD','DJB','DUSIB','Delhi Police','Transport Department',
                     'Health Department','Education Department','Revenue Department','BSES'];
  const CATS      = ['Water Supply','Drainage & Sewage','Roads & Infrastructure',
                     'Electricity & Power','Sanitation & Garbage','Public Safety',
                     'Healthcare','Education','Public Transport','Housing & Shelter','Land & Property'];

  ['if-district', 's-district'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML += DISTRICTS.map(d => `<option>${d}</option>`).join('');
  });

  const deptSel = document.getElementById('if-department');
  if (deptSel) deptSel.innerHTML += DEPTS.map(d => `<option>${d}</option>`).join('');

  ['if-category', 's-category'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML += CATS.map(c => `<option>${c}</option>`).join('');
  });

  document.getElementById('district-select').innerHTML =
    '<option value="">— Select a district to see its breakdown —</option>' +
    DISTRICTS.map(d => `<option>${d}</option>`).join('');

  goPage('overview');
});
