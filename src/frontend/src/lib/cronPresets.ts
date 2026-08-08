/**
 * Cron helper for the schedule form: common presets, a human-readable
 * description, and a lightweight next-run calculator. Pure frontend, no deps.
 *
 * Cron format: standard 5-field crontab — minute hour day-of-month month day-of-week.
 */

export interface CronPreset {
  /** cron expression, 5 fields */
  cron: string
  /** localized label key (resolved via i18n at call site) */
  labelKey: string
}

/** Quick-pick presets shown as pills above the cron text field. */
export const CRON_PRESETS: CronPreset[] = [
  { cron: '*/30 * * * *', labelKey: 'schedules.cronEvery30Min' },
  { cron: '0 * * * *', labelKey: 'schedules.cronHourly' },
  { cron: '0 8 * * *', labelKey: 'schedules.cronDaily8' },
  { cron: '0 9 * * 1-5', labelKey: 'schedules.cronWeekday9' },
  { cron: '0 8 * * 1', labelKey: 'schedules.cronWeeklyMon' },
  { cron: '0 0 1 * *', labelKey: 'schedules.cronMonthly1st' },
]

export const COMMON_TIMEZONES = [
  'Asia/Shanghai',
  'Asia/Hong_Kong',
  'Asia/Tokyo',
  'UTC',
  'America/New_York',
  'America/Los_Angeles',
  'Europe/London',
]

/** Common Chinese timezone display labels. */
const TZ_LABELS: Record<string, string> = {
  'Asia/Shanghai': '中国标准时间 (UTC+8)',
  'Asia/Hong_Kong': '香港时间 (UTC+8)',
  'Asia/Tokyo': '日本标准时间 (UTC+9)',
  UTC: 'UTC',
  'America/New_York': '美东时间',
  'America/Los_Angeles': '美西时间',
  'Europe/London': '伦敦时间',
}

export function timezoneLabel(tz: string): string {
  return TZ_LABELS[tz] || tz
}

/**
 * Parse a single cron field (one of the 5 positions) into a matcher over the
 * field's range. Returns null on an unparseable expression. Supports:
 *   star           - full range
 *   star slash N   - step
 *   a-b            - range
 *   a,b,c          - list
 *   a-b slash N    - stepped range
 *   plain a        - single value
 */
function parseField(field: string, min: number, max: number): Set<number> | null {
  const out = new Set<number>()
  const parts = field.split(',')
  for (const part of parts) {
    const stepped = part.split('/')
    const step = stepped.length === 2 ? parseInt(stepped[1], 10) : 1
    if (stepped.length > 2 || Number.isNaN(step) || step < 1) return null
    let lo = min
    let hi = max
    const rangePart = stepped[0].trim()
    if (rangePart !== '*') {
      if (rangePart.includes('-')) {
        const [a, b] = rangePart.split('-')
        lo = parseInt(a, 10)
        hi = parseInt(b, 10)
      } else {
        lo = parseInt(rangePart, 10)
        hi = stepped.length === 2 ? max : lo // "5/2" means from 5 to max step 2
      }
    }
    if (Number.isNaN(lo) || Number.isNaN(hi) || lo < min || hi > max || lo > hi) {
      return null
    }
    for (let v = lo; v <= hi; v += step) out.add(v)
  }
  return out.size > 0 ? out : null
}

// Day-of-week: cron uses 0-6 (0 or 7 = Sunday). Normalize 7 -> 0.
function parseDow(field: string): Set<number> | null {
  const raw = parseField(field.replace(/7/g, '0'), 0, 6)
  return raw
}

interface CronFields {
  minute: Set<number>
  hour: Set<number>
  dom: Set<number>
  month: Set<number>
  dow: Set<number>
}

/**
 * Parse a 5-field cron expression into matchers. Returns null if invalid.
 * Note: like standard cron, when both dom and dow are restricted (not "*"),
 * the trigger fires when EITHER matches (OR semantics).
 */
export function parseCron(expr: string): CronFields | null {
  const fields = expr.trim().split(/\s+/)
  if (fields.length !== 5) return null
  const minute = parseField(fields[0], 0, 59)
  const hour = parseField(fields[1], 0, 23)
  const dom = parseField(fields[2], 1, 31)
  const month = parseField(fields[3], 1, 12)
  const dow = parseDow(fields[4])
  if (!minute || !hour || !dom || !month || !dow) return null
  return { minute, hour, dom, month, dow }
}

export function isValidCron(expr: string): boolean {
  return parseCron(expr) !== null
}

function pad2(n: number): string {
  return n < 10 ? `0${n}` : String(n)
}

/**
 * Compute the next `count` run times after `from`. Returns up to `count` ISO
 * strings, empty on parse error.
 *
 * Implementation note: the cursor advances in the browser's wall clock (Date
 * local getters) with coarse jumps — minute-level only when minutes/hour/day
 * already match, otherwise leaping to the next hour / day / month. This keeps
 * it O(matches) instead of O(minutes), so monthly expressions like "0 0 1 * *"
 * resolve instantly instead of looping hundreds of thousands of times. The
 * returned instants are then formatted into the selected timezone by the
 * caller; the cron fields themselves are interpreted in the user's local clock.
 * This is a best-effort preview — the backend (APScheduler) runs the schedule
 * in its real timezone.
 */
