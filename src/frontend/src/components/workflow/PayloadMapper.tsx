import React, { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ChevronDown, ChevronRight } from 'lucide-react'

import type { InputFieldDef } from '@/lib/workflowSkillMeta'
import {
  patchPayloadForSkillParams,
  resolveSkillParamFields,
  type SkillParamFieldDef,
} from '@/lib/skillParamSchemas'

interface Props {
  skillName?: string
  fields: InputFieldDef[]
  upstreamNodeIds: string[]
  payload: Record<string, unknown>
  onChange: (next: Record<string, unknown>) => void
  workflowFields?: Record<string, any>
}

function setNestedValue(obj: Record<string, unknown>, path: string, value: string) {
  const next = { ...obj }
  const parts = path.split('.')
  let cur: Record<string, unknown> = next
  for (let i = 0; i < parts.length - 1; i += 1) {
    const key = parts[i]
    const child = { ...(cur[key] as Record<string, unknown> | undefined) }
    cur[key] = child
    cur = child
  }
  cur[parts[parts.length - 1]] = value
  return next
}

function getNestedValue(obj: Record<string, unknown>, path: string): string {
  let cur: unknown = obj
  for (const part of path.split('.')) {
    if (!cur || typeof cur !== 'object') return ''
    cur = (cur as Record<string, unknown>)[part]
  }
  if (cur == null) return ''
  return typeof cur === 'string' || typeof cur === 'number' ? String(cur) : JSON.stringify(cur)
}

function isVariableRef(value: string): boolean {
  return /^\$\{[^}]+\}$/.test(value.trim())
}

function ParamField({
  field,
  value,
  bindOptions,
  onChange,
}: {
  field: SkillParamFieldDef
  value: string
  bindOptions: string[]
  onChange: (value: string) => void
}) {
  const { t } = useTranslation()
  const [showBind, setShowBind] = useState(isVariableRef(value))

  return (
    <label className="block text-xs">
      <span className="font-medium text-gray-700 dark:text-gray-200">{field.label}</span>
      {field.hint ? (
        <span className="mt-0.5 block text-[10px] leading-snug text-gray-500 dark:text-gray-400">{field.hint}</span>
      ) : null}
      <div className="mt-1 space-y-1">
        {field.type === 'select' ? (
          <select
            className="block w-full rounded border border-gray-300 bg-white px-2 py-1 text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
            value={value}
            onChange={(e) => onChange(e.target.value)}
          >
            <option value="">{t('workflows.paramSelectPlaceholder')}</option>
            {(field.options || []).map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        ) : (
          <input
            type={field.type === 'number' ? 'number' : 'text'}
            className="block w-full rounded border border-gray-300 bg-white px-2 py-1 font-mono text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
            value={value}
            placeholder={field.placeholder}
            onChange={(e) => onChange(e.target.value)}
          />
        )}
        <div className="flex items-center gap-1">
          <button
            type="button"
            className="inline-flex items-center gap-0.5 text-[10px] text-gray-500 hover:text-primary-600 dark:text-gray-400"
            onClick={() => setShowBind((v) => !v)}
          >
            {showBind ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            {t('workflows.paramBindVariable')}
          </button>
        </div>
        {showBind ? (
          <div className="flex flex-wrap gap-1">
            {bindOptions.map((v) => (
              <button
                key={v}
                type="button"
                title={`\${${v}}`}
                onClick={() => onChange(`\${${v}}`)}
                className="rounded border border-gray-200 px-1.5 py-0.5 font-mono text-[10px] text-primary-700 hover:bg-primary-50 dark:border-gray-700 dark:text-primary-300 dark:hover:bg-primary-950/40"
              >
                {v}
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </label>
  )
}

export function PayloadMapper({ skillName = '', fields, upstreamNodeIds, payload, onChange, workflowFields }: Props) {
  const { t } = useTranslation()
  const [advancedOpen, setAdvancedOpen] = useState(false)

  const bindOptions = useMemo(() => {
    const vars: string[] = []
    for (const f of fields) vars.push(`input.${f.key}`)
    for (const id of upstreamNodeIds) {
      vars.push(`nodes.${id}.patent_ids`)
      vars.push(`nodes.${id}.sections`)
      vars.push(`nodes.${id}.charts`)
      vars.push(`nodes.${id}.result`)
    }
    vars.push('nodes.merge.sections')
    return vars
  }, [fields, upstreamNodeIds])

  const paramFields = useMemo(
    () => resolveSkillParamFields(skillName, payload, t, workflowFields),
    [skillName, payload, t, workflowFields],
  )

  const extraKeys = useMemo(() => {
    const known = new Set(paramFields.map((f) => f.key))
    return Object.keys(payload || {}).filter((k) => !known.has(k))
  }, [paramFields, payload])

  const updateField = (key: string, value: string) => {
    let next = setNestedValue(payload, key, value)
    next = patchPayloadForSkillParams(skillName, next, key)
    onChange(next)
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-500 dark:text-gray-400">{t('workflows.payloadMapperHint')}</p>

      <div className="space-y-2.5 rounded-md border border-gray-200 bg-gray-50/80 p-2 dark:border-gray-700 dark:bg-gray-900/40">
        {paramFields.map((field) => (
          <ParamField
            key={field.key}
            field={field}
            value={getNestedValue(payload, field.key)}
            bindOptions={bindOptions}
            onChange={(value) => updateField(field.key, value)}
          />
        ))}
        {extraKeys.length > 0 ? (
          <p className="text-[10px] text-gray-500 dark:text-gray-400">
            {t('workflows.paramExtraKeys', { keys: extraKeys.join(', ') })}
          </p>
        ) : null}
      </div>

      <div>
        <button
          type="button"
          className="inline-flex items-center gap-1 text-xs text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-200"
          onClick={() => setAdvancedOpen((v) => !v)}
        >
          {advancedOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          {t('workflows.payloadAdvancedJson')}
        </button>
        {advancedOpen ? (
          <textarea
            className="mt-1.5 h-32 w-full rounded border border-gray-300 bg-white px-2 py-1.5 font-mono text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
            value={JSON.stringify(payload || {}, null, 2)}
            onChange={(e) => {
              try {
                onChange(JSON.parse(e.target.value || '{}'))
              } catch {
                // ignore while typing invalid JSON
              }
            }}
          />
        ) : null}
      </div>
    </div>
  )
}
