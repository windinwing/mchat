import { Link } from 'react-router-dom'
import { isCloudEdition, isSignupEnabled } from '@/lib/edition'
import { useTranslation } from 'react-i18next'
import {
  Bot,
  BookOpen,
  Puzzle,
  MessageCircle,
  Globe,
  Layers,
  Github,
  Sparkles,
  Zap,
  Code2,
  Workflow,
  FileSearch,
  Store,
  CreditCard,
} from 'lucide-react'
import { LanguageSwitcher } from '@/components/common/LanguageSwitcher'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import { useAuthStore } from '@/stores/auth'
import { landingScreenshot, LANDING_PREVIEW_CARDS } from '@/lib/landingImages'
import { preferredStaffPath } from '@/lib/appPreferences'
import { SiteCopyrightFooter } from '@/components/common/SiteCopyrightFooter'

const GITHUB_URL = 'https://github.com/windinwing/mchat'

const coreFeatureIcons = [Bot, BookOpen, Puzzle, Workflow, MessageCircle, Globe, Layers] as const
const coreFeatureKeys = [
  'featureBot',
  'featureRag',
  'featureSkill',
  'featureWorkflow',
  'featureWidget',
  'featureChannel',
  'featureTenant',
] as const

const cloudFeatureIcons = [Store, BookOpen, Globe, Workflow, FileSearch, CreditCard] as const
const cloudFeatureKeys = [
  'featureMarket',
  'featureRag',
  'featureEmbed',
  'featureWorkflow',
  'featurePatent',
  'featureTrial',
] as const

