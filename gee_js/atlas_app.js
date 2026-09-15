/**** ==========================================================================
 * Goiás + Distrito Federal Agro-Market Suitability Atlas — Earth Engine App
 * ---------------------------------------------------------------------------
 * Interactive viewer for the built assets: present-day suitability (7 segments),
 * FAO classes, agro-environmental zones, realized land use, potential-vs-realized
 * under-utilization, and the CMIP6 mid-century shift. Click the map to read a
 * municipality's aggregated values.
 *
 * TO PUBLISH (manual, one-click — not available via the Python API):
 *   1. Open https://code.earthengine.google.com and paste this script.
 *   2. Confirm the assets under `projects/probformer/assets/goias/` are shared
 *      publicly (or with your intended audience).
 *   3. Click  Apps  ▸  NEW APP  ▸  publish from this script  →  get the App URL.
 * ======================================================================== ****/

var ROOT = 'projects/probformer/assets/goias/';
var aoi        = ee.FeatureCollection(ROOT + 'aoi');
var suit       = ee.Image(ROOT + 'suit_present');
var zones      = ee.Image(ROOT + 'zones_present');
var realized   = ee.Image(ROOT + 'feat_realized');
var underused  = ee.Image(ROOT + 'realized_vs_potential');
var muni       = ee.FeatureCollection(ROOT + 'municipal_godf');

var SEGS = ['soybean', 'sugarcane', 'other_crops', 'pisciculture',
            'cattle', 'conservation', 'solar'];

// palettes (mirror tools/make_figures.py + the notebooks)
var PAL_SUIT = ['#d7191c', '#fdae61', '#ffffbf', '#a6d96a', '#1a9641'];
var PAL_FAO  = ['#d7191c', '#fdae61', '#a6d96a', '#1a9641'];
var PAL_ZONE = ['#1f77b4', '#ff7f0e', '#2ca02c'];
var PAL_ROLE = ['#eeeeee', '#ffd400', '#7b3294', '#d95f0e', '#2c7fb8', '#addd8e', '#006837'];
var PAL_DIV  = ['#b2182b', '#f7f7f7', '#2166ac'];

// ---- build the selectable layer catalog ----------------------------------
var catalog = {};   // display name -> {img: ee.Image, vis: {}}
SEGS.forEach(function (s) {
  catalog['Suitability — ' + s] = {
    img: suit.select('suit_' + s), vis: {min: 0, max: 1, palette: PAL_SUIT}};
  catalog['FAO class — ' + s] = {
    img: suit.select('class_' + s), vis: {min: 0, max: 3, palette: PAL_FAO}};
});
catalog['Agro-environmental zones'] = {img: zones, vis: {min: 0, max: 2, palette: PAL_ZONE}};
catalog['Realized land use (role)'] = {img: realized.select('rl_role'),
                                       vis: {min: 0, max: 6, palette: PAL_ROLE}};
['soybean', 'sugarcane', 'other_crops', 'pisciculture'].forEach(function (s) {
  catalog['Under-utilization — ' + s] = {
    img: underused.select('underused_' + s), vis: {min: 0, max: 1, palette: ['#f7f7f7', '#d7301f']}};
});
// CMIP6 shift ΔS per scenario × window
['ssp245', 'ssp585'].forEach(function (ssp) {
  ['2031_2050', '2051_2070'].forEach(function (win) {
    var dl = ee.Image(ROOT + 'delta_' + ssp + '_' + win);
    ['soybean', 'sugarcane', 'other_crops'].forEach(function (s) {
      catalog['ΔS ' + s + ' — ' + ssp + ' ' + win] = {
        img: dl.select('delta_' + s), vis: {min: -0.15, max: 0.15, palette: PAL_DIV}};
    });
  });
});

// ---- map + UI -------------------------------------------------------------
Map.centerObject(aoi, 7);
Map.setOptions('HYBRID');

var names = Object.keys(catalog);
var current = 'Suitability — soybean';

function draw(name) {
  Map.layers().reset();
  var entry = catalog[name];
  Map.addLayer(entry.img.clip(aoi), entry.vis, name);
  Map.addLayer(ee.Image().paint(aoi, 1, 1), {palette: ['000000']}, 'AOI', true);
  current = name;
}

var select = ui.Select({items: names, value: current, onChange: draw, style: {width: '320px'}});

var title = ui.Label('Goiás + DF Agro-Market Suitability Atlas',
                     {fontWeight: 'bold', fontSize: '18px', margin: '4px 0'});
var subtitle = ui.Label('Present suitability · zoning · realized use · CMIP6 shift (250 m)',
                        {fontSize: '12px', color: '#555', margin: '0 0 8px 0'});

// click -> municipal values panel
var infoPanel = ui.Panel({style: {margin: '8px 0'}});
infoPanel.add(ui.Label('Click a municipality to read its values.', {fontSize: '12px'}));
Map.onClick(function (coords) {
  var pt = ee.Geometry.Point([coords.lon, coords.lat]);
  var f = muni.filterBounds(pt).first();
  infoPanel.clear();
  f.evaluate(function (feat) {
    if (!feat) { infoPanel.add(ui.Label('Outside GO + DF.', {fontSize: '12px'})); return; }
    var p = feat.properties;
    infoPanel.add(ui.Label(p.ADM2_NAME + ' (' + p.ADM1_NAME + ')',
                           {fontWeight: 'bold', fontSize: '13px'}));
    SEGS.forEach(function (s) {
      if (p['suit_' + s] !== undefined) {
        infoPanel.add(ui.Label('  suit ' + s + ': ' + p['suit_' + s].toFixed(3), {fontSize: '11px'}));
      }
    });
    if (p.delta_other_crops !== undefined) {
      infoPanel.add(ui.Label('  Δ other_crops (ssp585 2051-70): ' + p.delta_other_crops.toFixed(3),
                             {fontSize: '11px', color: '#b2182b'}));
    }
  });
});

var panel = ui.Panel({style: {width: '360px', padding: '8px'}});
panel.add(title).add(subtitle)
     .add(ui.Label('Layer', {fontWeight: 'bold', fontSize: '12px'})).add(select)
     .add(ui.Label('Municipal query', {fontWeight: 'bold', fontSize: '12px', margin: '10px 0 0 0'}))
     .add(infoPanel);
ui.root.insert(0, panel);

draw(current);
