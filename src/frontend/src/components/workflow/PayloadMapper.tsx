import React from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/Button'
import type { InputFieldDef } from '@/lib/workflowSkillMeta'

interface Props {
  fields: InputFieldDef[]
  upstreamNodeIds: string[]
  payload: Record<string, unknown>
  onChange: (next: Record<string, unknown>) => void
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
  return typeof cur === 'string' ? cur : cur == null ? '' : String(cur)
}

export function PayloadMapper({ fields, upstreamNodeIds, payload, onChange }: Props) {
  const { t } = useTranslation()

  const quickVars: string[] = []
  for (const f of fields) {
    quickVars.push(`input.${f.key}`)
  }
  for (const id of upstreamNodeIds) {
    quickVars.push(`nodes.${id}.patent_ids`)
    quickVars.push(`nodes.${id}.sections`)
    quickVars.push(`nodes.${id}.result`)
  }
  quickVars.push('nodes.merge.sections')

  const scalarFields = [
    { key: 'command', label: t('workflows.payloadCommand') },
    { key: 'query', label: t('workflows.payloadQuery') },
    { key: 'industry', label: t('workflows.payloadIndustry') },
    { key: 'dimension', label: t('workflows.payloadDimension') },
    { key: 'filename', label: t('workflows.payloadFilename') },
    { key: 'title', label: t('workflows.payloadTitle') },
  ]

  return (
    <div className="space-y-2">
      <p className="text-xs text-gray-500 dark:text-gray-400">{t('workflows.payloadMapperHint')}</p>
      <div className="flex flex-wrap gap-1">
        {quickVars.map((v) => (
          <button
            key={v}
            type="button"
            title={`\${${v}}`}
            onClick={() => {
              const clip = `\${${v}}`
              void navigator.clipboard.writeText(clip)
            }}
            className="rounded border border-gray-200 px-1.5 py-0.5 font-mono text-[10px] text-primary-700 hover:bg-primary-50 dark:border-gray-700 dark:text-primary-300 dark:hover:bg-primary-950/40"
          >
            {v}
          </button>
        ))}
      </div>
      {scalarFields.map((field) => {
        const val = getNestedValue(payload, field.key)
        if (val === '' && !Object.prototype.hasOwnProperty.call(payload, field.key)) return null
        return (
          <label key={field.key} className="block text-xs">
            <span className="text-gray-600 dark:text-gray-300">{field.label}</span>
            <input
              className="mt-0.5 block w-full rounded border border-gray-300 bg-white px-2 py-1 font-mono text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
              value={val}
              onChange={(e) => onChange(setNestedValue(payload, field.key, e.target.value))}
            />
          </label>
        )
      })}
      <div>
        <div className="mb-1 flex items-center justify-between">
          <span className="text-xs text-gray-600 dark:text-gray-300">payload_template</span>
          <Button
            size="sm"
            variant="outline"
            onClick={() => onChange({ ...payload, patent_ids: '${nodes.search.patent_ids}' })}
          >
            {t('workflows.payloadApplySearchRef')}
          </Button>
        </div>
        <textarea
          className="h-36 w-full rounded border border-gray-300 bg-white px-2 py-1.5 font-mono text-xs dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
          value={JSON.stringify(payload || {}, null, 2)}
          onChange={(e) => {
            try {
              onChange(JSON.parse(e.target.value || '{}'))
            } catch {
              // ignore while typing invalid JSON
            }
          }}
        />
      </div>
    </div>
  )
}
