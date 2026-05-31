/** Locale-aware paths for landing page screenshots under /public/landing/. */

export function landingScreenshot(name: string, locale: string): string {
  const zh = locale.startsWith('zh')
  if (name === 'workflow' || name === 'workflow.graph') {
    return `/landing/${name}.${zh ? 'cn' : 'en'}.png`
  }
  return `/landing/mchat.${name}.${zh ? 'zh' : 'en'}.png`
}

export const LANDING_PREVIEW_CARDS = [
  { key: 'previewCardConversations', image: 'conversations' },
  { key: 'previewCardKnowledge', image: 'knowledge' },
  { key: 'previewCardWidget', image: 'widget' },
  { key: 'previewCardWorkflow', image: 'workflow' },
  { key: 'previewCardWorkflowGraph', image: 'workflow.graph' },
] as const
