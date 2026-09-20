// @types/plotly.js types the 'plotly.js' module; we ship the smaller
// 'plotly.js-dist-min' bundle instead (docs/dashboard_ux_plan.md §2.1), which has
// no types package of its own. Its runtime export shape is identical, so alias it.
declare module 'plotly.js-dist-min' {
  import * as Plotly from 'plotly.js'
  export = Plotly
}
