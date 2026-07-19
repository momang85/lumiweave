/**
 * KnowledgeUploader — 知识库上传组件
 *
 * 拖拽上传 PDF/TXT/MD 文件，自动向量化。
 */
import { useState, useCallback, useEffect } from 'react'
import { Upload, FileText, Trash2, Loader2, Database } from 'lucide-react'
import * as api from '../api'
import type { KnowledgeStats } from '../types'

export default function KnowledgeUploader({ agentId }: { agentId: string }) {
  const [stats, setStats] = useState<KnowledgeStats>({ exists: false, chunks: 0 })
  const [uploading, setUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)

  useEffect(() => {
    if (agentId) {
      api.getKnowledgeStats(agentId).then(setStats).catch(console.error)
    }
  }, [agentId])

  const handleUpload = useCallback(
    async (file: File) => {
      setUploading(true)
      try {
        const result = await api.uploadKnowledge(agentId, file)
        if (result.error) {
          alert(`上传失败: ${result.error}`)
          return
        }
        if (result.chunks > 0) {
          setStats({ exists: true, chunks: result.chunks })
        } else {
          const textLen = (result as any).text_length ?? 0
          alert(`解析后内容为空: 提取到 ${textLen} 字符，${result.file_size ?? '?'} bytes。\n可能原因: PDF为扫描件/图片，或文件编码非UTF-8。`)
        }
      } catch (e: unknown) {
        alert(`上传失败: ${e instanceof Error ? e.message : e}`)
      }
      setUploading(false)
    },
    [agentId],
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragOver(false)
      const file = e.dataTransfer.files[0]
      if (file) handleUpload(file)
    },
    [handleUpload],
  )

  const handleDelete = async () => {
    if (!confirm('确定删除知识库？')) return
    try {
      await api.deleteKnowledge(agentId)
      setStats({ exists: false, chunks: 0 })
    } catch (e: unknown) {
      alert(`删除失败: ${e instanceof Error ? e.message : e}`)
    }
  }

  return (
    <div>
      {stats.exists && stats.chunks > 0 && (
        <div className="flex items-center justify-between bg-green-50 border border-green-200 rounded-lg px-3 py-2 mb-2">
          <div className="flex items-center gap-2 text-xs text-green-700">
            <Database size={14} />
            <span>{stats.chunks} 个文本块</span>
          </div>
          <button onClick={handleDelete} className="text-red-400 hover:text-red-600">
            <Trash2 size={14} />
          </button>
        </div>
      )}

      <label
        className={`flex flex-col items-center justify-center border-2 border-dashed rounded-lg p-4 cursor-pointer transition-colors text-center ${
          dragOver
            ? 'border-primary-500 bg-primary-50'
            : 'border-gray-300 hover:border-primary-400 hover:bg-gray-50'
        }`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        <input
          type="file"
          accept=".txt,.md,.pdf"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) handleUpload(file)
          }}
          className="hidden"
          disabled={uploading}
        />
        {uploading ? (
          <>
            <Loader2 size={20} className="text-primary-500 animate-spin mb-1" />
            <span className="text-xs text-gray-500">向量化中...</span>
          </>
        ) : (
          <>
            <Upload size={20} className="text-gray-400 mb-1" />
            <span className="text-xs text-gray-500">拖拽或点击上传</span>
            <span className="text-[10px] text-gray-400 mt-0.5">.txt .md .pdf</span>
          </>
        )}
      </label>
    </div>
  )
}
