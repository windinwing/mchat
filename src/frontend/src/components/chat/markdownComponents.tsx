import type { Components } from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { Copy, Check } from 'lucide-react'
import {
  isWechatBrowser,
  normalizeMiniProgramHref,
} from '@/lib/wechatMiniProgram'
export function createMarkdownComponents(
  onCopy: (text: string) => void,
  copied: boolean,
): Components {
  return {
    code({ className, children, ...props }) {
      const match = /language-(\w+)/.exec(className || '')
      const codeString = String(children).replace(/\n$/, '')
      if (match && (match[1] === 'text' || match[1] === 'plaintext')) {
        return (
          <pre className="text-sm whitespace-pre-wrap break-words font-sans leading-relaxed bg-transparent p-0 m-0 my-2 text-gray-800 dark:text-gray-200">
            {codeString}
          </pre>
        )
      }
      if (match) {
        return (
          <div className="relative group my-2">
            <button
              type="button"
              onClick={() => onCopy(codeString)}
              className="absolute right-2 top-2 p-1.5 rounded-lg bg-gray-700/50 text-gray-300 opacity-0 group-hover:opacity-100 transition-opacity hover:bg-gray-700"
            >
              {copied ? (
                <Check className="w-3.5 h-3.5 text-green-400" />
              ) : (
                <Copy className="w-3.5 h-3.5" />
              )}
            </button>
            <SyntaxHighlighter
              style={oneDark}
              language={match[1]}
              PreTag="div"
              customStyle={{
                margin: 0,
                borderRadius: '0.75rem',
                fontSize: '0.875rem',
              }}
            >
              {codeString}
            </SyntaxHighlighter>
          </div>
        )
      }
      return (
        <code
          className="bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200 px-1.5 py-0.5 rounded text-sm"
          {...props}
        >
          {children}
        </code>
      )
    },
    p({ children }) {
      return (
        <p className="text-sm mb-2 last:mb-0 leading-relaxed text-gray-800 dark:text-gray-200">
          {children}
        </p>
      )
    },
    ul({ children }) {
      return (
        <ul className="text-sm list-disc pl-4 mb-2 space-y-1 text-gray-800 dark:text-gray-200">
          {children}
        </ul>
      )
    },
    ol({ children }) {
      return (
        <ol className="text-sm list-decimal pl-4 mb-2 space-y-1 text-gray-800 dark:text-gray-200">
          {children}
        </ol>
      )
    },
    li({ children }) {
      return <li className="text-gray-800 dark:text-gray-200">{children}</li>
    },
    strong({ children }) {
      return (
        <strong className="font-semibold text-gray-900 dark:text-gray-100">{children}</strong>
      )
    },
    blockquote({ children }) {
      return (
        <blockquote className="border-l-4 border-gray-300 dark:border-gray-600 pl-3 italic text-gray-600 dark:text-gray-400 mb-2">
          {children}
        </blockquote>
      )
    },
    h1({ children }) {
      return (
        <h1 className="text-lg font-bold mb-2 mt-3 first:mt-0 text-gray-900 dark:text-gray-100">
          {children}
        </h1>
      )
    },
    h2({ children }) {
      return (
        <h2 className="text-base font-bold mb-2 mt-3 first:mt-0 text-gray-900 dark:text-gray-100">
          {children}
        </h2>
      )
    },
    h3({ children }) {
      return (
        <h3 className="text-sm font-semibold mb-1 mt-2 first:mt-0 text-gray-900 dark:text-gray-100">
          {children}
        </h3>
      )
    },
    a({ href, children }) {
      const label = typeof children === 'string' ? children : undefined
      const normalized = href ? normalizeMiniProgramHref(href, label) : { href: href || '', isMp: false }
      const linkHref = normalized.href
      const isMpLink = normalized.isMp
      if (!linkHref) {
        return <span className="text-sm text-gray-800 dark:text-gray-200">{children}</span>
      }
      const handleMpLink = (e: React.MouseEvent<HTMLAnchorElement>) => {
        if (!isMpLink) return
        e.preventDefault()
        const isWechat = isWechatBrowser()
        if (isWechat || linkHref.includes('/mini-program?')) {
          window.location.href = linkHref
          return
        }
        if (typeof (window as any).wx?.miniProgram?.postMessage === 'function') {
          ;(window as any).wx.miniProgram.postMessage({ data: { action: 'launchMiniProgram', url: linkHref } })
          return
        }
        window.location.href = linkHref
      }
      return (
        <a
          href={linkHref}
          onClick={handleMpLink}
          target={isMpLink ? undefined : '_blank'}
          rel={isMpLink ? undefined : 'noopener noreferrer'}
          className={
            isMpLink
              ? 'inline-flex items-center gap-1 text-green-600 dark:text-green-400 underline hover:no-underline font-medium cursor-pointer'
              : 'text-primary-600 dark:text-primary-400 underline hover:no-underline'
          }
        >
          {isMpLink && (
            <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-8.707l-3-3a1 1 0 00-1.414 1.414L10.586 9H7a1 1 0 100 2h3.586l-1.293 1.293a1 1 0 101.414 1.414l3-3a1 1 0 000-1.414z" clipRule="evenodd" />
            </svg>
          )}
          {children}
        </a>
      )
    },
    table({ children }) {
      return (
        <div className="my-3 w-full overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-600">
          <table className="min-w-full text-sm border-collapse">{children}</table>
        </div>
      )
    },
    thead({ children }) {
      return <thead className="bg-gray-50 dark:bg-gray-700/80">{children}</thead>
    },
    tbody({ children }) {
      return <tbody className="divide-y divide-gray-200 dark:divide-gray-600">{children}</tbody>
    },
    tr({ children }) {
      return <tr>{children}</tr>
    },
    th({ children }) {
      return (
        <th className="border-b border-gray-200 dark:border-gray-600 px-3 py-2 text-left font-semibold text-gray-900 dark:text-gray-100 whitespace-nowrap">
          {children}
        </th>
      )
    },
    td({ children }) {
      return (
        <td className="px-3 py-2 align-top text-gray-700 dark:text-gray-300 border-b border-gray-100 dark:border-gray-700 last:border-0">
          {children}
        </td>
      )
    },
  }
}
