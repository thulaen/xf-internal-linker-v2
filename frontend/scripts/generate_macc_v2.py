import os

src_path = r'c:\Users\goldm\Dev\xf-internal-linker-v2\frontend\signal-control-light-prototype.html'
dest_path = r'c:\Users\goldm\Dev\xf-internal-linker-v2\frontend\macc-prototype.html'

with open(src_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Inject Tailwind
tailwind_script = '<script src="https://cdn.tailwindcss.com"></script>\n<title>MACC Dashboard Beta (HIG)</title>'
content = content.replace('<title>Signal Control Light — Clickable Prototype</title>', tailwind_script)

macc_hig_css = """
<style id="macc-hig-overrides">
/* APPLE HIG MACOS DESKTOP OVERRIDES */
:root {
  /* Apple HIG Window and Content Surfaces */
  --canvas: #ECECEB !important; 
  --canvas-deep: #E1E1DF !important; 
  --panel: #FFFFFF !important; 
  --raised: #FFFFFF !important;
  --sunken: #F5F5F5 !important;
  
  /* Subtle borders */
  --border: #D1D1D6 !important; 
  --border-strong: #C7C7CC !important;
  --hairline: #E5E5EA !important;

  /* Typography */
  --text: #000000 !important; 
  --text-2: #3C3C43 !important; 
  --text-3: #3C3C4399 !important; 

  /* Apple Accent Color (macOS Blue) */
  --coral: #007AFF !important; 
  --coral-strong: #0066CC !important;
  --coral-tint: #E5F1FF !important;
  
  /* Signal Colors */
  --em: #34C759 !important; 
  --em-tint: #EAF9EE !important;
  --am: #FF9500 !important; 
  --am-tint: #FFF4E5 !important;
  --red: #FF3B30 !important; 
  --red-tint: #FFEBEA !important;
}

body {
  background-color: var(--canvas) !important;
  background-image: none !important;
}

/* Remove all of the heavy gradient stuff and replace with standard solid background */
.scl-view {
  background: var(--canvas) !important;
  background-image: none !important;
}

/* Translucency restricted to Topbar and Sidebar */
.scl-topbar {
  background: rgba(246, 246, 246, 0.8) !important;
  backdrop-filter: saturate(180%) blur(20px) !important;
  -webkit-backdrop-filter: saturate(180%) blur(20px) !important;
  border-bottom: 1px solid rgba(0, 0, 0, 0.1) !important;
  box-shadow: none !important;
}
.scl-rail {
  background: rgba(236, 236, 235, 0.6) !important;
  backdrop-filter: blur(30px) !important;
  -webkit-backdrop-filter: blur(30px) !important;
  border-right: 1px solid rgba(0, 0, 0, 0.05) !important;
}

/* Flatten Cards and Adjust Shadows */
.scl-panel, .scl-card, .scl-kpi, .scl-tabs, .vi-island, .scl-sum {
  background: var(--panel) !important;
  border: 1px solid var(--border) !important;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
  border-radius: 10px !important;
  backdrop-filter: none !important;
  -webkit-backdrop-filter: none !important;
}

/* Fix Buttons and Interactions */
.scl-btn, .tb-prop {
  background: #FFFFFF !important;
  border: 1px solid var(--border) !important;
  box-shadow: 0 1px 1px rgba(0,0,0,0.02) !important;
  color: var(--text) !important;
}
.scl-btn.primary {
  background: var(--coral) !important;
  color: #fff !important;
  border: none !important;
  box-shadow: 0 1px 1px rgba(0,0,0,0.1) !important;
}
.scl-btn:hover, .tb-prop:hover {
  background: var(--sunken) !important;
}
.scl-btn.primary:hover {
  background: var(--coral-strong) !important;
}

/* Search bar styling */
.tb-search {
  background: var(--panel) !important;
  border: 1px solid var(--border) !important;
  color: var(--text) !important;
}

/* Active Nav Selection */
.scl-nav.active {
  background: var(--coral) !important;
  color: #fff !important;
  border-color: transparent !important;
}
.scl-nav.active svg, .scl-nav.active .nav-ic {
  color: #fff !important;
  background: transparent !important;
}
.scl-nav:hover:not(.active) {
  background: rgba(0, 0, 0, 0.05) !important;
}
</style>
"""

content = content.replace('</head>', macc_hig_css + '</head>')

with open(dest_path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'Successfully copied full functionality to {dest_path} and injected HIG Apple styles + Tailwind.')
