/**
 * SessionHistory — 会话历史面板
 *
 * 显示历史会话列表，支持：
 * - 查看会话详情
 * - 恢复上下文继续对话
 * - 删除会话
 */
import { useState, useEffect } from 'react'
import { Clock, Trash2, MessageSquare, ChevronRight, Loader2, RefreshCw } from 'lucide-react'
import type { SessionSummary } from '../types'
import * as api from '../api'

interface Props {
  currentAgentId: string
  onSelectSession: (session: SessionSummary) => void
  onClose: () => void
}

export default function SessionHistory({ currentAgentId, onSelectSession, onClose }: Props) {
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState<string | null>(null)

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.listSessions()
      setSessions(data.sessions || [])
    } catch (e) {
      console.error('加载会话历史失败:', e)
    }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  const handleDelete = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation()
    setDeleting(sessionId)
    try {
      await api.deleteSession(sessionId)
      setSessions(prev => prev.filter(s => s.session_id !== sessionId))
    } catch (err) {
      console.error('删除失败:', err)
    }
    setDeleting(null)
  }

  const formatTime = (iso: string) => {
    if (!iso) return ''
    const d = new Date(iso)
    const now = new Date()
    const diff = now.getTime() - d.getTime()
    if (diff < 60000) return '刚刚'
    if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  }

  return (
    <div className="flex flex-col h-full bg-white">
      {/* 头部 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <Clock size={16} className="text-gray-400" />
          <h3 className="font-semibold text-sm text-gray-700">会话历史</h3>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={load} className="p-1 hover:bg-gray-100 rounded text-gray-400" title="刷新">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
          <button onClick={onClose} className="p-1 hover:bg-gray-100 rounded text-gray-400" title="关闭">
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      {/* 列表 */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-12 text-gray-400">
            <Loader2 size={20} className="animate-spin" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            <MessageSquare size={32} className="mx-auto mb-2 opacity-30" />
            <p className="text-sm">暂无会话记录</p>
            <p className="text-xs mt-1">开始一段对话后将自动保存</p>
          </div>
        ) : (
          sessions.map((s) => (
            <div
              key={s.session_id}
              onClick={() => onSelectSession(s)}
              className="group px-4 py-3 border-b border-gray-50 hover:bg-blue-50 cursor-pointer transition-colors"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-800 font-medium truncate">
                    {s.summary || '(空会话)'}
                  </p>
                  <div className="flex items-center gap-3 mt-1">
                    <span className="text-xs text-gray-400">{s.agent_name}</span>
                    <span className="text-xs text-gray-300">{s.message_count} 条消息</span>
                    {s.metadata?.dispatch_count > 0 && (
                      <span className="text-xs text-green-500">
                        {s.metadata.success_count}/{s.metadata.dispatch_count} 成功
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-300 mt-0.5">{formatTime(s.updated_at || s.created_at)}</p>
                </div>
                <button
                  onClick={(e) => handleDelete(e, s.session_id)}
                  className="p-1 opacity-0 group-hover:opacity-100 hover:bg-red-50 rounded text-gray-300 hover:text-red-500 transition-all"
                  title="删除"
                >
                  {deleting === s.session_id ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Trash2 size={14} />
                  )}
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
