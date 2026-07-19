/**
 * RuntimeLogs — 运行时日志查看面板 v0.7
 *
 * 增强功能：
 * - 按会话分组，可折叠
 * - 显示事件耗时（elapsed）和间隔（gap）
 * - 耗时 >10s 标红，>3s 标黄
 * - 错误自动展开
 * - text 自动合并（后端已去重）
 * - 子Agent结果显示执行时间
 */
import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { X, Trash2, Filter, Play, Pause, ChevronDown, ChevronRight, RefreshCw, Clock, Zap, AlertTriangle } from 'lucide-react'

interface LogEntry {
  id: string
  timestamp: number
  session_id: string
  agent_id: string
  agent_name: string
  type: string
  content: string
  elapsed_ms: number
  gap_ms: number
  detail: Record<string, unknown>
}

interface LogStats {
  total: number
  by_type: Record<string, number>
  max_capacity: number
  file_size_kb: number
}

const TYPE_COLORS: Record<string, string> = {
  session_start:  'border-blue-400 bg-blue-50',
  session_end:    'border-gray-300 bg-gray-50',
  info:           'border-gray-300 bg-gray-50',
  agent_dispatch: 'border-purple-400 bg-purple-50',
  agent_result:   'border-indigo-400 bg-indigo-50',
  text:           'border-gray-200 bg-white',
  reasoning:      'border-teal-400 bg-teal-50',
  error:          'border-red-400 bg-red-50',
  no_api_key:     'border-amber-400 bg-amber-50',
  orchestration_start: 'border-cyan-400 bg-cyan-50',
  done:           'border-green-400 bg-green-50',
  heartbeat:      'border-gray-100 bg-gray-50',
}

const TYPE_LABELS: Record<string, string> = {
  session_start:  '启动',
  session_end:    '结束',
  info:           '信息',
  agent_dispatch: '调用',
  agent_result:   '结果',
  text:           '文本',
  reasoning:      '推理',
  error:          '错误',
  no_api_key:     '无Key',
  orchestration_start: '编排',
  done:           '完成',
  heartbeat:      '心跳',
}

const FILTERABLE_TYPES = [
  { key: '', label: '全部' },
  { key: 'agent_dispatch', label: '调用' },
  { key: 'agent_result', label: '结果' },
  { key: 'error', label: '错误' },
  { key: 'no_api_key', label: 'Key缺失' },
  { key: 'done', label: '完成' },
]

interface Props {
  open: boolean
  onClose: () => void
}

