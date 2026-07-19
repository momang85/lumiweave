/**
 * AgentConfigPanel — 左侧 Agent 配置面板
 *
 * 包含：基本信息、System Prompt、模型参数、Tools 管理
 */
import { useState, useEffect } from 'react'
import { Save, Download, PackageOpen, Upload, Trash2, Plus, X, ChevronDown, ChevronRight } from 'lucide-react'
import type { AgentData, ToolDef } from '../types'
import * as api from '../api'
import KnowledgeUploader from './KnowledgeUploader'

interface Props {
  agent: AgentData | null
  onAgentChange: (agent: AgentData) => void
  onAgentDelete: (agentId: string) => void
  agents: AgentData[]
  onSelectAgent: (id: string) => void
}

export default function AgentConfigPanel({
  agent,
  onAgentChange,
  onAgentDelete,
  agents,
  onSelectAgent,
}: Props) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [systemPrompt, setSystemPrompt] = useState('')
  const [modelProvider, setModelProvider] = useState('openai')
  const [modelName, setModelName] = useState('gpt-4o-mini')
  const [temperature, setTemperature] = useState(0.7)
  const [maxTokens, setMaxTokens] = useState(4096)
  const [tools, setTools] = useState<ToolDef[]>([])
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([])
  const [suggestedQuestionInput, setSuggestedQuestionInput] = useState('')  // 新增问题输入
  const [saving, setSaving] = useState(false)
  const [showToolEditor, setShowToolEditor] = useState(false)
  const [importing, setImporting] = useState(false)
  const [mode, setMode] = useState('simple')              // v0.5
  const [modeConfig, setModeConfig] = useState<Record<string, unknown>>({})  // v0.5
  const [exportingAll, setExportingAll] = useState(false)

  // 将 OpenAI 格式工具转换为扁平 ToolDef 格式
  const normalizeTools = (rawTools: any[]): ToolDef[] => {
    if (!Array.isArray(rawTools)) return []
    return rawTools.map((t) => {
      // OpenAI 格式: { type: 'function', function: { name, description, parameters: {...} } }
      if (t && typeof t === 'object' && t.function) {
        const fn = t.function
        const params = fn.parameters || {}
        return {
          name: fn.name || '',
          description: fn.description || '',
          type: 'function',
          handler: fn.name || '',
          properties: params.properties || {},
          required: params.required || [],
          timeout: 30,
          requires_approval: false,
        } as ToolDef
      }
      // 已经是扁平格式
      return t as ToolDef
    })
  }

  useEffect(() => {
    if (agent) {
      setName(agent.name)
      setDescription(agent.description)
      setSystemPrompt(agent.system_prompt)
      setModelProvider(agent.model_provider || 'openai')
      setModelName(agent.model_name)
      setTemperature(agent.temperature)
      setMaxTokens(agent.max_tokens)
      setTools(normalizeTools(agent.tools))
      setSuggestedQuestions(agent.suggested_questions || [])
      setMode(agent.mode || 'simple')
      setModeConfig(agent.mode_config || {})
    }
  }, [agent])

  // 模式元信息
  const MODE_OPTIONS = [
    { value: 'simple',     label: '简单模式',    icon: '💬', desc: '标准 LLM 对话 + Function Calling' },
    { value: 'react',      label: 'ReAct 推理', icon: '🧠', desc: 'Thought → Action → Observation 循环推理' },
    { value: 'planner',    label: 'Planner 规划', icon: '📋', desc: 'LLM 拆解任务 → 顺序执行步骤' },
    { value: 'reflection', label: 'Reflection 反思', icon: '🪞', desc: '生成 → 自评 → 纠错 → 再生' },
  ]

  // Provider 切换时自动更换默认模型名
  const DEFAULT_MODELS: Record<string, string> = {
    openai: 'gpt-4o-mini',
    anthropic: 'claude-3-5-sonnet-20241022',
    google: 'gemini-2.0-flash',
    ollama: 'llama3.2',
    deepseek: 'deepseek-chat',
  }
  const handleProviderChange = (prov: string) => {
    setModelProvider(prov)
    setModelName(DEFAULT_MODELS[prov] || '')
  }

  const handleExportAll = async () => {
    if (!agent) return
    setExportingAll(true)
    try {
      await api.exportAgentAll(agent.agent_id)
    } catch (e: unknown) {
      alert(`导出失败: ${e instanceof Error ? e.message : e}`)
    }
    setExportingAll(false)
  }

  const handleSave = async () => {
    if (!agent) return
    setSaving(true)
    try {
      const { agent: updated } = await api.updateAgent(agent.agent_id, {
        name,
        description,
        mode,
        mode_config: modeConfig,
        system_prompt: systemPrompt,
        model_provider: modelProvider,
        model_name: modelName,
        temperature,
        max_tokens: maxTokens,
        tools,
        suggested_questions: suggestedQuestions,
      })
      onAgentChange(updated)
    } catch (e: unknown) {
      alert(`保存失败: ${e instanceof Error ? e.message : e}`)
    }
    setSaving(false)
  }

  const handleExport = async () => {
    if (!agent) return
    try {
      const { yaml } = await api.exportAgentYaml(agent.agent_id)
      const blob = new Blob([yaml], { type: 'text/yaml' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${agent.name}.yaml`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e: unknown) {
      alert(`导出失败: ${e instanceof Error ? e.message : e}`)
    }
  }

  const handleImport = () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.yaml,.yml'
    input.onchange = async () => {
      const file = input.files?.[0]
      if (!file) return
      setImporting(true)
      try {
        const text = await file.text()
        const { agent: imported } = await api.importAgentYaml(text)
        onSelectAgent(imported.agent_id)
      } catch (e: unknown) {
        alert(`导入失败: ${e instanceof Error ? e.message : e}`)
      }
      setImporting(false)
    }
    input.click()
  }

  const handleDelete = async () => {
    if (!agent) return
    if (!confirm(`确定删除 "${agent.name}"？此操作不可撤销。`)) return
    try {
      await api.deleteAgent(agent.agent_id)
      onAgentDelete(agent.agent_id)
    } catch (e: unknown) {
      alert(`删除失败: ${e instanceof Error ? e.message : e}`)
    }
  }

  const handleCreateNew = async () => {
    try {
      const { agent: created } = await api.createAgent({
        name: '我的 Agent',
        description: '',
        system_prompt: '你是一个有用的AI助手。',
      })
      onSelectAgent(created.agent_id)
    } catch (e: unknown) {
      alert(`创建失败: ${e instanceof Error ? e.message : e}`)
    }
  }

  const addTool = () => {
    setTools([
      ...tools,
      {
        name: '',
        description: '',
        type: 'function',
        handler: '',
        properties: {},
        required: [],
      },
    ])
    setShowToolEditor(true)
  }

  const updateTool = (index: number, updates: Partial<ToolDef>) => {
    const newTools = [...tools]
    newTools[index] = { ...newTools[index], ...updates }
    setTools(newTools)
  }

  const removeTool = (index: number) => {
    setTools(tools.filter((_, i) => i !== index))
  }

  return (
    <div className="flex flex-col h-full">
      {/* 头部 + Agent 选择器 */}
      <div className="px-4 py-3 border-b border-gray-200 bg-white">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-bold text-gray-800">Agent Builder</h2>
          <div className="flex gap-1">
            <button
              onClick={handleCreateNew}
              className="text-xs px-2 py-1 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
            >
              + 新建
            </button>
            <button
              onClick={handleImport}
              disabled={importing}
              className="p-1.5 hover:bg-gray-100 rounded-lg text-gray-400"
              title="导入 YAML"
            >
              <Upload size={14} />
            </button>
          </div>
        </div>

        {/* Agent 列表 — v0.5.2: 调度中心置顶 + 特殊标志 */}
        <select
          value={agent?.agent_id || ''}
          onChange={(e) => onSelectAgent(e.target.value)}
          className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary-500"
        >
          <option value="">选择 Agent...</option>
          {agents
            .slice()
            .sort((a, b) => {
              const isOrchA = a.name.includes('调度') || a.agent_id.includes('367c2a16')
              const isOrchB = b.name.includes('调度') || b.agent_id.includes('367c2a16')
              if (isOrchA && !isOrchB) return -1
              if (!isOrchA && isOrchB) return 1
              return 0
            })
            .map((a) => {
              const isOrch = a.name.includes('调度') || a.agent_id.includes('367c2a16')
              return (
                <option key={a.agent_id} value={a.agent_id}
                  className={isOrch ? 'font-semibold' : ''}
                >
                  {isOrch ? '🎯 ' : ''}{a.avatar} {a.name}{isOrch ? ' [中枢]' : ''}
                </option>
              )
            })}
        </select>
      </div>

      {!agent && (
        <div className="flex-1 flex items-center justify-center text-gray-400 px-4">
          <div className="text-center">
            <p className="text-sm">创建新 Agent 或从上方列表选择</p>
          </div>
        </div>
      )}


      {agent && (
        <>
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
          {/* 基本信息 */}
          <Section title="基本信息">
            <label className="text-xs text-gray-500 font-medium">名称</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm mt-1 focus:outline-none focus:border-primary-500"
            />
            <label className="text-xs text-gray-500 font-medium mt-3 block">描述</label>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm mt-1 focus:outline-none focus:border-primary-500"
            />
          </Section>

          {/* System Prompt */}
          <Section title="System Prompt">
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              rows={6}
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm mt-1 font-mono focus:outline-none focus:border-primary-500 resize-y"
              placeholder="定义 Agent 的角色、行为规则、输出格式..."
            />
            <div className="text-[10px] text-gray-400 mt-1 text-right">
              {systemPrompt.length} 字符
            </div>
          </Section>

          {/* 运行模式 v0.5 */}
          <Section title="运行模式">
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-1.5">
                {MODE_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => setMode(opt.value)}
                    className={`text-left px-2 py-1.5 rounded-lg border text-xs transition-colors ${
                      mode === opt.value
                        ? 'border-primary-400 bg-primary-50 text-primary-700'
                        : 'border-gray-200 text-gray-600 hover:border-gray-300'
                    }`}
                  >
                    <div className="flex items-center gap-1">
                      <span className="text-sm">{opt.icon}</span>
                      <span className="font-medium">{opt.label}</span>
                    </div>
                    <div className="text-[10px] text-gray-400 mt-0.5 leading-tight">{opt.desc}</div>
                  </button>
                ))}
              </div>
            </div>
          </Section>

          {/* 模型参数 */}
          <Section title="模型参数">
            <div className="space-y-3">
              <div>
                <label className="text-xs text-gray-500">Provider</label>
                <select
                  value={modelProvider}
                  onChange={(e) => handleProviderChange(e.target.value)}
                  className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-xs mt-1"
                >
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic</option>
                  <option value="google">Google</option>
                  <option value="ollama">Ollama (本地)</option>
                  <option value="deepseek">DeepSeek</option>
                </select>
              </div>
              <div>
                <label className="text-xs text-gray-500">模型</label>
                <input
                  type="text"
                  value={modelName}
                  onChange={(e) => setModelName(e.target.value)}
                  placeholder="输入模型名称，如 gpt-4o-mini"
                  className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-xs mt-1 focus:outline-none focus:border-primary-500"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-gray-500">Temperature</label>
                  <input
                    type="number"
                    min={0}
                    max={2}
                    step={0.1}
                    value={temperature}
                    onChange={(e) => setTemperature(parseFloat(e.target.value))}
                    className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-xs mt-1"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-500">Max Tokens</label>
                  <input
                    type="number"
                    min={256}
                    max={128000}
                    step={256}
                    value={maxTokens}
                    onChange={(e) => setMaxTokens(parseInt(e.target.value))}
                    className="w-full border border-gray-200 rounded-lg px-2 py-1.5 text-xs mt-1"
                  />
                </div>
              </div>
            </div>
          </Section>

          {/* 工具 */}
          <Section title="Tools">
            {tools.map((tool, i) => (
              <ToolCard
                key={i}
                tool={tool}
                index={i}
                onChange={(updates) => updateTool(i, updates)}
                onRemove={() => removeTool(i)}
              />
            ))}
            <button
              onClick={addTool}
              className="w-full border border-dashed border-gray-300 rounded-lg py-2 text-xs text-gray-400 hover:border-primary-400 hover:text-primary-500 transition-colors"
            >
              + 添加工具
            </button>
          </Section>

          {/* 推荐问题 */}
          <Section title="推荐问题">
            <div className="space-y-1.5">
              {suggestedQuestions.map((q, i) => (
                <div key={i} className="flex items-center gap-1 text-xs text-gray-600">
                  <span className="flex-1 truncate">{q}</span>
                  <button
                    onClick={() => setSuggestedQuestions(suggestedQuestions.filter((_, idx) => idx !== i))}
                    className="text-red-400 hover:text-red-600 p-0.5"
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
              {suggestedQuestions.length === 0 && (
                <p className="text-[10px] text-gray-400 italic">暂无推荐问题</p>
              )}
            </div>
            <div className="flex gap-1.5 mt-2">
              <input
                value={suggestedQuestionInput}
                onChange={(e) => setSuggestedQuestionInput(e.target.value)}
                placeholder="添加推荐问题..."
                className="flex-1 border border-gray-200 rounded-lg px-2 py-1 text-[11px] focus:outline-none focus:border-primary-400"
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); if (suggestedQuestionInput.trim()) { setSuggestedQuestions([...suggestedQuestions, suggestedQuestionInput.trim()]); setSuggestedQuestionInput(''); } } }}
              />
              <button
                onClick={() => {
                  if (suggestedQuestionInput.trim()) {
                    setSuggestedQuestions([...suggestedQuestions, suggestedQuestionInput.trim()])
                    setSuggestedQuestionInput('')
                  }
                }}
                className="px-2 py-1 bg-primary-50 text-primary-600 rounded-lg text-[11px] hover:bg-primary-100"
              >
                添加
              </button>
            </div>
          </Section>

          {/* 知识库 */}
          <Section title="知识库（RAG）">
            <KnowledgeUploader agentId={agent.agent_id} />
          </Section>
        </div>
        {/* v0.5.2: 保存按钮固定在面板底部 */}
        <div className="shrink-0 border-t border-gray-200 bg-white px-4 py-3">
          <div className="flex gap-2">
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex-1 flex items-center justify-center gap-2 bg-primary-600 text-white rounded-xl py-2.5 text-sm font-medium hover:bg-primary-700 disabled:opacity-50 transition-colors"
            >
              <Save size={14} />
              {saving ? '保存中...' : '保存'}
            </button>
            <button
              onClick={handleExport}
              className="px-2 py-2.5 border border-gray-200 rounded-xl text-sm text-gray-600 hover:bg-gray-50 transition-colors"
              title="导出 YAML"
            >
              <Download size={14} />
            </button>
            <button
              onClick={handleExportAll}
              disabled={exportingAll}
              className="px-2 py-2.5 border border-primary-200 bg-primary-50 rounded-xl text-sm text-primary-600 hover:bg-primary-100 disabled:opacity-50 transition-colors"
              title="多格式 ZIP 导出"
            >
              <PackageOpen size={14} />
            </button>
            <button
              onClick={handleDelete}
              className="px-2 py-2.5 border border-red-200 rounded-xl text-sm text-red-500 hover:bg-red-50 transition-colors"
              title="删除 Agent"
            >
              <Trash2 size={14} />
            </button>
          </div>
        </div>
      </>)}
    </div>
  )
}

/** 可折叠区块 */
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(true)
  return (
    <div className="border border-gray-100 rounded-xl bg-white p-3">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center justify-between w-full text-xs font-semibold text-gray-500 uppercase tracking-wide"
      >
        {title}
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      {open && <div className="mt-3">{children}</div>}
    </div>
  )
}

/** 单个工具编辑卡片 */
function ToolCard({
  tool,
  index,
  onChange,
  onRemove,
}: {
  tool: ToolDef
  index: number
  onChange: (updates: Partial<ToolDef>) => void
  onRemove: () => void
}) {
  return (
    <div className="border border-gray-200 rounded-lg p-3 mb-2 text-xs bg-gray-50">
      <div className="flex items-center justify-between mb-2">
        <span className="font-medium text-gray-700">工具 {index + 1}</span>
        <button onClick={onRemove} className="text-red-400 hover:text-red-600">
          <X size={12} />
        </button>
      </div>
      <input
        placeholder="工具名称 (如 search_docs)"
        value={tool.name}
        onChange={(e) => onChange({ name: e.target.value })}
        className="w-full border border-gray-300 rounded px-2 py-1 mb-1.5 focus:outline-none focus:border-primary-400"
      />
      <input
        placeholder="描述 (供 LLM 理解用途)"
        value={tool.description}
        onChange={(e) => onChange({ description: e.target.value })}
        className="w-full border border-gray-300 rounded px-2 py-1 mb-1.5 focus:outline-none focus:border-primary-400"
      />
      <input
        placeholder="Handler 名称 (如 search_docs)"
        value={tool.handler}
        onChange={(e) => onChange({ handler: e.target.value })}
        className="w-full border border-gray-300 rounded px-2 py-1 mb-1.5 focus:outline-none focus:border-primary-400"
      />
      <textarea
        placeholder='参数 (JSON): {"query": {"type": "string", "description": "..."}}'
        value={JSON.stringify(tool.properties, null, 2)}
        onChange={(e) => {
          try {
            const parsed = JSON.parse(e.target.value)
            onChange({ properties: parsed })
          } catch {
            // 输入中...
          }
        }}
        rows={3}
        className="w-full border border-gray-300 rounded px-2 py-1 mt-1 font-mono text-[11px] focus:outline-none focus:border-primary-400"
      />
    </div>
  )
}
