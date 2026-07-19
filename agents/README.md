# AI Agent Hub — Agent 目录

## 编程技术栈 (10)

| # | Agent ID | 名称 | 技术栈 | 文件 |
|---|----------|------|--------|------|
| 1 | `com.aihub.python-backend` | Python 后端大师 | FastAPI / Django / SQLAlchemy / asyncio | `python-backend.yaml` |
| 2 | `com.aihub.frontend-react` | 前端架构师 | Next.js 14 / React / TypeScript / Tailwind / Zustand | `frontend-react.yaml` |
| 3 | `com.aihub.golang-cloud` | Go 云原生专家 | Go / gRPC / K8s / 并发编程 / Protobuf | `golang-cloud.yaml` |
| 4 | `com.aihub.rust-system` | Rust 系统工匠 | Rust / tokio / WASM / FFI / 嵌入式 | `rust-system.yaml` |
| 5 | `com.aihub.java-spring` | Java 企业架构师 | Spring Boot 3 / Spring Cloud / JPA / DDD | `java-spring.yaml` |
| 6 | `com.aihub.cpp-system` | C/C++ 底层专家 | C++20/23 / CMake / SIMD / 图形学 / 嵌入式 | `cpp-system.yaml` |
| 7 | `com.aihub.devops-kubernetes` | DevOps 运维专家 | K8s / Docker / CI/CD / Terraform / Prometheus | `devops-kubernetes.yaml` |
| 8 | `com.aihub.sql-database` | 数据库架构师 | PostgreSQL / MySQL / 索引 / SQL 优化 / 数据建模 | `sql-database.yaml` |
| 9 | `com.aihub.mobile-flutter` | 移动端全栈 | Flutter / Dart / Riverpod / 跨平台 | `mobile-flutter.yaml` |
| 10 | `com.aihub.ai-ml-engineer` | AI/ML 工程师 | PyTorch / LLM / RAG / Agent / 模型部署 | `ai-ml-engineer.yaml` |

## AI Agent Hub 项目开发专用 (4)

| # | Agent ID | 名称 | 技术栈 | 文件 |
|---|----------|------|--------|------|
| 11 | `com.aihub.fullstack-builder` | 全栈构建器 | React + Vite + Tailwind + FastAPI + SSE + ChromaDB | `fullstack-builder.yaml` |
| 12 | `com.aihub.agent-dsl-architect` | Agent DSL 架构师 | YAML DSL / Pydantic IR / 跨平台适配映射 | `agent-dsl-architect.yaml` |
| 13 | `com.aihub.llm-provider-adapter` | LLM 适配专家 | OpenAI / Anthropic / Google / Ollama / DeepSeek 统一调用 | `llm-provider-adapter.yaml` |
| 14 | `com.aihub.rag-vector-engineer` | RAG 架构师 | ChromaDB / BGE / 文档分块 / 检索优化 / RAGAS 评估 | `rag-vector-engineer.yaml` |

## 领域通用 Agent (8) 🆕

| # | Agent ID | 名称 | 领域 | 文件 |
|---|----------|------|------|------|
| 15 | `com.aihub.agent-legal` | 法律助手 ⚖️ | 合同审查 / 法规检索 / 合规分析 | `agent-legal.yaml` |
| 16 | `com.aihub.agent-finance` | 金融分析师 💰 | 财务报表 / 投资风险 / 资产配置 | `agent-finance.yaml` |
| 17 | `com.aihub.agent-medical` | 健康顾问 🏥 | 体检解读 / 循证建议 / 文献检索 | `agent-medical.yaml` |
| 18 | `com.aihub.agent-education` | 教育导师 📚 | 课程设计 / 论文辅导 / 知识讲解 | `agent-education.yaml` |
| 19 | `com.aihub.agent-marketing` | 营销专家 📊 | 广告文案 / SEO / 品牌策略 | `agent-marketing.yaml` |
| 20 | `com.aihub.agent-customer-service` | 客服助手 💬 | FAQ问答 / 投诉处理 / 工单管理 | `agent-customer-service.yaml` |
| 21 | `com.aihub.agent-creative` | 创意文案 🎨 | 品牌故事 / Slogan / 社交媒体 | `agent-creative.yaml` |
| 22 | `com.aihub.agent-general` | 通用助手 🤖 | 百科问答 / 信息检索 / 多领域 | `agent-general.yaml` |

## 通用特性

每个 Agent 均包含：

- **system_prompt**：详细的角色定义、最佳实践、代码规范
- **tools**：预定义的工具接口（文档搜索、代码检查等）
- **knowledge**：关联的官方文档源
- **runtime**：本地运行所需的语言版本和依赖包
- **ui**：头像、欢迎语、推荐问题
- **model.fallback**：云端模型不可用时，降级到本地模型

## Agent 规范

详见 `spec.yaml`，每个 Agent 遵循统一的五板块 DSL：

```
meta → model → system_prompt → tools → knowledge → runtime → ui
```

## 使用方式

1. **Web 端**：将 .yaml 文件导入平台 Builder 即可运行
2. **本地端**：通过 CLI `agent run <文件>` 在本地启动
3. **定制**：Fork 任意 Agent，修改 system_prompt 和 tools 即可创建变体