export function nextRunTimes(
  expr: string,
  count = 3,
  from: Date = new Date(),
  _tz = 'Asia/Shanghai',
): string[] {
  const c = parseCron(expr)
  if (!c) return []
  const domStar = fieldsAreStar(expr, 2)
  const dowStar = fieldsAreStar(expr, 4)
  const results: string[] = []
  const cur = new Date(from.getTime() + 60_000)
  cur.setSeconds(0, 0)
  let guard = 0
  while (results.length < count && guard < 100_000) {
    guard++
    // Month: jump to the 1st of the next matching month.
    if (!c.month.has(cur.getMonth() + 1)) {
      cur.setMonth(cur.getMonth() + 1, 1)
      cur.setHours(0, 0, 0, 0)
      continue
    }
    const domOk = c.dom.has(cur.getDate())
    const dowOk = c.dow.has(cur.getDay())
    const dayMatch = domStar && dowStar ? domOk : domStar ? dowOk : dowStar ? domOk : domOk || dowOk
    // Day: jump to the next day at 00:00.
    if (!dayMatch) {
      cur.setDate(cur.getDate() + 1)
      cur.setHours(0, 0, 0, 0)
      continue
    }
    // Hour: jump to the next hour, minutes zeroed.
    if (!c.hour.has(cur.getHours())) {
      cur.setHours(cur.getHours() + 1, 0, 0, 0)
      continue
    }
    // Minute: step one minute.
    if (!c.minute.has(cur.getMinutes())) {
      cur.setMinutes(cur.getMinutes() + 1, 0, 0)
      continue
    }
    results.push(new Date(cur.getTime()).toISOString())
    cur.setMinutes(cur.getMinutes() + 1, 0, 0)
  }
  return results
}

/** Localized Y/M/D H:M display in the given timezone for an ISO string. */
export function formatRunTime(iso: string, tz = 'Asia/Shanghai'): string {
  try {
    return new Intl.DateTimeFormat('zh-CN', {
      timeZone: tz,
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(new Date(iso))
  } catch {
    return iso
  }
}

/** Whether cron field at `index` is "*" (unrestricted). */
function fieldsAreStar(expr: string, index: number): boolean {
  const fields = expr.trim().split(/\s+/)
  return fields[index] === '*'
}

/**
 * Human-readable description of a cron expression (zh-CN). Falls back to the
 * raw expression with a hint when it can't be described simply.
 */
export function describeCron(expr: string): string {
  const c = parseCron(expr)
  if (!c) return expr
  const fields = expr.trim().split(/\s+/)
  const [fMin, fHour, fDom, , fDow] = fields
  const domStar = fDom === '*'
  const dowStar = fDow === '*'

  // Every N minutes: */N * * * *
  const minStep = fMin.match(/^\*\/(\d+)$/)
  if (minStep && fHour === '*' && domStar && dowStar) {
    return `每 ${minStep[1]} 分钟`
  }
  // Every N hours: 0 */N * * *
  const hourStep = fHour.match(/^\*\/(\d+)$/)
  if (hourStep && fMin === '0' && domStar && dowStar) {
    return `每 ${hourStep[1]} 小时`
  }
  // Specific time on specific weekdays, e.g. 0 9 * * 1-5
  if (!dowStar && domStar) {
    const dowLabel = describeDow(fDow)
    const time = describeTime(fMin, fHour)
    return `${dowLabel} ${time}`
  }
  // Specific time on specific days of month
  if (!domStar && dowStar) {
    return `每月 ${describeDom(fDom)} ${describeTime(fMin, fHour)}`
  }
  // Daily at a time
  if (domStar && dowStar) {
    return `每天 ${describeTime(fMin, fHour)}`
  }
  return `${expr}（自定义）`
}

function describeTime(fMin: string, fHour: string): string {
  const m = fMin === '*' ? '00' : fMin.padStart(2, '0')
  const h = fHour === '*' ? '00' : fHour.padStart(2, '0')
  return `${h}:${m}`
}

function describeDow(fDow: string): string {
  const map: Record<string, string> = {
    '1-5': '工作日',
    '0,6': '周末',
    '6,0': '周末',
    '1': '每周一',
    '2': '每周二',
    '3': '每周三',
    '4': '每周四',
    '5': '每周五',
    '6': '每周六',
    '0': '每周日',
  }
  return map[fDow] || `每周（${fDow}）`
}

function describeDom(fDom: string): string {
  if (fDom === '1') return '1 号'
  if (fDom.includes(',')) {
    return fDom.split(',').map((d) => `${d} 号`).join('、')
  }
  return `${fDom} 号`
}

export { pad2 }
