/**
 * TemplateMarket — 模板市场弹窗
 *
 * 展示内置模板，一键创建 Agent。
 */
import { useState, useEffect } from 'react'
import { X, Search, Sparkles, Loader2 } from 'lucide-react'
import type { TemplateData } from '../types'
import * as api from '../api'

interface Props {
  open: boolean
  onClose: () => void
  onTemplateUse: (agentId: string) => void
}

export default function TemplateMarket({ open, onClose, onTemplateUse }: Props) {
  const [templates, setTemplates] = useState<TemplateData[]>([])
  const [search, setSearch] = useState('')
  const [using, setUsing] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      api.listTemplates().then((data) => setTemplates(data.templates)).catch(console.error)
    }
  }, [open])

  const handleUse = async (templateId: string) => {
    setUsing(templateId)
    try {
      const { agent } = await api.useTemplate(templateId)
      onTemplateUse(agent.agent_id)
      onClose()
    } catch (e: unknown) {
      alert(`创建失败: ${e instanceof Error ? e.message : e}`)
    }
    setUsing(null)
  }

  if (!open) return null

  const filtered = templates.filter(
    (t) =>
      t.name.includes(search) ||
      t.description.includes(search) ||
      t.tags.some((tag) => tag.includes(search)),
  )

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[80vh] flex flex-col">
        {/* 头部 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Sparkles size={20} className="text-amber-500" />
            <h2 className="font-bold text-lg text-gray-800">模板市场</h2>
            <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
              {templates.length}
            </span>
          </div>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-100 rounded-lg text-gray-400">
            <X size={18} />
          </button>
        </div>

        {/* 搜索 */}
        <div className="px-6 py-3">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索模板..."
              className="w-full pl-9 pr-3 py-2 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-primary-500"
            />
          </div>
        </div>

        {/* 模板列表 */}
        <div className="flex-1 overflow-y-auto px-6 py-2 space-y-3 pb-6">
          {filtered.map((tpl) => (
            <div
              key={tpl.id}
              className="border border-gray-100 rounded-xl p-4 hover:border-primary-200 hover:shadow-sm transition-all"
            >
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-3">
                  <span className="text-2xl">{tpl.icon}</span>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-gray-800 text-sm">{tpl.name}</h3>
                      <span className="text-[10px] bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">
                        {tpl.category}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">{tpl.description}</p>
                    <div className="flex gap-1 mt-2 flex-wrap">
                      {tpl.tags.map((tag) => (
                        <span
                          key={tag}
                          className="text-[10px] bg-primary-50 text-primary-600 px-1.5 py-0.5 rounded"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                    <div className="text-[10px] text-gray-400 mt-1.5">
                      {tpl.tools.length} 个工具 · 模型: {tpl.model.model_name}
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => handleUse(tpl.id)}
                  disabled={using === tpl.id}
                  className="shrink-0 px-4 py-2 bg-primary-600 text-white rounded-xl text-xs font-medium hover:bg-primary-700 disabled:opacity-50 flex items-center gap-1 transition-colors"
                >
                  {using === tpl.id ? (
                    <Loader2 size={12} className="animate-spin" />
                  ) : null}
                  使用
                </button>
              </div>
            </div>
          ))}

          {filtered.length === 0 && (
            <div className="text-center py-8 text-gray-400 text-sm">
              没有匹配的模板
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
