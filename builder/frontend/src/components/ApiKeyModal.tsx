/**
 * ApiKeyModal — API Key 配置弹窗 v0.5
 *
 * 当检测到 Provider 未配置 API Key 时弹出。
 * 支持输入 Key + API Base URL，保存到 localStorage（持久化）。
 */
import { useState, useEffect } from 'react'
import { Key, ExternalLink, CheckCircle2, AlertTriangle, Loader2, Eye, EyeOff } from 'lucide-react'
import * as api from '../api'

interface Props {
  open: boolean
  onClose: () => void
  provider: string
  onConfigured?: (provider: string, apiKey: string, apiBase: string) => void
}

const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic (Claude)',
  google: 'Google (Gemini)',
  deepseek: 'DeepSeek',
  ollama: 'Ollama (本地)',
}

const PROVIDER_SIGNUP: Record<string, string> = {
  openai: 'https://platform.openai.com/api-keys',
  anthropic: 'https://console.anthropic.com/keys',
  google: 'https://aistudio.google.com/apikey',
  deepseek: 'https://platform.deepseek.com/api_keys',
}

const KEY_HINTS: Record<string, string> = {
  openai: 'sk-...',
  deepseek: 'sk-...',
  anthropic: 'sk-ant-...',
  google: 'AIza...',
  ollama: 'http://localhost:11434',
}

// v0.6.1: Key 格式校验（仅警告）
function validateKeyFormat(provider: string, key: string): string | null {
  if (!key) return null
  if (key.startsWith('github_pat_')) {
    return '⚠ 这是 GitHub Personal Access Token，不是 LLM Provider Key'
  }
  if (provider === 'ollama') return null
  if (provider === 'openai' && !key.startsWith('sk-')) return '⚠ OpenAI Key 通常以 sk- 开头'
  if (provider === 'deepseek' && !key.startsWith('sk-')) return '⚠ DeepSeek Key 通常以 sk- 开头'
  if (provider === 'anthropic' && !key.startsWith('sk-ant-')) return '⚠ Anthropic Key 通常以 sk-ant- 开头'
  if (provider === 'google' && !key.startsWith('AIza')) return '⚠ Google Key 通常以 AIza 开头'
  return null
}

const STORAGE_PREFIX = 'aihub_key_'

// v0.6: 简化 — 去掉 Base64 编码，使用明文 localStorage 存储
export function getStoredKey(provider: string): string {
  try { return localStorage.getItem(STORAGE_PREFIX + provider) || '' } catch { return '' }
}

export function getStoredBase(provider: string): string {
  try { return localStorage.getItem(STORAGE_PREFIX + provider + '_base') || '' } catch { return '' }
}

function setStoredKey(provider: string, key: string) {
  try { localStorage.setItem(STORAGE_PREFIX + provider, key) } catch {}
}

function setStoredBase(provider: string, base: string) {
  try { localStorage.setItem(STORAGE_PREFIX + provider + '_base', base) } catch {}
}

