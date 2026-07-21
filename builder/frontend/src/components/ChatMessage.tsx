/**
 * ChatMessage v1.0 — 智能消息组件
 *
 * - 自动检测选择框/填空框问题，渲染为交互式UI
 * - 思考过程折叠显示（💭 标记）
 * - Agent层级标签
 */
import { useState, useMemo } from 'react'
import type { ChatMessage as ChatMessageType } from '../types'

interface Props {
  msg: ChatMessageType
  onSelectChoice?: (question: string, answer: string) => void
  onFillAnswer?: (question: string, answer: string) => void
  isStreaming?: boolean
}

interface ParsedQuestion {
  type: 'choice' | 'text' | null
  question: string
  options: string[]
  isMulti: boolean
}

interface ChoiceSection {
  title: string
  options: string[]
  isMulti: boolean
}

function parseChoices(text: string): ChoiceSection[] {
  const sections: ChoiceSection[] = []
  
  // 先按 --- 分隔，取第一部分（问题本体）
  const mainPart = text.split(/^---$/m)[0]
  
  // 方法1：按 ##/### 标题分段
  const headingRegex = /(?:^|\n)(#{2,3})\s+([^\n]+)\n([\s\S]*?)(?=\n#{2,3}\s|$)/g
  let match
  while ((match = headingRegex.exec(mainPart)) !== null) {
    const title = match[2].replace(/^\d+[\.\)、]?\s*/, '').trim()
    const body = match[3]
    const options = extractOptions(body)
    if (options.length >= 2 && options.length <= 8) {
      sections.push({ title, options, isMulti: body.includes('多选') })
    }
  }
  
  // 方法2：按 "N. 短标题 N. 选项" 模式分段
  if (sections.length === 0) {
    const lines = mainPart.split('\n')
    let currentTitle = ''
    let currentOptions: string[] = []
    let inSection = false
    
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim()
      if (!line) continue
      
      const shortMatch = line.match(/^(\d+)[\.\)、]\s*(.{1,20})$/)
      const longMatch = line.match(/^(\d+)[\.\)、]\s*(.+)$/)
      
      if (shortMatch && shortMatch[1] === '1') {
        // 新section开始：之前有内容就保存
        if (currentOptions.length >= 2) {
          sections.push({ title: currentTitle, options: [...currentOptions], isMulti: false })
        }
        currentTitle = shortMatch[2]
        currentOptions = []
        inSection = true
      } else if (inSection && longMatch) {
        currentOptions.push(longMatch[2])
      }
    }
    // 最后一个section
    if (currentOptions.length >= 2) {
      sections.push({ title: currentTitle, options: currentOptions, isMulti: false })
    }
  }
  
  // 方法3：整段提取（单section）
  if (sections.length === 0) {
    const options = extractOptions(mainPart)
    if (options.length >= 2 && options.length <= 8) {
      const title = mainPart.split('\n')[0].replace(/^#+\s*/, '').replace(/^\d+[\.\)、]?\s*/, '').trim() || '请选择'
      sections.push({ title, options, isMulti: mainPart.includes('多选') })
    }
  }
  
  return sections
}

function extractOptions(body: string): string[] {
  const options: string[] = []
  const optRegex = /(\d+)[\.\)、]\s*(.+?)(?=\n\d+[\.\)、]|\n?$)/g
  let m
  while ((m = optRegex.exec(body)) !== null) {
    options.push(m[2].trim())
  }
  return options
}

