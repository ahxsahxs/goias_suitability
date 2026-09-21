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
  // maplibre-gl resolves its worker as `new URL('./maplibre-gl-worker.mjs', import.meta.url)`.
  // Vite's dev dependency pre-bundler serves maplibre-gl from node_modules/.vite/deps/, which
  // doesn't include that sibling worker file, so the worker 404s (empty MIME type) in `npm run
  // dev` only — the production build handles this URL pattern correctly and is unaffected.
  // Excluding it from pre-bundling serves it straight from node_modules/maplibre-gl/dist/, where
  // the worker file actually exists alongside the entry point.
  optimizeDeps: {
    exclude: ['maplibre-gl'],
  },
})
