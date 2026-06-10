import os

src_path = r'c:\Users\goldm\Dev\xf-internal-linker-v2\frontend\signal-control-light-prototype.html'
dest_path = r'c:\Users\goldm\Dev\xf-internal-linker-v2\frontend\macc-prototype.html'

with open(src_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Inject Tailwind
tailwind_script = '<script src="https://cdn.tailwindcss.com"></script>\n<title>MACC Dashboard Beta</title>'
content = content.replace('<title>Signal Control Light — Clickable Prototype</title>', tailwind_script)

macc_css = """
<style id="macc-glass-overrides">
/* MACC LIQUID GLASS ENHANCEMENTS */
:root {
  --macc-bg: radial-gradient(at 10% 20%, hsla(28, 100%, 74%, 1) 0px, transparent 50%),
             radial-gradient(at 80% 0%, hsla(189, 100%, 56%, 1) 0px, transparent 50%),
             radial-gradient(at 0% 50%, hsla(355, 100%, 93%, 1) 0px, transparent 50%),
             radial-gradient(at 80% 50%, hsla(340, 100%, 76%, 1) 0px, transparent 50%),
             radial-gradient(at 0% 100%, hsla(22, 100%, 77%, 1) 0px, transparent 50%),
             radial-gradient(at 80% 100%, hsla(242, 100%, 70%, 1) 0px, transparent 50%),
             radial-gradient(at 0% 0%, hsla(343, 100%, 76%, 1) 0px, transparent 50%);
  --macc-bg-base: #ffecd2;
  --glass-panel: rgba(255, 255, 255, 0.45);
  --glass-border: rgba(255, 255, 255, 0.5);
  --glass-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.1);
  --glass-blur: blur(24px);
  --glass-blur-heavy: blur(40px);
}
body {
  background-color: var(--macc-bg-base) !important;
  background-image: var(--macc-bg) !important;
  background-size: cover !important;
  background-attachment: fixed !important;
}
.scl-topbar {
  background: rgba(255, 255, 255, 0.25) !important;
  backdrop-filter: var(--glass-blur-heavy) saturate(150%) !important;
  -webkit-backdrop-filter: var(--glass-blur-heavy) saturate(150%) !important;
  border-bottom: 1px solid var(--glass-border) !important;
  box-shadow: var(--glass-shadow) !important;
}
.scl-rail {
  background: rgba(255, 255, 255, 0.15) !important;
  backdrop-filter: var(--glass-blur) !important;
  -webkit-backdrop-filter: var(--glass-blur) !important;
  border-right: 1px solid var(--glass-border) !important;
}
.scl-view {
  background: transparent !important;
}
.scl-panel, .scl-kpi, .scl-card, .scl-tabs, .vi-island {
  background: var(--glass-panel) !important;
  backdrop-filter: var(--glass-blur) !important;
  -webkit-backdrop-filter: var(--glass-blur) !important;
  border: 1px solid var(--glass-border) !important;
  box-shadow: var(--glass-shadow) !important;
}
.scl-nav:hover {
  background: rgba(255, 255, 255, 0.3) !important;
}
.scl-nav.active {
  background: rgba(255, 255, 255, 0.5) !important;
  border-color: rgba(255, 255, 255, 0.6) !important;
}
.scl-nav.active .nav-ic, .scl-nav.active svg.nav-ic {
  background: rgba(0, 122, 255, 0.8) !important;
  color: white !important;
}
.tb-search, .tb-prop, .tb-icon {
  background: rgba(255, 255, 255, 0.3) !important;
  border-color: rgba(255, 255, 255, 0.5) !important;
}
.tb-search:hover, .tb-prop:hover, .tb-icon:hover {
  background: rgba(255, 255, 255, 0.5) !important;
}
.scl-btn {
  background: rgba(255, 255, 255, 0.4) !important;
  border: 1px solid var(--glass-border) !important;
  backdrop-filter: var(--glass-blur) !important;
}
.scl-btn:hover {
  background: rgba(255, 255, 255, 0.6) !important;
}
.scl-btn.primary {
  background: rgba(0, 122, 255, 0.8) !important;
  color: white !important;
  border-color: rgba(0, 122, 255, 0.4) !important;
}
.scl-btn.primary:hover {
  background: rgba(0, 122, 255, 1) !important;
}
.scl-kpi .scl-glabel:not([style*="color"]) {
  color: var(--text-2) !important;
}
.scl-table th {
  background: transparent !important;
  border-bottom: 1px solid var(--glass-border) !important;
}
.scl-table td {
  border-bottom: 1px solid rgba(255, 255, 255, 0.2) !important;
}
.scl-row:hover, .scl-table tr:hover td {
  background: rgba(255, 255, 255, 0.3) !important;
}
.scl-rail .scl-nav .nav-ic, .scl-rail .scl-nav svg.nav-ic {
  background: rgba(255, 255, 255, 0.4) !important;
}
</style>
"""

content = content.replace('</head>', macc_css + '</head>')

with open(dest_path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'Successfully copied full functionality to {dest_path} and injected macc glass styles + Tailwind.')
