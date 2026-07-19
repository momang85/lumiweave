/**
 * OrchestrationDashboard v0.5.1 — Agent 编排监视器
 *
 * 当中央调度 Agent 工作时替换左侧配置面板：
 * - 实时展示各子 Agent 的工作状态
 * - 数据流可视化
 * - 工作结束后还原
 */
import { Activity, CheckCircle2, XCircle, Clock, Loader2, ArrowRight } from 'lucide-react'
import type { AgentActivity } from '../types'

interface Props {
  activities: AgentActivity[]
  isOrchestrating: boolean
}

const STATUS_CONFIG: Record<string, { icon: typeof Activity; color: string; bgColor: string; label: string }> = {
  waiting:  { icon: Clock,        color: 'text-gray-400',  bgColor: 'bg-gray-50',  label: '等待中' },
  working:  { icon: Loader2,      color: 'text-blue-500',  bgColor: 'bg-blue-50',  label: '执行中' },
  done:     { icon: CheckCircle2, color: 'text-green-500', bgColor: 'bg-green-50', label: '已完成' },
  failed:   { icon: XCircle,      color: 'text-red-500',   bgColor: 'bg-red-50',   label: '失败' },
}

const AGENT_AVATARS: Record<string, string> = {
  // Defaults by keyword matching
  '前端': '🖥️', 'frontend': '🖥️',
  '后端': '⚙️', 'backend': '⚙️',
  '全栈': '🏗️', 'fullstack': '🏗️',
  '创意': '💡', 'creative': '💡', '文案': '💡',
  '法律': '⚖️', 'legal': '⚖️',
  '金融': '💰', 'finance': '💰',
  '通用': '🤖', 'general': '🤖',
  'Python': '🐍', 'python': '🐍',
  'Go': '🔷',
  'Rust': '🦀',
  'Java': '☕',
  'DevOps': '🚀', 'devops': '🚀',
  '调度': '🎯', 'orchestrator': '🎯',
  '客服': '💬',
  '教育': '📚',
  '营销': '📈',
  '数据库': '🗄️', 'SQL': '🗄️',
  '移动': '📱',
}

function guessAvatar(agentName: string): string {
  const lower = agentName.toLowerCase()
  for (const [key, avatar] of Object.entries(AGENT_AVATARS)) {
    if (lower.includes(key.toLowerCase())) return avatar
  }
  return '🤖'
}

function AgentCard({ act, index, total }: { act: AgentActivity; index: number; total: number }) {
  const cfg = STATUS_CONFIG[act.status] || STATUS_CONFIG.waiting
  const Icon = cfg.icon
  const animClass = act.status === 'working' ? 'animate-spin' : ''
  const duration = act.endTime ? Math.round((act.endTime - act.startTime) / 1000) : null

  return (
    <div className={`p-3 rounded-xl border ${cfg.bgColor} border-gray-100 transition-all duration-300`}>
      {/* Agent header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-lg">{guessAvatar(act.agentName)}</span>
          <div>
            <span className="font-medium text-xs text-gray-800">
              {act.agentName}
            </span>
            <span className="text-[10px] text-gray-400 ml-1">
              #{index + 1}/{total}
            </span>
          </div>
        </div>
        <span className={`flex items-center gap-1 text-[10px] font-medium ${cfg.color}`}>
          <Icon size={12} className={animClass} />
          {cfg.label}
          {duration != null && <span className="text-gray-300 ml-0.5">{duration}s</span>}
        </span>
      </div>

      {/* Task snippet */}
      <div className="text-[10px] text-gray-500 bg-white/70 rounded-lg px-2 py-1 mb-1.5 line-clamp-2">
        {act.task || '(无任务描述)'}
      </div>

      {/* Output snippet (if done/failed) */}
      {act.outputSnippet && (act.status === 'done' || act.status === 'failed') && (
        <div className={`text-[10px] rounded-lg px-2 py-1 line-clamp-2 ${
          act.status === 'done' ? 'text-green-700 bg-green-100/50' : 'text-red-700 bg-red-100/50'
        }`}>
          {act.status === 'done' ? '✓ ' : '✗ '}{act.outputSnippet}
        </div>
      )}

      {/* Needs key warning */}
      {act.needsKey && (
        <div className="text-[10px] text-amber-600 bg-amber-50 rounded-lg px-2 py-1 mt-1">
          ⚠ 需要 {act.neededProvider.toUpperCase()} API Key
        </div>
      )}

      {/* Tool calls count */}
      {act.toolCalls > 0 && (
        <div className="text-[9px] text-gray-400 mt-1">
          {act.toolCalls} 次工具调用
        </div>
      )}
    </div>
  )
}

export default function OrchestrationDashboard({ activities, isOrchestrating }: Props) {
  if (!isOrchestrating && activities.length === 0) return null

  const done = activities.filter(a => a.status === 'done').length
  const failed = activities.filter(a => a.status === 'failed').length
  const working = activities.filter(a => a.status === 'working').length
  const waiting = activities.filter(a => a.status === 'waiting').length

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 bg-gradient-to-r from-blue-50 to-indigo-50">
        <div className="flex items-center gap-2">
          <Activity size={16} className="text-blue-600" />
          <span className="text-sm font-semibold text-gray-800">Agent 编排监视器</span>
          {isOrchestrating && (
            <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
          )}
        </div>
        <div className="flex gap-2 text-[10px] font-mono">
          <span className="text-green-600">{done} ✓</span>
          <span className="text-red-500">{failed} ✗</span>
          <span className="text-blue-500">{working + waiting} ⋯</span>
        </div>
      </div>

      {/* Summary bar */}
      <div className="px-4 py-2 bg-white/50 border-b border-gray-50">
        <div className="flex items-center gap-2 text-[10px] text-gray-400">
          <span className="text-gray-800 font-medium">🎯 调度中心</span>
          <ArrowRight size={10} className="text-blue-300" />
          <span className="text-blue-500">
            {activities.length > 0 ? `已调派 ${activities.length} 个子 Agent` : '规划中...'}
          </span>
          {done + failed === activities.length && activities.length > 0 && (
            <>
              <span className="text-gray-300">|</span>
              <span className="text-green-600 font-medium">
                {failed === 0 ? '全部完成 ✓' : `${done}/${activities.length} 成功`}
              </span>
            </>
          )}
        </div>
      </div>

      {/* Agent cards */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
        {activities.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-gray-300">
            <Loader2 size={24} className="animate-spin mb-2" />
            <span className="text-xs">等待子 Agent 调度...</span>
          </div>
        ) : (
          activities.map((act, i) => (
            <AgentCard key={act.id} act={act} index={i} total={activities.length} />
          ))
        )}
      </div>

      {/* Lock notice */}
      <div className="px-3 py-2 border-t border-gray-100 bg-amber-50/50">
        <p className="text-[10px] text-amber-700 flex items-center gap-1">
          🔒 Agent 配置已锁定 — 工作完成后自动恢复
        </p>
      </div>
    </div>
  )
}
