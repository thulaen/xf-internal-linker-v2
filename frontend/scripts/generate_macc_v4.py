import os

src_path = r'c:\Users\goldm\Dev\xf-internal-linker-v2\frontend\signal-control-light-prototype.html'
dest_path = r'c:\Users\goldm\Dev\xf-internal-linker-v2\frontend\macc-v4.html'

with open(src_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Inject Tailwind
tailwind_script = '<script src="https://cdn.tailwindcss.com"></script>\n<title>MACC Dashboard Beta v4 (Original Tokens + Glass)</title>'
content = content.replace('<title>Signal Control Light — Clickable Prototype</title>', tailwind_script)

macc_v4_css = """
<style id="macc-v4-liquid-glass">
/* =========================================================
   MACC V4: ORIGINAL DESIGN TOKENS + LIQUID GLASS
   No colors are overwritten. We exclusively apply translucency 
   and blur to the original warm palette.
   ========================================================= */

/* 1. Ambient Background 
   Using the original --canvas (#F4F3EF) and --coral (#CC785C) to create a very subtle, creamy 
   mesh background. This gives the glass something to refract without being messy. */
body {
  background-color: var(--canvas) !important;
  background-image: 
    radial-gradient(at 0% 0%, rgba(204, 120, 92, 0.08) 0, transparent 40%), 
    radial-gradient(at 100% 0%, rgba(255, 255, 255, 0.8) 0, transparent 50%), 
    radial-gradient(at 0% 100%, rgba(255, 255, 255, 0.8) 0, transparent 50%), 
    radial-gradient(at 100% 100%, rgba(204, 120, 92, 0.05) 0, transparent 40%) !important;
  background-attachment: fixed !important;
  background-size: cover !important;
}

/* Make the main view wrapper transparent so the body background shows through */
.scl-view {
  background: transparent !important;
}

/* 2. Topbar - Liquid Glass */
/* We use white at 60% opacity so it's bright but translucent */
.scl-topbar {
  background: rgba(255, 255, 255, 0.6) !important;
  backdrop-filter: saturate(180%) blur(24px) !important;
  -webkit-backdrop-filter: saturate(180%) blur(24px) !important;
  border-bottom: 1px solid rgba(222, 221, 215, 0.6) !important; /* translucent --border */
  box-shadow: 0 4px 20px rgba(0,0,0,0.02) !important;
}

/* 3. Sidebar (Rail) - Liquid Glass */
/* Uses a slightly warmer translucent base to match original --canvas-deep */
.scl-rail {
  background: rgba(244, 243, 239, 0.5) !important; 
  backdrop-filter: saturate(180%) blur(24px) !important;
  -webkit-backdrop-filter: saturate(180%) blur(24px) !important;
  border-right: 1px solid rgba(222, 221, 215, 0.6) !important;
}

/* 4. Panels & Cards - Frosted Glass */
/* 80% opacity ensures text is perfectly legible, while still providing a deep liquid glass feel */
.scl-panel, .scl-card, .scl-kpi, .scl-tabs, .vi-island, .scl-sum {
  background: rgba(255, 255, 255, 0.80) !important; 
  backdrop-filter: saturate(150%) blur(20px) !important;
  -webkit-backdrop-filter: saturate(150%) blur(20px) !important;
  border: 1px solid rgba(255, 255, 255, 0.7) !important; /* crisp glass edge */
  box-shadow: 0 4px 16px rgba(0,0,0,0.03), inset 0 0 0 1px rgba(255,255,255,0.4) !important;
  border-radius: 12px !important;
}

/* 5. Inputs & Search - Sunken Glass */
.tb-search, .scl-navout {
  background: rgba(0,0,0,0.03) !important;
  backdrop-filter: blur(10px) !important;
  border: 1px solid rgba(0,0,0,0.05) !important;
  box-shadow: inset 0 1px 3px rgba(0,0,0,0.02) !important;
}
.tb-search:hover {
  background: rgba(0,0,0,0.05) !important;
}

/* 6. Buttons - Raised Glass */
.scl-btn, .tb-prop {
  background: rgba(255, 255, 255, 0.8) !important;
  backdrop-filter: blur(10px) !important;
  border: 1px solid rgba(222, 221, 215, 0.8) !important; /* --border */
  box-shadow: 0 1px 2px rgba(0,0,0,0.03) !important;
}
.scl-btn:hover, .tb-prop:hover {
  background: rgba(255, 255, 255, 1) !important;
}

.scl-btn.primary {
  /* Uses the original --coral but heavily glassed */
  background: rgba(204, 120, 92, 0.9) !important; 
  backdrop-filter: blur(10px) !important;
  color: #fff !important;
  border: 1px solid rgba(255,255,255,0.2) !important;
  box-shadow: 0 2px 6px rgba(204, 120, 92, 0.3) !important;
}
.scl-btn.primary:hover {
  background: var(--coral-strong) !important;
}

/* 7. Active Nav */
/* Replaces the solid white panel with a raised glass pill */
.scl-nav.active {
  background: rgba(255, 255, 255, 0.8) !important;
  backdrop-filter: blur(10px) !important;
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

content = content.replace('</head>', macc_v4_css + '</head>')

with open(dest_path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'Successfully copied full functionality to {dest_path} and injected HIG Apple Liquid Glass styles retaining original tokens + Tailwind.')
