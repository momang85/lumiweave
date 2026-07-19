import type { AgentData, TemplateData, KnowledgeStats, ProviderInfo, DomainInfo, GenerateResult } from './types'

const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

// ── Agent CRUD ──

export function listAgents() {
  return request<{ agents: AgentData[]; count: number }>('/agents')
}

export function getAgent(agentId: string) {
  return request<{ agent: AgentData }>(`/agents/${agentId}`)
}

export function createAgent(data: Partial<AgentData>) {
  return request<{ agent: AgentData }>('/agents', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateAgent(agentId: string, data: Partial<AgentData>) {
  return request<{ agent: AgentData }>(`/agents/${agentId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export function deleteAgent(agentId: string) {
  return request<{ message: string }>(`/agents/${agentId}`, { method: 'DELETE' })
}

export function exportAgentYaml(agentId: string) {
  return request<{ yaml: string }>(`/agents/${agentId}/export`)
}

export function importAgentYaml(yamlContent: string) {
  return request<{ agent: AgentData }>('/agents/import', {
    method: 'POST',
    body: JSON.stringify({ yaml_content: yamlContent }),
  })
}

// ── 增强路由 (v0.3) ──

/** 多格式 ZIP 导出 */
export function exportAgentAll(agentId: string) {
  return fetch(`${BASE}/agents/${agentId}/export/all`).then(async (res) => {
    if (!res.ok) throw new Error('导出失败')
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${agentId}_export.zip`
    a.click()
    URL.revokeObjectURL(url)
  })
}

/** NL → Agent 生成 v0.5 */
export function generateAgent(
  userInput: string,
  domainHint?: string,
  options?: { provider?: string; model?: string; apiKey?: string; apiBase?: string },
) {
  return request<GenerateResult>('/agents/generate', {
    method: 'POST',
    body: JSON.stringify({
      user_input: userInput,
      domain_hint: domainHint,
      provider: options?.provider || 'openai',
      model: options?.model || 'gpt-4o-mini',
      api_key: options?.apiKey || '',
      api_base: options?.apiBase || '',
    }),
  })
}

/** 列出所有 LLM Provider */
export function listProviders() {
  return request<{ providers: ProviderInfo[] }>('/providers')
}

/** 获取 Provider 的模型列表 */
export function getProviderModels(provider: string) {
  return request<{
    provider: string
    models: string[]
    default_model: string
    capabilities: Record<string, unknown>
  }>(`/providers/${provider}/models`)
}

/** 列出所有领域模板 */
export function listDomains() {
  return request<{ domains: DomainInfo[] }>('/domains')
}

// ── Auth v0.4 ──

export function checkProviderKey(provider: string) {
  return request<{ provider: string; has_key: boolean; env_key: string; models: string[]; note: string }>(
    '/auth/check',
    { method: 'POST', body: JSON.stringify({ provider }) },
  )
}

export function getAuthStatus() {
  return request<{
    providers: { provider: string; has_key: boolean; env_key: string; models: string[]; note: string }[]
    any_configured: boolean
    message: string
  }>('/auth/status')
}

// ── Chat v0.4 (支持多 Provider) ──

export interface ChatEvent {
  type: string
  content?: string
  name?: string
  provider?: string
  detail?: string
  total_tokens?: number
  env_key?: string
}

export function chatStream(
  agentId: string,
  message: string,
  onEvent: (event: ChatEvent) => void,
  onError: (err: Error) => void,
  onDone: () => void,
  options?: {
    apiKey?: string
    apiBase?: string
    enableRag?: boolean
    history?: { role: string; content: string }[]
    historyWindow?: number
    sessionId?: string
  },
) {
  const controller = new AbortController()

  fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      agent_id: agentId,
      message,
      enable_rag: options?.enableRag ?? true,
      api_key: options?.apiKey || '',
      api_base: options?.apiBase || '',
      history: options?.history || [],
      history_window: options?.historyWindow ?? 10,
      session_id: options?.sessionId || '',
    }),
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const reader = res.body?.getReader()
      if (!reader) throw new Error('No response body')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.type === 'done') {
                onDone()
                return
              }
              // v0.4: 传递完整的 ChatEvent
              onEvent(data as ChatEvent)
            } catch {
              // 忽略解析错误
            }
          }
        }
      }
      onDone()
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError(err)
      }
    })

  return controller
}

// ── Knowledge ──

export function uploadKnowledge(agentId: string, file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return fetch(`${BASE}/agents/${agentId}/knowledge`, {
    method: 'POST',
    body: formData,
  }).then((r) => r.json())
}

export function getKnowledgeStats(agentId: string) {
  return request<KnowledgeStats>(`/agents/${agentId}/knowledge`)
}

export function deleteKnowledge(agentId: string) {
  return request<{ message: string }>(`/agents/${agentId}/knowledge`, { method: 'DELETE' })
}

// ── Projects (v0.6) ──

export interface ProjectFile {
  name: string
  type: 'dir' | 'file'
  path: string
  size?: number
  children?: ProjectFile[]
  count?: number
}

export interface ProjectTree {
  root: string
  path: string
  items: ProjectFile[]
  count: number
}

export interface FileContent {
  path: string
  content: string
  lines: number
  total_lines: number
  size: number
  truncated: boolean
}

export function listProject(dir?: string) {
  const params = dir ? `?dir=${encodeURIComponent(dir)}` : ''
  return fetch(`${BASE}/projects/list${params}`).then((r) => r.json())
}

export function readProjectFile(path: string, limit?: number) {
  const params = `?path=${encodeURIComponent(path)}&limit=${limit || 500}`
  return fetch(`${BASE}/projects/read${params}`).then((r) => r.json())
}

// ── Templates ──

export function listTemplates() {
  return request<{ templates: TemplateData[]; count: number }>('/templates')
}

export function useTemplate(templateId: string) {
  return request<{ agent: AgentData }>(`/templates/${templateId}/use`, { method: 'POST' })
}

// ── 会话历史 v1.0 ──

import type { SessionSummary, SessionDetail } from './types'

export function listSessions(agentId = '') {
  return request<{ sessions: SessionSummary[] }>(`/sessions?agent_id=${encodeURIComponent(agentId)}`)
}

export function getSession(sessionId: string) {
  return request<SessionDetail>(`/sessions/${sessionId}`)
}

export function deleteSession(sessionId: string) {
  return request<{ message: string }>(`/sessions/${sessionId}`, { method: 'DELETE' })
}
