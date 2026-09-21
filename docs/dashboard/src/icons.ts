/** Minimal inline-SVG glyphs for the sidebar nav (no icon-library dependency —
 * kept in step with the project's zero-framework approach). Each value is the
 * inner markup of a 24x24 `stroke="currentColor"` SVG, keyed by the nav item's
 * route path (see router.ts's navSections) plus 'home' and 'toggle'. */
export const NAV_ICONS: Record<string, string> = {
  home: '<path d="M3 11.5 12 4l9 7.5"/><path d="M5 10v9a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1v-9"/>',
  '/study-area': '<path d="M9 3 3 6v15l6-3 6 3 6-3V3l-6 3-6-3z"/><path d="M9 3v15"/><path d="M15 6v15"/>',
  '/feature-themes':
    '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  '/feature-stack': '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 13 9 5 9-5"/><path d="m3 18 9 5 9-5"/>',
  '/suitability': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r=".6" fill="currentColor"/>',
  '/zoning': '<path d="M3 3h8v8H3z"/><path d="M13 3h8v5h-8z"/><path d="M13 10h8v11h-8z"/><path d="M3 13h8v8H3z"/>',
  '/cmip6': '<path d="M6.5 19a4.5 4.5 0 1 1 .5-8.98A6 6 0 0 1 18 12.06 4 4 0 0 1 17.5 19H6.5Z"/>',
  '/realized-use': '<path d="M5 21c7 0 13-6 13-13V5h-3C8 5 5 11 5 18v3Z"/>',
  '/validation': '<circle cx="12" cy="12" r="9"/><path d="m8.5 12.5 2.5 2.5 5-5"/>',
  '/municipal': '<path d="M12 21s7-6.5 7-11.5A7 7 0 0 0 5 9.5C5 14.5 12 21 12 21Z"/><circle cx="12" cy="9.5" r="2.5"/>',
  '/about': '<circle cx="12" cy="12" r="9"/><path d="M12 8h.01"/><path d="M11 12h1v5h1"/>',
  toggle: '<path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h16"/>',
}
