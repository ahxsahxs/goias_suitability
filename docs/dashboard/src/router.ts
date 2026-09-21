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
    title: 'Engenharia de atributos',
    items: [
      { label: 'Área de estudo e dados', path: '/study-area', part: 'Parte 1', enabled: true },
      { label: 'Temas de atributos', path: '/feature-themes', part: 'Partes 2–7d', enabled: true },
      { label: 'Pilha de atributos', path: '/feature-stack', part: 'Parte 8', enabled: true },
    ],
  },
  {
    title: 'Modelagem',
    items: [
      { label: 'Aptidão', path: '/suitability', part: 'Parte 9', enabled: true },
      { label: 'Zoneamento', path: '/zoning', part: 'Parte 10', enabled: true },
    ],
  },
  {
    title: 'Projeção e validação',
    items: [
      { label: 'Mudança climática', path: '/cmip6', part: 'Parte 11', enabled: true },
      { label: 'Uso realizado', path: '/realized-use', part: 'Partes 12–13', enabled: true },
      { label: 'Validação', path: '/validation', part: 'Parte 14', enabled: true },
    ],
  },
  {
    title: 'Explorar',
    items: [
      { label: 'Explorador municipal', path: '/municipal', part: 'transversal', enabled: true },
      { label: 'Sobre', path: '/about', part: '—', enabled: true },
    ],
  },
]

// Lazy-loaded per route: MapPanel (maplibre-gl) and PlotlyChart (plotly.js-dist-min)
// are heavy (~1.7 MB gzipped combined) — a static import would ship both to every
// route including text-only ones like About.
const routes: RouteRecordRaw[] = [
  { path: '/', name: 'home', component: () => import('./views/HomeView.vue') },
  { path: '/study-area', name: 'study-area', component: () => import('./views/StudyAreaView.vue') },
  {
    path: '/feature-themes/:theme?',
    name: 'feature-themes',
    component: () => import('./views/FeatureThemesView.vue'),
  },
  { path: '/feature-stack', name: 'feature-stack', component: () => import('./views/FeatureStackView.vue') },
  { path: '/suitability/:segment?', name: 'suitability', component: () => import('./views/SuitabilityView.vue') },
  { path: '/zoning', name: 'zoning', component: () => import('./views/ZoningView.vue') },
  {
    path: '/cmip6/:ssp?/:window?/:segment?',
    name: 'cmip6',
    component: () => import('./views/Cmip6View.vue'),
  },
  {
    path: '/realized-use/:crop?',
    name: 'realized-use',
    component: () => import('./views/RealizedUseView.vue'),
  },
  { path: '/validation', name: 'validation', component: () => import('./views/ValidationView.vue') },
  { path: '/municipal/:name?', name: 'municipal', component: () => import('./views/MunicipalExplorerView.vue') },
  { path: '/about', name: 'about', component: () => import('./views/AboutView.vue') },
  // Anything else falls back to Home.
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

export const router = createRouter({
  // Hash history: GitHub Pages cannot do SPA rewrites (§2.1).
  history: createWebHashHistory(import.meta.env.BASE_URL),
  routes,
})