export function LandingPage() {
  const { t, i18n } = useTranslation()
  const cloud = isCloudEdition
  const lp = (key: string) => t(cloud ? `landingCloud.${key}` : `landing.${key}`)
  const { isAuthenticated, user } = useAuthStore()
  const adminTarget =
    isAuthenticated
      ? (user?.role === 'user' ? '/portal/dashboard' : preferredStaffPath())
      : cloud
        ? '/admin/login'
        : '/admin/login'
  const primaryCta = isAuthenticated
    ? user?.role === 'user'
      ? '/portal/dashboard'
      : adminTarget
    : isSignupEnabled
      ? '/register'
      : '/portal/templates'

  return (
    <div className="min-h-screen bg-[#fafbfc] dark:bg-gray-950 text-gray-900 dark:text-gray-100">
      <header className="sticky top-0 z-50 border-b border-gray-200/80 dark:border-gray-800/80 bg-white/80 dark:bg-gray-950/80 backdrop-blur-md">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-primary-500 to-primary-700 flex items-center justify-center shadow-lg shadow-primary-500/25">
              <MessageCircle className="w-5 h-5 text-white" />
            </div>
            <span className="text-lg font-bold tracking-tight">MChat</span>
          </Link>
          <nav className="hidden sm:flex items-center gap-6 text-sm text-gray-600 dark:text-gray-400">
            <a href="#preview" className="hover:text-primary-600 transition-colors">
              {t('landing.navPreview')}
            </a>
            <a href="#features" className="hover:text-primary-600 transition-colors">
              {t('landing.navFeatures')}
            </a>
            <a
              href={cloud ? '#how-it-works' : '#quickstart'}
              className="hover:text-primary-600 transition-colors"
            >
              {cloud ? lp('navHowItWorks') : t('landing.quickTitle')}
            </a>
            {!cloud && (
              <>
                <Link to="/help" className="hover:text-primary-600 transition-colors">
                  {t('landing.navHelp')}
                </Link>
                <Link to="/showcase" className="hover:text-primary-600 transition-colors">
                  {t('landing.navShowcase')}
                </Link>
                <a
                  href={GITHUB_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-primary-600 transition-colors inline-flex items-center gap-1"
                >
                  <Github className="w-4 h-4" />
                  {t('common.github')}
                </a>
              </>
            )}
            {cloud && (
              <Link to="/portal/templates" className="hover:text-primary-600 transition-colors">
                {t('portal.templates')}
              </Link>
            )}
          </nav>
          <div className="flex items-center gap-3">
            <LanguageSwitcher />
            <ThemeToggle />
            {!cloud && (
              <Link
                to="/showcase"
                className="hidden sm:inline-flex text-sm font-medium text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white"
              >
                {t('landing.navShowcase')}
              </Link>
            )}
            {cloud && !isAuthenticated && (
              <Link
                to="/admin/login"
                className="hidden sm:inline-flex text-sm font-medium text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white"
              >
                {lp('ctaLogin')}
              </Link>
            )}
            <Link
              to={primaryCta}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium bg-primary-600 text-white hover:bg-primary-700 transition-colors"
            >
              {cloud
                ? isAuthenticated
                  ? t('portal.dashboard')
                  : lp('ctaRegister')
                : t('landing.ctaAdmin')}
            </Link>
          </div>
        </div>
      </header>

      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-primary-50/80 via-transparent to-transparent dark:from-primary-950/40 pointer-events-none" />
        <div
          className="absolute top-20 left-1/2 -translate-x-1/2 w-[800px] h-[400px] rounded-full bg-primary-400/10 blur-3xl pointer-events-none"
          aria-hidden
        />
        <div className="relative max-w-6xl mx-auto px-4 sm:px-6 pt-16 pb-24 sm:pt-24 sm:pb-32 text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary-100 dark:bg-primary-900/40 text-primary-700 dark:text-primary-300 text-xs font-medium mb-6">
            <Sparkles className="w-3.5 h-3.5" />
            {lp('badge')}
          </div>
          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight leading-tight">
            {lp('heroTitle')}
            <br />
            <span className="bg-gradient-to-r from-primary-600 to-violet-600 bg-clip-text text-transparent">
              {lp('heroTitleAccent')}
            </span>
          </h1>
          <p className="mt-6 max-w-2xl mx-auto text-lg text-gray-600 dark:text-gray-400 leading-relaxed">
            {lp('heroSubtitle')}
          </p>
          <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
            {cloud ? (
              <>
                <Link
                  to={primaryCta}
                  className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-primary-600 text-white text-base font-medium hover:bg-primary-700 transition-all shadow-lg shadow-primary-500/25"
                >
                  <Sparkles className="w-5 h-5" />
                  {isAuthenticated ? t('portal.dashboard') : lp('ctaRegister')}
                </Link>
                <Link
                  to="/portal/templates"
                  className="inline-flex items-center gap-2 px-6 py-3 rounded-xl border border-gray-300 dark:border-gray-600 bg-white/90 dark:bg-gray-900/80 text-base font-medium text-gray-700 dark:text-gray-300 hover:border-primary-400 transition-all"
                >
                  <Store className="w-5 h-5 text-primary-600" />
                  {lp('ctaTemplates')}
                </Link>
                <Link
                  to="/widget/demo"
                  className="inline-flex items-center gap-2 px-6 py-3 rounded-xl border border-gray-300 dark:border-gray-600 bg-white/90 dark:bg-gray-900/80 text-base font-medium text-gray-700 dark:text-gray-300 hover:border-primary-400 transition-all"
                >
                  <Zap className="w-5 h-5 text-primary-600" />
                  {lp('ctaWidget')}
                </Link>
              </>
            ) : (
              <>
                <Link
                  to="/widget/demo"
                  className="inline-flex items-center gap-2 px-6 py-3 rounded-xl border border-gray-300 dark:border-gray-600 bg-white/90 dark:bg-gray-900/80 text-base font-medium text-gray-700 dark:text-gray-300 hover:border-primary-400 hover:text-gray-900 dark:hover:text-white transition-all"
                >
                  <Zap className="w-5 h-5 text-primary-600" />
                  {t('landing.ctaWidget')}
                </Link>
                <Link
                  to="/showcase"
                  className="inline-flex items-center gap-2 px-6 py-3 rounded-xl border border-gray-300 dark:border-gray-600 bg-white/90 dark:bg-gray-900/80 text-base font-medium text-gray-700 dark:text-gray-300 hover:border-primary-400 hover:text-gray-900 dark:hover:text-white transition-all"
                >
                  <MessageCircle className="w-5 h-5 text-primary-600" />
                  {t('landing.ctaShowcase')}
                </Link>
                <a
                  href={GITHUB_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-6 py-3 rounded-xl border border-gray-300 dark:border-gray-600 bg-white/90 dark:bg-gray-900/80 text-base font-medium text-gray-700 dark:text-gray-300 hover:border-primary-400 hover:text-gray-900 dark:hover:text-white transition-all"
                >
                  <Github className="w-5 h-5" />
                  {t('landing.ctaGithub')}
                </a>
              </>
            )}
          </div>
          <div className="mt-16 grid grid-cols-3 gap-6 max-w-lg mx-auto">
            {cloud
              ? [
                  { v: '5+', k: 'statsTemplates' },
                  { v: '14', k: 'statsTrial' },
                  { v: '1', k: 'statsEmbed' },
                ].map((s) => (
                  <div key={s.k} className="text-center">
                    <p className="text-2xl sm:text-3xl font-bold text-primary-600">{s.v}</p>
                    <p className="text-xs sm:text-sm text-gray-500 mt-1">{lp(s.k)}</p>
                  </div>
                ))
              : [
                  { v: '10+', k: 'landing.statsModels' },
                  { v: '6+', k: 'landing.statsChannels' },
                  { v: '1', k: 'landing.statsDeploy' },
                ].map((s) => (
                  <div key={s.k} className="text-center">
                    <p className="text-2xl sm:text-3xl font-bold text-primary-600">{s.v}</p>
                    <p className="text-xs sm:text-sm text-gray-500 mt-1">{t(s.k)}</p>
                  </div>
                ))}
          </div>
        </div>
      </section>

      <section id="preview" className="py-20 sm:py-24 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900/40">
        <div className="max-w-6xl mx-auto px-4 sm:px-6">
          <div className="text-center max-w-3xl mx-auto mb-12">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary-100 dark:bg-primary-900/40 text-primary-700 dark:text-primary-300 text-xs font-medium mb-4">
              {lp('previewBadge')}
            </div>
            <h2 className="text-3xl sm:text-4xl font-bold">{lp('previewTitle')}</h2>
            <p className="mt-4 text-gray-600 dark:text-gray-400 leading-relaxed">{lp('previewSubtitle')}</p>
            <ul className="mt-6 text-left sm:text-center space-y-2 text-sm text-gray-600 dark:text-gray-400">
              {(['previewPoint1', 'previewPoint2', 'previewPoint3'] as const).map((key) => (
                <li key={key}>{lp(key)}</li>
              ))}
            </ul>
          </div>

          <div className="rounded-2xl border border-gray-200 dark:border-gray-700 overflow-hidden shadow-xl bg-gray-50 dark:bg-gray-800/50 mb-8">
            <div className="px-4 py-2 border-b border-gray-200 dark:border-gray-700 text-xs font-medium text-gray-500 dark:text-gray-400">
              {lp('previewFrameTitle')}
            </div>
            {cloud ? (
              <Link to="/portal/templates" className="block">
                <img
                  src={landingScreenshot('home.zone', i18n.language)}
                  alt={lp('previewTitle')}
                  className="w-full h-auto"
                  loading="lazy"
                />
              </Link>
            ) : (
              <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer" className="block">
                <img
                  src={landingScreenshot('home.zone', i18n.language)}
                  alt={t('landing.previewMainAlt')}
                  className="w-full h-auto"
                  loading="lazy"
                />
              </a>
            )}
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {LANDING_PREVIEW_CARDS.map(({ key, image }) => (
              <figure
                key={key}
                className="rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden bg-white dark:bg-gray-900 shadow-sm hover:shadow-md transition-shadow"
              >
                <img
                  src={landingScreenshot(image, i18n.language)}
                  alt={t(`landing.${key}`)}
                  className="w-full h-auto aspect-video object-cover object-top"
                  loading="lazy"
                />
                <figcaption className="px-3 py-2 text-xs font-medium text-gray-700 dark:text-gray-300 border-t border-gray-100 dark:border-gray-800">
                  {t(`landing.${key}`)}
                </figcaption>
              </figure>
            ))}
          </div>
        </div>
      </section>

      <section id="features" className="py-20 sm:py-28 bg-white dark:bg-gray-900/50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6">
          <div className="text-center max-w-2xl mx-auto mb-14">
            <h2 className="text-3xl sm:text-4xl font-bold">{lp('featuresTitle')}</h2>
            <p className="mt-4 text-gray-600 dark:text-gray-400">{lp('featuresSubtitle')}</p>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {(cloud ? cloudFeatureKeys : coreFeatureKeys).map((key, i) => {
              const Icon = cloud ? cloudFeatureIcons[i] : coreFeatureIcons[i]
              const prefix = cloud ? 'landingCloud' : 'landing'
              return (
                <div
                  key={key}
                  className="group p-6 rounded-2xl border border-gray-200 dark:border-gray-700 bg-gray-50/50 dark:bg-gray-800/30 hover:border-primary-300 dark:hover:border-primary-700 hover:shadow-lg hover:shadow-primary-500/5 transition-all"
                >
                  <div className="w-11 h-11 rounded-xl bg-primary-100 dark:bg-primary-900/50 flex items-center justify-center text-primary-600 mb-4 group-hover:scale-110 transition-transform">
                    <Icon className="w-6 h-6" />
                  </div>
                  <h3 className="text-lg font-semibold mb-2">{t(`${prefix}.${key}Title`)}</h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                    {t(`${prefix}.${key}Desc`)}
                  </p>
                </div>
              )
            })}
          </div>
        </div>
      </section>

      {cloud ? (
        <section id="how-it-works" className="py-20 sm:py-28 border-y border-gray-200 dark:border-gray-800">
          <div className="max-w-6xl mx-auto px-4 sm:px-6">
            <h2 className="text-3xl font-bold text-center mb-12">{lp('howTitle')}</h2>
            <div className="grid md:grid-cols-3 gap-8">
              {(['howStep1', 'howStep2', 'howStep3'] as const).map((step, idx) => (
                <div
                  key={step}
                  className="relative p-6 rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900/50"
                >
                  <span className="inline-flex w-8 h-8 rounded-full bg-primary-600 text-white text-sm font-bold items-center justify-center mb-4">
                    {idx + 1}
                  </span>
                  <h3 className="text-lg font-semibold mb-2">{lp(`${step}Title`)}</h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                    {lp(`${step}Desc`)}
                  </p>
                </div>
              ))}
            </div>
            <div className="mt-10 text-center">
              <Link
                to={isSignupEnabled ? '/register' : '/portal/templates'}
                className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-primary-600 text-white font-medium hover:bg-primary-700 transition-colors"
              >
                {lp('ctaRegister')}
              </Link>
            </div>
          </div>
        </section>
      ) : (
        <>
          <section className="py-16 border-y border-gray-200 dark:border-gray-800">
            <div className="max-w-6xl mx-auto px-4 sm:px-6 flex flex-col md:flex-row items-center gap-10">
              <div className="flex-1">
                <h2 className="text-2xl sm:text-3xl font-bold flex items-center gap-2">
                  <Code2 className="w-8 h-8 text-primary-600" />
                  {t('landing.archTitle')}
                </h2>
                <p className="mt-4 text-gray-600 dark:text-gray-400">{t('landing.archLine1')}</p>
                <p className="mt-2 text-gray-600 dark:text-gray-400">{t('landing.archLine2')}</p>
              </div>
              <div className="flex-1 w-full max-w-md p-6 rounded-2xl bg-gray-900 text-gray-100 font-mono text-xs sm:text-sm shadow-xl overflow-x-auto">
                <pre className="whitespace-pre">{`mchat/
├── src/backend/    # FastAPI + Bot + RAG
├── src/frontend/   # React admin + landing
├── skills/         # Skill packages
└── ops/docker/     # Compose stacks`}</pre>
              </div>
            </div>
          </section>

          <section id="quickstart" className="py-20 sm:py-28">
            <div className="max-w-6xl mx-auto px-4 sm:px-6">
              <h2 className="text-3xl font-bold text-center mb-12">{t('landing.quickTitle')}</h2>
              <div className="grid md:grid-cols-2 gap-8">
                <div className="rounded-2xl border border-gray-800 overflow-hidden bg-gray-950 text-gray-100">
                  <div className="px-4 py-2 bg-gray-900 text-sm font-medium border-b border-gray-800">
                    {t('landing.quickDocker')}
                  </div>
                  <pre className="p-4 text-sm bg-gray-950 text-gray-100 overflow-x-auto min-h-[156px]">
{`git clone https://github.com/windinwing/mchat.git
cd mchat
docker compose -f ops/docker/docker-compose.lite.yml up -d
# Admin: http://localhost:5173`}
                  </pre>
                </div>
                <div className="rounded-2xl border border-gray-800 overflow-hidden bg-gray-950 text-gray-100">
                  <div className="px-4 py-2 bg-gray-900 text-sm font-medium border-b border-gray-800">
                    {t('landing.quickDev')}
                  </div>
                  <pre className="p-4 text-sm bg-gray-950 text-gray-100 overflow-x-auto min-h-[156px]">
{`make install && make dev
# API:  http://localhost:3001/docs
# Web:  http://localhost:5173`}
                  </pre>
                </div>
              </div>
            </div>
          </section>
        </>
      )}

      <footer className="border-t border-gray-200 dark:border-gray-800 py-12 bg-white dark:bg-gray-900">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 pb-6">
          <SiteCopyrightFooter className="text-center" />
        </div>
        <div className="max-w-6xl mx-auto px-4 sm:px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <MessageCircle className="w-5 h-5 text-primary-600" />
            <span className="font-semibold">MChat</span>
            <span className="text-gray-400">·</span>
            <span className="text-sm text-gray-500">{lp('footerTagline')}</span>
          </div>
          <div className="flex items-center gap-4 text-sm text-gray-500">
            {cloud ? (
              <>
                {isSignupEnabled && (
                  <Link to="/register" className="hover:text-primary-600">
                    {lp('footerRegister')}
                  </Link>
                )}
                <Link to="/portal/templates" className="hover:text-primary-600">
                  {lp('footerTemplates')}
                </Link>
                <Link to={adminTarget} className="hover:text-primary-600">
                  {lp('ctaLogin')}
                </Link>
              </>
            ) : (
              <>
                <a href={GITHUB_URL} className="hover:text-primary-600" target="_blank" rel="noreferrer">
                  {t('common.github')}
                </a>
                <Link to={adminTarget} className="hover:text-primary-600">
                  {t('common.admin')}
                </Link>
                <Link to="/showcase" className="hover:text-primary-600">
                  {t('landing.navShowcase')}
                </Link>
                <span>{t('landing.footerLicense')}</span>
              </>
            )}
          </div>
        </div>
      </footer>
    </div>
  )
}
