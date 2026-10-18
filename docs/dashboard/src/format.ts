/**
 * pt-BR number formatting, following the thesis' conventions (tools/gen_thesis_tables.num):
 * decimal comma, dot thousands separator, a true minus sign (U+2212), an explicit "+"
 * on signed quantities (ΔS, correlations), en dash in ranges, "km²".
 *
 * Every number the dashboard prints goes through here — never `toFixed`, never
 * `toLocaleString()` without a locale (that follows the VIEWER's locale, which is how
 * the atlas used to print "0.864" next to "45,4%").
 *
 * Decimal places used across views, matching the thesis tables:
 *   ΔS territorial mean 4 · ΔS by zone 3 · suitability 2 · AUC/Boyce/κ 3 ·
 *   Spearman 2 · percentages 1.
 */

const formatters = new Map<number, Intl.NumberFormat>()
function nf(digits: number): Intl.NumberFormat {
  let f = formatters.get(digits)
  if (!f) {
    f = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: digits, maximumFractionDigits: digits })
    formatters.set(digits, f)
  }
  return f
}

const MINUS = '−'
const DASH = '—'

function valid(x: number | null | undefined): x is number {
  return typeof x === 'number' && Number.isFinite(x)
}

/** `signed`: prefix "+" on positive values (ΔS, ρ). A value that rounds to zero gets no sign. */
export function fmtNum(x: number | null | undefined, digits = 2, signed = false): string {
  if (!valid(x)) return DASH
  const body = nf(digits).format(Math.abs(x))
  if (Number(body.replace(/\./g, '').replace(',', '.')) === 0) return body
  if (x < 0) return MINUS + body
  return signed ? `+${body}` : body
}

/** Signed number: ΔS, correlation coefficients. */
export const fmtSigned = (x: number | null | undefined, digits = 2): string => fmtNum(x, digits, true)

/** `x` already in percent (e.g. 45.4). */
export const fmtPct = (x: number | null | undefined, digits = 1): string =>
  valid(x) ? `${fmtNum(x, digits)}%` : DASH

/** `x` a fraction in [0, 1]. */
export const fmtShare = (x: number | null | undefined, digits = 1): string =>
  valid(x) ? fmtPct(100 * x, digits) : DASH

/** Percentage points, signed (e.g. "−15,8 p.p."). */
export const fmtPp = (x: number | null | undefined, digits = 1): string =>
  valid(x) ? `${fmtSigned(x, digits)} p.p.` : DASH

export const fmtInt = (x: number | null | undefined): string => (valid(x) ? nf(0).format(Math.round(x)) : DASH)

export const fmtKm2 = (x: number | null | undefined): string => (valid(x) ? `${fmtInt(x)} km²` : DASH)

export const fmtRange = (a: number | string, b: number | string): string => `${a}–${b}`

/** p-value as the thesis prints it. */
export function fmtP(p: number | null | undefined): string {
  if (!valid(p)) return DASH
  if (p < 0.001) return 'p < 0,001'
  if (p < 0.01) return `p = ${fmtNum(p, 3)}`
  return `p = ${fmtNum(p, 2)}`
}
