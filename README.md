# LumiWeave

> AI Agent 协作工作台 — 像 PM 一样调度多个 AI Agent 完成复杂编程任务

契约驱动 → 并行分派 → 自动验证 → 修正交付。一个任务，多个专业 Agent 协作完成。

---

## 快速开始（3 分钟）

### Docker（推荐）

```bash
git clone https://github.com/lumiweave/lumiweave.git
cd lumiweave
cp .env.example .env    # 编辑填入 API Key
docker compose up -d     # 启动
# 浏览器打开 http://localhost:8000
```

### pip 安装

```bash
pip install lumiweave
lumiweave start
# 浏览器打开 http://localhost:8000
```

### Windows exe

下载 `lumiweave.exe`，双击运行。自动打开浏览器。

---

## 它能做什么

在聊天框输入任务，LumiWeave 自动：

1. **制定契约** — 定义 API 端点、字段类型、实现细节
2. **并行分派** — 同时调度后端 Agent 和前端 Agent
3. **逐文件验证** — 检查每个文件是否存在、行数是否达标
4. **集成测试** — 启动后端 → curl 端点 → 报告 pass/fail
5. **自动修正** — 缺失文件自动补委托（最多 3 轮）

```
用户: "做一个股票监控网站"
  │
  ├─ Orchestrator 制定 contract.json
  ├─ [并行] python-backend Agent → main.py + stock_data.py
  ├─ [并行] frontend-react Agent → index.html + app.js + style.css
  └─ test_project → 3/3 端点通过 ✅
```

---

## 架构

```
┌─────────────┐     ┌──────────────────────────────┐
│  浏览器界面  │────▶│       Orchestrator            │
│  React 前端  │     │  制定契约→分派→验证→修正       │
└─────────────┘     └──────────┬───────────────────┘
                               │ delegate_task
                    ┌──────────┼──────────┐
                    ▼          ▼          ▼
              ┌─────────┐ ┌─────────┐ ┌─────────┐
              │ 后端Agent│ │ 前端Agent│ │ 通用Agent│
              │ Python  │ │ React   │ │ 54个可用 │
              └─────────┘ └─────────┘ └─────────┘
```

**核心能力：**
- 54 个预定义 Agent + AI 动态生成
- 19 个工具处理器（文件读写、Web搜索、代码执行、GitHub API...）
- 5 个 LLM Provider（OpenAI / DeepSeek / Anthropic / Google / Ollama）
- 失败自动换人 + 429 限流控制 + Agent 评分系统

---

## 配置

编辑 `.env`：

```bash
# API 密钥（至少填一个）
OPENAI_API_KEY=sk-xxx
DEEPSEEK_API_KEY=sk-xxx

# 国内用户如需要代理（可选，海外用户不需要）
# LLM_PROXY=http://127.0.0.1:7897
```

也可以在 Web 界面的 ApiKey 弹窗中配置。

---

## 模型选择建议

| 角色 | 推荐模型 | 原因 |
|---|---|---|
| Orchestrator | DeepSeek-V3.2 / Qwen3.5-35B | 强推理、支持 Function Calling |
| 子Agent | Qwen3.5-7B / DeepSeek-V3.2 | 快、便宜、够用 |

---

## 命令行

```bash
lumiweave start              # 启动 Web 工作台
lumiweave start --port 8080  # 指定端口
lumiweave templates           # 查看 10 个内置模板
lumiweave version             # 版本号
```

---

## 项目结构

```
lumiweave/
├── agents/               # 54 个 Agent 定义 (YAML)
├── shared/               # 调度器、适配器、评分系统
│   ├── agent_dispatcher.py
│   ├── adapters/         # OpenAI/DeepSeek/Anthropic/Google/Ollama
│   └── agent_memory.py   # ChromaDB 经验记忆
├── runner/               # 19 个工具处理器
├── builder/
│   ├── backend/          # FastAPI 后端
│   └── frontend/         # React + Vite + Tailwind
├── lumiweave/            # CLI 入口 + exe 启动器
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

---

## 技术栈

| 层 | 技术 |
|---|---|
| 后端框架 | FastAPI + Uvicorn |
| 前端 | React 18 + TypeScript + Vite + Tailwind |
| Agent 调度 | 自研契约驱动多Agent框架 |
| LLM 适配 | OpenAI / DeepSeek / Anthropic / Google / Ollama |
| 向量记忆 | ChromaDB + sentence-transformers |
| 部署 | Docker / pip / PyInstaller |
