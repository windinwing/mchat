/** Detect patent-search tool output block. */
export function isPatentSearchContent(content: string): boolean {
  const text = content.trim()
  if (!text) return false
  if (text.startsWith('```') && text.includes('🔍 搜索完成')) return true
  return text.includes('🔍 搜索完成') && text.includes('📊 找到')
}

/** GFM pipe table (header row + separator). */
export function hasMarkdownTable(content: string): boolean {
  const lines = content.split('\n')
  for (let i = 0; i < lines.length - 1; i += 1) {
    const line = lines[i].trim()
    if (!line.startsWith('|') || !line.endsWith('|')) continue
    const next = lines[i + 1]?.trim() ?? ''
    if (/^\|[\s:|-]+\|$/.test(next)) return true
  }
  return false
}

function splitTableRow(line: string): string[] {
  if (line.includes('\t')) {
    return line.split('\t').map((cell) => cell.trim())
  }
  if (line.includes('|')) {
    return line
      .split('|')
      .map((cell) => cell.trim())
      .filter(Boolean)
  }
  return [line.trim()]
}

function isTabTableHeader(line: string): boolean {
  const trimmed = line.trim()
  return /^序号[\t|]/.test(trimmed) && trimmed.includes('专利号')
}

function isTabTableDataRow(line: string): boolean {
  const trimmed = line.trim()
  if (!trimmed) return false
  if (line.includes('\t')) return /^\d+\t/.test(trimmed)
  if (line.includes('|')) return /^\d+\s*\|/.test(trimmed)
  return false
}

function toPipeRow(cells: string[]): string {
  const escaped = cells.map((cell) => cell.replace(/\|/g, '\\|'))
  return `| ${escaped.join(' | ')} |`
}

/** Convert LLM tab-separated patent tables to GFM pipe tables for ReactMarkdown. */
export function convertTabTablesToMarkdown(content: string): string {
  const lines = content.split('\n')
  const out: string[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]
    if (isTabTableHeader(line)) {
      const tableLines: string[] = [line]
      i += 1
      while (i < lines.length && isTabTableDataRow(lines[i])) {
        tableLines.push(lines[i])
        i += 1
      }

      const rows = tableLines.map(splitTableRow).filter((row) => row.length > 1)
      if (rows.length >= 1) {
        const [header, ...body] = rows
        out.push(toPipeRow(header))
        out.push(`| ${header.map(() => '---').join(' | ')} |`)
        for (const row of body) {
          const cells = [...row]
          while (cells.length < header.length) cells.push('')
          out.push(toPipeRow(cells.slice(0, header.length)))
        }
        continue
      }

      out.push(line)
      i += 1
      continue
    }

    out.push(line)
    i += 1
  }

  return out.join('\n')
}

/** Strip legacy ```text fences from server-side formatting experiments. */
export function stripPatentTextFence(content: string): string {
  const trimmed = content.trim()
  const fenced = trimmed.match(/^```(?:text|plaintext)?\n([\s\S]*?)\n```$/i)
  if (fenced) return fenced[1].trimEnd()
  return content
}

/** Full patent-search reply: header + tab table + 初步观察 (LLM presentation). */
export function isPatentSearchPresentation(content: string): boolean {
  const text = content.trim()
  if (!isPatentSearchContent(text)) return false
  return (
    text.includes('初步观察')
    || text.includes('序号\t专利号')
    || text.includes('序号 | 专利号')
  )
}

function hasTabTable(content: string): boolean {
  return content.split('\n').some(isTabTableHeader)
}

/**
 * Prepare assistant markdown for ReactMarkdown:
 * - Full patent presentation: convert tab tables → GFM pipe tables
 * - Raw patent CLI emoji list: wrap in ```text to avoid "1." ordered-list styling
 */
export function prepareAssistantMarkdown(content: string): string {
  const stripped = stripPatentTextFence(content)

  if (!isPatentSearchContent(stripped)) {
    return hasTabTable(stripped) ? convertTabTablesToMarkdown(stripped) : stripped
  }

  if (isPatentSearchPresentation(stripped) || hasMarkdownTable(stripped)) {
    return hasTabTable(stripped)
      ? convertTabTablesToMarkdown(stripped)
      : stripped
  }

  return `\`\`\`text\n${stripPatentTextFence(stripped)}\n\`\`\``
}

/**
 * Convert dot-separated operation text into clickable action links.
 * e.g. "下一页 · 导出Excel" → "[下一页](action:下一页) · [导出Excel](action:导出Excel)"
 * Idempotent - skips text that already contains action links.
 */
export function injectActionLinksInMarkdown(content: string): string {
  if (!content || content.includes('](action:')) return content
  return content.replace(
    /(?:^|\n)([^·\n]+(?:·[^·\n]+){2,})/gm,
    (_, ops: string) => {
      const items = ops.split(/·/).map(s => s.trim()).filter(Boolean)
      if (items.length <= 1) return _
      const linked = items
        .filter(item => !item.includes(']('))
        .map(item => `[${item}](action:${item})`)
      if (!linked.length) return _
      return linked.join(' · ')
    },
  )
}
