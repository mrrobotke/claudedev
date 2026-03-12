"""Web dashboard routes for project monitoring and management.

Provides a simple HTML dashboard served by the webhook FastAPI app.
"""

from __future__ import annotations

from typing import TypedDict

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select

from claudedev.core.state import (
    AgentSession,
    Project,
    SessionStatus,
    TrackedIssue,
    TrackedPR,
    get_session,
)

logger = structlog.get_logger(__name__)


class DashboardStats(TypedDict):
    """Aggregated dashboard statistics."""

    projects: int
    issues: int
    prs: int
    active_sessions: int
    total_cost_usd: float


router = APIRouter(prefix="/dashboard", tags=["dashboard"])

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ClaudeDev Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/apexcharts"></script>
  <script src="https://unpkg.com/lucide@latest"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] },
          colors: {
            surface: { DEFAULT: '#0d1117', card: '#161b22', hover: '#1c2128', border: '#30363d' },
            accent: {
              blue: '#58a6ff', green: '#3fb950', yellow: '#d29922',
              orange: '#db6d28', red: '#f85149', purple: '#a371f7', pink: '#db61a2'
            }
          }
        }
      }
    }
  </script>
  <style>
    body { background: #0d1117; color: #e6edf3; }
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: #0d1117; }
    ::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: #484f58; }

    @keyframes pulse-dot {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.3; }
    }
    .pulse-dot { animation: pulse-dot 1.5s ease-in-out infinite; }

    @keyframes slideIn {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .slide-in { animation: slideIn 0.25s ease-out; }

    @keyframes spin-slow {
      from { stroke-dashoffset: 100; }
      to { stroke-dashoffset: 0; }
    }

    .tab-active { border-bottom: 2px solid #58a6ff; color: #e6edf3 !important; }
    .tab-inactive { border-bottom: 2px solid transparent; color: #8b949e; }
    .tab-inactive:hover { color: #c9d1d9; border-bottom-color: #484f58; }

    .stat-card { border-top: 2px solid var(--accent-color, #30363d); }

    .apexcharts-tooltip { background: #161b22 !important; border: 1px solid #30363d !important; color: #e6edf3 !important; }
    .apexcharts-tooltip-title { background: #0d1117 !important; border-bottom: 1px solid #30363d !important; }
    .apexcharts-xaxistooltip { background: #161b22 !important; border: 1px solid #30363d !important; color: #e6edf3 !important; }
    .apexcharts-menu { background: #161b22 !important; border: 1px solid #30363d !important; }
    .apexcharts-menu-item:hover { background: #1c2128 !important; }

    .table-row:hover { background: #1c2128; }
    .findings-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }

    .countdown-ring { transform: rotate(-90deg); transform-origin: 50% 50%; }
  </style>
</head>
<body class="font-sans min-h-screen">

<!-- STATUS BAR -->
<header id="status-bar" class="sticky top-0 z-50 border-b border-surface-border bg-surface-card/80 backdrop-blur-md">
  <div class="max-w-screen-2xl mx-auto px-4 h-12 flex items-center justify-between gap-4">
    <!-- Left: Logo -->
    <div class="flex items-center gap-2 shrink-0">
      <span class="text-accent-blue font-bold text-base tracking-tight">&#9889; ClaudeDev</span>
      <span class="text-surface-border text-sm">/</span>
      <span class="text-secondary text-sm text-[#8b949e]">Dashboard</span>
    </div>
    <!-- Center: Status chips -->
    <div id="status-chips" class="flex items-center gap-3 text-xs overflow-x-auto">
      <span class="text-[#8b949e]">Loading...</span>
    </div>
    <!-- Right: Feature flags + countdown -->
    <div class="flex items-center gap-3 shrink-0">
      <div id="feature-flags" class="hidden md:flex items-center gap-2"></div>
      <div id="refresh-ring" class="relative w-7 h-7 cursor-pointer" title="Refresh now" onclick="manualRefresh()">
        <svg class="w-7 h-7" viewBox="0 0 28 28">
          <circle cx="14" cy="14" r="11" fill="none" stroke="#30363d" stroke-width="2"/>
          <circle id="countdown-circle" cx="14" cy="14" r="11" fill="none" stroke="#58a6ff" stroke-width="2"
            stroke-dasharray="69.12" stroke-dashoffset="0" class="countdown-ring" style="transition: stroke-dashoffset 1s linear;"/>
        </svg>
        <span id="countdown-text" class="absolute inset-0 flex items-center justify-center text-[9px] font-semibold text-accent-blue">10</span>
      </div>
    </div>
  </div>
</header>

<!-- TAB NAV -->
<nav class="sticky top-12 z-40 bg-surface/95 backdrop-blur-sm border-b border-surface-border">
  <div class="max-w-screen-2xl mx-auto px-4 flex items-center gap-0 overflow-x-auto">
    <button class="tab-btn px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap tab-active" data-tab="overview">Overview</button>
    <button class="tab-btn px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap tab-inactive" data-tab="issues">
      Issues <span id="badge-issues" class="ml-1 px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-accent-blue/20 text-accent-blue hidden"></span>
    </button>
    <button class="tab-btn px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap tab-inactive" data-tab="prs">
      Pull Requests <span id="badge-prs" class="ml-1 px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-accent-green/20 text-accent-green hidden"></span>
    </button>
    <button class="tab-btn px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap tab-inactive" data-tab="sessions">
      Sessions <span id="badge-sessions" class="ml-1 px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-accent-yellow/20 text-accent-yellow hidden"></span>
    </button>
    <button class="tab-btn px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap tab-inactive" data-tab="projects">Projects</button>
    <button class="tab-btn px-4 py-3 text-sm font-medium transition-colors whitespace-nowrap tab-inactive" data-tab="budget">Budget</button>
  </div>
</nav>

<!-- ERROR BANNER -->
<div id="error-banner" class="hidden max-w-screen-2xl mx-auto px-4 pt-3">
  <div class="flex items-center gap-2 px-4 py-2 rounded-lg bg-accent-red/10 border border-accent-red/30 text-accent-red text-sm">
    <i data-lucide="alert-triangle" class="w-4 h-4 shrink-0"></i>
    <span id="error-text">Failed to fetch dashboard data.</span>
    <button onclick="manualRefresh()" class="ml-auto text-xs underline">Retry</button>
  </div>
</div>

<div id="toast-container" class="fixed bottom-6 right-6 z-50 flex flex-col gap-2"></div>

<!-- MAIN CONTENT -->
<main class="max-w-screen-2xl mx-auto px-4 py-6">

  <!-- OVERVIEW TAB -->
  <section id="tab-overview" class="tab-panel">

    <!-- Hero stat cards -->
    <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
      <div class="stat-card bg-surface-card border border-surface-border rounded-xl p-4" style="--accent-color:#58a6ff">
        <i data-lucide="folder" class="w-5 h-5 text-accent-blue mb-2"></i>
        <div id="sc-projects" class="text-3xl font-bold text-[#e6edf3]">-</div>
        <div class="text-xs text-[#8b949e] mt-1">Projects</div>
      </div>
      <div class="stat-card bg-surface-card border border-surface-border rounded-xl p-4" style="--accent-color:#f85149">
        <i data-lucide="alert-circle" class="w-5 h-5 text-accent-red mb-2"></i>
        <div id="sc-issues" class="text-3xl font-bold text-[#e6edf3]">-</div>
        <div class="text-xs text-[#8b949e] mt-1">Active Issues</div>
      </div>
      <div class="stat-card bg-surface-card border border-surface-border rounded-xl p-4" style="--accent-color:#3fb950">
        <i data-lucide="git-pull-request" class="w-5 h-5 text-accent-green mb-2"></i>
        <div id="sc-prs" class="text-3xl font-bold text-[#e6edf3]">-</div>
        <div class="text-xs text-[#8b949e] mt-1">Open PRs</div>
      </div>
      <div class="stat-card bg-surface-card border border-surface-border rounded-xl p-4" style="--accent-color:#a371f7">
        <i data-lucide="cpu" class="w-5 h-5 text-accent-purple mb-2"></i>
        <div id="sc-sessions" class="text-3xl font-bold text-[#e6edf3]">-</div>
        <div class="text-xs text-[#8b949e] mt-1">Active Sessions</div>
      </div>
      <div class="stat-card bg-surface-card border border-surface-border rounded-xl p-4" style="--accent-color:#d29922">
        <i data-lucide="dollar-sign" class="w-5 h-5 text-accent-yellow mb-2"></i>
        <div id="sc-cost-total" class="text-3xl font-bold text-[#e6edf3]">-</div>
        <div class="text-xs text-[#8b949e] mt-1">Total Cost</div>
      </div>
      <div class="stat-card bg-surface-card border border-surface-border rounded-xl p-4" style="--accent-color:#db6d28">
        <i data-lucide="trending-up" class="w-5 h-5 text-accent-orange mb-2"></i>
        <div id="sc-cost-today" class="text-3xl font-bold text-[#e6edf3]">-</div>
        <div class="text-xs text-[#8b949e] mt-1">Today's Cost</div>
      </div>
    </div>

    <!-- Budget + Pipeline row -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
      <!-- Budget gauges -->
      <div class="bg-surface-card border border-surface-border rounded-xl p-4">
        <h3 class="text-sm font-semibold text-[#8b949e] uppercase tracking-wide mb-4">Daily Budget</h3>
        <div class="flex flex-col md:flex-row items-center gap-6">
          <div id="chart-budget-gauge" class="w-full md:w-48 shrink-0"></div>
          <div id="budget-project-bars" class="flex-1 w-full space-y-2"></div>
        </div>
      </div>
      <!-- Pipeline chart -->
      <div class="bg-surface-card border border-surface-border rounded-xl p-4">
        <h3 class="text-sm font-semibold text-[#8b949e] uppercase tracking-wide mb-4">Issue Pipeline</h3>
        <div id="chart-pipeline"></div>
      </div>
    </div>

    <!-- Activity feed -->
    <div class="bg-surface-card border border-surface-border rounded-xl p-4">
      <h3 class="text-sm font-semibold text-[#8b949e] uppercase tracking-wide mb-4">Recent Activity</h3>
      <div id="activity-feed" class="space-y-2 max-h-72 overflow-y-auto pr-1"></div>
    </div>
  </section>

  <!-- ISSUES TAB -->
  <section id="tab-issues" class="tab-panel hidden">
    <div class="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
      <div class="p-4 border-b border-surface-border flex items-center justify-between">
        <h3 class="text-sm font-semibold text-[#8b949e] uppercase tracking-wide">Tracked Issues</h3>
        <div class="flex items-center gap-3">
          <div id="issues-filter-toggle" class="flex items-center gap-2">
            <button data-issues-filter="open" class="px-2.5 py-1 rounded-md text-xs font-medium cursor-pointer transition-all border"></button>
            <button data-issues-filter="all" class="px-2.5 py-1 rounded-md text-xs font-medium cursor-pointer transition-all border"></button>
          </div>
          <span id="issues-count" class="text-xs text-[#8b949e]"></span>
        </div>
      </div>
      <div id="issues-table-wrap" class="overflow-x-auto"></div>
    </div>
  </section>

  <!-- PRS TAB -->
  <section id="tab-prs" class="tab-panel hidden">
    <div class="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
      <div class="p-4 border-b border-surface-border flex items-center justify-between">
        <h3 class="text-sm font-semibold text-[#8b949e] uppercase tracking-wide">Pull Requests</h3>
        <span id="prs-count" class="text-xs text-[#8b949e]"></span>
      </div>
      <div id="prs-table-wrap" class="overflow-x-auto"></div>
    </div>
  </section>

  <!-- SESSIONS TAB -->
  <section id="tab-sessions" class="tab-panel hidden">
    <div class="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
      <div class="p-4 border-b border-surface-border flex items-center justify-between">
        <h3 class="text-sm font-semibold text-[#8b949e] uppercase tracking-wide">Agent Sessions</h3>
        <span id="sessions-count" class="text-xs text-[#8b949e]"></span>
      </div>
      <div id="sessions-table-wrap" class="overflow-x-auto"></div>
    </div>
  </section>

  <!-- PROJECTS TAB -->
  <section id="tab-projects" class="tab-panel hidden">
    <div id="projects-grid" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4"></div>
  </section>

  <!-- BUDGET TAB -->
  <section id="tab-budget" class="tab-panel hidden">
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div class="bg-surface-card border border-surface-border rounded-xl p-4">
        <h3 class="text-sm font-semibold text-[#8b949e] uppercase tracking-wide mb-4">Daily Budget Utilization</h3>
        <div id="chart-budget-gauge-full"></div>
      </div>
      <div class="space-y-3">
        <div class="grid grid-cols-3 gap-3">
          <div class="bg-surface-card border border-surface-border rounded-xl p-3">
            <div class="text-xs text-[#8b949e] mb-1">Per Issue</div>
            <div id="budget-per-issue" class="text-lg font-bold text-[#e6edf3]">-</div>
          </div>
          <div class="bg-surface-card border border-surface-border rounded-xl p-3">
            <div class="text-xs text-[#8b949e] mb-1">Per Project / Day</div>
            <div id="budget-per-project" class="text-lg font-bold text-[#e6edf3]">-</div>
          </div>
          <div class="bg-surface-card border border-surface-border rounded-xl p-3">
            <div class="text-xs text-[#8b949e] mb-1">Total Daily</div>
            <div id="budget-total-daily" class="text-lg font-bold text-[#e6edf3]">-</div>
          </div>
        </div>
        <div class="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
          <div class="p-3 border-b border-surface-border text-xs font-semibold text-[#8b949e] uppercase">Per-Project Breakdown</div>
          <div id="budget-project-table-wrap" class="overflow-x-auto"></div>
        </div>
      </div>
    </div>
  </section>

</main>

<script>
(function() {
  'use strict';

  const state = {
    data: null,
    activeTab: 'overview',
    refreshInterval: 10,
    refreshCountdown: 10,
    countdownTimer: null,
    durationTimer: null,
    charts: {}
  };

  // ---- Helpers ----

  function timeAgo(iso) {
    if (!iso) return '-';
    // Normalise the ISO string so all JS engines parse timezone-aware stamps
    // correctly (replace space-separated offset with 'Z' only when there is no
    // explicit offset; otherwise leave the offset intact - Date.parse handles it).
    const ts = new Date(iso).getTime();
    if (isNaN(ts)) return '-';
    const diff = Math.floor((Date.now() - ts) / 1000);
    // Future timestamps (clock skew, timezone mismatch) show as "just now"
    if (diff < 0) return 'just now';
    if (diff < 60) return diff + 's ago';
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400) {
      const h = Math.floor(diff / 3600);
      const m = Math.floor((diff % 3600) / 60);
      return m > 0 ? h + 'h ' + m + 'm ago' : h + 'h ago';
    }
    return Math.floor(diff / 86400) + 'd ago';
  }

  function formatDuration(seconds) {
    if (seconds === null || seconds === undefined) return '-';
    const s = Math.floor(seconds);
    if (s < 60) return s + 's';
    if (s < 3600) return Math.floor(s / 60) + 'm ' + (s % 60) + 's';
    return Math.floor(s / 3600) + 'h ' + Math.floor((s % 3600) / 60) + 'm';
  }

  function liveDuration(startedAt) {
    const diff = Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000);
    return formatDuration(diff);
  }

  function formatCost(usd) {
    if (usd === null || usd === undefined) return '$0.00';
    return '$' + Number(usd).toFixed(2);
  }

  function esc(str) {
    return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function statusColor(status) {
    const map = {
      new: '#58a6ff', enhancing: '#d29922', enhanced: '#db6d28',
      triaged: '#a371f7', implementing: '#a371f7', in_review: '#db61a2',
      fixing: '#f85149', done: '#3fb950',
      running: '#3fb950', completed: '#3fb950', failed: '#f85149', pending: '#d29922'
    };
    return map[status] || '#8b949e';
  }

  function statusBadge(status) {
    const c = statusColor(status);
    return '<span style="background:' + c + '22;color:' + c + '" class="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-semibold">'
      + (status === 'running' ? '<span class="pulse-dot w-1.5 h-1.5 rounded-full inline-block" style="background:' + c + '"></span>' : '')
      + esc(status) + '</span>';
  }

  function tierBadge(tier) {
    if (!tier) return '<span class="text-[#8b949e] text-xs">-</span>';
    return '<span class="inline-flex items-center justify-center w-5 h-5 rounded-full bg-accent-purple/20 text-accent-purple text-xs font-bold">' + esc(tier) + '</span>';
  }

  function linkedNum(num, url, prefix) {
    if (!num) return '<span class="text-[#8b949e]">-</span>';
    const label = (prefix || '#') + num;
    if (url) return '<a href="' + esc(url) + '" target="_blank" class="text-accent-blue hover:underline font-mono text-sm">' + esc(label) + '</a>';
    return '<span class="font-mono text-sm">' + esc(label) + '</span>';
  }

  function domainBadge(domain) {
    const map = { backend: '#58a6ff', frontend: '#3fb950', mobile: '#a371f7', shared: '#8b949e' };
    const c = map[domain] || '#8b949e';
    return '<span style="background:' + c + '22;color:' + c + '" class="px-2 py-0.5 rounded text-xs font-mono">' + esc(domain || 'repo') + '</span>';
  }

  function costColor(usd, limit) {
    const pct = limit ? (usd / limit) * 100 : 0;
    if (pct >= 90) return '#f85149';
    if (pct >= 70) return '#d29922';
    return '#3fb950';
  }

  function emptyState(iconName, title, subtitle) {
    return '<div class="flex flex-col items-center justify-center py-16 text-center">'
      + '<i data-lucide="' + iconName + '" class="w-10 h-10 text-[#30363d] mb-3"></i>'
      + '<p class="text-sm font-semibold text-[#8b949e]">' + esc(title) + '</p>'
      + '<p class="text-xs text-[#484f58] mt-1">' + esc(subtitle) + '</p>'
      + '</div>';
  }

  function tableHTML(headers, rows, emptyIcon, emptyTitle, emptySub) {
    if (!rows || rows.length === 0) {
      return emptyState(emptyIcon, emptyTitle, emptySub);
    }
    let html = '<table class="w-full text-sm"><thead><tr class="border-b border-surface-border">';
    headers.forEach(function(h) { html += '<th class="px-4 py-2.5 text-left text-xs font-semibold text-[#8b949e] uppercase tracking-wide whitespace-nowrap">' + esc(h) + '</th>'; });
    html += '</tr></thead><tbody>';
    rows.forEach(function(row) {
      html += '<tr class="table-row border-b border-surface-border/50 transition-colors">';
      row.forEach(function(cell) {
        html += '<td class="px-4 py-2.5 whitespace-nowrap">' + (cell === null || cell === undefined ? '<span class="text-[#8b949e]">-</span>' : cell) + '</td>';
      });
      html += '</tr>';
    });
    html += '</tbody></table>';
    return html;
  }

  // ---- Data fetch ----

  async function fetchData() {
    try {
      const resp = await fetch('/api/dashboard/enriched');
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      state.data = await resp.json();
      hideBanner();
    } catch (e) {
      showBanner('Failed to load dashboard data: ' + e.message);
    }
  }

  function showBanner(msg) {
    const b = document.getElementById('error-banner');
    document.getElementById('error-text').textContent = msg;
    b.classList.remove('hidden');
  }

  function hideBanner() {
    document.getElementById('error-banner').classList.add('hidden');
  }

  // ---- Render ----

  function render() {
    if (!state.data) return;
    renderStatusBar();
    renderBadges();
    if (state.activeTab === 'overview') renderOverview();
    else if (state.activeTab === 'issues') renderIssues();
    else if (state.activeTab === 'prs') renderPRs();
    else if (state.activeTab === 'sessions') renderSessions();
    else if (state.activeTab === 'projects') renderProjects();
    else if (state.activeTab === 'budget') renderBudget();
    initIcons();
  }

  function initIcons() {
    if (window.lucide) lucide.createIcons();
  }

  // ---- Status Bar ----

  function renderStatusBar() {
    const d = state.data;
    const sys = d.system || {};
    const chipsEl = document.getElementById('status-chips');

    const daemonOk = sys.tunnel_status === 'running';
    const daemonColor = daemonOk ? '#3fb950' : '#f85149';
    const daemonLabel = daemonOk ? 'Running' : 'Stopped';

    const tunnelUrl = sys.tunnel_url || '';
    let tunnelDisplay = tunnelUrl;
    if (tunnelUrl) {
      const parts = tunnelUrl.replace(/https?:\\/\\//, '').split('/');
      tunnelDisplay = parts.slice(0, 2).join('/');
    }

    const maxS = sys.max_concurrent_sessions || 1;
    const activeS = sys.active_sessions || 0;
    const sessionPct = Math.round((activeS / maxS) * 100);

    let chips = '<div class="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-surface-hover border border-surface-border text-xs">'
      + '<span class="pulse-dot w-1.5 h-1.5 rounded-full" style="background:' + daemonColor + ';animation:' + (daemonOk ? 'pulse-dot 1.5s ease-in-out infinite' : 'none') + '"></span>'
      + '<span style="color:' + daemonColor + '">' + daemonLabel + '</span>'
      + '</div>';

    if (tunnelUrl) {
      chips += '<a href="' + esc(tunnelUrl) + '" target="_blank" class="flex items-center gap-1 px-2.5 py-1 rounded-full bg-surface-hover border border-surface-border text-xs text-accent-blue hover:bg-surface-hover">'
        + '<i data-lucide="link" class="w-3 h-3"></i><span class="max-w-[140px] truncate">' + esc(tunnelDisplay) + '</span></a>';
    }

    chips += '<div class="flex items-center gap-2 px-2.5 py-1 rounded-full bg-surface-hover border border-surface-border text-xs">'
      + '<i data-lucide="zap" class="w-3 h-3 text-accent-yellow"></i>'
      + '<span class="text-[#e6edf3]">' + activeS + '/' + maxS + ' sessions</span>'
      + '<div class="w-12 h-1 rounded-full bg-surface-border overflow-hidden"><div class="h-full rounded-full" style="width:' + sessionPct + '%;background:#58a6ff"></div></div>'
      + '</div>';

    chipsEl.innerHTML = chips;

    const flags = sys.feature_flags || {};
    const flagsEl = document.getElementById('feature-flags');
    const flagDefs = [
      { key: 'auto_enhance_issues', label: 'Auto-Enhance' },
      { key: 'auto_implement', label: 'Auto-Implement' },
      { key: 'review_on_pr', label: 'Review' }
    ];
    let flagsHtml = '';
    flagDefs.forEach(function(f) {
      const on = flags[f.key];
      const c = on ? '#3fb950' : '#f85149';
      const icon = on ? '&#10003;' : '&#10005;';
      flagsHtml += '<span style="background:' + c + '22;color:' + c + ';border:1px solid ' + c + '44" class="px-2 py-0.5 rounded text-xs font-medium">'
        + icon + ' ' + esc(f.label) + '</span>';
    });
    flagsEl.innerHTML = flagsHtml;
    flagsEl.classList.remove('hidden');
    flagsEl.classList.add('flex');
  }

  // ---- Tab badges ----

  function renderBadges() {
    const d = state.data;
    if (!d) return;
    const stats = d.stats || {};
    const ai = stats.active_issues || 0;
    const op = stats.open_prs || 0;
    const as2 = stats.completed_sessions || 0;

    function setBadge(id, val) {
      const el = document.getElementById(id);
      if (!el) return;
      if (val > 0) { el.textContent = val; el.classList.remove('hidden'); }
      else el.classList.add('hidden');
    }
    setBadge('badge-issues', ai);
    setBadge('badge-prs', op);
    setBadge('badge-sessions', as2);

    document.getElementById('issues-count').textContent = (d.issues || []).length + ' issues';
    document.getElementById('prs-count').textContent = (d.prs || []).length + ' pull requests';
    document.getElementById('sessions-count').textContent = (d.sessions || []).length + ' sessions';
  }

  // ---- Overview ----

  function renderOverview() {
    const d = state.data;
    const stats = d.stats || {};
    const budget = d.budget || {};

    document.getElementById('sc-projects').textContent = stats.projects || 0;
    document.getElementById('sc-issues').textContent = stats.active_issues || 0;
    document.getElementById('sc-prs').textContent = stats.open_prs || 0;
    document.getElementById('sc-sessions').textContent = (d.system || {}).active_sessions || 0;
    document.getElementById('sc-cost-total').textContent = formatCost(stats.total_cost_usd);
    document.getElementById('sc-cost-today').textContent = formatCost(stats.today_cost_usd);

    renderBudgetGauge('chart-budget-gauge', budget.today_spend_pct || 0, true);
    renderProjectBars(budget.per_project_daily || []);
    renderPipelineChart(d.pipeline || {});
    renderActivityFeed(d.activity || []);
  }

  function renderBudgetGauge(containerId, pct, small) {
    if (state.charts[containerId]) {
      try { state.charts[containerId].destroy(); } catch(e) {}
    }
    const color = pct >= 90 ? '#f85149' : pct >= 70 ? '#d29922' : '#3fb950';
    const opts = {
      chart: { type: 'radialBar', height: small ? 160 : 260, background: 'transparent', sparkline: { enabled: small } },
      series: [Math.min(100, Math.round(pct))],
      plotOptions: {
        radialBar: {
          hollow: { size: small ? '55%' : '60%' },
          dataLabels: {
            name: { show: !small, color: '#8b949e', fontSize: '11px', offsetY: -4 },
            value: { color: '#e6edf3', fontSize: small ? '18px' : '28px', fontWeight: '700', offsetY: small ? 6 : 8, formatter: function(v) { return v + '%'; } }
          },
          track: { background: '#30363d', strokeWidth: '100%' }
        }
      },
      fill: { colors: [color] },
      labels: ['Daily Budget'],
      theme: { mode: 'dark' }
    };
    const el = document.getElementById(containerId);
    if (!el) return;
    const chart = new ApexCharts(el, opts);
    chart.render();
    state.charts[containerId] = chart;
  }

  function renderProjectBars(projects) {
    const el = document.getElementById('budget-project-bars');
    if (!el) return;
    if (!projects.length) { el.innerHTML = '<p class="text-xs text-[#8b949e]">No project budgets configured.</p>'; return; }
    let html = '';
    projects.forEach(function(p) {
      const pct = Math.min(100, Math.round(p.pct || 0));
      const c = pct >= 90 ? '#f85149' : pct >= 70 ? '#d29922' : '#3fb950';
      html += '<div class="space-y-0.5">'
        + '<div class="flex justify-between text-xs"><span class="text-[#c9d1d9] font-medium truncate max-w-[120px]">' + esc(p.project_name) + '</span>'
        + '<span class="text-[#8b949e] ml-2 shrink-0">' + formatCost(p.spend) + ' / ' + formatCost(p.limit) + '</span></div>'
        + '<div class="w-full h-1.5 rounded-full bg-surface-border overflow-hidden"><div class="h-full rounded-full transition-all" style="width:' + pct + '%;background:' + c + '"></div></div>'
        + '</div>';
    });
    el.innerHTML = html;
  }

  function renderPipelineChart(pipeline) {
    if (state.charts['chart-pipeline']) {
      try { state.charts['chart-pipeline'].destroy(); } catch(e) {}
    }
    const stages = ['new','enhancing','enhanced','triaged','implementing','in_review','fixing','done'];
    const colors = ['#58a6ff','#d29922','#db6d28','#a371f7','#a371f7','#db61a2','#f85149','#3fb950'];
    const values = stages.map(function(s) { return pipeline[s] || 0; });

    const el = document.getElementById('chart-pipeline');
    if (!el) return;

    const opts = {
      chart: { type: 'bar', height: 160, background: 'transparent', toolbar: { show: false }, sparkline: { enabled: false } },
      series: [{ name: 'Issues', data: values }],
      xaxis: { categories: stages, labels: { style: { colors: '#8b949e', fontSize: '10px' } } },
      yaxis: { labels: { style: { colors: '#8b949e' }, formatter: function(v) { return Math.round(v); } }, min: 0 },
      fill: { colors: colors },
      plotOptions: { bar: { distributed: true, borderRadius: 3, columnWidth: '60%', dataLabels: { position: 'top' } } },
      dataLabels: { enabled: true, style: { colors: ['#e6edf3'], fontSize: '10px' }, offsetY: -14 },
      legend: { show: false },
      grid: { borderColor: '#21262d', strokeDashArray: 3 },
      tooltip: { theme: 'dark' },
      theme: { mode: 'dark' }
    };
    const chart = new ApexCharts(el, opts);
    chart.render();
    state.charts['chart-pipeline'] = chart;
  }

  function renderActivityFeed(activity) {
    const el = document.getElementById('activity-feed');
    if (!el) return;
    if (!activity.length) {
      el.innerHTML = emptyState('activity', 'No recent activity', 'Activity events will appear here as the system processes work.');
      return;
    }
    const typeColors = {
      issue_created: '#58a6ff', issue_enhanced: '#db6d28', implementation_started: '#a371f7',
      pr_opened: '#3fb950', session_started: '#d29922', session_completed: '#3fb950', session_failed: '#f85149'
    };
    let html = '';
    activity.slice(0, 30).forEach(function(item) {
      const c = typeColors[item.type] || '#8b949e';
      html += '<div class="flex items-start gap-3 slide-in">'
        + '<div class="mt-1.5 w-2 h-2 rounded-full shrink-0" style="background:' + c + '"></div>'
        + '<div class="flex-1 min-w-0">'
        + '<span class="text-sm text-[#e6edf3]">' + esc(item.message) + '</span>'
        + (item.repo ? '<span class="ml-2 text-xs text-[#8b949e] font-mono">' + esc(item.repo) + '</span>' : '')
        + '</div>'
        + '<span class="text-xs text-[#484f58] shrink-0 mt-0.5" title="' + esc(item.timestamp) + '">' + timeAgo(item.timestamp) + '</span>'
        + '</div>';
    });
    el.innerHTML = html;
  }

  // ---- Issues ----

  function renderIssues() {
    var issues = (state.data && state.data.issues) || [];
    var rows = issues.map(function(i) {
      var actions = '';
      if (i.status === 'enhancing' || i.status === 'implementing') {
        actions = '<span class="inline-flex items-center gap-1.5 text-xs text-[#d29922]"><svg class="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>' + esc(i.status === 'enhancing' ? 'Enhancing\u2026' : 'Implementing\u2026') + '</span>';
      } else if (i.status === 'done') {
        actions = '<span class="inline-flex items-center gap-1 text-xs text-[#3fb950]"><i data-lucide="check-circle" class="w-3.5 h-3.5"></i>Done</span>';
      } else {
        var btns = '';
        if (i.status === 'new') {
          btns += '<button data-issue-id="' + i.id + '" data-action="enhance" class="action-btn px-2.5 py-1 rounded-md text-xs font-medium bg-[#58a6ff]/15 text-[#58a6ff] hover:bg-[#58a6ff]/25 border border-[#58a6ff]/20 transition-all duration-150 cursor-pointer whitespace-nowrap">&#9889; Enhance</button>';
        }
        if (i.status === 'new' || i.status === 'enhanced' || i.status === 'triaged') {
          btns += '<button data-issue-id="' + i.id + '" data-action="implement" class="action-btn px-2.5 py-1 rounded-md text-xs font-medium bg-[#a371f7]/15 text-[#a371f7] hover:bg-[#a371f7]/25 border border-[#a371f7]/20 transition-all duration-150 cursor-pointer whitespace-nowrap">&#128640; Implement</button>';
        }
        actions = '<div class="flex items-center gap-1.5">' + btns + '</div>';
      }
      return [
        linkedNum(i.issue_number, i.github_url, '#'),
        '<span class="font-mono text-xs text-[#c9d1d9]">' + esc(i.repo_full_name) + '</span>',
        '<span class="text-xs text-[#8b949e]">' + esc(i.project_name || '-') + '</span>',
        statusBadge(i.status),
        tierBadge(i.tier),
        linkedNum(i.pr_number, i.pr_url, '#'),
        '<span title="' + esc(i.created_at) + '" class="text-xs text-[#8b949e]">' + timeAgo(i.created_at) + '</span>',
        actions
      ];
    });
    document.getElementById('issues-count').textContent = issues.length + ' issues';
    document.getElementById('issues-table-wrap').innerHTML = tableHTML(
      ['Issue', 'Repository', 'Project', 'Status', 'Tier', 'PR', 'Created', 'Actions'],
      rows, 'alert-circle', 'No issues tracked yet', 'Issues appear here when they arrive via GitHub webhooks'
    );
    initIcons();
    updateIssuesFilterUI();
  }

  function updateIssuesFilterUI() {
    var current = (state.data && state.data.system && state.data.system.feature_flags && state.data.system.feature_flags.issues_display_filter) || 'open';
    var toggles = document.querySelectorAll('[data-issues-filter]');
    toggles.forEach(function(btn) {
      var val = btn.dataset.issuesFilter;
      btn.textContent = val === 'open' ? 'Open Only' : 'All Issues';
      if (val === current) {
        btn.className = 'px-2.5 py-1 rounded-md text-xs font-medium cursor-pointer transition-all border bg-[#58a6ff]/20 text-[#58a6ff] border-[#58a6ff]/30';
      } else {
        btn.className = 'px-2.5 py-1 rounded-md text-xs font-medium cursor-pointer transition-all border bg-transparent text-[#8b949e] border-[#30363d] hover:border-[#58a6ff]/30 hover:text-[#58a6ff]';
      }
    });
  }

  // ---- PRs ----

  function renderPRs() {
    const prs = (state.data && state.data.prs) || [];
    const rows = prs.map(function(p) {
      const f = p.findings_summary || {};
      const findings = '<span class="flex items-center gap-1.5">'
        + '<span class="findings-dot" style="background:#f85149"></span><span class="text-xs text-[#f85149]">' + (f.critical || 0) + '</span>'
        + '<span class="findings-dot" style="background:#db6d28"></span><span class="text-xs text-[#db6d28]">' + (f.high || 0) + '</span>'
        + '<span class="findings-dot" style="background:#d29922"></span><span class="text-xs text-[#d29922]">' + (f.medium || 0) + '</span>'
        + '</span>';
      const iter = p.review_iteration
        ? '<span class="inline-flex items-center justify-center w-6 h-6 rounded-full bg-accent-purple/20 text-accent-purple text-xs font-bold">' + p.review_iteration + '</span>'
        : '<span class="text-[#8b949e]">-</span>';
      return [
        linkedNum(p.pr_number, p.github_url, '#'),
        '<span class="font-mono text-xs text-[#c9d1d9]">' + esc(p.repo_full_name) + '</span>',
        statusBadge(p.status),
        iter,
        findings,
        linkedNum(p.linked_issue_number, null, '#'),
        '<span title="' + esc(p.created_at) + '" class="text-xs text-[#8b949e]">' + timeAgo(p.created_at) + '</span>'
      ];
    });
    document.getElementById('prs-table-wrap').innerHTML = tableHTML(
      ['PR', 'Repository', 'Status', 'Reviews', 'Findings', 'Issue', 'Created'],
      rows, 'git-pull-request', 'No pull requests yet', 'Pull requests will appear here when opened by the system'
    );
    initIcons();
  }

  // ---- Sessions ----

  function renderSessions() {
    if (state.durationTimer) { clearInterval(state.durationTimer); state.durationTimer = null; }
    const sessions = (state.data && state.data.sessions) || [];
    const budgetLimit = state.data && state.data.budget && state.data.budget.max_per_issue;
    const rows = sessions.map(function(s) {
      const durId = 'dur-' + s.id;
      const dur = s.status === 'running'
        ? '<span id="' + durId + '" class="text-xs text-accent-yellow">' + liveDuration(s.started_at) + '</span>'
        : '<span class="text-xs text-[#8b949e]">' + formatDuration(s.duration_seconds) + '</span>';
      const c = costColor(s.cost_usd, budgetLimit);
      return [
        '<span class="px-2 py-0.5 rounded text-xs font-mono" style="background:#58a6ff22;color:#58a6ff">' + esc(s.session_type) + '</span>',
        statusBadge(s.status),
        linkedNum(s.issue_number, null, '#'),
        '<span class="font-mono text-xs text-[#c9d1d9]">' + esc(s.repo_full_name || '-') + '</span>',
        '<span class="text-xs font-semibold" style="color:' + c + '">' + formatCost(s.cost_usd) + '</span>',
        dur,
        '<span title="' + esc(s.started_at) + '" class="text-xs text-[#8b949e]">' + timeAgo(s.started_at) + '</span>',
        s.summary ? '<span class="text-xs text-[#8b949e] max-w-[180px] truncate block" title="' + esc(s.summary) + '">' + esc(s.summary.substring(0, 60)) + (s.summary.length > 60 ? '...' : '') + '</span>' : '<span class="text-[#484f58]">-</span>'
      ];
    });
    document.getElementById('sessions-table-wrap').innerHTML = tableHTML(
      ['Type', 'Status', 'Issue', 'Repository', 'Cost', 'Duration', 'Started', 'Summary'],
      rows, 'cpu', 'No agent sessions yet', 'Sessions appear here when the system starts processing issues'
    );
    initIcons();

    // Make session rows clickable to open history modal
    document.querySelectorAll('#sessions-table-wrap tbody tr').forEach(function(row, idx) {
      if (sessions[idx]) {
        row.style.cursor = 'pointer';
        row.title = 'Click to view session history';
        (function(sid) {
          row.addEventListener('click', function() { window.openSessionDetail(sid); });
        })(sessions[idx].id);
      }
    });

    // Live duration update for running sessions
    const running = sessions.filter(function(s) { return s.status === 'running'; });
    if (running.length) {
      state.durationTimer = setInterval(function() {
        running.forEach(function(s) {
          const el = document.getElementById('dur-' + s.id);
          if (el) el.textContent = liveDuration(s.started_at);
        });
      }, 1000);
    }
  }

  // ---- Projects ----

  function renderProjects() {
    const projects = (state.data && state.data.projects) || [];
    const el = document.getElementById('projects-grid');
    if (!projects.length) {
      el.innerHTML = emptyState('folder', 'No projects yet', 'Projects appear here after you register GitHub repositories');
      initIcons();
      return;
    }
    let html = '';
    projects.forEach(function(p) {
      const typeBg = p.type === 'monorepo' ? '#db6d2822' : '#58a6ff22';
      const typeC = p.type === 'monorepo' ? '#db6d28' : '#58a6ff';
      html += '<div class="bg-surface-card border border-surface-border rounded-xl p-4 space-y-3">'
        + '<div class="flex items-start justify-between gap-2">'
        + '<div><h4 class="font-semibold text-[#e6edf3] text-sm">' + esc(p.name) + '</h4>'
        + '<span style="background:' + typeBg + ';color:' + typeC + '" class="text-xs px-1.5 py-0.5 rounded mt-1 inline-block">' + esc(p.type || 'unknown') + '</span></div>'
        + '<span class="text-xs text-[#8b949e] shrink-0">' + timeAgo(p.created_at) + '</span>'
        + '</div>';

      if (p.repos && p.repos.length) {
        html += '<div class="space-y-2">';
        p.repos.forEach(function(r) {
          const stackTags = (r.tech_stack || []).map(function(t) {
            return '<span class="px-1.5 py-0.5 rounded text-[10px] bg-surface-hover border border-surface-border text-[#8b949e]">' + esc(t) + '</span>';
          }).join(' ');
          var credBadge = r.id
            ? '<span data-cred-repo-id="' + r.id + '" data-cred-repo-name="' + esc(r.full_name) + '" class="cursor-pointer inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-[#1f6feb]/20 text-[#58a6ff] hover:bg-[#1f6feb]/30 transition-colors ml-1">&#128273; Credentials</span>'
            : '';
          html += '<div class="flex items-start gap-2 p-2 rounded-lg bg-surface-hover">'
            + domainBadge(r.domain)
            + '<div class="min-w-0 flex-1">'
            + '<div class="flex items-center gap-1 flex-wrap"><span class="font-mono text-xs text-[#c9d1d9] truncate">' + esc(r.full_name) + '</span>' + credBadge + '</div>'
            + (stackTags ? '<div class="flex flex-wrap gap-1 mt-1">' + stackTags + '</div>' : '')
            + '</div>'
            + '<div class="text-right text-xs text-[#8b949e] shrink-0">'
            + '<div>' + (r.issue_count || 0) + ' issues</div>'
            + '<div>' + (r.open_pr_count || 0) + ' PRs</div>'
            + '</div>'
            + '</div>';
        });
        html += '</div>';
      }

      html += '<div class="flex items-center justify-between pt-2 border-t border-surface-border/50 text-xs text-[#8b949e]">'
        + '<span>' + (p.total_issues || 0) + ' total issues</span>'
        + '<span class="font-semibold text-accent-yellow">' + formatCost(p.total_cost_usd) + '</span>'
        + '</div></div>';
    });
    el.innerHTML = html;
    initIcons();
  }

  // ---- Budget Tab ----

  function renderBudget() {
    const d = state.data;
    const budget = (d && d.budget) || {};

    renderBudgetGauge('chart-budget-gauge-full', budget.today_spend_pct || 0, false);

    document.getElementById('budget-per-issue').textContent = formatCost(budget.max_per_issue);
    document.getElementById('budget-per-project').textContent = formatCost(budget.max_per_project_daily);
    document.getElementById('budget-total-daily').textContent = formatCost(budget.max_total_daily);

    const projects = budget.per_project_daily || [];
    const rows = projects.map(function(p) {
      const pct = Math.min(100, Math.round(p.pct || 0));
      const c = pct >= 90 ? '#f85149' : pct >= 70 ? '#d29922' : '#3fb950';
      const bar = '<div class="flex items-center gap-2"><div class="w-24 h-1.5 rounded-full bg-surface-border overflow-hidden"><div class="h-full rounded-full" style="width:' + pct + '%;background:' + c + '"></div></div><span class="text-xs text-[#8b949e]">' + pct + '%</span></div>';
      return [
        '<span class="text-sm text-[#e6edf3]">' + esc(p.project_name) + '</span>',
        '<span class="text-sm font-semibold" style="color:' + c + '">' + formatCost(p.spend) + '</span>',
        '<span class="text-sm text-[#8b949e]">' + formatCost(p.limit) + '</span>',
        bar
      ];
    });
    document.getElementById('budget-project-table-wrap').innerHTML = tableHTML(
      ['Project', 'Today Spend', 'Daily Limit', 'Utilization'],
      rows, 'dollar-sign', 'No budget data', 'Budget tracking begins once projects are registered'
    );
    initIcons();
  }

  // ---- Tab switching ----

  function switchTab(name) {
    state.activeTab = name;
    window.location.hash = name;
    document.querySelectorAll('.tab-btn').forEach(function(btn) {
      if (btn.dataset.tab === name) {
        btn.classList.remove('tab-inactive');
        btn.classList.add('tab-active');
      } else {
        btn.classList.remove('tab-active');
        btn.classList.add('tab-inactive');
      }
    });
    document.querySelectorAll('.tab-panel').forEach(function(panel) {
      panel.classList.add('hidden');
    });
    const panelEl = document.getElementById('tab-' + name);
    if (panelEl) panelEl.classList.remove('hidden');
    render();
  }

  // ---- Refresh countdown ----

  function updateCountdownDisplay() {
    const text = document.getElementById('countdown-text');
    const circle = document.getElementById('countdown-circle');
    if (text) text.textContent = state.refreshCountdown;
    if (circle) {
      const circumference = 69.12;
      const pct = state.refreshCountdown / state.refreshInterval;
      circle.style.strokeDashoffset = (circumference * (1 - pct)).toFixed(2);
    }
  }

  function startRefresh() {
    state.countdownTimer = setInterval(function() {
      state.refreshCountdown--;
      updateCountdownDisplay();
      if (state.refreshCountdown <= 0) {
        fetchData().then(function() { render(); });
        state.refreshCountdown = state.refreshInterval;
      }
    }, 1000);
  }

  function manualRefresh() {
    state.refreshCountdown = state.refreshInterval;
    updateCountdownDisplay();
    fetchData().then(function() { render(); });
  }
  function pollForLiveSession(issueId) {
    var attempts = 0;
    var maxAttempts = 10;
    var interval = setInterval(function() {
      attempts++;
      if (attempts > maxAttempts) { clearInterval(interval); return; }
      fetch('/api/sessions').then(function(r) { return r.json(); }).then(function(sessions) {
        var match = sessions.find(function(s) {
          return s.issue_id === issueId && s.status === 'running';
        });
        if (match) {
          clearInterval(interval);
          var liveUrl = '/session/' + esc(String(match.id)) + '/live';
          window.open(liveUrl, '_blank');
          showToast('Live session opened in new tab', 'success');
        }
      }).catch(function() {});
    }, 2000);
  }

  async function triggerAction(issueId, action, btnEl) {
    var origHTML = btnEl.innerHTML;
    btnEl.disabled = true;
    btnEl.innerHTML = '<svg class="w-3.5 h-3.5 animate-spin inline" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path></svg>';
    btnEl.classList.add('opacity-60');
    try {
      var resp = await fetch('/api/issues/' + issueId + '/' + action, { method: 'POST' });
      var data = await resp.json();
      if (!resp.ok) {
        showToast(data.error || 'Request failed', 'error');
        btnEl.innerHTML = origHTML;
        btnEl.disabled = false;
        btnEl.classList.remove('opacity-60');
        return;
      }
      showToast((action === 'enhance' ? 'Enhancement' : 'Implementation') + ' dispatched successfully', 'success');
      if (action === 'implement') {
        // Update local state immediately so the button disappears without waiting for refresh
        if (state.data && state.data.issues) {
          var issue = state.data.issues.find(function(i) { return i.id === issueId; });
          if (issue) { issue.status = 'implementing'; }
        }
        render();
        if (data.issue_id) {
          pollForLiveSession(data.issue_id);
        }
      }
      setTimeout(function() { fetchData().then(render); }, 1500);
    } catch (e) {
      showToast('Network error: ' + e.message, 'error');
      btnEl.innerHTML = origHTML;
      btnEl.disabled = false;
      btnEl.classList.remove('opacity-60');
    }
  }

  function showToast(message, type, isHtml) {
    var container = document.getElementById('toast-container');
    var toast = document.createElement('div');
    var colors = type === 'success'
      ? 'bg-[#238636]/90 border-[#3fb950]/40 text-[#3fb950]'
      : 'bg-[#da3633]/20 border-[#f85149]/40 text-[#f85149]';
    var icon = type === 'success' ? '\u2713' : '\u2715';
    toast.className = 'flex items-center gap-2 px-4 py-2.5 rounded-lg border backdrop-blur-sm shadow-lg text-sm transform translate-x-full transition-transform duration-300 ' + colors;
    var content = isHtml ? message : esc(message);
    toast.innerHTML = '<span class="font-bold text-base">' + icon + '</span><span>' + content + '</span>';
    container.appendChild(toast);
    requestAnimationFrame(function() {
      requestAnimationFrame(function() { toast.classList.remove('translate-x-full'); });
    });
    setTimeout(function() {
      toast.classList.add('translate-x-full');
      setTimeout(function() { toast.remove(); }, 300);
    }, 4000);
  }

  // Event delegation for action buttons (avoids escaping issues with inline onclick)
  document.addEventListener('click', function(e) {
    var filterBtn = e.target.closest('[data-issues-filter]');
    if (filterBtn) {
      var newFilter = filterBtn.dataset.issuesFilter;
      fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ issues_display_filter: newFilter })
      })
        .then(function(r) { return r.json(); })
        .then(function() {
          showToast('Filter updated to: ' + newFilter, 'success');
          fetchData();
        })
        .catch(function() { showToast('Failed to update filter', 'error'); });
      return;
    }
    var btn = e.target.closest('[data-action]');
    if (btn) {
      var issueId = parseInt(btn.dataset.issueId, 10);
      var action = btn.dataset.action;
      if (issueId && action) {
        triggerAction(issueId, action, btn);
      }
    }
  });

  window.showToast = showToast;
  window.manualRefresh = manualRefresh;

  // ---- Init ----

  document.querySelectorAll('.tab-btn').forEach(function(btn) {
    btn.addEventListener('click', function() { switchTab(btn.dataset.tab); });
  });

  // Restore tab from URL hash
  const hashTab = (window.location.hash || '').replace('#', '');
  if (hashTab && document.getElementById('tab-' + hashTab)) {
    state.activeTab = hashTab;
    switchTab(hashTab);
  }

  document.addEventListener('DOMContentLoaded', function() {
    fetchData().then(function() { render(); });
    startRefresh();
    initIcons();
  });

  // Also run immediately in case DOMContentLoaded already fired
  if (document.readyState !== 'loading') {
    fetchData().then(function() { render(); });
    startRefresh();
    initIcons();
  }

  // ── Session detail modal functions ──────────────────────────────
  function openSessionDetail(sessionId) {
    var modal = document.getElementById('session-modal');
    modal.classList.remove('hidden');
    document.getElementById('session-modal-body').innerHTML = '<div class="flex items-center justify-center h-32 text-[#484f58]"><span class="animate-pulse">Loading session history...</span></div>';
    fetch('/api/sessions/' + sessionId + '/history')
      .then(function(r) { return r.json(); })
      .then(function(data) { renderSessionModal(data); })
      .catch(function() {
        document.getElementById('session-modal-body').innerHTML = '<div class="text-center text-[#f85149] py-8">Failed to load session history</div>';
      });
  }

  function closeSessionModal() {
    document.getElementById('session-modal').classList.add('hidden');
  }

  function formatModalTime(isoStr) {
    if (!isoStr) return '';
    try {
      var d = new Date(isoStr);
      return d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit', second: '2-digit'});
    } catch(e) { return ''; }
  }

  function escModalHtml(str) {
    return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function renderSessionModal(data) {
    var info = data.session_info || {};
    var typeLabel = info.session_type
      ? info.session_type.charAt(0).toUpperCase() + info.session_type.slice(1) + ' Session'
      : 'Session';
    document.getElementById('session-modal-title').textContent = typeLabel;
    var subtitle = (info.repo_full_name || '') + (info.issue_number ? ' #' + info.issue_number : '');
    document.getElementById('session-modal-subtitle').textContent = subtitle;

    var sc = info.status ? info.status : '';
    var sColor = {running:'#3fb950',completed:'#3fb950',failed:'#f85149',pending:'#d29922'}[sc] || '#8b949e';
    var infoHtml = '<span style="background:' + sColor + '22;color:' + sColor + '" class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold">' + escModalHtml(sc) + '</span>'
      + '<span class="text-[#8b949e]">Cost: <span class="font-semibold text-[#d29922]">$' + Number(info.cost_usd || 0).toFixed(2) + '</span></span>';
    if (info.started_at) {
      var startedDiff = Math.floor((Date.now() - new Date(info.started_at).getTime()) / 1000);
      var startedAgo = startedDiff < 0 ? 'just now' : startedDiff < 60 ? startedDiff + 's ago' : startedDiff < 3600 ? Math.floor(startedDiff/60) + 'm ago' : startedDiff < 86400 ? Math.floor(startedDiff/3600) + 'h ' + Math.floor((startedDiff%3600)/60) + 'm ago' : Math.floor(startedDiff/86400) + 'd ago';
      infoHtml += '<span class="text-[#8b949e]">Started: ' + startedAgo + '</span>';
    }
    if (info.started_at && info.ended_at) {
      var durSec = Math.round((new Date(info.ended_at) - new Date(info.started_at)) / 1000);
      var durStr = durSec < 60 ? durSec + 's' : durSec < 3600 ? Math.floor(durSec/60) + 'm ' + (durSec%60) + 's' : Math.floor(durSec/3600) + 'h ' + Math.floor((durSec%3600)/60) + 'm';
      infoHtml += '<span class="text-[#8b949e]">Duration: ' + durStr + '</span>';
    }
    if (info.summary) {
      infoHtml += '<span class="text-[#8b949e] truncate max-w-xs" title="' + escModalHtml(info.summary) + '">' + escModalHtml(info.summary) + '</span>';
    }
    if (info.status === 'running') {
      infoHtml += '<button id="terminate-session-btn" onclick="terminateSession(' + info.id + ')" class="ml-auto px-3 py-1 rounded-md text-xs font-semibold bg-[#f85149]/20 text-[#f85149] hover:bg-[#f85149]/30 transition-colors">Terminate</button>';
    }
    document.getElementById('session-modal-info').innerHTML = infoHtml;

    var events = data.events || [];
    if (!events.length) {
      document.getElementById('session-modal-body').innerHTML = '<div class="text-center text-[#484f58] py-8">' + escModalHtml(data.message || 'No conversation history available') + '</div>';
      return;
    }

    var html = '';
    events.forEach(function(ev) {
      if (ev.type === 'user') {
        html += '<div class="flex gap-3">'
          + '<div class="w-7 h-7 rounded-full bg-[#58a6ff]/20 flex items-center justify-center shrink-0 mt-0.5"><svg class="w-3.5 h-3.5 text-[#58a6ff]" fill="currentColor" viewBox="0 0 20 20"><path d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z"/></svg></div>'
          + '<div class="flex-1 min-w-0">'
          + '<div class="text-xs text-[#8b949e] mb-1">User <span class="ml-2">' + formatModalTime(ev.timestamp) + '</span></div>'
          + '<div class="bg-[#161b22] border border-[#30363d] rounded-lg px-4 py-3 text-sm text-[#c9d1d9] whitespace-pre-wrap break-words max-h-64 overflow-y-auto">' + escModalHtml(ev.content || '') + '</div>'
          + '</div></div>';
      } else if (ev.type === 'assistant_text') {
        html += '<div class="flex gap-3">'
          + '<div class="w-7 h-7 rounded-full bg-[#a371f7]/20 flex items-center justify-center shrink-0 mt-0.5"><svg class="w-3.5 h-3.5 text-[#a371f7]" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clip-rule="evenodd"/></svg></div>'
          + '<div class="flex-1 min-w-0">'
          + '<div class="text-xs text-[#8b949e] mb-1">Claude <span class="ml-2">' + formatModalTime(ev.timestamp) + '</span></div>'
          + '<div class="bg-[#1c1f26] border border-[#30363d] rounded-lg px-4 py-3 text-sm text-[#e6edf3] whitespace-pre-wrap break-words max-h-96 overflow-y-auto">' + escModalHtml(ev.content || '') + '</div>'
          + '</div></div>';
      } else if (ev.type === 'tool_use') {
        html += '<div class="flex gap-3">'
          + '<div class="w-7 h-7 rounded-full bg-[#d29922]/20 flex items-center justify-center shrink-0 mt-0.5"><svg class="w-3.5 h-3.5 text-[#d29922]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg></div>'
          + '<div class="flex-1 min-w-0">'
          + '<div class="text-xs text-[#8b949e] mb-1">Tool: <span class="text-[#d29922] font-mono">' + escModalHtml(ev.tool_name || '') + '</span> <span class="ml-2">' + formatModalTime(ev.timestamp) + '</span></div>'
          + '<div class="bg-[#1a1b1e] border border-[#30363d] rounded-lg px-3 py-2 text-xs font-mono text-[#8b949e] whitespace-pre-wrap break-words max-h-32 overflow-y-auto">' + escModalHtml(ev.tool_input || '') + '</div>'
          + '</div></div>';
      }
    });

    if (data.event_count && data.event_count > events.length) {
      html += '<div class="text-center text-xs text-[#484f58] py-2">Showing last ' + events.length + ' of ' + data.event_count + ' events</div>';
    }

    document.getElementById('session-modal-body').innerHTML = html;
  }

  function terminateSession(sessionId) {
    var btn = document.getElementById('terminate-session-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Terminating...'; }
    fetch('/api/sessions/' + sessionId + '/terminate', { method: 'POST' })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (data.status === 'terminated') {
          if (btn) { btn.textContent = 'Terminated'; btn.classList.remove('bg-[#f85149]/20', 'text-[#f85149]'); btn.classList.add('bg-[#3fb950]/20', 'text-[#3fb950]'); }
          if (typeof showToast === 'function') showToast('Session terminated', 'success');
          setTimeout(function() { closeSessionModal(); fetchData(); }, 1500);
        } else {
          if (btn) { btn.disabled = false; btn.textContent = 'Terminate'; }
          if (typeof showToast === 'function') showToast(data.error || 'Failed to terminate', 'error');
        }
      })
      .catch(function() {
        if (btn) { btn.disabled = false; btn.textContent = 'Terminate'; }
        if (typeof showToast === 'function') showToast('Failed to terminate session', 'error');
      });
  }

  // Expose modal functions globally for onclick handlers and row clicks
  // ── Credentials modal functions ──────────────────────────────
  function openCredentialsModal(repoId, repoName) {
    var modal = document.getElementById('credentials-modal');
    if (modal) modal.classList.remove('hidden');
    var title = document.getElementById('cred-modal-title');
    if (title) title.textContent = repoName;
    var body = document.getElementById('cred-modal-content');
    if (body) body.innerHTML = '<p class="text-[#8b949e]">Loading...</p>';
    fetch('/api/repos/' + repoId + '/credentials')
      .then(function(r) { return r.json(); })
      .then(function(data) { renderCredentialsModal(repoId, repoName, data.credentials || {}); })
      .catch(function() { showToast('Failed to load credentials', 'error'); });
  }

  function renderCredentialsModal(repoId, repoName, credentials) {
    var body = document.getElementById('cred-modal-content');
    if (!body) return;
    var html = '';

    // Credentials table
    var credKeys = credentials ? Object.keys(credentials) : [];
    if (credKeys.length > 0) {
      html += '<table class="w-full text-sm mb-4"><thead><tr class="border-b border-[#30363d]">'
        + '<th class="px-3 py-2 text-left text-xs font-semibold text-[#8b949e] uppercase">Key</th>'
        + '<th class="px-3 py-2 text-left text-xs font-semibold text-[#8b949e] uppercase">Value</th>'
        + '</tr></thead><tbody>';
      credKeys.forEach(function(key) {
        html += '<tr class="border-b border-[#30363d]/50 hover:bg-[#1c2128] transition-colors">'
          + '<td class="px-3 py-2 font-mono text-xs text-[#c9d1d9]">' + esc(key) + '</td>'
          + '<td class="px-3 py-2 font-mono text-xs text-[#8b949e]">' + esc(credentials[key]) + '</td>'
          + '</tr>';
      });
      html += '</tbody></table>';
    } else {
      html += '<p class="text-sm text-[#8b949e] mb-4">No credentials stored for this repository.</p>';
    }

    // Actions
    html += '<div class="flex flex-wrap gap-2 mb-4">'
      + '<button data-cred-discover="' + repoId + '" class="px-3 py-1.5 rounded-md text-xs font-medium bg-[#a371f7]/15 text-[#a371f7] hover:bg-[#a371f7]/25 border border-[#a371f7]/20 transition-all cursor-pointer">&#128269; Auto-Discover</button>'
      + '<button data-cred-clear="' + repoId + '" class="px-3 py-1.5 rounded-md text-xs font-medium bg-[#f85149]/10 text-[#f85149] hover:bg-[#f85149]/20 border border-[#f85149]/20 transition-all cursor-pointer">&#128465; Clear All</button>'
      + '</div>';

    // Add credential form
    html += '<div class="border border-[#30363d] rounded-lg p-4">'
      + '<h3 class="text-xs font-semibold text-[#8b949e] uppercase tracking-wide mb-3">Add Credential</h3>'
      + '<div class="flex flex-col sm:flex-row gap-2 mb-2">'
      + '<input id="cred-key-input" type="text" placeholder="KEY_NAME" class="flex-1 px-3 py-1.5 rounded-md text-xs bg-[#0d1117] border border-[#30363d] text-[#e6edf3] placeholder-[#484f58] focus:outline-none focus:border-[#58a6ff]">'
      + '<input id="cred-value-input" type="text" placeholder="value" class="flex-1 px-3 py-1.5 rounded-md text-xs bg-[#0d1117] border border-[#30363d] text-[#e6edf3] placeholder-[#484f58] focus:outline-none focus:border-[#58a6ff]">'
      + '<button data-cred-add="' + repoId + '" class="px-3 py-1.5 rounded-md text-xs font-medium bg-[#238636]/15 text-[#3fb950] hover:bg-[#238636]/25 border border-[#238636]/20 transition-all cursor-pointer whitespace-nowrap">+ Add</button>'
      + '</div></div>';

    body.innerHTML = html;
  }

  function closeCredentialsModal() {
    var m = document.getElementById('credentials-modal');
    if (m) m.classList.add('hidden');
  }

  // Event delegation for credentials modal buttons
  document.addEventListener('click', function(e) {
    // Credential badge click - open modal
    var badge = e.target.closest('[data-cred-repo-id]');
    if (badge) {
      var rid = parseInt(badge.dataset.credRepoId, 10);
      var rname = badge.dataset.credRepoName || '';
      openCredentialsModal(rid, rname);
      return;
    }
    // Discover button
    var discoverBtn = e.target.closest('[data-cred-discover]');
    if (discoverBtn) {
      var rid = parseInt(discoverBtn.dataset.credDiscover, 10);
      var rname = (document.getElementById('cred-modal-title') || {}).textContent || '';
      discoverBtn.disabled = true;
      discoverBtn.textContent = 'Discovering...';
      fetch('/api/repos/' + rid + '/credentials/discover', { method: 'POST' })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          showToast('Discovered ' + (data.discovered_count || 0) + ' credentials', 'success');
          openCredentialsModal(rid, rname);
        })
        .catch(function() { showToast('Discovery failed', 'error'); discoverBtn.disabled = false; });
      return;
    }
    // Add credential button
    var addBtn = e.target.closest('[data-cred-add]');
    if (addBtn) {
      var rid = parseInt(addBtn.dataset.credAdd, 10);
      var rname = (document.getElementById('cred-modal-title') || {}).textContent || '';
      var key = (document.getElementById('cred-key-input') || {}).value || '';
      var val = (document.getElementById('cred-value-input') || {}).value || '';
      key = key.trim(); val = val.trim();
      if (!key || !val) { showToast('Key and value required', 'error'); return; }
      var creds = {}; creds[key] = val;
      fetch('/api/repos/' + rid + '/credentials', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ credentials: creds })
      })
        .then(function(r) { return r.json(); })
        .then(function() {
          showToast('Credential added', 'success');
          openCredentialsModal(rid, rname);
        })
        .catch(function() { showToast('Failed to add credential', 'error'); });
      return;
    }
    // Clear all credentials button
    var clearBtn = e.target.closest('[data-cred-clear]');
    if (clearBtn) {
      var rid = parseInt(clearBtn.dataset.credClear, 10);
      var rname = (document.getElementById('cred-modal-title') || {}).textContent || '';
      fetch('/api/repos/' + rid + '/credentials', { method: 'DELETE' })
        .then(function(r) { return r.json(); })
        .then(function() {
          showToast('Credentials cleared', 'success');
          openCredentialsModal(rid, rname);
        })
        .catch(function() { showToast('Failed to clear credentials', 'error'); });
      return;
    }
  });

  window.openCredentialsModal = openCredentialsModal;
  window.closeCredentialsModal = closeCredentialsModal;

  window.openSessionDetail = openSessionDetail;
  window.closeSessionModal = closeSessionModal;
  window.terminateSession = terminateSession;

  // Modal backdrop click to close
  document.addEventListener('click', function(e) {
    var modal = document.getElementById('session-modal');
    if (modal && e.target === modal) closeSessionModal();
  });
  // Escape key to close
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') { closeSessionModal(); closeCredentialsModal(); }
  });

  // Credentials modal backdrop click to close
  document.addEventListener('click', function(e) {
    var cm = document.getElementById('credentials-modal');
    if (cm && e.target === cm) closeCredentialsModal();
  });

})();
</script>

