import React from 'react'
import { cn } from '@/lib/utils'

interface CardProps {
  className?: string
  children: React.ReactNode
  onClick?: () => void
  hover?: boolean
}

export function Card({ className, children, onClick, hover = false }: CardProps) {
  return (
    <div
      className={cn(
        'bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm',
        hover && 'hover:shadow-md hover:border-gray-300 dark:hover:border-gray-600 transition-all cursor-pointer',
        className,
      )}
      onClick={onClick}
    >
      {children}
    </div>
  )
}

export function CardHeader({
  className,
  children,
}: {
  className?: string
  children: React.ReactNode
}) {
  return (
    <div
      className={cn(
        'px-4 py-2.5 border-b border-gray-200 dark:border-gray-700 text-sm font-semibold text-gray-900 dark:text-gray-100',
        className,
      )}
    >
      {children}
    </div>
  )
}

export function CardContent({
  className,
  children,
}: {
  className?: string
  children: React.ReactNode
}) {
  return <div className={cn('px-4 py-3', className)}>{children}</div>
}

export function CardFooter({
  className,
  children,
}: {
  className?: string
  children: React.ReactNode
}) {
  return (
    <div
      className={cn(
        'px-6 py-4 border-t border-gray-200 dark:border-gray-700',
        className,
      )}
    >
      {children}
    </div>
  )
}
