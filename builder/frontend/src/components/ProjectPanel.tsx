/**
 * ProjectPanel v0.6 — 项目文件浏览器
 *
 * 左侧文件树 + 右侧文件预览
 */
import { useState, useEffect, useCallback } from 'react'
import {
  Folder, FolderOpen, FileText, Code, FileJson,
  ChevronRight, ChevronDown, RefreshCw, X, Loader2, File
} from 'lucide-react'
import * as api from '../api'

interface Props {
  open: boolean
  onClose: () => void
}

// 文件图标映射
function FileIcon({ name }: { name: string }) {
  const ext = name.split('.').pop()?.toLowerCase()
  if (ext === 'tsx' || ext === 'ts' || ext === 'jsx' || ext === 'js') return <Code size={14} className="text-yellow-500" />
  if (ext === 'py') return <Code size={14} className="text-blue-500" />
  if (ext === 'yaml' || ext === 'yml') return <FileJson size={14} className="text-green-500" />
  if (ext === 'json') return <FileJson size={14} className="text-orange-500" />
  if (ext === 'md') return <FileText size={14} className="text-purple-500" />
  return <File size={14} className="text-gray-400" />
}

// 格式化文件大小
function fmtSize(bytes?: number): string {
  if (!bytes || bytes === 0) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function ProjectPanel({ open, onClose }: Props) {
  const [tree, setTree] = useState<api.ProjectTree | null>(null)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [fileContent, setFileContent] = useState<api.FileContent | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await api.listProject()
      setTree(result)
      // 默认展开根目录
      setExpanded({ '': true })
    } catch (e: unknown) {
      setError((e instanceof Error ? e.message : String(e)) || '加载失败')
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    if (open) refresh()
  }, [open, refresh])

  const toggleDir = (path: string) => {
    setExpanded((prev) => ({ ...prev, [path]: !prev[path] }))
  }

  const openFile = async (path: string) => {
    setSelectedFile(path)
    setFileContent(null)
    try {
      const result = await api.readProjectFile(path)
      setFileContent(result)
    } catch (e: unknown) {
      setFileContent(null)
    }
  }

  const renderTree = (items: api.ProjectFile[], depth: number = 0): React.ReactNode => {
    return items.map((item) => {
      const isOpen = expanded[item.path]
      const isSelected = selectedFile === item.path

      if (item.type === 'dir') {
        return (
          <div key={item.path}>
            <button
              onClick={() => toggleDir(item.path)}
              className="w-full flex items-center gap-1 px-2 py-1 text-xs hover:bg-gray-100 text-left"
              style={{ paddingLeft: 8 + depth * 16 }}
            >
              {isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              {isOpen ? <FolderOpen size={14} className="text-amber-500" /> : <Folder size={14} className="text-amber-500" />}
              <span className="truncate">{item.name}</span>
              {item.count !== undefined && (
                <span className="text-[10px] text-gray-400 ml-auto">{item.count}</span>
              )}
            </button>
            {isOpen && item.children && renderTree(item.children, depth + 1)}
          </div>
        )
      }

      return (
        <button
          key={item.path}
          onClick={() => openFile(item.path)}
          className={`w-full flex items-center gap-1 px-2 py-1 text-xs hover:bg-gray-100 text-left ${
            isSelected ? 'bg-blue-50 text-blue-700' : 'text-gray-700'
          }`}
          style={{ paddingLeft: 8 + depth * 16 + 16 }}
        >
          <FileIcon name={item.name} />
          <span className="truncate flex-1">{item.name}</span>
          <span className="text-[10px] text-gray-400">{fmtSize(item.size)}</span>
        </button>
      )
    })
  }

  if (!open) return null

  return (
    <div className="flex flex-col h-full">
      {/* 头部 */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200 bg-gray-50">
        <div className="flex items-center gap-2">
          <Folder size={16} className="text-primary-600" />
          <span className="text-sm font-semibold text-gray-800">项目文件</span>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={refresh} className="p-1 hover:bg-gray-200 rounded text-gray-400" title="刷新">
            <RefreshCw size={14} />
          </button>
          <button onClick={onClose} className="p-1 hover:bg-gray-200 rounded text-gray-400">
            <X size={14} />
          </button>
        </div>
      </div>

      {/* 主体：左侧文件树 + 右侧预览 */}
      <div className="flex-1 flex min-h-0">
        {/* 文件树 */}
        <div className={`${selectedFile ? 'w-2/5' : 'w-full'} border-r border-gray-100 overflow-y-auto`}>
          {loading && (
            <div className="flex items-center gap-2 p-4 text-xs text-gray-400">
              <Loader2 size={14} className="animate-spin" />
              加载中...
            </div>
          )}
          {error && (
            <div className="p-4 text-xs text-red-500">{error}</div>
          )}
          {tree && !loading && tree.count === 0 && (
            <div className="p-4 text-xs text-gray-400">项目目录为空</div>
          )}
          {tree && tree.items && renderTree(tree.items)}
        </div>

        {/* 文件预览 */}
        {selectedFile && (
          <div className="flex-1 flex flex-col min-w-0">
            <div className="px-3 py-1.5 border-b border-gray-100 bg-gray-50 text-[11px] text-gray-500 flex items-center justify-between">
              <span className="truncate">{selectedFile}</span>
              {fileContent && <span>{fileContent.total_lines} 行 · {fmtSize(fileContent.size)}</span>}
              <button onClick={() => setSelectedFile(null)} className="text-gray-400 hover:text-gray-600 ml-2">
                <X size={12} />
              </button>
            </div>
            <div className="flex-1 overflow-auto p-2">
              {!fileContent && (
                <div className="flex items-center gap-2 p-4 text-xs text-gray-400">
                  <Loader2 size={14} className="animate-spin" />
                  加载中...
                </div>
              )}
              {fileContent && (
                <pre className="text-[11px] font-mono text-gray-700 whitespace-pre-wrap break-all">
                  {fileContent.content}
                  {fileContent.truncated && (
                    <div className="text-center text-gray-400 py-2">... (文件被截断，共 {fileContent.total_lines} 行)</div>
                  )}
                </pre>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
