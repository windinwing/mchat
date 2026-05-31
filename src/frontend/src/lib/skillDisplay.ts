/** Resolve skill display text from config.i18n / config.display_name by UI locale. */

type SkillLike = {
  name: string
  description?: string | null
  config?: Record<string, unknown> | null
}

function uiLang(locale: string): 'zh' | 'en' {
  return locale.startsWith('zh') ? 'zh' : 'en'
}

function pickLocalized(
  map: Record<string, string> | undefined,
  lang: 'zh' | 'en',
  fallback: string,
): string {
  if (!map) return fallback
  return map[lang] || map.en || map.zh || fallback
}

/** Display title for lists / workflow palette (falls back to skill.name). */
export function getSkillDisplayName(skill: SkillLike, locale: string): string {
  const lang = uiLang(locale)
  const config = skill.config || {}
  const i18n = config.i18n as Record<string, { title?: string; description?: string }> | undefined
  if (i18n?.[lang]?.title) return String(i18n[lang].title)
  const displayName = config.display_name
  if (displayName && typeof displayName === 'object' && !Array.isArray(displayName)) {
    return pickLocalized(displayName as Record<string, string>, lang, skill.name)
  }
  if (typeof displayName === 'string' && displayName.trim()) return displayName.trim()
  return skill.name
}

/** Description for tooltips / palette subtitle. */
export function getSkillDisplayDescription(skill: SkillLike, locale: string): string {
  const lang = uiLang(locale)
  const config = skill.config || {}
  const i18n = config.i18n as Record<string, { title?: string; description?: string }> | undefined
  if (i18n?.[lang]?.description) return String(i18n[lang].description)
  const i18nDesc = config.i18n_description as Record<string, string> | undefined
  if (i18nDesc?.[lang]) return i18nDesc[lang]
  return skill.description || ''
}
