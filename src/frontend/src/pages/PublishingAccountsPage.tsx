import { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation, useNavigate } from 'react-router-dom'
import { Plus, Trash2, CheckCircle, XCircle, KeyRound, Pencil, RefreshCw, Send } from 'lucide-react'
import { getPublishingAccountTypes } from '@/i18n/publishingAccountTypes'
import api from '@/lib/api'
import { Card, CardContent } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Switch } from '@/components/ui/Switch'
import { Badge } from '@/components/ui/Badge'
import { Dialog } from '@/components/ui/Dialog'
import { toast } from '@/components/ui/Toast'
import { Spinner } from '@/components/ui/Spinner'

interface Account {
  id: string
  name: string
  channel_type: string
  config: Record<string, any> | null
  enabled: boolean
  is_connected: boolean
  created_at: string
  updated_at: string
}

/** Publisher channel types (subset of Channel table). Inbound types filtered out. */
const PUBLISHER_TYPES = [
  'feishu', 'dingtalk', 'wecom', 'wechat_mp', 'slack', 'discord',
  'telegram_channel', 'twitter_x', 'facebook', 'linkedin', 'playwright_client',
]

export function PublishingAccountsPage() {
  const { t } = useTranslation()
  const location = useLocation()
  const navigate = useNavigate()
  // Portal (user-facing) uses /portal/publishing-accounts (plan-gated, no
  // CHANNELS_WRITE needed). Admin uses /channels.
  const isPortal = location.pathname.startsWith('/portal')
  const API_BASE = isPortal ? '/portal/publishing-accounts' : '/channels'
  const types = useMemo(() => getPublishingAccountTypes(t), [t])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [loading, setLoading] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<Account | null>(null)
  // form state
  const [formType, setFormType] = useState('feishu')
  const [formName, setFormName] = useState('')
  const [formConfig, setFormConfig] = useState<Record<string, string>>({})
  const [formEnabled, setFormEnabled] = useState(true)
  const [saving, setSaving] = useState(false)
  const [noPermission, setNoPermission] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const all = await api.get<Account[]>(API_BASE)
      setAccounts((all || []).filter((c) => PUBLISHER_TYPES.includes(c.channel_type)))
      setNoPermission(false)
    } catch (e: any) {
      const status = e?.status || e?.statusCode || 0
      const msg = e?.message || ''
      if (status === 402 || msg.includes('402') || msg.includes('publishing_plan_required') || msg.includes('需开通')) {
        setNoPermission(true)
      } else {
        toast(t('publishingAccounts.toastLoadFailed', '加载失败'), { type: 'error', message: msg })
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const openCreate = () => {
    setEditing(null)
    setFormType('feishu')
    setFormName('')
    setFormConfig({})
    setFormEnabled(true)
    setDialogOpen(true)
  }

  const openEdit = (acc: Account) => {
    setEditing(acc)
    setFormType(acc.channel_type)
    setFormName(acc.name)
    // Sensitive values come back masked (********); prefill only non-sensitive keys.
    const cfg: Record<string, string> = {}
    for (const [k, v] of Object.entries(acc.config || {})) {
      if (typeof v === 'string' && v !== '********') cfg[k] = v
    }
    setFormConfig(cfg)
    setFormEnabled(acc.enabled)
    setDialogOpen(true)
  }

  const handleSave = async () => {
    if (!formName.trim()) {
      toast(t('publishingAccounts.nameRequired', '请填写账号名称'), { type: 'warning' })
      return
    }
    setSaving(true)
    try {
      const payload = {
        name: formName.trim(),
        channel_type: formType,
        config: formConfig,
        enabled: formEnabled,
      }
      if (editing) {
        await api.put(`${API_BASE}/${editing.id}`, payload)
        toast(t('publishingAccounts.toastUpdated', '账号已更新'), { type: 'success' })
      } else {
        await api.post(API_BASE, payload)
        toast(t('publishingAccounts.toastCreated', '账号已创建'), { type: 'success' })
      }
      setDialogOpen(false)
      await load()
    } catch (e: any) {
      toast(t('publishingAccounts.toastSaveFailed', '保存失败'), { type: 'error', message: e?.message })
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (acc: Account) => {
    if (!confirm(t('publishingAccounts.confirmDelete', '确认删除该账号？'))) return
    try {
      await api.delete(`${API_BASE}/${acc.id}`)
      toast(t('publishingAccounts.toastDeleted', '账号已删除'), { type: 'success' })
      await load()
    } catch (e: any) {
      toast(t('publishingAccounts.toastDeleteFailed', '删除失败'), { type: 'error', message: e?.message })
    }
  }

  const handleToggle = async (acc: Account, enabled: boolean) => {
    try {
      await api.put(`${API_BASE}/${acc.id}`, { enabled })
      await load()
    } catch (e: any) {
      toast(t('publishingAccounts.toastToggleFailed', '切换失败'), { type: 'error', message: e?.message })
    }
  }

  const currentTypeDef = types[formType]
  const typeOptions = PUBLISHER_TYPES.map((k) => ({
    value: k,
    label: types[k]?.label || k,
  }))

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{t('publishingAccounts.pageTitle', '发布账号管理')}</h1>
          <p className="text-sm text-gray-500 mt-1">
            {t('publishingAccounts.pageSubtitle', '管理多渠道发布账号的凭证，用于工作流自动分发')}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="secondary" leftIcon={<RefreshCw className="w-4 h-4" />} onClick={load}>
            {t('common.refresh', '刷新')}
          </Button>
          <Button leftIcon={<Plus className="w-4 h-4" />} onClick={openCreate}>
            {t('publishingAccounts.addAccount', '添加账号')}
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><Spinner size="lg" /></div>
      ) : noPermission ? (
        <Card>
          <CardContent className="py-16 text-center space-y-4">
            <div className="flex justify-center">
              <div className="p-4 rounded-full bg-blue-50">
                <Send className="w-8 h-8 text-blue-500" />
              </div>
            </div>
            <div>
              <h3 className="text-lg font-semibold">{t('publishingAccounts.noPlanTitle', '开通推广套餐后即可使用')}</h3>
              <p className="text-sm text-gray-500 mt-1">
                {t('publishingAccounts.noPlanDesc', '管理发布账号需要开通推广套餐（基础版1元/年5账号，标准版2元/年10账号）')}
              </p>
            </div>
            <Button onClick={() => navigate('/portal/templates')}>
              {t('publishingAccounts.goToTemplates', '前往开通')}
            </Button>
          </CardContent>
        </Card>
      ) : accounts.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-gray-500">
            {t('publishingAccounts.empty', '暂无发布账号，点击"添加账号"创建')}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {accounts.map((acc) => {
            const def = types[acc.channel_type]
            const Icon = def?.icon || KeyRound
            return (
              <Card key={acc.id} className="hover:shadow-md transition-shadow">
                <CardContent className="p-4 space-y-3">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2">
                      <div className="p-2 rounded-lg bg-blue-50">
                        <Icon className="w-5 h-5 text-blue-600" />
                      </div>
                      <div>
                        <div className="font-medium">{acc.name}</div>
                        <div className="text-xs text-gray-500">{def?.label || acc.channel_type}</div>
                      </div>
                    </div>
                    <Badge variant={acc.enabled ? 'success' : 'default'}>
                      {acc.enabled ? (
                        <span className="flex items-center gap-1"><CheckCircle className="w-3 h-3" />{t('common.enabled', '启用')}</span>
                      ) : (
                        <span className="flex items-center gap-1"><XCircle className="w-3 h-3" />{t('common.disabled', '禁用')}</span>
                      )}
                    </Badge>
                  </div>
                  {def?.transport === 'client' && (
                    <Badge variant="info">{t('publishingAccounts.clientMachine', '客户机')}</Badge>
                  )}
                  <div className="flex items-center justify-between pt-2 border-t border-gray-100">
                    <Switch checked={acc.enabled} onChange={(v) => handleToggle(acc, v)} />
                    <div className="flex gap-1">
                      <Button size="sm" variant="secondary" leftIcon={<Pencil className="w-3.5 h-3.5" />} onClick={() => openEdit(acc)}>
                        {t('common.edit', '编辑')}
                      </Button>
                      <Button size="sm" variant="secondary" leftIcon={<Trash2 className="w-3.5 h-3.5" />} onClick={() => handleDelete(acc)}>
                        {t('common.delete', '删除')}
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      {/* Create / Edit dialog */}
      <Dialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        title={editing ? t('publishingAccounts.dialogEdit', '编辑账号') : t('publishingAccounts.dialogAdd', '添加发布账号')}
        size="md"
      >
        <div className="space-y-4">
          <Select
            label={t('publishingAccounts.platform', '平台')}
            value={formType}
            onChange={(e) => {
              setFormType((e.target as HTMLSelectElement).value)
              setFormConfig({})
            }}
            options={typeOptions}
            disabled={!!editing}
          />
          <Input
            label={t('publishingAccounts.accountName', '账号名称')}
            placeholder={t('publishingAccounts.accountNamePlaceholder', '如：小红书主号')}
            value={formName}
            onChange={(e) => setFormName(e.target.value)}
          />
          {currentTypeDef?.description && (
            <p className="text-xs text-gray-500">{currentTypeDef.description}</p>
          )}
          {/* Dynamic credential fields driven by type metadata */}
          {currentTypeDef?.fields.map((field) => {
            const label = field.label + (field.required ? ' *' : '')
            if (field.type === 'select') {
              return (
                <Select
                  key={field.key}
                  label={label}
                  value={formConfig[field.key] || ''}
                  onChange={(e) => setFormConfig({ ...formConfig, [field.key]: (e.target as HTMLSelectElement).value })}
                  options={field.options || []}
                />
              )
            }
            return (
              <Input
                key={field.key}
                label={label}
                placeholder={field.placeholder}
                type={field.type === 'password' ? 'password' : 'text'}
                value={formConfig[field.key] || ''}
                onChange={(e) => setFormConfig({ ...formConfig, [field.key]: e.target.value })}
              />
            )
          })}
          <div className="flex items-center justify-between">
            <span className="text-sm">{t('publishingAccounts.enableAccount', '启用此账号')}</span>
            <Switch checked={formEnabled} onChange={setFormEnabled} />
          </div>
          {editing && (
            <p className="text-xs text-gray-400">
              {t('publishingAccounts.secretHint', '敏感凭证已加密存储，留空表示不修改')}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setDialogOpen(false)}>
              {t('common.cancel', '取消')}
            </Button>
            <Button onClick={handleSave} isLoading={saving}>
              {t('common.save', '保存')}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  )
}
