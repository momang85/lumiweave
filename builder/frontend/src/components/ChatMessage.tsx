/**
 * ChatMessage — 单条聊天消息 v0.7
 *
 * 增强：
 * - 超长消息自动折叠（>800字符显示"展开"）
 * - 相对时间显示
 * - Markdown 代码块带语言标签
 */
import { useState } from 'react'
import type { ChatMessage as ChatMessageType } from '../types'

export default function ChatMessage({ msg }: { msg: ChatMessageType }) {
  const isUser = msg.role === 'user'
  const isTool = msg.role === 'tool'
  const isLong = msg.content.length > 800
  const [expanded, setExpanded] = useState(false)

  const displayContent = isLong && !expanded ? msg.content.slice(0, 800) + '\n\n... (点击展开全部)' : msg.content

  const relativeTime = (ts: number) => {
    const now = Date.now()
    const diff = now - ts
    if (diff < 60000) return '刚刚'
    if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
    return new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }

  if (isTool) {
    return (
      <div className="flex justify-center mb-2">
        <div className="text-[10px] text-gray-400 bg-gray-100 px-2 py-0.5 rounded font-mono max-w-[80%] truncate">
          🔧 {msg.toolName}: {msg.content.slice(0, 80)}
        </div>
      </div>
    )
  }

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        onClick={() => isLong && setExpanded(!expanded)}
        className={`max-w-[85%] rounded-2xl px-4 py-3 cursor-pointer transition-colors ${
          isUser
            ? 'bg-primary-600 text-white rounded-br-md'
            : 'bg-white border border-gray-200 shadow-sm rounded-bl-md hover:shadow-md'
        } ${isLong && !expanded ? 'opacity-90' : ''}`}
      >
        {msg.toolName && (
          <div className="text-xs text-amber-600 mb-1 font-mono">🔧 {msg.toolName}</div>
        )}
        <div
          className={`text-sm whitespace-pre-wrap chat-message ${isUser ? '' : 'text-gray-800'}`}
          dangerouslySetInnerHTML={{ __html: formatContent(displayContent) }}
        />
        <div className={`text-[10px] mt-1 flex items-center gap-2 ${isUser ? 'text-primary-200' : 'text-gray-400'}`}>
          <span>{relativeTime(msg.timestamp)}</span>
          {isLong && <span className="text-blue-400">{expanded ? '收起' : '展开全部'}</span>}
        </div>
      </div>
    </div>
  )
}

function formatContent(text: string): string {
  let html = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // 代码块
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    const label = lang ? `<span class="code-lang">${lang}</span>` : ''
    return `<pre class="code-block">${label}<code>${code.trim()}</code></pre>`
  })

  // 行内代码
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')

  // 粗体
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')

  // 换行
  html = html.replace(/\n/g, '<br/>')

  return html
}
