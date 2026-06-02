"""Dark laser-themed styling for NiceGUI."""

from __future__ import annotations

from nicegui import ui

LASER_HEADER_SVG = """
<svg viewBox="0 0 320 56" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"
     style="width:100%;max-width:420px;height:56px;display:block;margin:0 auto 8px;">
  <defs>
    <linearGradient id="beam" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" style="stop-color:#22d3ee;stop-opacity:0.2"/>
      <stop offset="50%" style="stop-color:#22d3ee;stop-opacity:1"/>
      <stop offset="100%" style="stop-color:#f43f5e;stop-opacity:0.9"/>
    </linearGradient>
    <linearGradient id="cavity" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:#334155"/>
      <stop offset="100%" style="stop-color:#1e293b"/>
    </linearGradient>
  </defs>
  <rect x="8" y="18" width="72" height="20" rx="4" fill="url(#cavity)" stroke="#475569" stroke-width="1"/>
  <rect x="240" y="18" width="72" height="20" rx="4" fill="url(#cavity)" stroke="#475569" stroke-width="1"/>
  <line x1="84" y1="28" x2="236" y2="28" stroke="url(#beam)" stroke-width="3" stroke-linecap="round"/>
  <circle cx="160" cy="28" r="6" fill="#0f172a" stroke="#22d3ee" stroke-width="2"/>
  <text x="160" y="52" text-anchor="middle" fill="#94a3b8" font-size="11" font-family="system-ui,sans-serif">
    TLB-8800 Control
  </text>
</svg>
"""

LASER_CSS = """
:root {
  --laser-bg: #0b1220;
  --laser-card: #111827;
  --laser-border: #1e293b;
  --laser-accent: #22d3ee;
  --laser-danger: #f43f5e;
  --laser-muted: #94a3b8;
}
body, .nicegui-content {
  background: radial-gradient(ellipse at top, #0f172a 0%, var(--laser-bg) 55%) !important;
}
.laser-panel {
  background: var(--laser-card) !important;
  border: 1px solid var(--laser-border) !important;
  border-radius: 12px !important;
}
.laser-section-title {
  color: var(--laser-accent) !important;
  font-weight: 600 !important;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-size: 0.72rem !important;
}
.laser-status-log textarea {
  font-family: ui-monospace, Consolas, monospace !important;
  font-size: 0.8rem !important;
  background: #020617 !important;
  color: #e2e8f0 !important;
}
.laser-telemetry .q-field__native {
  color: #cbd5e1 !important;
}
"""


def apply_laser_theme() -> None:
    ui.dark_mode().enable()
    ui.add_head_html(f"<style>{LASER_CSS}</style>")


def laser_header() -> None:
    ui.html(LASER_HEADER_SVG, sanitize=False).classes("w-full")
