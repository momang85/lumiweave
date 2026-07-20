/**
 * SettingsModal v0.6 — API 设置管理面板（重做版）
 *
 * 架构：localStorage 持久存储 + 后端会话同步
 * - 打开时从 GET /api/settings 获取 env key 状态
 * - 编辑时操作 localStorage（持久 + 即读即写）
 * - 保存时 POST /api/settings 同步后端会话
 * - 一键清除 DELETE /api/settings + localStorage
 */
import { useState, useEffect, useRef } from 'react'
import { Settings, Eye, EyeOff, X, AlertTriangle, Wrench, Trash2, RefreshCw, SlidersHorizontal } from 'lucide-react'
import { getStoredKey, getStoredBase } from './ApiKeyModal'

/* ── 类型 ── */
interface ProviderInfo {
  id: string; name: string; env_key: string; base_env: string
  signup: string; hint: string
  has_env_key: boolean; has_frontend_key: boolean
  has_key: boolean; models: string[]; needs_key: boolean
  base_url: string
}
interface ToolPresetInfo {
  name: string; id: string; description: string
  handler: string; category: string
  needs_key: boolean; has_key: boolean
  secret_env_keys: string[]; params: { name: string; type: string; description: string; required: boolean }[]
}
interface SettingsData {
  providers: ProviderInfo[]
  tool_presets: ToolPresetInfo[]
  any_configured: boolean
  env_count: number
  frontend_count: number
}

interface Props { open: boolean; onClose: () => void }

/* ── 常量 ── */
const STORAGE_PREFIX = 'aihub_key_'
const TOOL_PREFIX = 'aihub_tool_'
const PROVIDER_COLORS: Record<string, string> = {
  openai: '#19c37d', deepseek: '#8b5cf6', anthropic: '#f97316', google: '#3b82f6', ollama: '#6b7280',
}
const LABELS: Record<string, string> = {
  openai: 'OpenAI', deepseek: 'DeepSeek', anthropic: 'Anthropic', google: 'Google', ollama: 'Ollama',
}

// v0.6.1: Provider Key 格式校验（仅警告，不阻止保存）
const KEY_FORMATS: Record<string, { prefix: string[]; hint: string }> = {
  openai: { prefix: ['sk-'], hint: 'OpenAI Key 通常以 sk- 开头' },
  deepseek: { prefix: ['sk-'], hint: 'DeepSeek Key 通常以 sk- 开头' },
  anthropic: { prefix: ['sk-ant-'], hint: 'Anthropic Key 通常以 sk-ant- 开头' },
  google: { prefix: ['AIza'], hint: 'Google Key 通常以 AIza 开头' },
  ollama: { prefix: [], hint: 'Ollama 不需要 API Key，请填写服务地址' },
}

function validateKeyFormat(provider: string, key: string): string | null {
  if (!key) return null
  const rule = KEY_FORMATS[provider]
  if (!rule) return null
  // 常见误填检测
  if (key.startsWith('github_pat_')) {
    return '⚠ 这是 GitHub Personal Access Token，不是 LLM Provider Key，请检查是否复制错'
  }
  if (provider === 'ollama') return null
  if (rule.prefix.length > 0 && !rule.prefix.some(p => key.startsWith(p))) {
    return `⚠ ${rule.hint}，当前内容看起来不匹配`
  }
  return null
}