export default function RuntimeLogs({ open, onClose }: Props) {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [stats, setStats] = useState<LogStats | null>(null)
  const [filter, setFilter] = useState('')
  const [paused, setPaused] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [collapsedSessions, setCollapsedSessions] = useState<Set<string>>(new Set())
  const listRef = useRef<HTMLDivElement>(null)
  const esRef = useRef<EventSource | null>(null)
  const pauseBuffer = useRef<LogEntry[]>([])

  const loadHistory = useCallback(async () => {
    try {
      const res = await fetch('/api/logs?limit=500')
      const data = await res.json()
      setLogs(data.logs || [])
      setStats(data.stats || null)
    } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    if (!open) {
      esRef.current?.close()
      esRef.current = null
      return
    }
    loadHistory()
    const es = new EventSource('/api/logs/stream')
    esRef.current = es
    es.onmessage = (event) => {
      try {
        const entry = JSON.parse(event.data) as LogEntry
        if (entry.type === 'heartbeat') return
        if (paused) {
          pauseBuffer.current.push(entry)
        } else {
          setLogs((prev) => [...prev, entry])
        }
      } catch { /* skip */ }
    }
    return () => { es.close(); esRef.current = null }
  }, [open, paused, loadHistory])

  useEffect(() => {
    if (!paused && pauseBuffer.current.length > 0) {
      setLogs((prev) => [...prev, ...pauseBuffer.current])
      pauseBuffer.current = []
    }
  }, [paused])

  useEffect(() => {
    if (!paused && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight
    }
  }, [logs, paused])

  const handleClear = async () => {
    try { await fetch('/api/logs', { method: 'DELETE' }) } catch { /* ignore */ }
    setLogs([]); setStats(null)
  }

  // 按 session 分组
  const sessions = useMemo(() => {
    const map: Record<string, { entries: LogEntry[]; startTime: number; endTime: number; dispatchCount: number; okCount: number; failCount: number }> = {}
    for (const entry of logs) {
      const sid = entry.session_id
      if (!sid) continue
      if (!map[sid]) {
        map[sid] = { entries: [], startTime: entry.timestamp, endTime: entry.timestamp, dispatchCount: 0, okCount: 0, failCount: 0 }
      }
      map[sid].entries.push(entry)
      map[sid].endTime = entry.timestamp
      if (entry.type === 'agent_dispatch') map[sid].dispatchCount++
      if (entry.type === 'agent_result') {
        const ok = entry.detail?.success as boolean
        if (ok) map[sid].okCount++
        else map[sid].failCount++
      }
    }
    return Object.entries(map).sort((a, b) => a[1].startTime - b[1].startTime)
  }, [logs])

  const toggleSession = (sid: string) => {
    setCollapsedSessions(prev => {
      const next = new Set(prev)
      if (next.has(sid)) next.delete(sid)
      else next.add(sid)
      return next
    })
  }

  const filtered = filter
    ? logs.filter((l) => l.type === filter)
    : logs.filter((l) => l.type !== 'heartbeat')

  const errorCount = logs.filter((l) => l.type === 'error' || l.type === 'no_api_key').length

  const fmtTime = (ts: number) => {
    const d = new Date(ts * 1000)
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }

  const fmtDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`
    if (ms < 60000) return `${(ms/1000).toFixed(1)}s`
    return `${Math.floor(ms/60000)}m${Math.round((ms%60000)/1000)}s`
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).catch(() => {})
  }

  if (!open) return null

  // 渲染单条日志
  const renderEntry = (entry: LogEntry) => {
    const color = TYPE_COLORS[entry.type] || 'border-gray-200 bg-white'
    const label = TYPE_LABELS[entry.type] || entry.type
    const isExpanded = expandedId === entry.id
    const isError = entry.type === 'error' || entry.type === 'no_api_key'
    const hasDetail = entry.detail && Object.keys(entry.detail).length > 1
    const gapSec = entry.gap_ms / 1000
    const elapsedSec = entry.elapsed_ms / 1000

    return (
      <div
        key={entry.id}
        className={`text-xs border-l-2 rounded-r py-0.5 px-2 cursor-pointer hover:opacity-85 ${color}`}
        onClick={() => setExpandedId(isExpanded ? null : entry.id)}
      >
        <div className="flex items-center gap-1.5">
          {/* 时间 */}
          <span className="text-[10px] text-gray-400 shrink-0 w-14">{fmtTime(entry.timestamp)}</span>

          {/* 耗时（>3s 标黄，>10s 标红） */}
          {elapsedSec > 1 && (
            <span className={`text-[9px] shrink-0 ${elapsedSec > 30 ? 'text-red-500 font-bold' : elapsedSec > 10 ? 'text-red-400' : 'text-amber-500'}`}
              title={`会话已运行 ${fmtDuration(entry.elapsed_ms)}`}>
              <Clock size={10} className="inline mr-0.5" />{fmtDuration(entry.elapsed_ms)}
            </span>
          )}

          {/* 间隔（>3s 显示） */}
          {gapSec > 3 && (
            <span className="text-[9px] text-amber-500 shrink-0" title={`距上条事件 ${gapSec.toFixed(1)}s`}>
              <Zap size={10} className="inline mr-0.5" />+{gapSec.toFixed(0)}s
            </span>
          )}

          {/* 类型标签 */}
          <span className={`text-[9px] px-1 rounded font-medium shrink-0 ${
            isError ? 'bg-red-100 text-red-600' : 'bg-gray-100 text-gray-500'
          }`}>
            {label}
          </span>

          {/* Agent名 */}
          {entry.agent_name && (
            <span className="text-[9px] text-gray-400 truncate">{entry.agent_name}</span>
          )}

          {/* 内容 */}
          <span className="text-gray-600 truncate flex-1">{entry.content}</span>

          {/* 展开图标 */}
          {hasDetail && (
            <span className="text-gray-300 shrink-0">
              {isExpanded ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
            </span>
          )}
        </div>

        {/* 展开详情 */}
        {isExpanded && (
          <div className="mt-1 bg-white/60 rounded p-1.5 text-[10px]">
            <div className="flex items-center gap-2 mb-1 text-gray-400">
              <span>ID: {entry.id}</span>
              <span>Session: {entry.session_id?.slice(0,12)}</span>
              <span>elapsed: {fmtDuration(entry.elapsed_ms)}</span>
              <span>gap: {fmtDuration(entry.gap_ms)}</span>
            </div>
            <pre
              className="whitespace-pre-wrap break-all text-gray-600 max-h-32 overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              {JSON.stringify(entry.detail, null, 2)}
            </pre>
            <button
              onClick={(e) => { e.stopPropagation(); copyToClipboard(JSON.stringify(entry.detail, null, 2)) }}
              className="mt-1 text-[9px] text-blue-500 hover:text-blue-700"
            >
              复制详情
            </button>
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-white border-l border-gray-200">
      {/* 标题栏 */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 bg-gray-50">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-gray-700">运行时日志</span>
          {stats && <span className="text-[10px] text-gray-400">{stats.total}/{stats.max_capacity}</span>}
          {errorCount > 0 && (
            <span className="text-[10px] text-red-500 bg-red-50 px-1.5 py-0.5 rounded-full font-medium flex items-center gap-0.5">
              <AlertTriangle size={10} />{errorCount}
            </span>
          )}
          <span className="text-[10px] text-gray-400">{sessions.length} 次会话</span>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => { loadHistory(); setExpandedId(null) }} className="p-1 hover:bg-gray-200 rounded text-gray-400" title="刷新">
            <RefreshCw size={14} />
          </button>
          <button onClick={() => { setPaused(!paused); pauseBuffer.current = [] }} className="p-1 hover:bg-gray-200 rounded text-gray-400" title={paused ? '继续' : '暂停'}>
            {paused ? <Play size={14} /> : <Pause size={14} />}
          </button>
          <button onClick={handleClear} className="p-1 hover:bg-red-100 rounded text-gray-400 hover:text-red-500" title="清空">
            <Trash2 size={14} />
          </button>
          <button onClick={onClose} className="p-1 hover:bg-gray-200 rounded text-gray-400" title="关闭">
            <X size={14} />
          </button>
        </div>
      </div>

      {/* 过滤器 */}
      <div className="flex items-center gap-1 px-3 py-2 border-b border-gray-100 bg-white overflow-x-auto">
        <Filter size={12} className="text-gray-300 shrink-0" />
        {FILTERABLE_TYPES.map((t) => (
          <button
            key={t.key}
            onClick={() => setFilter(t.key)}
            className={`px-2 py-0.5 text-[10px] rounded-full whitespace-nowrap transition-colors ${
              filter === t.key ? 'bg-primary-100 text-primary-700 font-medium' : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100'
            }`}
          >
            {t.label}
          </button>
        ))}
        {stats && (
          <span className="ml-auto text-[10px] text-gray-300 whitespace-nowrap">
            {Object.entries(stats.by_type).filter(([k]) => k !== 'heartbeat').map(([k, v]) => `${TYPE_LABELS[k]||k}:${v}`).join(' ')}
          </span>
        )}
      </div>

      {/* 日志列表 — 按 session 分组 */}
      <div ref={listRef} className="flex-1 overflow-y-auto" style={{ fontFamily: "'JetBrains Mono','Fira Code','Consolas',monospace" }}>
        {sessions.length === 0 && (
          <div className="text-center text-gray-300 text-xs py-8">暂无日志，开始聊天后将自动记录</div>
        )}

        {sessions.map(([sid, session]) => {
          const duration = session.endTime - session.startTime
          const isCollapsed = collapsedSessions.has(sid)
          const entries = filter ? session.entries.filter(e => e.type === filter) : session.entries

          return (
            <div key={sid} className="border-b border-gray-100">
              {/* Session 头部 */}
              <div
                className="flex items-center gap-2 px-3 py-1.5 bg-gray-50 cursor-pointer hover:bg-gray-100 sticky top-0 z-10"
                onClick={() => toggleSession(sid)}
              >
                {isCollapsed ? <ChevronRight size={12} className="text-gray-400" /> : <ChevronDown size={12} className="text-gray-400" />}
                <span className="text-[10px] font-medium text-gray-600">会话 {sid.slice(0,12)}</span>
                <span className={`text-[10px] ${duration > 120 ? 'text-red-500 font-bold' : duration > 60 ? 'text-amber-500' : 'text-gray-400'}`}>
                  {fmtDuration(duration * 1000)}
                </span>
                {session.dispatchCount > 0 && (
                  <span className="text-[9px] text-purple-500">
                    派发{session.dispatchCount}次
                    <span className="text-green-500 ml-1">OK:{session.okCount}</span>
                    {session.failCount > 0 && <span className="text-red-500 ml-1">FAIL:{session.failCount}</span>}
                  </span>
                )}
                <span className="text-[9px] text-gray-300 ml-auto">{entries.length}条</span>
              </div>

              {/* Session 内容 */}
              {!isCollapsed && (
                <div className="px-1 py-0.5 space-y-0.5">
                  {entries.map(renderEntry)}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* 底部状态栏 */}
      <div className="px-3 py-1 border-t border-gray-100 bg-gray-50 flex items-center gap-2">
        <span className="text-[10px] text-gray-400">
          {filtered.length} 条
          {paused && <span className="text-amber-500 ml-1">(已暂停)</span>}
        </span>
        <span className={`ml-auto w-1.5 h-1.5 rounded-full ${paused ? 'bg-amber-400' : 'bg-green-400 animate-pulse'}`} />
        <span className="text-[10px] text-gray-400">{paused ? '已暂停' : '实时'}</span>
      </div>
    </div>
  )
}
