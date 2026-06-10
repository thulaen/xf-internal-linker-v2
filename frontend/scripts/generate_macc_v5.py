import os

src_path = r'c:\Users\goldm\Dev\xf-internal-linker-v2\frontend\signal-control-light-prototype.html'
dest_path = r'c:\Users\goldm\Dev\xf-internal-linker-v2\frontend\macc-v5.html'

with open(src_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Inject Tailwind
tailwind_script = '<script src="https://cdn.tailwindcss.com"></script>\n<title>MACC Dashboard Beta v5 (Heavy Glass)</title>'
content = content.replace('<title>Signal Control Light — Clickable Prototype</title>', tailwind_script)

macc_v5_css = """
<style id="macc-v5-heavy-glass">
/* =========================================================
   MACC V5: HEAVY LIQUID GLASS (High Readability)
   Increased blur radius and tweaked translucency to maximize 
   the glassmorphism effect while smoothing out background 
   noise for perfect readability.
   ========================================================= */

body {
  background-color: var(--canvas) !important;
  background-image: 
    radial-gradient(at 0% 0%, rgba(204, 120, 92, 0.12) 0, transparent 40%), 
    radial-gradient(at 100% 0%, rgba(255, 255, 255, 0.9) 0, transparent 50%), 
    radial-gradient(at 0% 100%, rgba(255, 255, 255, 0.9) 0, transparent 50%), 
    radial-gradient(at 100% 100%, rgba(204, 120, 92, 0.08) 0, transparent 40%) !important;
  background-attachment: fixed !important;
  background-size: cover !important;
}

.scl-view {
  background: transparent !important;
}

/* 2. Topbar - Heavy Liquid Glass */
.scl-topbar {
  background: rgba(255, 255, 255, 0.55) !important;
  backdrop-filter: saturate(200%) blur(40px) !important;
  -webkit-backdrop-filter: saturate(200%) blur(40px) !important;
  border-bottom: 1px solid rgba(222, 221, 215, 0.6) !important; 
  box-shadow: 0 4px 20px rgba(0,0,0,0.02) !important;
}

/* 3. Sidebar (Rail) - Heavy Liquid Glass */
.scl-rail {
  background: rgba(244, 243, 239, 0.45) !important; 
  backdrop-filter: saturate(200%) blur(40px) !important;
  -webkit-backdrop-filter: saturate(200%) blur(40px) !important;
  border-right: 1px solid rgba(222, 221, 215, 0.6) !important;
}

/* 4. Panels & Cards - Ultra Frosted Glass */
/* Dropped opacity to 65% for MORE glass, but raised blur to 40px for perfect readability */
.scl-panel, .scl-card, .scl-kpi, .scl-tabs, .vi-island, .scl-sum {
  background: rgba(255, 255, 255, 0.65) !important; 
  backdrop-filter: saturate(180%) blur(40px) !important;
  -webkit-backdrop-filter: saturate(180%) blur(40px) !important;
  border: 1px solid rgba(255, 255, 255, 0.8) !important; 
  box-shadow: 0 4px 16px rgba(0,0,0,0.03), inset 0 0 0 1px rgba(255,255,255,0.5) !important;
  border-radius: 12px !important;
}

/* 5. Inputs & Search - Deep Sunken Glass */
.tb-search, .scl-navout {
  background: rgba(0,0,0,0.04) !important;
  backdrop-filter: saturate(150%) blur(20px) !important;
  border: 1px solid rgba(0,0,0,0.05) !important;
  box-shadow: inset 0 1px 3px rgba(0,0,0,0.02) !important;
}
.tb-search:hover {
  background: rgba(0,0,0,0.06) !important;
}

/* 6. Buttons - Raised Heavy Glass */
.scl-btn, .tb-prop {
  background: rgba(255, 255, 255, 0.7) !important;
  backdrop-filter: saturate(150%) blur(20px) !important;
  border: 1px solid rgba(222, 221, 215, 0.8) !important; 
  box-shadow: 0 1px 2px rgba(0,0,0,0.03) !important;
}
.scl-btn:hover, .tb-prop:hover {
  background: rgba(255, 255, 255, 0.9) !important;
}

.scl-btn.primary {
  background: rgba(204, 120, 92, 0.85) !important; 
  backdrop-filter: saturate(150%) blur(20px) !important;
  color: #fff !important;
  border: 1px solid rgba(255,255,255,0.25) !important;
  box-shadow: 0 2px 6px rgba(204, 120, 92, 0.3) !important;
}
.scl-btn.primary:hover {
  background: var(--coral-strong) !important;
}

/* 7. Active Nav - Glass Pill */
.scl-nav.active {
  background: rgba(255, 255, 255, 0.6) !important;
  backdrop-filter: saturate(150%) blur(20px) !important;
  box-shadow: 0 2px 6px rgba(0,0,0,0.04) !important;
  border: 1px solid rgba(255,255,255,0.6) !important;
}

/* 8. Tables */
.scl-table th {
  background: transparent !important;
  border-bottom: 1px solid rgba(0,0,0,0.06) !important;
}
.scl-table td {
  border-bottom: 1px solid rgba(0,0,0,0.04) !important;
}
.scl-row:hover, .scl-table tr:hover td {
  background: rgba(0,0,0,0.03) !important;
}
</style>
"""

content = content.replace('</head>', macc_v5_css + '</head>')

with open(dest_path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'Successfully copied full functionality to {dest_path} and injected HIG Heavy Liquid Glass.')
