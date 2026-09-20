import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'

/** A top-nav entry. `enabled: false` = declared in the IA (§3), not yet built. */
export interface NavItem {
  label: string
  /** Route path as it will exist once built; also the router path when enabled. */
  path: string
  /** Pipeline Part(s) this route serves, for the nav tooltip. */
  part: string
  enabled: boolean
}

/** Top nav, grouped exactly as docs/dashboard_ux_plan.md §3. */
export const navSections: ReadonlyArray<{ title: string; items: readonly NavItem[] }> = [
  {
    title: 'Feature engineering',
    items: [
      { label: 'Study Area & Data', path: '/study-area', part: 'Part 1', enabled: false },
      { label: 'Feature Themes', path: '/feature-themes', part: 'Parts 2–7d', enabled: false },
      { label: 'Feature Stack', path: '/feature-stack', part: 'Part 8', enabled: false },
    ],
  },
  {
    title: 'Modelling',
    items: [
      { label: 'Suitability', path: '/suitability', part: 'Part 9', enabled: true },
      { label: 'Zoning', path: '/zoning', part: 'Part 10', enabled: true },
    ],
  },
  {
    title: 'Forecast & validation',
    items: [
      { label: 'Climate Shift', path: '/cmip6', part: 'Part 11', enabled: false },
      { label: 'Realized Use', path: '/realized-use', part: 'Parts 12–13', enabled: false },
      { label: 'Validation', path: '/validation', part: 'Part 14', enabled: false },
    ],
  },
  {
    title: 'Explore',
    items: [
      { label: 'Municipal Explorer', path: '/municipal', part: 'cross-cutting', enabled: true },
      { label: 'About', path: '/about', part: '—', enabled: false },
    ],
  },
]

// Lazy-loaded per route: MapPanel (maplibre-gl) and PlotlyChart (plotly.js-dist-min)
// are heavy (~1.7 MB gzipped combined) and only Suitability/Zoning/Municipal need
// them — a static import would ship both to every route including Home's text.
const routes: RouteRecordRaw[] = [
  { path: '/', name: 'home', component: () => import('./views/HomeView.vue') },
  { path: '/suitability/:segment?', name: 'suitability', component: () => import('./views/SuitabilityView.vue') },
  { path: '/zoning', name: 'zoning', component: () => import('./views/ZoningView.vue') },
  { path: '/municipal/:name?', name: 'municipal', component: () => import('./views/MunicipalExplorerView.vue') },
  // Anything else (including a stale deep link into a not-yet-built v2 route) falls back to Home.
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export const router = createRouter({
  // Hash history: GitHub Pages cannot do SPA rewrites (§2.1).
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes,
})