<!-- SESSION DETAIL MODAL -->
<div id="session-modal" class="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 hidden flex items-start justify-center pt-16 px-4 overflow-y-auto">
  <div class="bg-[#0d1117] border border-[#30363d] rounded-xl w-full max-w-4xl max-h-[80vh] flex flex-col shadow-2xl mb-16">
    <div class="flex items-center justify-between px-6 py-4 border-b border-[#30363d]">
      <div>
        <h3 class="text-lg font-semibold text-[#e6edf3]" id="session-modal-title">Session History</h3>
        <p class="text-xs text-[#8b949e] mt-0.5" id="session-modal-subtitle"></p>
      </div>
      <button onclick="closeSessionModal()" class="text-[#8b949e] hover:text-[#e6edf3] transition-colors p-1">
        <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
      </button>
    </div>
    <div id="session-modal-info" class="px-6 py-3 border-b border-[#30363d] bg-[#161b22] flex items-center gap-4 text-xs flex-wrap"></div>
    <div id="session-modal-body" class="flex-1 overflow-y-auto px-6 py-4 space-y-4">
      <div class="flex items-center justify-center h-32 text-[#484f58]">Loading...</div>
    </div>
  </div>
</div>


<!-- CREDENTIALS MODAL -->
<div id="credentials-modal" class="hidden fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-start justify-center pt-16 px-4 overflow-y-auto">
  <div class="bg-[#0d1117] border border-[#30363d] rounded-xl w-full max-w-2xl flex flex-col shadow-2xl mb-16">
    <!-- Header -->
    <div class="flex items-center justify-between px-6 py-4 border-b border-[#30363d]">
      <div>
        <h2 class="text-lg font-semibold text-[#f0f6fc]">&#128273; Test Credentials</h2>
        <p id="cred-modal-title" class="text-sm text-[#8b949e] mt-0.5"></p>
      </div>
      <button onclick="window.closeCredentialsModal()" class="text-[#8b949e] hover:text-[#f0f6fc] text-2xl leading-none transition-colors p-1">&times;</button>
    </div>
    <!-- Content -->
    <div id="cred-modal-content" class="p-6 overflow-y-auto max-h-[60vh]">
      <p class="text-[#8b949e]">Loading...</p>
    </div>
  </div>