/* ── 组件 ── */
export default function SettingsModal({ open, onClose }: Props) {
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  const [editKey, setEditKey] = useState('')
  const [editBase, setEditBase] = useState('')
  const [show, setShow] = useState<Record<string, boolean>>({})
  const [saved, setSaved] = useState<Record<string, boolean>>({})
  const [sync, setSync] = useState(0)

  // v0.6.1: 运行时配置 — localStorage 双重持久化
  const [rtConfig, setRtConfig] = useState<Record<string, number | boolean | string> | null>(null)
  const [rtDefaults, setRtDefaults] = useState<Record<string, number | boolean | string> | null>(null)
  const [rtDirty, setRtDirty] = useState(false)

  // 打开时：同步 localStorage → 后端，然后拉取最新状态
  useEffect(() => {
    if (!open) return

    // v0.6.1: 先把 localStorage 中所有 Provider Key 同步到后端会话
    // 解决重启后端后 "前端已配置" 但 backend frontend_count=0 的不一致
    const providers: Record<string, { key: string; base: string }> = {}
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i)
      if (!k || !k.startsWith(STORAGE_PREFIX)) continue
      if (k.endsWith('_base')) {
        const pid = k.slice(STORAGE_PREFIX.length, -5)
        providers[pid] = { ...(providers[pid] || { key: '' }), base: localStorage.getItem(k) || '' }
      } else {
        const pid = k.slice(STORAGE_PREFIX.length)
        providers[pid] = { ...(providers[pid] || { base: '' }), key: localStorage.getItem(k) || '' }
      }
    }

    const syncThenLoad = async () => {
      try {
        await fetch('/api/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ providers }),
        })
      } catch { /* ignore */ }
      fetch('/api/settings').then(r => r.json()).then(data => {
        setSettings(data)
      }).catch(() => {})
      // v0.6.1: 加载运行时配置（优先localStorage，其次API，最后默认值）
      if (!rtConfig) {  // 只在首次加载或重置后加载
        const stored = localStorage.getItem('aihub_rt_config')
        if (stored) {
          try {
            const parsed = JSON.parse(stored)
            setRtConfig(parsed)
            const fb = { max_tool_iterations: 60, max_delegate_calls: 10, max_sub_iterations: 5, sub_agent_max_tokens: 8192, sub_agent_temperature: 0.3, sub_agent_timeout: 120, orchestrator_max_tokens: 8192, history_window: 10, run_command_timeout: 10, code_executor_timeout: 10, max_list_dir_per_session: 5, max_run_command_per_session: 5, delegate_cache_max: 50, search_result_limit: 5, web_search_timeout: 8, file_read_default_lines: 500, search_file_max_results: 50, output_truncate_limit: 8000, agent_session_ttl: 3600, sub_agent_system_prompt_limit: 8000, enable_rag: true, enable_web_search: true }
            setRtDefaults(fb)
          } catch {}
        }
        // 2. 再从后端API加载（覆盖localStorage，以后端为准）
        fetch('/api/runtime-config').then(r => r.json()).then(data => {
          setRtConfig(data.config || {})
          setRtDefaults(data.defaults || {})
          // 同步到localStorage
          try { localStorage.setItem('aihub_rt_config', JSON.stringify(data.config || {})) } catch {}
        }).catch(() => {
          // API不可用时，如果localStorage也没有，才用硬编码默认值
          if (!stored) {
            const fb = { max_tool_iterations: 60, max_delegate_calls: 10, max_sub_iterations: 5, sub_agent_max_tokens: 8192, sub_agent_temperature: 0.3, sub_agent_timeout: 120, orchestrator_max_tokens: 8192, history_window: 10, run_command_timeout: 10, code_executor_timeout: 10, max_list_dir_per_session: 5, max_run_command_per_session: 5, delegate_cache_max: 50, search_result_limit: 5, web_search_timeout: 8, file_read_default_lines: 500, search_file_max_results: 50, output_truncate_limit: 8000, agent_session_ttl: 3600, sub_agent_system_prompt_limit: 8000, enable_rag: true, enable_web_search: true }
            setRtConfig({ ...fb })
            setRtDefaults({ ...fb })
          }
        })
      }
    }

    syncThenLoad()
  }, [open, sync])

  // 切换 provider 时重置编辑区
  useEffect(() => {
    if (expanded) {
      setEditKey(getStoredKey(expanded))
      setEditBase(getStoredBase(expanded))
    } else {
      setEditKey(''); setEditBase('')
    }
  }, [expanded])

  // 保存单个 provider
  const handleSave = async (provId: string) => {
    // 1. 持久化到 localStorage
    try { localStorage.setItem(STORAGE_PREFIX + provId, editKey) } catch {}
    try { localStorage.setItem(STORAGE_PREFIX + provId + '_base', editBase) } catch {}

    // 2. 同步后端
    try {
      await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ providers: { [provId]: { key: editKey, base: editBase } } }),
      })
    } catch {}

    setSaved(p => ({ ...p, [provId]: true }))
    setTimeout(() => setSaved(p => ({ ...p, [provId]: false })), 2000)
    setExpanded(null)
    setSync(s => s + 1) // 刷新状态
  }

  // 清除单个 provider
  const handleClear = async (provId: string) => {
    try { localStorage.removeItem(STORAGE_PREFIX + provId) } catch {}
    try { localStorage.removeItem(STORAGE_PREFIX + provId + '_base') } catch {}
    try {
      await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ providers: { [provId]: { key: '', base: '' } } }),
      })
    } catch {}
    setEditKey(''); setEditBase(''); setExpanded(null)
    setSync(s => s + 1)
  }

  // 清除所有
  const handleClearAll = async () => {
    // 清除所有 localStorage 中相关键
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const k = localStorage.key(i)
      if (k && (k.startsWith(STORAGE_PREFIX) || k.startsWith(TOOL_PREFIX))) {
        try { localStorage.removeItem(k) } catch {}
      }
    }
    try { await fetch('/api/settings', { method: 'DELETE' }) } catch {}
    setExpanded(null); setEditKey(''); setEditBase('')
    setSync(s => s + 1)
  }

  if (!open) return null
  const loading = !settings

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-2xl w-[540px] max-h-[82vh] overflow-hidden flex flex-col"
           onClick={e => e.stopPropagation()}>

        {/* ── 头部 ── */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-gray-100 shrink-0">
          <div className="flex items-center gap-2.5">
            <Settings size={18} className="text-gray-500" />
            <div>
              <h3 className="font-bold text-sm text-gray-800">API 设置</h3>
              <p className="text-[11px] text-gray-400">管理 Provider 密钥 & 工具预设</p>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
        </div>

        {/* ── 内容区 ── */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-2">
          {loading ? (
            <div className="text-center py-10 text-gray-400 text-sm">加载中...</div>
          ) : (
            <>
              {/* Provider 列表 */}
              {settings!.providers.map((prov) => {
                const isExpanded = expanded === prov.id
                const hasLocalKey = !!getStoredKey(prov.id)
                const keySource = prov.has_env_key ? '环境变量' : hasLocalKey ? '前端已配置' : '未配置'
                const keyStyle = prov.has_env_key ? 'text-green-600' : hasLocalKey ? 'text-blue-600' : 'text-red-400'

                return (
                  <div key={prov.id} className="border border-gray-200 rounded-xl overflow-hidden">
                    {/* 行头 */}
                    <div className="flex items-center justify-between px-4 py-2.5 hover:bg-gray-50 cursor-pointer"
                         onClick={() => setExpanded(isExpanded ? null : prov.id)}>
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className="w-2 h-2 rounded-full shrink-0"
                             style={{ backgroundColor: prov.has_env_key ? '#22c55e' : hasLocalKey ? '#3b82f6' : '#ef4444' }} />
                        <span className="text-sm font-medium text-gray-700 truncate">{prov.name}</span>
                        <span className={`text-[10px] shrink-0 ${keyStyle}`} title={keySource}>
                          {keySource}
                        </span>
                      </div>
                      <span className="text-[10px] text-gray-400 shrink-0 ml-2">
                        {isExpanded ? '收起' : '编辑'}
                      </span>
                    </div>

                    {/* 编辑区 */}
                    {isExpanded && (
                      <div className="px-4 pb-3 pt-2 border-t border-gray-100 space-y-2.5">
                        {prov.needs_key && (
                          <div>
                            <label className="text-[10px] text-gray-500 mb-1 block">API Key</label>
                            <div className="relative">
                              <input
                                type={show[prov.id] ? 'text' : 'password'}
                                value={editKey}
                                onChange={e => setEditKey(e.target.value)}
                                placeholder={prov.hint}
                                className={`w-full border rounded-lg px-3 py-2 text-xs pr-8 focus:outline-none focus:border-blue-400 ${
                                  validateKeyFormat(prov.id, editKey) ? 'border-amber-300 bg-amber-50' : 'border-gray-200'
                                }`}
                              />
                              <button
                                onClick={e => { e.stopPropagation(); setShow(s => ({ ...s, [prov.id]: !s[prov.id] })) }}
                                className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                              >
                                {show[prov.id] ? <EyeOff size={14} /> : <Eye size={14} />}
                              </button>
                            </div>
                            {validateKeyFormat(prov.id, editKey) && (
                              <p className="text-[10px] text-amber-600 mt-1">{validateKeyFormat(prov.id, editKey)}</p>
                            )}
                          </div>
                        )}
                        {prov.id === 'ollama' ? (
                          <div>
                            <label className="text-[10px] text-gray-500 mb-1 block">服务地址</label>
                            <input type="text" value={editBase || 'http://localhost:11434'}
                              onChange={e => setEditBase(e.target.value)}
                              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-blue-400" />
                          </div>
                        ) : (
                          <details className="text-[10px]">
                            <summary className="text-gray-400 cursor-pointer">自定义 API 地址</summary>
                            <input type="text" value={editBase}
                              onChange={e => setEditBase(e.target.value)}
                              placeholder="留空使用默认"
                              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-[10px] mt-1 focus:outline-none focus:border-blue-400" />
                          </details>
                        )}
                        {prov.signup && (
                          <a href={prov.signup} target="_blank" rel="noopener noreferrer"
                             className="inline-block text-[10px] text-blue-500 hover:text-blue-700">
                            获取 {prov.name} Key ↗
                          </a>
                        )}
                        {prov.has_env_key && editKey && (
                          <p className="text-[10px] text-amber-600">
                            ⚠ 检测到环境变量 {prov.env_key} 已配置。实际运行时优先使用当前前端 Key（环境变量仅在未输入时兜底）。
                          </p>
                        )}
                        <div className="flex gap-2 pt-1">
                          <button onClick={() => setExpanded(null)}
                            className="flex-1 border border-gray-200 rounded-lg py-1.5 text-[11px] text-gray-600 hover:bg-gray-50">
                            取消
                          </button>
                          <button onClick={() => handleSave(prov.id)}
                            className="flex-1 bg-blue-600 text-white rounded-lg py-1.5 text-[11px] font-medium hover:bg-blue-700">
                            {saved[prov.id] ? '已保存 ✓' : '保存并同步'}
                          </button>
                        </div>
                        {(hasLocalKey || editKey) && (
                          <button onClick={() => handleClear(prov.id)}
                            className="w-full text-[10px] text-red-400 hover:text-red-600 py-0.5">
                            清除此 Provider 的 Key
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                )
              })}

              {/* 工具预设 */}
              <div className="pt-3 border-t border-gray-200">
                <div className="flex items-center gap-2 mb-2">
                  <Wrench size={13} className="text-gray-400" />
                  <span className="text-[11px] font-semibold text-gray-600">工具预设</span>
                  <span className="text-[10px] text-gray-400">创建 Agent 时自动注入</span>
                </div>
                <div className="space-y-1.5">
                  {settings!.tool_presets.map((tool) => {
                    const envKey = tool.secret_env_keys?.[0] || ''
                    const savedTool = localStorage.getItem(TOOL_PREFIX + envKey) || ''
                    const hasToolKey = tool.has_key || !!savedTool
                    return (
                      <ToolPresetRow key={tool.id} tool={tool} envKey={envKey}
                        hasKey={hasToolKey} savedValue={savedTool}
                        onSaved={() => setSync(s => s + 1)} />
                    )
                  })}
                </div>
              </div>

              {/* v0.6.1: 运行参数 */}
              {rtConfig && rtDefaults && (
                <RuntimeConfigPanel
                  config={rtConfig}
                  defaults={rtDefaults}
                  onSave={async (updated) => {
                    // 双重持久化：localStorage 立即可靠 + 后端 API
                    try { localStorage.setItem('aihub_rt_config', JSON.stringify(updated)) } catch {}
                    try {
                      await fetch('/api/runtime-config', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(updated),
                      })
                    } catch {}
                    setRtConfig(prev => prev ? { ...prev, ...updated } : null)
                    setRtDirty(false)
                  }}
                  onChange={() => setRtDirty(true)}
                  dirty={rtDirty}
                />
              )}
            </>
          )}
        </div>

        {/* ── 底部 ── */}
        <div className="px-5 py-3 border-t border-gray-100 bg-gray-50 flex items-center justify-between shrink-0">
          <span className="text-[10px] text-gray-400">
            {settings ? `环境变量: ${settings.env_count} · 前端配置: ${settings.frontend_count}` : ''}
          </span>
          <button onClick={handleClearAll}
            className="flex items-center gap-1 text-[10px] text-red-500 hover:text-red-700 px-2 py-1 rounded">
            <Trash2 size={11} />清除所有 Key
          </button>
        </div>
      </div>
    </div>
  )
}

/* ── 工具预设立行 ── */
/* ── 运行参数面板 ── */
const RT_PARAMS: { key: string; label: string; desc: string; type: 'int' | 'bool' | 'str' }[] = [
  { key: 'llm_proxy', label: 'LLM代理', desc: 'HTTP代理地址(如 http://127.0.0.1:7897)', type: 'str' },
  { key: 'web_search_proxy', label: '搜索代理', desc: '网页搜索HTTP代理', type: 'str' },
  { key: 'sub_agent_model', label: '子Agent模型', desc: '快模型名称', type: 'str' },
  { key: 'max_tool_iterations', label: '调度器最大工具轮次', desc: '单次会话最多工具调用', type: 'int' },
  { key: 'max_delegate_calls', label: '最大委托次数', desc: '最多 delegate_task 调用', type: 'int' },
  { key: 'max_sub_iterations', label: '子Agent最大迭代', desc: '每个子Agent工具轮次上限', type: 'int' },
  { key: 'sub_agent_max_tokens', label: '子Agent最大输出', desc: '子Agent每次回复 token 数', type: 'int' },
  { key: 'sub_agent_temperature', label: '子Agent温度', desc: 'LLM 创造性 (0-1)', type: 'int' },
  { key: 'sub_agent_timeout', label: '子Agent整体超时(秒)', desc: '子Agent最长执行时间，超强制终止', type: 'int' },
  { key: 'orchestrator_max_tokens', label: '调度器最大输出', desc: 'orchestrator max_tokens', type: 'int' },
  { key: 'history_window', label: '对话历史窗口', desc: '保留最近N轮对话', type: 'int' },
  { key: 'run_command_timeout', label: '命令超时(秒)', desc: 'run_command 默认超时', type: 'int' },
  { key: 'code_executor_timeout', label: '代码执行超时(秒)', desc: 'code_executor 默认超时', type: 'int' },
  { key: 'max_list_dir_per_session', label: 'list_dir上限', desc: '防滥用：列目录上限', type: 'int' },
  { key: 'max_run_command_per_session', label: 'run_command上限', desc: '单会话最多命令次数', type: 'int' },
  { key: 'delegate_cache_max', label: '委托缓存条数', desc: 'delegate_task 结果缓存', type: 'int' },
  { key: 'search_result_limit', label: '搜索结果数量', desc: '每次搜索返回条数', type: 'int' },
  { key: 'web_search_timeout', label: '搜索超时(秒)', desc: 'DuckDuckGo HTTP 超时', type: 'int' },
  { key: 'file_read_default_lines', label: '读文件默认行数', desc: 'read_file 默认行数', type: 'int' },
  { key: 'search_file_max_results', label: '搜文件结果上限', desc: 'search_file 返回上限', type: 'int' },
  { key: 'output_truncate_limit', label: '输出截断长度', desc: 'stdout/stderr 截断', type: 'int' },
  { key: 'agent_session_ttl', label: 'Session过期(秒)', desc: '子Agent session 过期', type: 'int' },
  { key: 'sub_agent_system_prompt_limit', label: '提示词截断', desc: 'system_prompt 截断字符数', type: 'int' },
  { key: 'enable_rag', label: '启用RAG', desc: '是否注入知识库', type: 'bool' },
  { key: 'enable_web_search', label: '启用网页搜索', desc: '是否允许搜索', type: 'bool' },
]

function RuntimeConfigPanel({ config, defaults, onSave, onChange, dirty }: {
  config: Record<string, number | boolean | string>
  defaults: Record<string, number | boolean | string>
  onSave: (updated: Record<string, number | boolean | string>) => void
  onChange: () => void
  dirty: boolean
}) {
  const [values, setValues] = useState<Record<string, number | boolean | string>>({})

  useEffect(() => { setValues({ ...config }) }, [config])

  const handleChange = (key: string, val: string | boolean) => {
    if (typeof config[key] === 'string' || (config[key] === undefined && key.includes('proxy'))) {
      setValues(prev => ({ ...prev, [key]: String(val) }))
    } else if (typeof config[key] === 'boolean') {
      setValues(prev => ({ ...prev, [key]: Boolean(val) }))
    } else {
      setValues(prev => ({ ...prev, [key]: Number(val) || 0 }))
    }
    onChange()
  }

  return (
    <div className="pt-3 border-t border-gray-200">
      <div className="flex items-center gap-2 mb-3">
        <SlidersHorizontal size={13} className="text-gray-400" />
        <span className="text-[11px] font-semibold text-gray-600">运行参数</span>
        <span className="text-[10px] text-gray-400">限制和开关</span>
        {dirty && <span className="text-[10px] text-amber-500">已修改</span>}
      </div>

      <div className="grid grid-cols-2 gap-x-3 gap-y-2">
        {RT_PARAMS.map(param => {
          const val = values[param.key] ?? defaults[param.key]
          const defVal = defaults[param.key]
          const changed = val !== defVal

          return (
            <div key={param.key} className={`flex items-center justify-between py-1 px-2 rounded-lg text-[10px] ${changed ? 'bg-blue-50' : 'bg-gray-50'}`}>
              <div className="min-w-0 flex-1" title={param.desc}>
                <span className={`${changed ? 'text-blue-700 font-medium' : 'text-gray-600'}`}>{param.label}</span>
              </div>
              {param.type === 'bool' ? (
                <label className="relative inline-flex items-center cursor-pointer shrink-0 ml-2">
                  <input type="checkbox" checked={Boolean(val)} onChange={e => handleChange(param.key, e.target.checked)}
                    className="sr-only peer" />
                  <div className="w-7 h-4 bg-gray-300 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-3 peer-checked:bg-blue-600 after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:rounded-full after:h-3 after:w-3 after:transition-all" />
                </label>
              ) : param.type === 'str' ? (
                <div className="flex items-center gap-1 shrink-0">
                  <input
                    type="text"
                    value={String(val || '')}
                    onChange={e => handleChange(param.key, e.target.value)}
                    className={`w-32 text-center border rounded-md py-0.5 text-[10px] focus:outline-none focus:border-blue-400 ${changed ? 'border-blue-300 bg-blue-50' : 'border-gray-200'}`}
                    placeholder="留空=直连"
                  />
                </div>
              ) : (
                <div className="flex items-center gap-1 shrink-0">
                  <input
                    type="number"
                    value={Number(val)}
                    min={0}
                    max={9999}
                    onChange={e => handleChange(param.key, e.target.value)}
                    className={`w-12 text-center border rounded-md py-0.5 text-[10px] focus:outline-none focus:border-blue-400 ${changed ? 'border-blue-300 bg-blue-50' : 'border-gray-200'}`}
                  />
                  {changed && <span className="text-blue-400 text-[8px]">({String(defVal)})</span>}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {dirty && (
        <div className="flex gap-2 mt-2">
          <button
            onClick={() => onSave(values)}
            className="flex-1 bg-blue-600 text-white rounded-lg py-1.5 text-[11px] font-medium hover:bg-blue-700"
          >
            保存运行参数
          </button>
          <button
            onClick={() => { setValues({ ...config }); onChange() }}
            className="px-3 border border-gray-200 rounded-lg py-1.5 text-[11px] text-gray-600 hover:bg-gray-50"
          >
            取消
          </button>
        </div>
      )}
    </div>
  )
}

/* ── 工具预设行 ── */
function ToolPresetRow({ tool, envKey, hasKey, savedValue, onSaved }: {
  tool: ToolPresetInfo; envKey: string; hasKey: boolean; savedValue: string; onSaved: () => void
}) {
  const [val, setVal] = useState(savedValue)
  const [saveState, setSaveState] = useState('')

  const handleSave = async () => {
    try { localStorage.setItem(TOOL_PREFIX + envKey, val) } catch {}
    try {
      await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tools: { [envKey]: val } }),
      })
    } catch {}
    setSaveState('已同步')
    setTimeout(() => setSaveState(''), 1500)
    onSaved()
  }
  const handleClear = async () => {
    try { localStorage.removeItem(TOOL_PREFIX + envKey) } catch {}
    try {
      await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tools: { [envKey]: '' } }),
      })
    } catch {}
    setVal('')
    onSaved()
  }

  return (
    <div className="flex items-center gap-2 p-2 rounded-lg border border-gray-100 bg-white">
      <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${hasKey || val ? 'bg-green-500' : 'bg-gray-300'}`} />
      <div className="flex-1 min-w-0">
        <span className="text-[11px] text-gray-700">{tool.name}</span>
        <span className="text-[10px] text-gray-400 ml-1">{tool.category}</span>
      </div>
      {tool.needs_key ? (
        <div className="flex items-center gap-1 shrink-0">
          <input type={hasKey ? 'password' : 'text'}
            value={val} placeholder={envKey}
            onChange={e => setVal(e.target.value)}
            className="w-28 border border-gray-200 rounded px-2 py-1 text-[10px] focus:outline-none focus:border-blue-400" />
          <button onClick={handleSave}
            className="text-[10px] text-blue-500 hover:text-blue-700 px-1 shrink-0">
            {saveState || '保存'}
          </button>
          {val && (
            <button onClick={handleClear}
              className="text-[10px] text-red-400 hover:text-red-600 px-1 shrink-0">清</button>
          )}
        </div>
      ) : (
        <span className="text-[10px] text-gray-400 shrink-0">无需配置</span>
      )}
    </div>
  )
}
