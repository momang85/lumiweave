export interface ToolDef {
  name: string
  description: string
  type: string
  handler: string
  properties: Record<string, { type: string; description?: string; enum?: string[]; default?: unknown }>
  required: string[]
  timeout?: number
  requires_approval?: boolean
}

export interface AgentData {
  agent_id: string
  name: string
  description: string
  system_prompt: string
  model_provider: string
  model_name: string
  temperature: number
  max_tokens: number
  tools: ToolDef[]
  tags: string[]
  avatar: string
  suggested_questions: string[]
  mode: string              // v0.5: 运行模式
  mode_config: Record<string, unknown>  // v0.5: 模式配置
  created_at: string
  updated_at: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'tool' | 'system'
  content: string
  toolName?: string
  timestamp: number
}

// v0.5.1: 编排面板 — 子Agent活动记录
export interface AgentActivity {
  id: string
  agentId: string
  agentName: string
  task: string
  status: 'waiting' | 'working' | 'done' | 'failed'
  toolCalls: number
  outputSnippet: string
  needsKey: boolean
  neededProvider: string
  startTime: number
  endTime?: number
}

export interface TemplateData {
  id: string
  name: string
  icon: string
  category: string
  description: string
  tags: string[]
  system_prompt: string
  model: {
    provider: string
    model_name: string
    parameters: { temperature: number; max_tokens: number }
  }
  tools: ToolDef[]
  suggested_questions: string[]
}

export interface KnowledgeStats {
  exists: boolean
  chunks: number
}

export interface SSEEvent {
  type: 'text' | 'tool_call' | 'done' | 'error'
  content?: string
  name?: string
}

// v0.3 新增
export interface ProviderInfo {
  provider: string
  supports_streaming: boolean
  supports_tools: boolean
  supports_vision: boolean
  max_context_tokens: number
  models: string[]
  notes: string
}

export interface DomainInfo {
  domain: string
  name_cn: string
  avatar: string
  tool_count: number
  knowledge_count: number
}

export interface GenerateResult {
  success: boolean
  agent: AgentData | null
  yaml: string
  warnings: string[]
  error: string
  domain: string
}

// v1.0: 会话历史
export interface SessionSummary {
  session_id: string
  agent_id: string
  agent_name: string
  summary: string
  message_count: number
  created_at: string
  updated_at: string
  metadata: {
    dispatch_count: number
    success_count: number
    [key: string]: unknown
  }
}

export interface SessionDetail extends SessionSummary {
  messages: { role: string; content: string }[]
}
