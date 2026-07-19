/**
 * App — Builder 主布局
 *
 * ┌──────────────┬──────────────────┐
 * │  配置面板     │   对话预览        │
 * │  (40%)       │   (60%)          │
 * │              │                  │
 * └──────────────┴──────────────────┘
 */
import { useState, useEffect, useCallback } from 'react'
import { Sparkles, Code, PanelLeftClose, PanelLeftOpen, Wand2, Settings, Folder, ScrollText, History } from 'lucide-react'
import type { AgentData, AgentActivity, SessionSummary } from './types'
import * as api from './api'
import AgentConfigPanel from './components/AgentConfigPanel'
import ChatPreview from './components/ChatPreview'
import TemplateMarket from './components/TemplateMarket'
import AgentGenerationWizard from './components/AgentGenerationWizard'
import SettingsModal from './components/SettingsModal'
import OrchestrationDashboard from './components/OrchestrationDashboard'
import ProjectPanel from './components/ProjectPanel'
import RuntimeLogs from './components/RuntimeLogs'
import SessionHistory from './components/SessionHistory'

export default function App() {
  const [agents, setAgents] = useState<AgentData[]>([])
  const [currentAgent, setCurrentAgent] = useState<AgentData | null>(null)
  const [showTemplate, setShowTemplate] = useState(false)
  const [showWizard, setShowWizard] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [panelCollapsed, setPanelCollapsed] = useState(false)
  const [loading, setLoading] = useState(true)
  const [orchestrating, setOrchestrating] = useState(false)
  const [orchestrationActivities, setOrchestrationActivities] = useState<AgentActivity[]>([])
  const [showProject, setShowProject] = useState(false)
  const [showLogs, setShowLogs] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [sessionId, setSessionId] = useState('')

  // 加载 Agent 列表
  const loadAgents = useCallback(async () => {
    try {
      const data = await api.listAgents()
      setAgents(data.agents)
    } catch (e) {
      console.error('加载 Agent 列表失败:', e)
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    loadAgents()
  }, [loadAgents])

  // 选择 Agent
  const handleSelectAgent = useCallback(
    async (agentId: string) => {
      if (!agentId) {
        setCurrentAgent(null)
        return
      }
      try {
        const { agent } = await api.getAgent(agentId)
        setCurrentAgent(agent)
      } catch (e) {
        console.error('加载 Agent 失败:', e)
      }
    },
    [],
  )

  // Agent 更新
  const handleAgentChange = useCallback(
    (updated: AgentData) => {
      setCurrentAgent(updated)
      setAgents((prev) => prev.map((a) => (a.agent_id === updated.agent_id ? updated : a)))
    },
    [],
  )

  // Agent 删除
  const handleAgentDelete = useCallback(
    (agentId: string) => {
      setAgents((prev) => prev.filter((a) => a.agent_id !== agentId))
      if (currentAgent?.agent_id === agentId) {
        setCurrentAgent(null)
      }
    },
    [currentAgent],
  )

  // 模板使用
  const handleTemplateUse = useCallback(
    async (agentId: string) => {
      await loadAgents()
      handleSelectAgent(agentId)
    },
    [loadAgents, handleSelectAgent],
  )

  // 会话选择 — 切换到对应 Agent 并带入 session_id
  const handleSelectSession = useCallback(
    (session: SessionSummary) => {
      setSessionId(session.session_id)
      setShowHistory(false)
      if (session.agent_id && session.agent_id !== currentAgent?.agent_id) {
        handleSelectAgent(session.agent_id)
      }
    },
    [currentAgent, handleSelectAgent],
  )

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      {/* 左侧：配置面板 / 编排监视器 */}
      <div
        className={`${
          panelCollapsed ? 'w-0 overflow-hidden' : 'w-[420px] min-w-[360px]'
        } border-r border-gray-200 bg-white transition-all duration-300 flex flex-col`}
      >
        {orchestrating ? (
          <OrchestrationDashboard
            activities={orchestrationActivities}
            isOrchestrating={orchestrating}
          />
        ) : (
          <AgentConfigPanel
            agent={currentAgent}
            onAgentChange={handleAgentChange}
            onAgentDelete={handleAgentDelete}
            agents={agents}
            onSelectAgent={handleSelectAgent}
          />
        )}
      </div>

      {/* 右侧：对话预览 */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* 顶部工具栏 */}
        <div className="flex items-center justify-between px-4 py-2 bg-white border-b border-gray-100">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setPanelCollapsed(!panelCollapsed)}
              className="p-1.5 hover:bg-gray-100 rounded-lg text-gray-400"
              title={panelCollapsed ? '展开面板' : '收起面板'}
            >
              {panelCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
            </button>
            <div className="flex items-center gap-2">
              <Code size={18} className="text-primary-600" />
              <span className="font-bold text-gray-800 text-sm">AI Agent Hub</span>
              <span className="text-[10px] bg-primary-100 text-primary-700 px-1.5 py-0.5 rounded font-medium">
                Builder
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowSettings(true)}
              className="p-1.5 hover:bg-gray-100 rounded-lg text-gray-400 hover:text-gray-600"
              title="API 设置"
            >
              <Settings size={16} />
            </button>
            <button
              onClick={() => setShowWizard(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-primary-50 text-primary-700 border border-primary-200 rounded-xl text-xs font-medium hover:bg-primary-100 transition-colors"
            >
              <Wand2 size={14} />
              AI 生成
            </button>
            <button
              onClick={() => setShowTemplate(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-50 text-amber-700 border border-amber-200 rounded-xl text-xs font-medium hover:bg-amber-100 transition-colors"
            >
              <Sparkles size={14} />
              模板市场
            </button>
            <button
              onClick={() => setShowProject(!showProject)}
              className={`p-1.5 rounded-lg transition-colors ${
                showProject ? 'bg-primary-100 text-primary-700' : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100'
              }`}
              title="项目文件"
            >
              <Folder size={16} />
            </button>
            <button
              onClick={() => setShowLogs(!showLogs)}
              className={`p-1.5 rounded-lg transition-colors ${
                showLogs ? 'bg-primary-100 text-primary-700' : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100'
              }`}
              title="运行日志"
            >
              <ScrollText size={16} />
            </button>
            <button
              onClick={() => setShowHistory(!showHistory)}
              className={`p-1.5 rounded-lg transition-colors ${
                showHistory ? 'bg-primary-100 text-primary-700' : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100'
              }`}
              title="会话历史"
            >
              <History size={16} />
            </button>
          </div>
        </div>

        {/* 对话区域 + 项目面板 */}
        <div className="flex-1 flex min-h-0">
          <div className="flex-1 overflow-hidden">
            <ChatPreview
              agent={currentAgent}
              sessionId={sessionId}
              onOrchestrationChange={(active, acts) => {
                setOrchestrating(active && acts.length > 0)
                setOrchestrationActivities(acts)
              }}
            />
          </div>
          {showProject && (
            <div className="w-[360px] min-w-[280px] border-l border-gray-200 bg-white">
              <ProjectPanel open={showProject} onClose={() => setShowProject(false)} />
            </div>
          )}
          {showLogs && (
            <div className="w-[420px] min-w-[320px] border-l border-gray-200 bg-white">
              <RuntimeLogs open={showLogs} onClose={() => setShowLogs(false)} />
            </div>
          )}
          {showHistory && (
            <div className="w-[380px] min-w-[300px] border-l border-gray-200 bg-white">
              <SessionHistory
                currentAgentId={currentAgent?.agent_id || ''}
                onSelectSession={handleSelectSession}
                onClose={() => setShowHistory(false)}
              />
            </div>
          )}
        </div>
      </div>

      {/* 模板市场弹窗 */}
      <TemplateMarket
        open={showTemplate}
        onClose={() => setShowTemplate(false)}
        onTemplateUse={handleTemplateUse}
      />

      {/* AI 生成向导 */}
      <AgentGenerationWizard
        open={showWizard}
        onClose={() => setShowWizard(false)}
        onAgentCreated={async (agentId) => {
          await loadAgents()
          handleSelectAgent(agentId)
        }}
      />

      {/* API 设置 */}
      <SettingsModal
        open={showSettings}
        onClose={() => setShowSettings(false)}
      />
    </div>
  )
}
