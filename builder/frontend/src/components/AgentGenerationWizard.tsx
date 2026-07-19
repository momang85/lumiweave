/**
 * AgentGenerationWizard — 自然语言 → Agent 生成向导
 *
 * 用户输入描述 → 选择领域 → 生成 → 预览 → 确认保存
 */
import { useState, useEffect } from 'react'
import { Wand2, Loader2, CheckCircle2, AlertTriangle, Sparkles } from 'lucide-react'
import type { DomainInfo, GenerateResult, AgentData } from '../types'
import * as api from '../api'
import { getStoredKey, getStoredBase } from './ApiKeyModal'

interface Props {
  open: boolean
  onClose: () => void
  onAgentCreated: (agentId: string) => void
}

export default function AgentGenerationWizard({ open, onClose, onAgentCreated }: Props) {
  const [step, setStep] = useState<'input' | 'generating' | 'preview'>('input')
  const [userInput, setUserInput] = useState('')
  const [domains, setDomains] = useState<DomainInfo[]>([])
  const [selectedDomain, setSelectedDomain] = useState('')
  const [genProvider, setGenProvider] = useState('openai')        // v0.5
  const [genModel, setGenModel] = useState('gpt-4o-mini')        // v0.5
  const [result, setResult] = useState<GenerateResult | null>(null)
  const [error, setError] = useState('')
  const [editingAgent, setEditingAgent] = useState<AgentData | null>(null)
  const [creating, setCreating] = useState(false)

  // 生成完成后初始化可编辑副本
  useEffect(() => {
    if (result?.agent) {
      setEditingAgent({ ...result.agent, mode: result.agent.mode || 'simple' })
    }
  }, [result])

  // Provider 切换时自动填默认模型
  const DEFAULT_GEN_MODELS: Record<string, string> = {
    openai: 'gpt-4o-mini',
    anthropic: 'claude-3-5-sonnet-20241022',
    google: 'gemini-2.0-flash',
    deepseek: 'deepseek-chat',
    ollama: 'llama3.2',
  }
  const handleGenProviderChange = (prov: string) => {
    setGenProvider(prov)
    setGenModel(DEFAULT_GEN_MODELS[prov] || '')
  }

  useEffect(() => {
    if (open) {
      api.listDomains().then((d) => setDomains(d.domains)).catch(() => {})
    }
  }, [open])

  const handleGenerate = async () => {
    if (!userInput.trim()) return
    setStep('generating')
    setError('')
    try {
      const apiKey = getStoredKey(genProvider)
      const apiBase = getStoredBase(genProvider)
      const res = await api.generateAgent(
        userInput,
        selectedDomain || undefined,
        { provider: genProvider, model: genModel, apiKey, apiBase },
      )
      setResult(res)
      setStep('preview')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '生成失败')
      setStep('input')
    }
  }

  const handleSave = async () => {
    if (!editingAgent) return
    setCreating(true)
    try {
      const { agent: created } = await api.createAgent({
        name: editingAgent.name,
        description: editingAgent.description,
        mode: editingAgent.mode,
        system_prompt: editingAgent.system_prompt,
        model_provider: genProvider,
        model_name: genModel,
        temperature: editingAgent.temperature ?? 0.3,
        max_tokens: editingAgent.max_tokens ?? 8192,
        tools: editingAgent.tools || [],
        tags: editingAgent.tags || [],
        avatar: editingAgent.avatar || '🤖',
        suggested_questions: editingAgent.suggested_questions || [],
      })
      onAgentCreated(created.agent_id)
      onClose()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '保存失败')
    }
    setCreating(false)
  }

  const handleClose = () => {
    setStep('input')
    setUserInput('')
    setSelectedDomain('')
    setResult(null)
    setError('')
    onClose()
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-2xl shadow-2xl w-[560px] max-h-[85vh] overflow-hidden flex flex-col">
        {/* 头部 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Sparkles size={18} className="text-amber-500" />
            <h3 className="font-bold text-gray-800">AI 生成 Agent</h3>
          </div>
          <button
            onClick={handleClose}
            className="text-gray-400 hover:text-gray-600 text-sm"
          >
            取消
          </button>
        </div>

        {/* 内容 */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Step 1: 输入 */}
          {step === 'input' && (
            <div className="space-y-4">
              <p className="text-sm text-gray-500">
                用自然语言描述你想要的 AI Agent，系统会自动生成完整的定义。
              </p>

              <div>
                <label className="text-xs font-medium text-gray-500 mb-1 block">
                  描述你的 Agent
                </label>
                <textarea
                  value={userInput}
                  onChange={(e) => setUserInput(e.target.value)}
                  placeholder="例如：我要一个帮我审查法律合同的专业助手，能检索法律法规，分析条款风险..."
                  rows={4}
                  className="w-full border border-gray-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-primary-500 focus:ring-1 focus:ring-primary-200 resize-none"
                  autoFocus
                />
              </div>

              <div>
                <label className="text-xs font-medium text-gray-500 mb-1 block">
                  领域（可选）
                </label>
                <div className="grid grid-cols-4 gap-2">
                  {domains.map((d) => (
                    <button
                      key={d.domain}
                      onClick={() =>
                        setSelectedDomain(selectedDomain === d.domain ? '' : d.domain)
                      }
                      className={`text-xs px-3 py-2 rounded-lg border transition-colors ${
                        selectedDomain === d.domain
                          ? 'border-primary-500 bg-primary-50 text-primary-700'
                          : 'border-gray-200 text-gray-600 hover:border-gray-300'
                      }`}
                    >
                      {d.avatar} {d.name_cn}
                    </button>
                  ))}
                  {!domains.length && (
                    <span className="text-xs text-gray-400">加载中...</span>
                  )}
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-gray-500 mb-1 block">
                  生成使用的 LLM
                </label>
                <div className="flex gap-2">
                  <select
                    value={genProvider}
                    onChange={(e) => handleGenProviderChange(e.target.value)}
                    className="flex-1 border border-gray-200 rounded-lg px-2 py-1.5 text-xs"
                  >
                    <option value="openai">OpenAI</option>
                    <option value="anthropic">Anthropic</option>
                    <option value="google">Google</option>
                    <option value="deepseek">DeepSeek</option>
                  </select>
                  <input
                    type="text"
                    value={genModel}
                    onChange={(e) => setGenModel(e.target.value)}
                    placeholder="模型名"
                    className="flex-1 border border-gray-200 rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:border-primary-500"
                  />
                </div>
                {getStoredKey(genProvider) ? (
                  <p className="text-[10px] text-green-600 mt-1">
                    ● {genProvider.toUpperCase()} Key 已配置 — 将使用 AI 生成
                  </p>
                ) : (
                  <p className="text-[10px] text-amber-600 mt-1">
                    ⚠ 未配置 {genProvider.toUpperCase()} Key — 将降级为模板生成
                  </p>
                )}
              </div>

              {error && (
                <div className="flex items-center gap-2 text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">
                  <AlertTriangle size={14} />
                  {error}
                </div>
              )}

              <button
                onClick={handleGenerate}
                disabled={!userInput.trim()}
                className="w-full flex items-center justify-center gap-2 bg-primary-600 text-white rounded-xl py-3 text-sm font-medium hover:bg-primary-700 disabled:opacity-40 transition-colors"
              >
                <Wand2 size={16} />
                生成 Agent
              </button>
            </div>
          )}

          {/* Step 2: 生成中 */}
          {step === 'generating' && (
            <div className="flex flex-col items-center justify-center py-16">
              <Loader2 size={40} className="text-primary-500 animate-spin mb-4" />
              <p className="text-sm text-gray-500">正在分析需求并生成 Agent 定义...</p>
            </div>
          )}

          {/* Step 3: 预览/编辑 */}
          {step === 'preview' && result && editingAgent && (
            <div className="space-y-4">
              {/* 生成模式标记 */}
              <div className={`text-xs rounded-lg px-3 py-2 ${
                (result.warnings || []).some(w => w.includes('LLM') || w.includes('模板'))
                  ? 'bg-amber-50 text-amber-700'
                  : 'bg-green-50 text-green-700'
              }`}>
                {(result.warnings || []).some(w => w.includes('LLM') || w.includes('模板'))
                  ? '⚠ 模板生成 — 未使用 AI。配置 API Key 可获得更精准的 AI 生成结果。'
                  : '✓ AI 生成 — 基于 LLM 自动分析生成'}
              </div>

              {result.warnings?.length > 0 && (
                <div className="flex items-start gap-2 text-xs text-amber-700 bg-amber-50 rounded-lg px-3 py-2">
                  <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                  <div>
                    {result.warnings.map((w, i) => (
                      <p key={i}>{w}</p>
                    ))}
                  </div>
                </div>
              )}

              {/* Avatar */}
              <div className="flex items-center gap-2">
                <input
                  value={editingAgent.avatar || '🤖'}
                  onChange={(e) => setEditingAgent({ ...editingAgent, avatar: e.target.value })}
                  className="w-12 h-12 text-center text-2xl border border-gray-200 rounded-xl focus:outline-none focus:border-primary-500"
                  maxLength={3}
                />
                <div>
                  <label className="text-[10px] text-gray-400">图标</label>
                </div>
              </div>

              {/* 名称 */}
              <div>
                <label className="text-xs font-medium text-gray-500 mb-1 block">名称</label>
                <input
                  value={editingAgent.name}
                  onChange={(e) => setEditingAgent({ ...editingAgent, name: e.target.value })}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary-500"
                />
              </div>

              {/* 描述 */}
              <div>
                <label className="text-xs font-medium text-gray-500 mb-1 block">描述</label>
                <input
                  value={editingAgent.description}
                  onChange={(e) => setEditingAgent({ ...editingAgent, description: e.target.value })}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary-500"
                />
              </div>

              {/* 模式 */}
              <div>
                <label className="text-xs font-medium text-gray-500 mb-1 block">运行模式</label>
                <div className="grid grid-cols-4 gap-1.5">
                  {[
                    { v: 'simple', l: '💬 简单' },
                    { v: 'react', l: '🧠 ReAct' },
                    { v: 'planner', l: '📋 规划' },
                    { v: 'reflection', l: '🪞 反思' },
                  ].map((opt) => (
                    <button
                      key={opt.v}
                      onClick={() => setEditingAgent({ ...editingAgent, mode: opt.v })}
                      className={`text-[10px] px-2 py-1.5 rounded-lg border ${
                        editingAgent.mode === opt.v
                          ? 'border-primary-400 bg-primary-50 text-primary-700'
                          : 'border-gray-200 text-gray-500 hover:border-gray-300'
                      }`}
                    >
                      {opt.l}
                    </button>
                  ))}
                </div>
              </div>

              {/* System Prompt */}
              <div>
                <label className="text-xs font-medium text-gray-500 mb-1 block">
                  System Prompt <span className="text-gray-400">({editingAgent.system_prompt?.length || 0} 字符)</span>
                </label>
                <textarea
                  value={editingAgent.system_prompt}
                  onChange={(e) => setEditingAgent({ ...editingAgent, system_prompt: e.target.value })}
                  rows={10}
                  className="w-full border border-gray-200 rounded-xl px-3 py-2 text-xs font-mono focus:outline-none focus:border-primary-500 resize-y"
                />
              </div>

              {/* 工具 */}
              <div>
                <label className="text-xs font-medium text-gray-500 mb-1 block">
                  Tools ({editingAgent.tools?.length || 0})
                </label>
                <div className="max-h-[120px] overflow-y-auto space-y-1">
                  {(editingAgent.tools || []).map((tool, i) => (
                    <div key={i} className="flex gap-2 items-start">
                      <input
                        value={tool.name}
                        onChange={(e) => {
                          const t = [...(editingAgent.tools || [])]
                          t[i] = { ...t[i], name: e.target.value }
                          setEditingAgent({ ...editingAgent, tools: t })
                        }}
                        placeholder="工具名"
                        className="flex-1 border border-gray-200 rounded-lg px-2 py-1 text-[11px] focus:outline-none focus:border-primary-400"
                      />
                      <input
                        value={tool.description || ''}
                        onChange={(e) => {
                          const t = [...(editingAgent.tools || [])]
                          t[i] = { ...t[i], description: e.target.value }
                          setEditingAgent({ ...editingAgent, tools: t })
                        }}
                        placeholder="描述"
                        className="flex-[2] border border-gray-200 rounded-lg px-2 py-1 text-[11px] focus:outline-none focus:border-primary-400"
                      />
                    </div>
                  ))}
                </div>
              </div>

              {/* 推荐问题 */}
              <div>
                <label className="text-xs font-medium text-gray-500 mb-1 block">
                  推荐问题 (每行一个)
                </label>
                <textarea
                  value={(editingAgent.suggested_questions || []).join('\n')}
                  onChange={(e) => setEditingAgent({
                    ...editingAgent,
                    suggested_questions: e.target.value.split('\n').filter(Boolean),
                  })}
                  rows={4}
                  placeholder="每行一个问题"
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-primary-500 resize-y"
                />
              </div>

              {error && (
                <div className="flex items-center gap-2 text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">
                  <AlertTriangle size={14} />
                  {error}
                </div>
              )}

              <div className="flex gap-2 pt-2">
                <button
                  onClick={() => setStep('input')}
                  className="flex-1 border border-gray-200 rounded-xl py-2.5 text-sm text-gray-600 hover:bg-gray-50 transition-colors"
                >
                  返回修改
                </button>
                <button
                  onClick={handleSave}
                  disabled={creating || !result.success}
                  className="flex-1 flex items-center justify-center gap-2 bg-primary-600 text-white rounded-xl py-2.5 text-sm font-medium hover:bg-primary-700 disabled:opacity-40 transition-colors"
                >
                  {creating ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <CheckCircle2 size={16} />
                  )}
                  {creating ? '保存中...' : '保存 Agent'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