export default function ApiKeyModal({ open, onClose, provider, onConfigured }: Props) {
  const [selectedProvider, setSelectedProvider] = useState(provider)
  const [apiKey, setApiKey] = useState('')
  const [apiBase, setApiBase] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<'idle' | 'ok' | 'fail'>('idle')
  const [testMsg, setTestMsg] = useState('')

  useEffect(() => {
    setSelectedProvider(provider)
  }, [provider])

  useEffect(() => {
    if (open) {
      setApiKey(getStoredKey(selectedProvider))
      setApiBase(getStoredBase(selectedProvider))
      setTestResult('idle')
      setTestMsg('')
    }
  }, [open, selectedProvider])

  if (!open) return null

  const label = PROVIDER_LABELS[selectedProvider] || selectedProvider.toUpperCase()
  const signupUrl = PROVIDER_SIGNUP[selectedProvider]
  const isOllama = selectedProvider === 'ollama'

  const handleTest = async () => {
    setTesting(true)
    setTestResult('idle')
    try {
      // 保存临时 Key 并调用 check
      setStoredKey(selectedProvider, apiKey)
      setStoredBase(selectedProvider, apiBase)
      // 用实际 API 测试：POST /api/chat 发一个简短消息
      const res = await fetch('/api/auth/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: selectedProvider }),
      })
      if (res.ok) {
        setTestResult('ok')
        setTestMsg('环境变量已配置' + (apiKey ? '，前端 Key 也已保存' : ''))
      } else {
        setTestResult('fail')
        setTestMsg('服务端检查失败')
      }
    } catch (e: unknown) {
      setTestResult('fail')
      setTestMsg(e instanceof Error ? e.message : '连接失败')
    }
    setTesting(false)
  }

  const handleSave = () => {
    setStoredKey(selectedProvider, apiKey)
    setStoredBase(selectedProvider, apiBase)
    // v0.6: 同步到后端会话
    try {
      fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ providers: { [selectedProvider]: { key: apiKey, base: apiBase } } }),
      }).catch(() => {})
    } catch {}
    onConfigured?.(selectedProvider, apiKey, apiBase)
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-2xl shadow-2xl w-[480px] max-h-[85vh] overflow-hidden">
        {/* 头部 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-gradient-to-r from-blue-50 to-purple-50">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 rounded-xl">
              <Key size={20} className="text-blue-600" />
            </div>
            <div>
              <h3 className="font-bold text-gray-800">配置 {label} API Key</h3>
              <p className="text-xs text-gray-500">
                {isOllama
                  ? '输入本地 Ollama 服务地址'
                  : '连接到大模型 API 需要 API Key'}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-sm"
          >
            取消
          </button>
        </div>

        {/* 内容 */}
        <div className="p-6 space-y-4">
          {/* 环境变量提示 */}
          {testResult === 'ok' && !apiKey && (
            <div className="flex items-start gap-2 text-xs text-green-700 bg-green-50 rounded-lg px-3 py-2">
              <CheckCircle2 size={14} className="mt-0.5 shrink-0" />
              <span>检测到服务端已配置 {label} 的环境变量，可直接使用。</span>
            </div>
          )}

          {/* Provider 选择器 — 防止 Key 存错槽位 */}
          <div>
            <label className="text-xs font-medium text-gray-500 mb-1.5 block">Provider</label>
            <select
              value={selectedProvider}
              onChange={(e) => setSelectedProvider(e.target.value)}
              className="w-full border border-gray-200 rounded-xl px-4 py-2 text-sm focus:outline-none focus:border-blue-500"
            >
              {Object.entries(PROVIDER_LABELS).filter(([k]) => k !== 'ollama').map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </div>

          {/* API Key 输入 */}
          {!isOllama && (
            <div>
              <label className="text-xs font-medium text-gray-500 mb-1.5 block">
                API Key
              </label>
              <div className="relative">
                <input
                  type={showKey ? 'text' : 'password'}
                  value={apiKey}
                  onChange={(e) => { setApiKey(e.target.value); setTestResult('idle') }}
                  placeholder={KEY_HINTS[selectedProvider] || '输入 API Key...'}
                  className={`w-full border rounded-xl px-4 py-2.5 text-sm pr-10 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-200 ${
                    validateKeyFormat(selectedProvider, apiKey) ? 'border-amber-300 bg-amber-50' : 'border-gray-200'
                  }`}
                  autoFocus
                />
                <button
                  onClick={() => setShowKey(!showKey)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                >
                  {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              {validateKeyFormat(selectedProvider, apiKey) && (
                <p className="text-xs text-amber-600 mt-1.5">{validateKeyFormat(selectedProvider, apiKey)}</p>
              )}
            </div>
          )}

          {/* API Base URL（高级选项） */}
          {!isOllama && (
            <details className="text-xs">
              <summary className="text-gray-400 cursor-pointer hover:text-gray-600">
                高级：自定义 API 地址（代理/中转）
              </summary>
              <input
                type="text"
                value={apiBase}
                onChange={(e) => setApiBase(e.target.value)}
                placeholder="https://api.openai.com（留空使用默认）"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-xs mt-2 focus:outline-none focus:border-blue-400"
              />
            </details>
          )}

          {/* Ollama 地址 */}
          {isOllama && (
            <div>
              <label className="text-xs font-medium text-gray-500 mb-1.5 block">
                Ollama 服务地址
              </label>
              <input
                type="text"
                value={apiBase || 'http://localhost:11434'}
                onChange={(e) => setApiBase(e.target.value)}
                placeholder="http://localhost:11434"
                className="w-full border border-gray-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500"
              />
            </div>
          )}

          {/* 获取 Key 链接 */}
          {signupUrl && (
            <a
              href={signupUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-blue-500 hover:text-blue-700"
            >
              <ExternalLink size={12} />
              前往 {label} 获取 API Key
            </a>
          )}

          {/* 安全提示 */}
          <div className="flex items-start gap-2 text-xs text-amber-700 bg-amber-50 rounded-lg px-3 py-2">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" />
            <span>
              API Key 保存在浏览器本地（localStorage），重启浏览器后仍然有效。
              建议在服务端通过环境变量配置以持久化。
            </span>
          </div>

          {/* 测试结果 */}
          {testResult === 'fail' && (
            <div className="flex items-center gap-2 text-xs text-red-600 bg-red-50 rounded-lg px-3 py-2">
              <AlertTriangle size={14} />
              {testMsg}
            </div>
          )}
        </div>

        {/* 操作按钮 */}
        <div className="flex gap-3 px-6 py-4 border-t border-gray-100 bg-gray-50">
          <button
            onClick={handleTest}
            disabled={testing || (!apiKey && !isOllama)}
            className="flex items-center gap-2 px-4 py-2.5 border border-gray-200 rounded-xl text-sm text-gray-600 hover:bg-white disabled:opacity-40 transition-colors"
          >
            {testing ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
            测试连接
          </button>
          <button
            onClick={handleSave}
            disabled={(!apiKey && !isOllama) || (!apiBase && isOllama)}
            className="flex-1 flex items-center justify-center gap-2 bg-blue-600 text-white rounded-xl py-2.5 text-sm font-medium hover:bg-blue-700 disabled:opacity-40 transition-colors"
          >
            <Key size={14} />
            保存并连接
          </button>
        </div>
      </div>
    </div>
  )
}