function parseQuestion(text: string): ParsedQuestion {
  // 检测填空题
  const fillMatch = text.match(/请输入|填写|回复你的选择/)
  if (fillMatch && !text.match(/\d+[\.\)、]/)) {
    return { type: 'text', question: text.trim(), options: [], isMulti: false }
  }
  
  // 检测编号列表
  const options: string[] = []
  const numberedPattern = /(\d+)[\.\)、]\s*(.+?)(?=\n\d+[\.\)、]|\n\n|$)/g
  let match
  while ((match = numberedPattern.exec(text)) !== null) {
    options.push(match[2].trim())
  }

  if (options.length >= 2 && options.length <= 8) {
    const optStart = text.indexOf(`1${text[text.indexOf('1')+1] || '.'}`)
    const question = optStart > 0 ? text.slice(0, optStart).replace(/^#+\s*/, '').trim() : text.split('\n')[0].trim()
    const isMulti = text.includes('多选') || text.includes('可多选')
    return { type: 'choice', question, options, isMulti }
  }

  return { type: null, question: '', options: [], isMulti: false }
}

export default function ChatMessage({ msg, onSelectChoice, onFillAnswer, isStreaming }: Props) {
  const isUser = msg.role === 'user'
  const isTool = msg.role === 'tool'
  const isLong = msg.content.length > 800
  const [expanded, setExpanded] = useState(false)
  const [showThinking, setShowThinking] = useState(false)
  const [fillValue, setFillValue] = useState('')
  const [selections, setSelections] = useState<Record<number, string>>({})

  // 分离思考过程和正文
  const { thinking, mainContent } = useMemo(() => {
    const t = msg.content || ''
    const thinkMatch = t.match(/💭([\s\S]*?)(?=💭|$)/)
    if (thinkMatch) {
      return { thinking: thinkMatch[1].trim(), mainContent: t.replace(thinkMatch[0], '').trim() }
    }
    // Also check for reasoning in thinking field
    if ((msg as any).thinking) {
      return { thinking: (msg as any).thinking, mainContent: t }
    }
    return { thinking: '', mainContent: t }
  }, [msg.content, (msg as any).thinking])

  // 检测问题
  const parsed = useMemo(() => isUser ? { type: null as any, question: '', options: [], isMulti: false } : parseQuestion(mainContent), [mainContent, isUser])
  const choiceSections = useMemo(() => isUser ? [] : parseChoices(mainContent), [mainContent, isUser])

  const displayContent = isLong && !expanded ? mainContent.slice(0, 800) + '\n\n... (点击展开全部)' : mainContent
  const relativeTime = (ts: number) => {
    const diff = Date.now() - ts
    if (diff < 60000) return '刚刚'
    if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
    return new Date(ts).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }

  const handleChoice = (option: string) => {
    onSelectChoice?.(parsed.question, option)
  }

  const handleFillSubmit = () => {
    if (fillValue.trim()) {
      onFillAnswer?.(parsed.question, fillValue.trim())
      setFillValue('')
    }
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
      <div className={`max-w-[88%] ${isUser ? 'w-auto' : 'w-full'}`}>
        {/* Agent层级标签 */}
        {!isUser && (msg as any).agentLayer && (
          <div className="text-[10px] text-gray-400 mb-1 ml-1">
            {((msg as any).agentLayer === 1 ? '🧠 规划师' : (msg as any).agentLayer === 2 ? '🎯 调度中心' : '🐍 子Agent')}
            {(msg as any).agentName && <span className="ml-1 text-gray-300">{(msg as any).agentName}</span>}
          </div>
        )}

        {/* 思考过程 */}
        {thinking && (
          <div className="mb-2">
            <button
              onClick={() => setShowThinking(!showThinking)}
              className="text-[10px] text-blue-500 hover:text-blue-700 flex items-center gap-1"
            >
              💭 {showThinking ? '收起思考' : '查看思考过程'}
            </button>
            {showThinking && (
              <div className="mt-1 p-2 bg-blue-50 rounded-lg border border-blue-100 text-[11px] text-gray-600 italic whitespace-pre-wrap">
                {thinking}
              </div>
            )}
          </div>
        )}

        {/* 消息气泡 */}
        <div
          onClick={() => isLong && setExpanded(!expanded)}
          className={`rounded-2xl px-4 py-3 ${isLong && !expanded ? 'opacity-90 cursor-pointer' : ''} ${
            isUser
              ? 'bg-primary-600 text-white rounded-br-md'
              : 'bg-white border border-gray-200 shadow-sm rounded-bl-md'
          }`}
        >
          {msg.toolName && (
            <div className="text-xs text-amber-600 mb-1 font-mono">🔧 {msg.toolName}</div>
          )}
          
          {/* 流式输出指示器 */}
          {isStreaming && !mainContent && (
            <div className="text-sm text-gray-400 animate-pulse">思考中...</div>
          )}

          <div
            className={`text-sm whitespace-pre-wrap chat-message ${isUser ? '' : 'text-gray-800'}`}
            dangerouslySetInnerHTML={{ __html: formatContent(displayContent) }}
          />

          {/* 多段选择框 */}
          {choiceSections.length > 0 && !isStreaming && (
            <div className="mt-3 border-t border-gray-100 pt-3 space-y-3">
              {choiceSections.map((section, si) => (
                <div key={si}>
                  <div className="text-[11px] font-semibold text-gray-700 mb-1.5">
                    {section.title}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {section.options.map((opt, oi) => {
                      const isSel = selections[si] === opt
                      return (
                        <button
                          key={oi}
                          onClick={() => {
                            const up = { ...selections }
                            if (selections[si] === opt) delete up[si]
                            else up[si] = opt
                            setSelections(up)
                          }}
                          className={`px-3 py-1.5 text-[12px] rounded-full border transition-colors ${
                            isSel
                              ? 'border-primary-500 bg-primary-600 text-white'
                              : 'border-primary-300 text-primary-700 bg-primary-50 hover:bg-primary-100'
                          }`}
                        >
                          {isSel && '✓ '}{opt}
                        </button>
                      )
                    })}
                  </div>
                </div>
              ))}
              {Object.keys(selections).length > 0 && (
                <button
                  onClick={() => {
                    const answers = choiceSections
                      .map((s, i) => selections[i] ? `${s.title}: ${selections[i]}` : null)
                      .filter(Boolean)
                      .join('\n')
                    onSelectChoice?.('', answers)
                    setSelections({})
                  }}
                  className="w-full py-2 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 transition-colors"
                >
                  提交选择 →
                </button>
              )}
            </div>
          )}

          {/* 交互式选择框 */}
          {parsed.type === 'choice' && !isStreaming && (
            <div className="mt-3 border-t border-gray-100 pt-3">
              <div className="text-[10px] text-gray-400 mb-2">
                {parsed.isMulti ? '（可多选，点击选项回复）' : '（点击选项快速回复）'}
              </div>
              <div className="flex flex-wrap gap-1.5">
                {parsed.options.map((opt, i) => (
                  <button
                    key={i}
                    onClick={() => handleChoice(opt)}
                    className="px-3 py-1.5 text-[12px] rounded-full border border-primary-300 text-primary-700 bg-primary-50 hover:bg-primary-100 hover:border-primary-500 transition-colors"
                  >
                    {opt}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 交互式填空框 */}
          {parsed.type === 'text' && !isStreaming && (
            <div className="mt-3 border-t border-gray-100 pt-3">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={fillValue}
                  onChange={e => setFillValue(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleFillSubmit()}
                  placeholder="输入你的答案..."
                  className="flex-1 border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-primary-400"
                  autoFocus
                />
                <button
                  onClick={handleFillSubmit}
                  className="px-4 py-1.5 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700"
                >
                  → 
                </button>
              </div>
            </div>
          )}

          <div className={`text-[10px] mt-1 flex items-center gap-2 ${isUser ? 'text-primary-200' : 'text-gray-400'}`}>
            <span>{relativeTime(msg.timestamp)}</span>
            {isLong && <span className="text-blue-400">{expanded ? '收起' : '展开全部'}</span>}
          </div>
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
