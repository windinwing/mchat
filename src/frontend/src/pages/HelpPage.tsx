import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  BookOpen,
  Code2,
  Puzzle,
  Globe,
  Bot,
  MessageCircle,
  Github,
  Terminal,
  Server,
  Shield,
  Cpu,
  ArrowRight,
  Menu,
  X,
} from 'lucide-react'
import { LanguageSwitcher } from '@/components/common/LanguageSwitcher'

const GITHUB_URL = 'https://github.com/windinwing/mchat'

export function HelpPage() {
  const { t } = useTranslation()
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  return (
    <div className="min-h-screen bg-[#fafbfc] dark:bg-gray-950 text-gray-900 dark:text-gray-100">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-gray-200/80 dark:border-gray-800/80 bg-white/80 dark:bg-gray-950/80 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-primary-500 to-primary-700 flex items-center justify-center shadow-lg shadow-primary-500/25">
              <MessageCircle className="w-5 h-5 text-white" />
            </div>
            <span className="text-lg font-bold tracking-tight">MChat</span>
          </Link>
          <nav className="hidden sm:flex items-center gap-6 text-sm text-gray-600 dark:text-gray-400">
            <Link to="/" className="hover:text-primary-600 transition-colors">
              {t('help.backHome')}
            </Link>
            <Link to="/showcase" className="hover:text-primary-600 transition-colors">
              {t('landing.navShowcase')}
            </Link>
            <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className="hover:text-primary-600 transition-colors inline-flex items-center gap-1">
              <Github className="w-4 h-4" />
              GitHub
            </a>
          </nav>
          {/* Mobile hamburger */}
          <button
            type="button"
            onClick={() => setMobileNavOpen((v) => !v)}
            className="sm:hidden p-2.5 -mr-2 rounded-lg text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
            aria-label="Toggle navigation"
          >
            {mobileNavOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
          {mobileNavOpen && (
            <div className="sm:hidden absolute top-16 left-0 right-0 z-40 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 px-4 py-3 space-y-1 shadow-lg">
              <Link to="/" onClick={() => setMobileNavOpen(false)} className="block py-2 text-sm text-gray-700 dark:text-gray-300 hover:text-primary-600">
                {t('help.backHome')}
              </Link>
              <Link to="/showcase" onClick={() => setMobileNavOpen(false)} className="block py-2 text-sm text-gray-700 dark:text-gray-300 hover:text-primary-600">
                {t('landing.navShowcase')}
              </Link>
              <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className="block py-2 text-sm text-gray-700 dark:text-gray-300 hover:text-primary-600">
                GitHub
              </a>
            </div>
          )}
          <div className="flex items-center gap-3">
            <LanguageSwitcher />
            <Link to="/admin/login" className="text-sm font-medium text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white">
              {t('landing.ctaAdmin')}
            </Link>
          </div>
        </div>
      </header>

      {/* Content */}
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-16 space-y-24">
        {/* Hero */}
        <section className="text-center">
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight">{t('help.title')}</h1>
          <p className="mt-4 text-lg text-gray-500 dark:text-gray-400 max-w-2xl mx-auto">
            {t('help.subtitle')}
          </p>
        </section>

        {/* Quick Start */}
        <section>
          <h2 className="text-2xl font-bold mb-8 flex items-center gap-3">
            <Terminal className="w-6 h-6 text-primary-600" />
            {t('help.quickStartTitle')}
          </h2>
          <div className="space-y-6">
            <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-6">
              <h3 className="font-semibold mb-3">{t('help.dockerTitle')}</h3>
              <pre className="bg-gray-900 text-green-400 rounded-lg p-4 text-sm overflow-x-auto">
{`git clone https://github.com/windinwing/mchat.git
cd mchat
docker compose -f ops/docker/docker-compose.lite.yml up -d`}
              </pre>
              <ul className="mt-4 text-sm text-gray-500 dark:text-gray-400 space-y-1">
                <li>{t('help.adminPanelUrlLabel')}: <code className="text-primary-600">http://localhost:5173</code></li>
                <li>{t('help.apiDocsUrlLabel')}: <code className="text-primary-600">http://localhost:3001/docs</code></li>
                <li>{t('help.defaultAccount')}: <code className="text-primary-600">admin</code> / <code className="text-primary-600">admin123</code></li>
              </ul>
            </div>
            <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-6">
              <h3 className="font-semibold mb-3">{t('help.localDev')}</h3>
              <pre className="bg-gray-900 text-green-400 rounded-lg p-4 text-sm overflow-x-auto">
{`make install
make dev`}
              </pre>
            </div>
          </div>
        </section>

        {/* Widget Embedding */}
        <section>
          <h2 className="text-2xl font-bold mb-8 flex items-center gap-3">
            <Code2 className="w-6 h-6 text-primary-600" />
            {t('help.widgetTitle')}
          </h2>
          <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-6">
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">{t('help.widgetDesc')}</p>
            <pre className="bg-gray-900 text-green-400 rounded-lg p-4 text-sm overflow-x-auto">
{`<script
  src="http://localhost:5173/widget-loader.js"
  data-mchat-url="http://localhost:3001"
  data-agent-id="YOUR_AGENT_ID"
  data-primary-color="#3b82f6"
  data-welcome-message="${t('help.widgetExampleWelcome')}"
  data-bot-name="${t('help.widgetExampleBotName')}"
></script>`}
            </pre>
            <p className="text-xs text-gray-400 mt-3">{t('help.widgetNote')}</p>
          </div>
        </section>

        {/* Knowledge Base */}
        <section>
          <h2 className="text-2xl font-bold mb-8 flex items-center gap-3">
            <BookOpen className="w-6 h-6 text-primary-600" />
            {t('help.knowledgeTitle')}
          </h2>
          <div className="space-y-4">
            <Step num={1} title={t('help.kbStep1Title')} desc={t('help.kbStep1Desc')} />
            <Step num={2} title={t('help.kbStep2Title')} desc={t('help.kbStep2Desc')} />
            <Step num={3} title={t('help.kbStep3Title')} desc={t('help.kbStep3Desc')} />
            <Step num={4} title={t('help.kbStep4Title')} desc={t('help.kbStep4Desc')} />
          </div>
          <div className="mt-6 grid sm:grid-cols-2 gap-4">
            <ConfigCard icon={Cpu} title={t('help.chunkStrategies')} items={[t('help.chunkFixed'), t('help.chunkParagraph'), t('help.chunkMarkdown'), t('help.chunkSemantic')]} />
            <ConfigCard icon={Server} title={t('help.retrievalModes')} items={[t('help.retrievalVector'), t('help.retrievalKeyword'), t('help.retrievalHybrid')]} />
          </div>
        </section>

        {/* Skills */}
        <section>
          <h2 className="text-2xl font-bold mb-8 flex items-center gap-3">
            <Puzzle className="w-6 h-6 text-primary-600" />
            {t('help.skillsTitle')}
          </h2>
          <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-6">
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">{t('help.skillsDesc')}</p>
            <ul className="space-y-2 text-sm text-gray-600 dark:text-gray-300">
              <li className="flex items-start gap-2">
                <ArrowRight className="w-4 h-4 text-primary-500 mt-0.5 shrink-0" />
                {t('help.skillsItem1')}
              </li>
              <li className="flex items-start gap-2">
                <ArrowRight className="w-4 h-4 text-primary-500 mt-0.5 shrink-0" />
                {t('help.skillsItem2')}
              </li>
              <li className="flex items-start gap-2">
                <ArrowRight className="w-4 h-4 text-primary-500 mt-0.5 shrink-0" />
                {t('help.skillsItem3')}
              </li>
            </ul>
          </div>
        </section>

        {/* Channels */}
        <section>
          <h2 className="text-2xl font-bold mb-8 flex items-center gap-3">
            <Globe className="w-6 h-6 text-primary-600" />
            {t('help.channelsTitle')}
          </h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {['Web Widget', '微信公众号', 'Telegram', 'WhatsApp', 'Slack', 'LINE', 'DingTalk', t('help.custom')].map((ch) => (
              <div key={ch} className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4 py-3 text-sm font-medium text-center text-gray-700 dark:text-gray-300">
                {ch}
              </div>
            ))}
          </div>
        </section>

        {/* API Reference */}
        <section>
          <h2 className="text-2xl font-bold mb-8 flex items-center gap-3">
            <Terminal className="w-6 h-6 text-primary-600" />
            API {t('help.reference')}
          </h2>
          <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-6">
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">{t('help.apiDesc')}</p>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="text-left py-2 px-3 font-medium">{t('help.apiModule')}</th>
                    <th className="text-left py-2 px-3 font-medium">{t('help.apiPrefix')}</th>
                    <th className="text-left py-2 px-3 font-medium">{t('help.apiDesc2')}</th>
                  </tr>
                </thead>
                <tbody className="text-gray-600 dark:text-gray-400">
                  <tr className="border-b border-gray-100 dark:border-gray-800"><td className="py-2 px-3">{t('help.apiChat')}</td><td className="py-2 px-3"><code className="text-primary-600 text-xs">/api/chat/*</code></td><td className="py-2 px-3">{t('help.apiChatDesc')}</td></tr>
                  <tr className="border-b border-gray-100 dark:border-gray-800"><td className="py-2 px-3">{t('help.apiAgent')}</td><td className="py-2 px-3"><code className="text-primary-600 text-xs">/api/agents/*</code></td><td className="py-2 px-3">{t('help.apiAgentDesc')}</td></tr>
                  <tr className="border-b border-gray-100 dark:border-gray-800"><td className="py-2 px-3">{t('help.apiKnowledge')}</td><td className="py-2 px-3"><code className="text-primary-600 text-xs">/api/knowledge/*</code></td><td className="py-2 px-3">{t('help.apiKnowledgeDesc')}</td></tr>
                  <tr className="border-b border-gray-100 dark:border-gray-800"><td className="py-2 px-3">{t('help.apiSkills')}</td><td className="py-2 px-3"><code className="text-primary-600 text-xs">/api/skills/*</code></td><td className="py-2 px-3">{t('help.apiSkillsDesc')}</td></tr>
                  <tr className="border-b border-gray-100 dark:border-gray-800"><td className="py-2 px-3">{t('help.apiChannels')}</td><td className="py-2 px-3"><code className="text-primary-600 text-xs">/api/channels/*</code></td><td className="py-2 px-3">{t('help.apiChannelsDesc')}</td></tr>
                  <tr><td className="py-2 px-3">{t('help.apiWidget')}</td><td className="py-2 px-3"><code className="text-primary-600 text-xs">/api/widget/*</code></td><td className="py-2 px-3">{t('help.apiWidgetDesc')}</td></tr>
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* LLM Providers */}
        <section>
          <h2 className="text-2xl font-bold mb-8 flex items-center gap-3">
            <Bot className="w-6 h-6 text-primary-600" />
            {t('help.providersTitle')}
          </h2>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {['OpenAI', 'Anthropic', 'Google Gemini', 'DeepSeek', 'Ollama', 'Groq', '智谱 / Moonshot / SiliconFlow', 'OpenAI Compatible'].map((p) => (
              <div key={p} className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-4 py-3 text-sm text-center text-gray-700 dark:text-gray-300">
                {p}
              </div>
            ))}
          </div>
        </section>

        {/* Security */}
        <section>
          <h2 className="text-2xl font-bold mb-8 flex items-center gap-3">
            <Shield className="w-6 h-6 text-primary-600" />
            {t('help.securityTitle')}
          </h2>
          <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-6">
            <ul className="space-y-3 text-sm text-gray-600 dark:text-gray-300">
              <li className="flex items-start gap-2">
                <ArrowRight className="w-4 h-4 text-primary-500 mt-0.5 shrink-0" />
                {t('help.securityItem1')}
              </li>
              <li className="flex items-start gap-2">
                <ArrowRight className="w-4 h-4 text-primary-500 mt-0.5 shrink-0" />
                {t('help.securityItem2')}
              </li>
              <li className="flex items-start gap-2">
                <ArrowRight className="w-4 h-4 text-primary-500 mt-0.5 shrink-0" />
                {t('help.securityItem3')}
              </li>
              <li className="flex items-start gap-2">
                <ArrowRight className="w-4 h-4 text-primary-500 mt-0.5 shrink-0" />
                {t('help.securityItem4')}
              </li>
            </ul>
          </div>
        </section>
      </div>

      {/* Footer */}
      <footer className="border-t border-gray-200 dark:border-gray-800 py-8 text-center text-sm text-gray-400">
        <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 hover:text-gray-600 dark:hover:text-gray-300 transition-colors">
          <Github className="w-4 h-4" /> GitHub
        </a>
      </footer>
    </div>
  )
}

function Step({ num, title, desc }: { num: number; title: string; desc: string }) {
  return (
    <div className="flex gap-4 items-start">
      <div className="w-8 h-8 rounded-full bg-primary-100 dark:bg-primary-900/40 text-primary-700 dark:text-primary-300 flex items-center justify-center text-sm font-bold shrink-0">
        {num}
      </div>
      <div>
        <h4 className="font-medium text-gray-900 dark:text-gray-100">{title}</h4>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">{desc}</p>
      </div>
    </div>
  )
}

function ConfigCard({ icon: Icon, title, items }: { icon: any; title: string; items: string[] }) {
  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-5">
      <h4 className="font-medium text-sm mb-3 flex items-center gap-2">
        <Icon className="w-4 h-4 text-primary-500" />
        {title}
      </h4>
      <ul className="space-y-1.5">
        {items.map((item) => (
          <li key={item} className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-1.5">
            <span className="w-1 h-1 rounded-full bg-primary-400" />
            {item}
          </li>
        ))}
      </ul>
    </div>
  )
}