</div>

</body>
</html>"""


@router.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> HTMLResponse:
    """Serve the dashboard page with auth token for browser API access.

    Uses two auth delivery mechanisms (standard CSRF-token pattern):
    1. HttpOnly cookie — automatically sent by the browser on same-origin requests.
    2. Meta-tag injection — JS reads the token and sets it as an ``X-Dashboard-Token``
       header on every ``fetch('/api/...')`` call.  This mirrors the CSRF-token pattern
       used by Django, Rails, and Laravel.
    """
    token: str = request.app.state.dashboard_token
    # Inject auth bootstrap script right after <head> opening tag.
    # The script overrides window.fetch to attach the auth header on /api/ calls
    # and is executed before any other scripts in the page.
    auth_script = (
        f'<meta name="dashboard-token" content="{token}">'
        "<script>"
        "(function(){"
        "var t=document.querySelector('meta[name=\"dashboard-token\"]').content;"
        "var _f=window.fetch;"
        "window.fetch=function(u,o){"
        "if(typeof u==='string'&&u.startsWith('/api/')){"
        "o=o||{};o.headers=o.headers||{};"
        "o.headers['X-Dashboard-Token']=t;"
        "}"
        "return _f.call(this,u,o);"
        "};"
        "})();"
        "</script>"
    )
    html = DASHBOARD_HTML.replace("<head>", "<head>" + auth_script, 1)
    response = HTMLResponse(html)
    response.set_cookie(
        key="_claudedev_dash",
        value=token,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return response


@router.get("/stats")
async def dashboard_stats() -> DashboardStats:
    """Get aggregated dashboard statistics."""
    async with get_session() as session:
        project_count = await session.scalar(select(func.count(Project.id)))
        issue_count = await session.scalar(select(func.count(TrackedIssue.id)))
        pr_count = await session.scalar(select(func.count(TrackedPR.id)))
        active_sessions = await session.scalar(
            select(func.count(AgentSession.id)).where(AgentSession.status == SessionStatus.RUNNING)
        )
        total_cost = await session.scalar(
            select(func.sum(AgentSession.cost_usd)).where(
                AgentSession.status == SessionStatus.COMPLETED
            )
        )

        return {
            "projects": project_count or 0,
            "issues": issue_count or 0,
            "prs": pr_count or 0,
            "active_sessions": active_sessions or 0,
            "total_cost_usd": float(total_cost or 0),
        }
