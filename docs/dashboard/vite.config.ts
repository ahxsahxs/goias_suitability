import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// GitHub Pages project page: https://ahxsahxs.github.io/goias_suitability/
// Derived from the git remote (github.com/ahxsahxs/goias_suitability), NOT from the
// local checkout directory name. Set unconditionally (not gated on prod mode) so the
// dev server also serves under this prefix and a hard-coded-root-path bug surfaces
// locally instead of on first deploy. Becomes '/' only on a custom domain or an
// org/user root page (docs/dashboard_ux_plan.md §2.5).
export default defineConfig({
  base: '/goias_suitability/',
  plugins: [vue()],
  // maplibre-gl resolves its worker with a *dynamic* `new URL(`./${name}`, import.meta.url)` —
  // the template-literal form defeats both Vite's dev pre-bundler and its static asset analysis
  // at build time, so in `npm run dev` the worker 404s (empty MIME type) unless it's excluded
  // from pre-bundling here, and in `vite build` it's silently omitted from dist/assets/ unless
  // main.ts explicitly imports it with `?url` and wires it in via `maplibregl.setWorkerUrl()`
  // (see src/main.ts). Don't drop either half of this fix.
  optimizeDeps: {
    exclude: ['maplibre-gl'],
  },
})
