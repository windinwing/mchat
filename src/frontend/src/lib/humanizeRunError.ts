/**
 * 把工作流运行/节点的原始错误（Python traceback、pip stderr、连接超时等）
 * 转成用户可读的友好提示。
 *
 * 工作流错误链路：技能异常 → {"error": str(exc)} → node_run.error → run.error。
 * 原始内容常含完整 Python traceback、文件路径、pip 输出，普通用户看不懂。
 * 这里做模式匹配，返回 { title, hint }；调用方再决定如何展示原始错误（折叠）。
 */

export interface HumanizedError {
  /** 一句话标题（友好）。 */
  title: string
  /** 补充说明（可空）。 */
  hint?: string
  /** 是否建议用户重试。 */
  retryable: boolean
}

export function humanizeRunError(error: string | null | undefined): HumanizedError {
  const raw = (error || '').trim()
  if (!raw) {
    return { title: '节点执行失败，未返回详细错误信息', retryable: false }
  }
  const lower = raw.toLowerCase()

  // 依赖缺失（技能 import 失败）
  const modMatch = raw.match(/ModuleNotFoundError: No module named '([^']+)'/)
  if (modMatch) {
    return {
      title: `技能依赖缺失（${modMatch[1]}）`,
      hint: '系统会自动安装依赖。若刚创建/重建容器，请稍后重试；持续报错请联系管理员。',
      retryable: true,
    }
  }
  // pip 安装失败
  if (lower.includes('容器内依赖安装失败') || lower.includes('pip install failed') || lower.includes('依赖安装失败')) {
    return {
      title: '技能依赖安装失败',
      hint: '请稍后重试。若多次失败，可能是网络问题或依赖冲突，请联系管理员。',
      retryable: true,
    }
  }
  // 数据源限流
  if (lower.includes('too many requests') || lower.includes('rate limit')) {
    return {
      title: '数据源请求过于频繁',
      hint: '上游数据接口限流，请稍后再试。',
      retryable: true,
    }
  }
  // 网络/连接/超时
  if (lower.includes('timeout') || lower.includes('timed out')) {
    return {
      title: '请求超时',
      hint: '网络或数据源响应超时，请稍后重试。',
      retryable: true,
    }
  }
  if (lower.includes('connection') && (lower.includes('refused') || lower.includes('reset') || lower.includes('aborted') || lower.includes('unreachable'))) {
    return {
      title: '网络连接失败',
      hint: '无法连接到数据源或服务，请稍后重试。',
      retryable: true,
    }
  }
  // 东财/数据源风控
  if (lower.includes('remotedisconnected') || lower.includes('403') && lower.includes('forbidden')) {
    return {
      title: '数据源访问被拒',
      hint: '上游数据接口拒绝了请求（可能风控），请稍后重试。',
      retryable: true,
    }
  }
  // 技能未找到
  if (lower.includes('skill not found') || lower.includes('no module named') && lower.includes('main')) {
    return {
      title: '技能未找到或未安装',
      hint: '工作流引用的技能不存在，请检查编排或联系管理员。',
      retryable: false,
    }
  }
  // 权限
  if (lower.includes('not allowed') || lower.includes('forbidden') || lower.includes('permission')) {
    return {
      title: '权限不足',
      hint: '当前账户无权执行此操作。',
      retryable: false,
    }
  }
  // 通用兜底：取前几行非空行做标题
  const lines = raw.split('\n').map((l) => l.trim()).filter(Boolean)
  const firstLine = lines[0].slice(0, 160)
  return {
    title: firstLine || '执行失败',
    hint: lines.length > 1 ? undefined : undefined,
    retryable: false,
  }
}
