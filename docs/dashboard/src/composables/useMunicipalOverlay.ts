import * as maplibregl from 'maplibre-gl'
import type { Map as MapLibreMap, MapGeoJSONFeature, MapLayerMouseEvent } from 'maplibre-gl'
import { onUnmounted, watch, type Ref } from 'vue'
import { dataUrl } from './useJson'

export const MUNI_SOURCE_ID = 'muni-overlay'
export const MUNI_FILL_LAYER_ID = 'muni-overlay-fill'
export const MUNI_LINE_LAYER_ID = 'muni-overlay-line'

const LINE_DEFAULT = 'rgba(27, 31, 26, 0.35)'
const LINE_HIGHLIGHT = '#3f7d3a'

/**
 * Re-assert the municipal overlay's stacking position. `map.addLayer(layer)`
 * with no `beforeId` always appends on top, so any raster/choropleth layer
 * (re)added after this overlay would otherwise bury it — callers that add
 * their own layers (usePmtilesLayer's addNow, MapPanel's addChoropleth/
 * addOutline) call this afterward to keep the boundary + hover layer on top.
 */
export function promoteMunicipalOverlay(m: MapLibreMap): void {
  if (m.getLayer(MUNI_FILL_LAYER_ID)) m.moveLayer(MUNI_FILL_LAYER_ID)
  if (m.getLayer(MUNI_LINE_LAYER_ID)) m.moveLayer(MUNI_LINE_LAYER_ID)
}

/**
 * Adds a municipal-boundary overlay to every map: an invisible fill layer for
 * whole-polygon hover hit-testing (MapLibre only hit-tests `line` layers within
 * a few px of the stroke, not the enclosed area) plus a thin visible boundary
 * line. Hovering shows a name-only popup balloon; `highlightName`, when set,
 * draws that one municipality's boundary thicker and in the accent color.
 */
export function useMunicipalOverlay(map: Ref<MapLibreMap | null>, highlightName?: Ref<string | null>): void {
  let popup: maplibregl.Popup | null = null
  let hoveredName: string | null = null

  function removePopup(): void {
    popup?.remove()
    popup = null
    hoveredName = null
  }

  function onMouseMove(e: MapLayerMouseEvent): void {
    const m = map.value
    if (!m) return
    const feature = e.features?.[0] as MapGeoJSONFeature | undefined
    const name = (feature?.properties?.NM_MUN as string | undefined) ?? null
    m.getCanvas().style.cursor = name ? 'pointer' : ''
    if (!name) {
      removePopup()
      return
    }
    if (!popup) {
      popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 8 })
    }
    if (name !== hoveredName) {
      hoveredName = name
      popup.setText(name)
    }
    popup.setLngLat(e.lngLat)
    if (!popup.isOpen()) popup.addTo(m)
  }

  function onMouseLeave(): void {
    const m = map.value
    if (m) m.getCanvas().style.cursor = ''
    removePopup()
  }

  function applyHighlight(): void {
    const m = map.value
    if (!m || !m.getLayer(MUNI_LINE_LAYER_ID)) return
    const name = highlightName?.value ?? null
    if (!name) {
      m.setPaintProperty(MUNI_LINE_LAYER_ID, 'line-color', LINE_DEFAULT)
      m.setPaintProperty(MUNI_LINE_LAYER_ID, 'line-width', 0.6)
      return
    }
    m.setPaintProperty(MUNI_LINE_LAYER_ID, 'line-color', ['match', ['get', 'NM_MUN'], name, LINE_HIGHLIGHT, LINE_DEFAULT])
    m.setPaintProperty(MUNI_LINE_LAYER_ID, 'line-width', ['match', ['get', 'NM_MUN'], name, 2.2, 0.6])
  }

  function remove(): void {
    const m = map.value
    removePopup()
    if (!m || !m.getStyle()) return
    if (m.getLayer(MUNI_FILL_LAYER_ID)) m.removeLayer(MUNI_FILL_LAYER_ID)
    if (m.getLayer(MUNI_LINE_LAYER_ID)) m.removeLayer(MUNI_LINE_LAYER_ID)
    if (m.getSource(MUNI_SOURCE_ID)) m.removeSource(MUNI_SOURCE_ID)
  }

  function addNow(m: MapLibreMap): void {
    remove()
    m.addSource(MUNI_SOURCE_ID, { type: 'geojson', data: dataUrl('geojson/municipios.geojson') })
    m.addLayer({
      id: MUNI_FILL_LAYER_ID,
      type: 'fill',
      source: MUNI_SOURCE_ID,
      paint: { 'fill-color': '#000000', 'fill-opacity': 0 },
    })
    m.addLayer({
      id: MUNI_LINE_LAYER_ID,
      type: 'line',
      source: MUNI_SOURCE_ID,
      paint: { 'line-color': LINE_DEFAULT, 'line-width': 0.6 },
    })
    m.on('mousemove', MUNI_FILL_LAYER_ID, onMouseMove)
    m.on('mouseleave', MUNI_FILL_LAYER_ID, onMouseLeave)
    applyHighlight()
  }

  function add(): void {
    const m = map.value
    if (!m) return
    if (m.isStyleLoaded()) {
      addNow(m)
    } else {
      m.once('load', () => addNow(m))
    }
  }

  watch(map, add, { immediate: true })
  if (highlightName) watch(highlightName, applyHighlight)

  onUnmounted(remove)
}
