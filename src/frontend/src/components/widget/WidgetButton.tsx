import React, { useEffect, useState } from 'react'
import { Bot, Headphones, MessageCircle, Sparkles, X } from 'lucide-react'
import { cn } from '@/lib/utils'

interface WidgetButtonProps {
  isOpen: boolean
  onClick: () => void
  position: 'right' | 'left'
  primaryColor?: string
  launcherIcon?: string
  launcherText?: string
}

function resolveLauncherIcon(name?: string) {
  const normalized = (name || '').toLowerCase()
  if (normalized === 'bot' || normalized === 'robot') return Bot
  if (normalized === 'spark' || normalized === 'sparkles') return Sparkles
  if (normalized === 'support' || normalized === 'headset') return Headphones
  if (normalized === 'message' || normalized === 'chat') return MessageCircle
  return MessageCircle
}

export function WidgetButton({
  isOpen,
  onClick,
  position,
  primaryColor = '#3b82f6',
  launcherIcon = 'chat',
  launcherText = '',
}: WidgetButtonProps) {
  const LauncherIcon = resolveLauncherIcon(launcherIcon)
  const showText = !isOpen && launcherText.trim().length > 0
  const [hover, setHover] = useState(false)

  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      className={cn(
        'fixed z-[9999] flex items-center justify-center gap-2 transition-all duration-200',
        'shadow-lg hover:shadow-xl ring-1 ring-white/20',
        showText
          ? 'h-12 px-5 rounded-full'
          : 'w-14 h-14 rounded-full',
        position === 'right' ? 'right-6' : 'left-6',
        'bottom-[calc(1.5rem+env(safe-area-inset-bottom))]',
        hover ? 'scale-105' : 'scale-100',
      )}
      style={{
        background: `linear-gradient(135deg, ${primaryColor}, ${primaryColor}dd)`,
      }}
    >
      {isOpen ? (
        <X className="w-6 h-6 text-white" />
      ) : (
        <>
          <LauncherIcon className={cn('text-white', showText ? 'w-5 h-5' : 'w-6 h-6')} />
          {showText && <span className="text-sm font-medium text-white whitespace-nowrap">{launcherText}</span>}
        </>
      )}
    </button>
  )
}
