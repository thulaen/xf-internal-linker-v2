import os

src_path = r'c:\Users\goldm\Dev\xf-internal-linker-v2\frontend\signal-control-light-prototype.html'
dest_path = r'c:\Users\goldm\Dev\xf-internal-linker-v2\frontend\macc-v3.html'

with open(src_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Inject Tailwind
tailwind_script = '<script src="https://cdn.tailwindcss.com"></script>\n<title>MACC Dashboard Beta v3 (Liquid Glass HIG)</title>'
content = content.replace('<title>Signal Control Light — Clickable Prototype</title>', tailwind_script)

macc_hig_glass_css = """
<style id="macc-v3-overrides">
/* =========================================================
   MACC V3: AUTHENTIC APPLE HIG LIQUID GLASS
   ========================================================= */

/* 1. Base Variables: macOS System Colors & Crisp Contrasts */
:root {
  --text: #000000 !important;
  --text-2: #3C3C43 !important;
  --text-3: #8E8E93 !important;
  
  --coral: #007AFF !important; /* systemBlue */
  --coral-strong: #0056B3 !important;
  --coral-tint: #E5F1FF !important;
  
  --em: #34C759 !important; /* systemGreen */
  --em-tint: #EAF9EE !important;
  --am: #FF9500 !important; /* systemOrange */
  --am-tint: #FFF4E5 !important;
  --red: #FF3B30 !important; /* systemRed */
  --red-tint: #FFEBEA !important;
  
  --border: rgba(0,0,0,0.08) !important;
  --border-strong: rgba(0,0,0,0.15) !important;
}

/* 2. Wallpaper: Elegant, soft fluid gradient (Apple desktop style) */
body {
  background-color: #f8f9fa !important;
  background-image: 
    radial-gradient(at 0% 0%, hsla(253, 40%, 90%, 1) 0, transparent 50%), 
    radial-gradient(at 100% 0%, hsla(339, 40%, 90%, 1) 0, transparent 50%), 
    radial-gradient(at 0% 100%, hsla(189, 40%, 90%, 1) 0, transparent 50%), 
    radial-gradient(at 100% 100%, hsla(28, 40%, 90%, 1) 0, transparent 50%) !important;
  background-attachment: fixed !important;
  background-size: cover !important;
}

/* 3. Liquid Glass Structural Panels (Sidebar & Topbar) 
      These provide the heavy, satisfying frosted glass effect over the wallpaper */
.scl-topbar {
  background: rgba(255, 255, 255, 0.65) !important;
  backdrop-filter: saturate(200%) blur(30px) !important;
  -webkit-backdrop-filter: saturate(200%) blur(30px) !important;
  border-bottom: 1px solid rgba(0,0,0,0.06) !important;
  box-shadow: 0 1px 3px rgba(0,0,0,0.02) !important;
}

.scl-rail {
  background: rgba(245, 245, 247, 0.5) !important;
  backdrop-filter: saturate(200%) blur(30px) !important;
  -webkit-backdrop-filter: saturate(200%) blur(30px) !important;
  border-right: 1px solid rgba(0,0,0,0.06) !important;
}

/* 4. Main Canvas Wash
      A subtle glass wash so the wallpaper shines through beautifully but doesn't overpower content */
.scl-view {
  background: rgba(255, 255, 255, 0.35) !important;
  backdrop-filter: saturate(150%) blur(20px) !important;
  -webkit-backdrop-filter: saturate(150%) blur(20px) !important;
}

/* 5. Opaque Content Containers
      To solve the "messy text" issue, all data cards are OPAQUE white. 
      This is standard Apple HIG: glass for structure, opaque white for content. */
.scl-panel, .scl-card, .scl-kpi, .scl-tabs, .vi-island, .scl-sum {
  background: rgba(255, 255, 255, 0.95) !important;
  border: 1px solid rgba(0,0,0,0.05) !important;
  box-shadow: 0 4px 16px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02) !important;
  border-radius: 12px !important;
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
}

/* Ensure secondary labels don't get recolored by legacy brand overrides */
.scl-kpi .scl-glabel:not([style*="color"]) {
  color: var(--text-2) !important;
}

/* 6. Inputs & Search (Sunken Fields) */
.tb-search, .scl-navout {
  background: rgba(0,0,0,0.05) !important;
  border: 1px solid rgba(0,0,0,0.03) !important;
  color: var(--text) !important;
  border-radius: 8px !important;
}
.tb-search:hover {
  background: rgba(0,0,0,0.08) !important;
}
.tb-search::placeholder {
  color: var(--text-3) !important;
}

/* 7. Buttons (macOS standard) */
.scl-btn, .tb-prop {
  background: #FFFFFF !important;
  border: 1px solid rgba(0,0,0,0.1) !important;
  box-shadow: 0 1px 2px rgba(0,0,0,0.03) !important;
  color: var(--text) !important;
  border-radius: 6px !important;
}
.scl-btn:hover, .tb-prop:hover {
  background: #F5F5F5 !important;
}

.scl-btn.primary {
  background: var(--coral) !important;
  color: #fff !important;
  border: none !important;
  box-shadow: 0 2px 4px rgba(0,122,255,0.25) !important;
}
.scl-btn.primary:hover {
  background: var(--coral-strong) !important;
}

/* 8. Active Nav Selection (Modern macOS Sidebar) */
.scl-nav.active {
  background: var(--coral) !important;
  color: #fff !important;
  border-color: transparent !important;
  box-shadow: 0 2px 6px rgba(0,122,255,0.2) !important;
}
.scl-nav.active svg, .scl-nav.active .nav-ic {
  color: #fff !important;
  background: transparent !important;
}
.scl-nav:hover:not(.active) {
  background: rgba(0,0,0,0.05) !important;
}

/* Nav Icons (resting) */
.scl-rail .scl-nav .nav-ic, .scl-rail .scl-nav svg.nav-ic {
  background: rgba(0,0,0,0.04) !important;
  color: var(--text-2) !important;
}

/* 9. Tables */
.scl-table th {
  background: transparent !important;
  border-bottom: 1px solid rgba(0,0,0,0.06) !important;
  color: var(--text-3) !important;
}
.scl-table td {
  border-bottom: 1px solid rgba(0,0,0,0.04) !important;
}
.scl-row:hover, .scl-table tr:hover td {
  background: rgba(0,0,0,0.02) !important;
}
</style>
"""

content = content.replace('</head>', macc_hig_glass_css + '</head>')

with open(dest_path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'Successfully copied full functionality to {dest_path} and injected HIG Apple Liquid Glass styles + Tailwind.')
