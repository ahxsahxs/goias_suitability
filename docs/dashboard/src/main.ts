import * as maplibregl from 'maplibre-gl'
import { createPinia } from 'pinia'
import { Protocol } from 'pmtiles'
import { createApp } from 'vue'

import 'maplibre-gl/dist/maplibre-gl.css'
import './styles/tokens.css'
import './style.css'
import App from './App.vue'
import { router } from './router'

// Registered exactly once, here (docs/dashboard_ux_plan.md §2.1) — every
// MapPanel.vue instance can then reference a `pmtiles://...` source URL.
const protocol = new Protocol()
maplibregl.addProtocol('pmtiles', protocol.tile)

createApp(App).use(createPinia()).use(router).mount('#app')
