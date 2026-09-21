import * as maplibregl from 'maplibre-gl'
import { createPinia } from 'pinia'
import { Protocol } from 'pmtiles'
import { createApp } from 'vue'

import 'maplibre-gl/dist/maplibre-gl.css'
import './styles/tokens.css'
import './style.css'
import App from './App.vue'
import { router } from './router'
// maplibre-gl resolves its worker script at runtime via a *dynamic*
// `new URL(`./${name}`, import.meta.url)` — the template-literal form defeats
// Vite's static asset analysis, so the worker file is never emitted into
// dist/assets and the browser 404s on it (which GitHub Pages serves as an
// HTML 404 page, tripping the worker's strict MIME-type check). Importing it
// here with the `?url` suffix forces Vite to bundle it as a real, hashed
// asset and hand back its correct (base-path-aware) URL, which we then wire
// in explicitly via setWorkerUrl before any Map is constructed.
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'

maplibregl.setWorkerUrl(maplibreWorkerUrl)

// Registered exactly once, here (docs/dashboard_ux_plan.md §2.1) — every
// MapPanel.vue instance can then reference a `pmtiles://...` source URL.
const protocol = new Protocol()
maplibregl.addProtocol('pmtiles', protocol.tile)

createApp(App).use(createPinia()).use(router).mount('#app')
