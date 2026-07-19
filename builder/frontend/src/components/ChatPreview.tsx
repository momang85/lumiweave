/**
 * ChatPreview — 右侧对话窗口 v0.7
 *
 * 增强：
 * - 会话耗时显示
 * - 内联子Agent调度卡片
 * - 工具调用统计
 * - 代码块语法高亮样式
 */
import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { Send, Square, Trash2, Plus, Zap, Clock, CheckCircle2, XCircle, Loader2, GitBranch } from 'lucide-react'
import type { AgentData, ChatMessage as ChatMessageType, AgentActivity } from '../types'
import { useAgentChat } from '../hooks/useAgentChat'
import { getStoredKey } from './ApiKeyModal'
import ApiKeyModal from './ApiKeyModal'
import ChatMessage from './ChatMessage'

interface Props {
  agent: AgentData | null
  sessionId?: string
  onOrchestrationChange?: (active: boolean, activities: AgentActivity[]) => void
}

const PROVIDER_COLORS: Record<string, string> = {
  openai: 'bg-green-100 text-green-700',
  anthropic: 'bg-orange-100 text-orange-700',
  google: 'bg-blue-100 text-blue-700',
  deepseek: 'bg-purple-100 text-purple-700',
  ollama: 'bg-gray-100 text-gray-700',
}

export default function ChatPreview({ agent, sessionId, onOrchestrationChange }: Props) {
  const {
    messages, isStreaming, provider, providerDowngraded, originalProvider,
    keyModalProvider,
    activities, isOrchestrating,
    sendMessage, stopStreaming, clearMessages,
    closeKeyModal,
  } = useAgentChat(
    agent?.agent_id ?? null,
    agent?.model_provider,
    agent?.model_name,
    sessionId,
  )

  // 通知父组件编排状态变化
  useEffect(() => {
    onOrchestrationChange?.(isOrchestrating, activities)
  }, [isOrchestrating, activities, onOrchestrationChange])

  const [input, setInput] = useState('')
  const [sessionStart] = useState(Date.now())
  const [elapsed, setElapsed] = useState(0)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Session timer
  useEffect(() => {
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - sessionStart) / 1000)), 1000)
    return () => clearInterval(t)
  }, [sessionStart])

  const dispatchStats = useMemo(() => ({
    total: activities.length,
    working: activities.filter(a => a.status === 'working').length,
    done: activities.filter(a => a.status === 'done').length,
    failed: activities.filter(a => a.status === 'failed').length,
  }), [activities])

  const fmtDuration = (s: number) => {
    if (s < 60) return `${s}s`
    return `${Math.floor(s/60)}m${s%60}s`
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isStreaming])

  const handleSend = () => {
    if (input.trim()) {
      sendMessage(input)
      setInput('')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  if (!agent) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        <div className="text-center">
          <div className="text-5xl mb-4">🤖</div>
          <p className="text-lg font-medium mb-2">选择一个 Agent 开始对话</p>
          <p className="text-sm">在左侧面板创建或选择一个 Agent</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* 头部 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-white">
        <div className="flex items-center gap-2">
          <span className="text-xl">{agent.avatar}</span>
          <div>
            <h3 className="font-semibold text-gray-800 text-sm">{agent.name}</h3>
            <div className="flex items-center gap-1.5">
              <p className="text-xs text-gray-400">{agent.model_name}</p>
              <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${PROVIDER_COLORS[provider] || 'bg-gray-100 text-gray-600'}`}>
                {provider.toUpperCase()}
              </span>
              {providerDowngraded && (
                <span className="text-[10px] text-amber-600" title={`原配置 ${originalProvider.toUpperCase()} 无 Key`}>↓降级</span>
              )}
            </div>
          </div>
        </div>
        {/* 会话计时 + 派发统计 */}
        <div className="flex items-center gap-3">
          {elapsed > 0 && (
            <span className="text-xs text-gray-400 flex items-center gap-1">
              <Clock size={12} />
              {fmtDuration(elapsed)}
            </span>
          )}
          {dispatchStats.total > 0 && (
            <span className="text-xs text-gray-400 flex items-center gap-1" title={`派发${dispatchStats.total}次 成功${dispatchStats.done} 失败${dispatchStats.failed}`}>
              <GitBranch size={12} />
              {dispatchStats.done}/{dispatchStats.total}
            </span>
          )}
        </div>
        <div className="flex gap-1">
          {agent.suggested_questions.length > 0 && (
            <QuickQuestions
              suggestions={agent.suggested_questions}
              onSelect={setInput}
            />
          )}
          <button
            onClick={clearMessages}
            className="p-2 hover:bg-gray-100 rounded-lg text-gray-400"
            title="清空对话"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {/* 消息列表 */}
      <div className="flex-1 overflow-y-auto px-4 py-4 bg-gray-50">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 mt-20">
            <p className="text-sm">发送消息开始测试你的 Agent</p>
            {agent.suggested_questions.length > 0 && (
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {agent.suggested_questions.slice(0, 3).map((q, i) => (
                  <button
                    key={i}
                    onClick={() => sendMessage(q)}
                    className="text-xs px-3 py-1.5 bg-white border border-gray-200 rounded-full hover:bg-primary-50 hover:border-primary-300 text-gray-600 transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {messages.map((msg) => (
          <ChatMessage key={msg.id} msg={msg} />
        ))}

        {isStreaming && (
          <div className="flex justify-start mb-4">
            <div className="bg-white border border-gray-200 rounded-2xl px-4 py-3 shadow-sm">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.1s' }} />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* 输入框 */}
      <div className="px-4 py-3 border-t border-gray-200 bg-white">
        <div className="flex items-center gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入消息测试 Agent..."
            rows={1}
            className="flex-1 resize-none border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
            disabled={isStreaming}
          />
          {isStreaming ? (
            <button
              onClick={stopStreaming}
              className="p-2.5 bg-red-500 text-white rounded-xl hover:bg-red-600 transition-colors"
            >
              <Square size={16} />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim()}
              className="p-2.5 bg-primary-600 text-white rounded-xl hover:bg-primary-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <Send size={16} />
            </button>
          )}
        </div>
      </div>

      {/* API Key 弹窗 */}
      <ApiKeyModal
        open={!!keyModalProvider}
        onClose={closeKeyModal}
        provider={keyModalProvider || ''}
      />
    </div>
  )
}

/** 推荐问题快捷按钮 */
function QuickQuestions({
  suggestions,
  onSelect,
}: {
  suggestions: string[]
  onSelect: (q: string) => void
}) {
  const [open, setOpen] = useState(false)

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="p-2 hover:bg-gray-100 rounded-lg text-gray-400"
        title="推荐问题"
      >
        <Plus size={14} />
      </button>
      {open && (
        <div className="absolute right-0 top-10 w-64 bg-white border border-gray-200 rounded-xl shadow-lg z-50 p-2">
          <p className="text-xs text-gray-400 px-2 py-1">推荐问题</p>
          {suggestions.map((q, i) => (
            <button
              key={i}
              onClick={() => {
                onSelect(q)
                setOpen(false)
              }}
              className="block w-full text-left text-sm px-3 py-2 hover:bg-gray-50 rounded-lg text-gray-700"
            >
              {q}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
