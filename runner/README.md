# AI Agent Hub — Runner 原型

基于 Agent DSL v0.1 的**命令行运行器**，加载 Agent 定义文件并进行交互式对话。

## 快速开始

```bash
# 1. 安装依赖
cd runner
pip install -r requirements.txt

# 2. 设置 API Key（Windows PowerShell）
set OPENAI_API_KEY=sk-xxx

# 3. 启动交互式对话
python cli.py ../agents/python-backend.yaml

# 4. 或者交互式选择 Agent
python cli.py

# 5. 列出所有可用 Agent
python cli.py --list

# 6. 仅查看 Agent 信息
python cli.py ../agents/python-backend.yaml --info
```

**无 API Key 也能跑**：不设置 `OPENAI_API_KEY` 时自动进入 Mock 演示模式，体验完整流程。

## 架构

```
cli.py              # 终端交互入口（/help /reset /history /tools 等命令）
    ↓
runner.py           # Agent 运行器：管理对话历史、编排推理流程
    ↓
loader.py           # Agent 加载器：解析 YAML → Pydantic 模型 → 校验
    ↓
llm.py              # LLM 客户端：OpenAI (云端) → Mock (降级)
```

## 支持的 Agent

### 编程技术栈 (10) | 项目开发 (4) | 领域通用 (8) — 共 22

| # | 文件名 | Agent |
|---|--------|-------|
| 1-10 | `python-backend.yaml` ~ `ai-ml-engineer.yaml` | 编程技术栈 |
| 11-14 | `fullstack-builder.yaml` ~ `rag-vector-engineer.yaml` | 项目开发专用 |
| 15 | `agent-legal.yaml` | 法律助手 ⚖️ |
| 16 | `agent-finance.yaml` | 金融分析师 💰 |
| 17 | `agent-medical.yaml` | 健康顾问 🏥 |
| 18 | `agent-education.yaml` | 教育导师 📚 |
| 19 | `agent-marketing.yaml` | 营销专家 📊 |
| 20 | `agent-customer-service.yaml` | 客服助手 💬 |
| 21 | `agent-creative.yaml` | 创意文案 🎨 |
| 22 | `agent-general.yaml` | 通用助手 🤖 |

### 支持 Provider

| Provider | CLI 方式 |
|----------|---------|
| OpenAI | `set OPENAI_API_KEY=sk-xxx` |
| Anthropic | `set ANTHROPIC_API_KEY=sk-ant-xxx` |
| Google | `set GOOGLE_API_KEY=xxx` |
| DeepSeek | `set DEEPSEEK_API_KEY=sk-xxx` |
| Ollama | 本地启动：`ollama serve` |

## 对话命令

| 命令 | 说明 |
|------|------|
| `/help` | 显示命令帮助 |
| `/info` | Agent 详细信息（模型、工具、知识源） |
| `/tools` | 列出可用工具 |
| `/suggestions` | 显示推荐问题 |
| `/reset` | 重置对话（清空上下文） |
| `/history` | 对话历史摘要 |
| `/exit` | 退出 |
| 数字 | 快捷选择推荐问题 |

## 扩展方向

- [ ] Tool Call 真实实现（Function Calling）
- [ ] 知识库 RAG（加载 knowledge 源并注入上下文）
- [ ] 流式输出 (SSE / Streaming)
- [ ] 多 Provider 支持（Anthropic、Ollama、本地模型）
- [ ] 对话持久化（保存/加载会话）
- [ ] Web UI 版本
