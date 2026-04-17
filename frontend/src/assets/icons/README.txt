PWA icon assets for XF Internal Linker
=======================================

These PNG files are referenced in src/manifest.webmanifest.
Generate them from your logo at any size: 72x72, 96x96, 128x128, 144x144, 192x192, 384x384, 512x512.

Quick generation using ImageMagick (if you have it installed):
  convert logo.png -resize 192x192 icon-192x192.png

Or use https://realfavicongenerator.net/ which generates all sizes at once.

Until real icons are added the app still works — the manifest just won't show an icon
when users install it as a PWA ("Add to Home Screen").
