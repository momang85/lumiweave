/**
 * useAgentChat v0.5.1 — Agent 绑定聊天 Hook
 *
 * 核心逻辑：
 * 1. 运行时强制使用 Agent 绑定的 model_provider/model_name
 * 2. API Key 缺失 → 后端返回 no_api_key 事件 → 弹窗
 * 3. 编排状态追踪 → agent_dispatch/agent_result 事件 → AgentActivity[]
 */
import { useState, useRef, useCallback } from 'react'
import type { ChatMessage, AgentActivity } from '../types'
import { chatStream, type ChatEvent } from '../api'
import { getStoredKey, getStoredBase } from '../components/ApiKeyModal'

/** 判断错误事件是否与 API Key 相关 */
function isApiKeyError(event: ChatEvent): boolean {
  if (event.type === 'no_api_key') return true
  if (event.type === 'error') {
    const msg = ((event.content || '') + (event.detail || '')).toLowerCase()
    return msg.includes('api') || msg.includes('key')
      || msg.includes('未设置') || msg.includes('auth')
      || msg.includes('401') || msg.includes('认证')
  }
  return false
}

export function useAgentChat(
  agentId: string | null,
  agentProvider?: string,
  agentModel?: string,
  sessionId?: string,
) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [keyModalProvider, setKeyModalProvider] = useState<string | null>(null)
  const [activities, setActivities] = useState<AgentActivity[]>([])
  const [isOrchestrating, setIsOrchestrating] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const revertTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const originalProvider = (agentProvider || 'openai').toLowerCase()

  // v0.6: 自动降级 — 如果当前 Provider 没有 Key，尝试已配置的其他 Provider
  const provider = (() => {
    if (originalProvider === 'ollama') return 'ollama'
    if (getStoredKey(originalProvider)) return originalProvider
    // 尝试其他已配置的 Provider
    for (const p of ['deepseek', 'openai', 'anthropic', 'google']) {
      if (getStoredKey(p)) return p
    }
    return originalProvider // 都没有，保持原样（弹窗提示）
  })()
  const providerDowngraded = provider !== originalProvider

  const sendMessage = useCallback(
    (text: string) => {
      // 清除上一次编排的还原定时器
      if (revertTimerRef.current) { clearTimeout(revertTimerRef.current); revertTimerRef.current = null }
      setIsOrchestrating(false)
      setActivities([])

      if (!agentId || !text.trim() || isStreaming) return

      // ── 前置 Key 检查：无 Key 立即弹窗，不发送请求 ──
      const apiKey = getStoredKey(provider)
      if (!apiKey && provider !== 'ollama') {
        setKeyModalProvider(provider)
        return
      }
      const apiBase = getStoredBase(provider)

      // 捕获当前历史（不含即将添加的新消息）
      const messageHistory = [...messages]

      const userMsg: ChatMessage = {
        id: `u-${Date.now()}`,
        role: 'user',
        content: text,
        timestamp: Date.now(),
      }

      const assistantMsg: ChatMessage = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
      }

      setMessages((prev) => [...prev, userMsg, assistantMsg])
      setIsStreaming(true)

      const controller = chatStream(
        agentId,
        text,
        (event: ChatEvent) => {
          // ── 检测 API Key 相关错误 ──
          if (isApiKeyError(event)) {
            const prov = (event as any).provider || provider
            setKeyModalProvider(prov)
            setMessages((prev) => {
              const last = prev[prev.length - 1]
              if (!last || last.role !== 'assistant') return prev
              return [
                ...prev.slice(0, -1),
                {
                  ...last,
                  content:
                    event.type === 'no_api_key'
                      ? `[需要 API Key] ${event.content || '请配置 ' + prov.toUpperCase() + ' API Key'}`
                      : `[认证失败] ${event.content || event.detail || '请检查 API Key'}`,
                },
              ]
            })
            setIsStreaming(false)
            return
          }

          // v0.5.1: 编排事件处理
          if (event.type === 'orchestration_start') {
            setIsOrchestrating(true)
            return
          }

          if (event.type === 'agent_dispatch') {
            setIsOrchestrating(true)
            setActivities((prev) => {
              const agentId = (event as any).agent_id || ''
              const task = (event as any).task || ''
              // 避免重复
              if (prev.some(a => a.agentId === agentId && a.status === 'working')) return prev
              return [...prev, {
                id: `act-${Date.now()}`,
                agentId,
                agentName: (event as any).agent_name || agentId,
                task: task.slice(0, 80),
                status: 'working' as const,
                toolCalls: 0,
                outputSnippet: '',
                needsKey: false,
                neededProvider: '',
                startTime: Date.now(),
              }]
            })
            return
          }

          if (event.type === 'agent_result') {
            setActivities((prev) => prev.map(a => {
              const e = event as any
              if (a.agentId === e.agent_id && a.status === 'working') {
                return {
                  ...a,
                  agentName: e.agent_name || a.agentName,
                  status: e.success ? 'done' as const : 'failed' as const,
                  toolCalls: e.tool_calls || 0,
                  outputSnippet: (e.output_snippet || '').slice(0, 120),
                  needsKey: e.needs_key || false,
                  neededProvider: e.needed_provider || '',
                  endTime: Date.now(),
                }
              }
              return a
            }))
            return
          }

          setMessages((prev) => {
            const last = prev[prev.length - 1]
            if (!last || last.role !== 'assistant') return prev

            if (event.type === 'text') {
              return [
                ...prev.slice(0, -1),
                { ...last, content: last.content + (event.content || '') },
              ]
            }
            if (event.type === 'tool_call') {
              // 在思考区展示
              return [
                ...prev.slice(0, -1),
                {
                  ...last,
                  thinking: (last as any).thinking + `\n🔧 ${event.name || ''}`,
                  toolName: event.name,
                },
              ]
            }
            if (event.type === 'info') {
              const c = (event.content || '')
              // 跳过纯工具执行日志（这些进 RuntimeLogs）
              if (c.includes('[执行工具]') || c.includes('工具调用结果') || c.includes('[工具调用]') || c.includes('上下文:')) {
                return prev
              }
              // 只显示关键状态更新
              if (c.includes('正在分析') || c.includes('正在生成') || c.includes('完成')) {
                return [
                  ...prev.slice(0, -1),
                  { ...last, content: last.content + `\n${c}` },
                ]
              }
              return prev
            }
            if (event.type === 'reasoning') {
              // DeepSeek R1 思维链 — 连续累积，不截断
              return [
                ...prev.slice(0, -1),
                { ...last, content: last.content + (event.content || '') },
              ]
            }
            if (event.type === 'error') {
              return [
                ...prev.slice(0, -1),
                {
                  ...last,
                  content:
                    last.content +
                    `\n\n[错误] ${event.content || event.detail}`,
                },
              ]
            }
            return prev
          })
        },
        (err) => {
          setMessages((prev) => {
            const last = prev[prev.length - 1]
            if (!last || last.role !== 'assistant') return prev
            return [
              ...prev.slice(0, -1),
              { ...last, content: last.content + `\n\n[网络错误] ${err.message}` },
            ]
          })
          setIsStreaming(false)
          setIsOrchestrating(false)
        },
        () => {
          setIsStreaming(false)
          // v0.5.1: 延迟5秒还原编排面板，让用户有时间查看结果
          if (revertTimerRef.current) clearTimeout(revertTimerRef.current)
          revertTimerRef.current = setTimeout(() => setIsOrchestrating(false), 5000)
        },
        {
          // v0.5: sessionStorage Key 发送给后端（dev 环境）
          apiKey,
          apiBase,
          enableRag: true,
          // 发送对话历史（不含当前消息和占位 assistant）
          history: messageHistory.map((m: ChatMessage) => ({
            role: m.role,
            content: m.content,
          })),
          historyWindow: 10,
          sessionId,
        },
      )

      abortRef.current = controller
    },
    [agentId, isStreaming, provider, messages],
  )

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort()
    setIsStreaming(false)
    setIsOrchestrating(false)
  }, [])

  const clearMessages = useCallback(() => {
    setMessages([])
    setActivities([])
    setIsOrchestrating(false)
  }, [])

  return {
    messages,
    isStreaming,
    provider,
    providerDowngraded,
    originalProvider,
    keyModalProvider,
    activities,
    isOrchestrating,
    sendMessage,
    stopStreaming,
    clearMessages,
    closeKeyModal: () => setKeyModalProvider(null),
  }
}
