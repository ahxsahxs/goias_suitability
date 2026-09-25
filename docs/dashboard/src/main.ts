import * as maplibregl from 'maplibre-gl'
import { createPinia } from 'pinia'
import { Protocol } from 'pmtiles'
import { createApp } from 'vue'

import 'maplibre-gl/dist/maplibre-gl.css'
import './styles/tokens.css'
import './style.css'
import App from './App.vue'
import { router } from './router'
// maplibre-gl resolves its worker via a dynamic `new URL(`./${name}`,
// import.meta.url)` that Vite can't see, so the worker is never emitted and
// the browser 404s on it (Pages serves an HTML 404 → MIME-type error).
// `?worker&url` makes Vite bundle the worker as its own entry — inlining its
// `./maplibre-gl-shared.mjs` import, which a plain `?url` copy would 404 on —
// and hand back its hashed, base-aware URL. See vite.config.ts.
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'

maplibregl.setWorkerUrl(maplibreWorkerUrl)

// Registered exactly once, here (docs/dashboard_ux_plan.md §2.1) — every
// MapPanel.vue instance can then reference a `pmtiles://...` source URL.
const protocol = new Protocol()
maplibregl.addProtocol('pmtiles', protocol.tile)

// A tab opened before a redeploy still holds the old index-*.js, whose lazy
// route chunks no longer exist (Pages serves its HTML 404 → MIME error).
// Reload once to pick up the new build; the timestamp guard avoids a loop if
// a chunk is genuinely missing from the current deploy.
window.addEventListener('vite:preloadError', (event) => {
  const key = 'chunk-reload-at'
  const last = Number(sessionStorage.getItem(key) ?? 0)
  if (Date.now() - last < 10_000) return
  event.preventDefault()
  sessionStorage.setItem(key, String(Date.now()))
  window.location.reload()
})

createApp(App).use(createPinia()).use(router).mount('#app')
