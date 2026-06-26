import type React from 'react'
import type { TFunction } from 'i18next'
import {
  Send, MessageSquare, Phone, Rss, Twitter, Facebook, Linkedin, Share2, Bot,
} from 'lucide-react'

export type PublishingAccountFieldDef = {
  key: string
  label: string
  placeholder: string
  /** ``select`` renders a dropdown driven by ``options``. */
  type?: 'text' | 'password' | 'textarea' | 'select'
  /** For ``type: 'select'`` — the dropdown choices. */
  options?: { value: string; label: string }[]
  required?: boolean
}

export type PublishingAccountTypeDef = {
  label: string
  icon: React.FC<{ className?: string }>
  description: string
  /** "api" channels run server-side; "client" channels need the Playwright client machine. */
  transport: 'api' | 'client'
  fields: PublishingAccountFieldDef[]
}

/**
 * Metadata for outbound publisher accounts. Drives the dynamic credential form
 * in PublishingAccountsPage. Keys match the publisher ``provider_key`` values
 * (see app/publish/publishers). Sensitive fields use ``type: 'password'`` so the
 * form renders a masked input; the backend encrypts them at rest regardless.
 */
export function getPublishingAccountTypes(
  t: TFunction
): Record<string, PublishingAccountTypeDef> {
  return {
    feishu: {
      label: t('publishingAccounts.types.feishu.label', '飞书 Feishu'),
      icon: MessageSquare,
      description: t('publishingAccounts.types.feishu.description', '群机器人 Webhook'),
      transport: 'api',
      fields: [
        { key: 'webhook_url', label: 'Webhook URL', placeholder: 'https://open.feishu.cn/open-apis/bot/v2/hook/...', type: 'password', required: true },
        { key: 'secret', label: '签名密钥(可选)', placeholder: 'secxxxx', type: 'password' },
        { key: 'msg_type', label: '消息类型', placeholder: 'text / card' },
      ],
    },
    dingtalk: {
      label: t('publishingAccounts.types.dingtalk.label', '钉钉'),
      icon: MessageSquare,
      description: t('publishingAccounts.types.dingtalk.description', '群机器人 Webhook'),
      transport: 'api',
      fields: [
        { key: 'webhook_url', label: 'Webhook URL', placeholder: 'https://oapi.dingtalk.com/robot/send?...', type: 'password', required: true },
        { key: 'secret', label: '加签密钥(可选)', placeholder: 'SEC...', type: 'password' },
      ],
    },
    wecom: {
      label: t('publishingAccounts.types.wecom.label', '企业微信'),
      icon: MessageSquare,
      description: t('publishingAccounts.types.wecom.description', '群机器人 Key'),
      transport: 'api',
      fields: [
        { key: 'key', label: '机器人 Key', placeholder: 'xxxxxxxx', type: 'password', required: true },
      ],
    },
    slack: {
      label: t('publishingAccounts.types.slack.label', 'Slack'),
      icon: Share2,
      description: t('publishingAccounts.types.slack.description', 'Incoming Webhook'),
      transport: 'api',
      fields: [
        { key: 'webhook_url', label: 'Webhook URL', placeholder: 'https://hooks.slack.com/services/...', type: 'password', required: true },
      ],
    },
    discord: {
      label: t('publishingAccounts.types.discord.label', 'Discord'),
      icon: MessageSquare,
      description: t('publishingAccounts.types.discord.description', 'Webhook'),
      transport: 'api',
      fields: [
        { key: 'webhook_url', label: 'Webhook URL', placeholder: 'https://discord.com/api/webhooks/...', type: 'password', required: true },
      ],
    },
    telegram_channel: {
      label: t('publishingAccounts.types.telegram_channel.label', 'Telegram'),
      icon: Send,
      description: t('publishingAccounts.types.telegram_channel.description', 'Bot → Channel'),
      transport: 'api',
      fields: [
        { key: 'bot_token', label: 'Bot Token', placeholder: '123456:ABC...', type: 'password', required: true },
        { key: 'chat_id', label: 'Channel/Chat ID', placeholder: '@yourchannel', required: true },
      ],
    },
    twitter_x: {
      label: t('publishingAccounts.types.twitter_x.label', 'X (Twitter)'),
      icon: Twitter,
      description: t('publishingAccounts.types.twitter_x.description', 'API v2'),
      transport: 'api',
      fields: [
        { key: 'access_token', label: 'Access Token', placeholder: 'OAuth2 token', type: 'password', required: true },
      ],
    },
    facebook: {
      label: t('publishingAccounts.types.facebook.label', 'Facebook'),
      icon: Facebook,
      description: t('publishingAccounts.types.facebook.description', 'Page Graph API'),
      transport: 'api',
      fields: [
        { key: 'page_id', label: 'Page ID', placeholder: '123456', required: true },
        { key: 'page_access_token', label: 'Page Access Token', placeholder: 'EAAB...', type: 'password', required: true },
      ],
    },
    linkedin: {
      label: t('publishingAccounts.types.linkedin.label', 'LinkedIn'),
      icon: Linkedin,
      description: t('publishingAccounts.types.linkedin.description', 'UGC Posts API'),
      transport: 'api',
      fields: [
        { key: 'access_token', label: 'Access Token', placeholder: 'AQX...', type: 'password', required: true },
        { key: 'author_urn', label: 'Author URN', placeholder: 'urn:li:person:xxx', required: true },
      ],
    },
    wechat_mp: {
      label: t('publishingAccounts.types.wechat_mp.label', '微信公众号'),
      icon: Rss,
      description: t('publishingAccounts.types.wechat_mp.description', '草稿/发布 API'),
      transport: 'api',
      fields: [
        { key: 'app_id', label: 'App ID', placeholder: 'wx...', required: true },
        { key: 'app_secret', label: 'App Secret', placeholder: 'App Secret', type: 'password', required: true },
      ],
    },
    playwright_client: {
      label: t('publishingAccounts.types.playwright_client.label', '客户机 (小红书/抖音/微博)'),
      icon: Bot,
      description: t('publishingAccounts.types.playwright_client.description', '浏览器自动化发布，由客户机自动登录'),
      transport: 'client',
      fields: [
        {
          key: 'platform',
          label: t('publishingAccounts.types.playwright_client.fields.platform', '平台'),
          type: 'select',
          required: true,
          placeholder: '',
          options: [
            { value: 'xiaohongshu', label: '小红书' },
            { value: 'douyin', label: '抖音' },
            { value: 'weibo', label: '微博' },
          ],
        },
        {
          key: 'login_account',
          label: t('publishingAccounts.types.playwright_client.fields.login_account', '登录账号'),
          placeholder: t('publishingAccounts.types.playwright_client.fields.login_account_ph', '手机号 / 邮箱'),
          required: true,
        },
        {
          key: 'login_password',
          label: t('publishingAccounts.types.playwright_client.fields.login_password', '登录密码'),
          placeholder: t('publishingAccounts.types.playwright_client.fields.login_password_ph', '账号密码'),
          type: 'password',
          required: true,
        },
      ],
    },
  }
}
