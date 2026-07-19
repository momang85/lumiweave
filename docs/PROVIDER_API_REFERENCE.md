# LLM Provider API 模式参考

## 已适配厂商对比

| 特性 | OpenAI | Anthropic | Google | DeepSeek | Ollama |
|------|--------|-----------|--------|----------|--------|
| **Chat 端点** | `POST /v1/chat/completions` | `POST /v1/messages` | `generateContent` | `POST /v1/chat/completions` | `POST /api/chat` |
| **SDK** | `openai` | `anthropic` | `google-generativeai` | `openai` (兼容) | HTTP REST |
| **System Prompt** | `messages[{role:"system"}]` | 独立 `system` 字段 | `system_instruction` | 同 OpenAI | 同 OpenAI |
| **工具格式** | `tools: [{type:"function", function:{name,description,parameters}}]` | `tools: [{name,description,input_schema}]` | `tools: [{functionDeclarations:[{name,description,parameters}]}]` | 同 OpenAI | 同 OpenAI |
| **工具结果回传** | `role:"tool" + tool_call_id` | `role:"user" + content[{type:"tool_result",tool_use_id,content}]` | `role:"tool"` functionResponse | 同 OpenAI | 同 OpenAI |
| **流式 SSE** | `data: {choices:[{delta:{content}}]}` → `data: [DONE]` | `event: content_block_delta` → `event: message_stop` | `chunk.text` 迭代 | 同 OpenAI + reasoning_content | JSON Lines `{"message":{"content":...}}` |
| **认证** | `Authorization: Bearer sk-xxx` | `x-api-key: sk-ant-xxx` | `?key=xxx` 或 `x-goog-api-key` | `Authorization: Bearer sk-xxx` | 无需认证 |
| **温度** | `temperature` (0-2) | `temperature` (0-1) | `temperature` (0-2) | `temperature` (0-2) | `temperature` (0-2) |
| **Max Context** | 128K | 200K | 1M (Gemini 1.5) | 128K | 模型相关 |
| **环境变量** | `OPENAI_API_KEY` | `ANTHROPIC_API_KEY` | `GOOGLE_API_KEY` | `DEEPSEEK_API_KEY` | 无需 |
| **获取 Key** | platform.openai.com/api-keys | console.anthropic.com/keys | aistudio.google.com/apikey | platform.deepseek.com/api_keys | 本地 `ollama pull` |

## 国产厂商（待适配）

| 厂商 | API 格式 | 兼容性 | 特殊字段 |
|------|---------|--------|---------|
| **百度文心** | OpenAI 兼容 + 原生 | `/v2/respond` (原生) | `grant_type` 获取 token |
| **阿里通义** | OpenAI 兼容 | DashScope SDK | `dashscope.Generation.call()` |
| **智谱 GLM** | OpenAI 兼容 | `/api/paas/v4/chat/completions` | `tools` 格式一致 |
| **月之暗面 Moonshot** | OpenAI 兼容 | 完全兼容 | 128K 上下文 |
| **零一万物 Yi** | OpenAI 兼容 | 完全兼容 | 200K 上下文 |
| **MiniMax** | OpenAI 兼容 | 需 `group_id` | — |

## 调用链路

```
前端输入消息 + 选择 Provider
  │
  ├─ 未检测到 API Key → 弹出 ApiKeyModal → 用户输入 Key → 保存到 sessionStorage
  │
  ▼
POST /api/chat
  {agent_id, message, provider, api_key, api_base, enable_rag}
  │
  ▼
后端 _chat_generator_v4()
  │
  ├─ 读取 Agent 定义（system_prompt + tools + RAG 知识库）
  ├─ 构建 MessageIR + ToolDefIR（统一 IR 格式）
  │
  ├─ OpenAI    → OpenAIAdapter  → OpenAI SDK     → SSE 流式
  ├─ Anthropic → AnthropicAdapter → Anthropic SDK → SSE 流式
  ├─ Google    → GoogleAdapter   → google-genai   → 迭代流式
  ├─ Ollama    → OllamaAdapter   → HTTP REST      → SSE 流式
  └─ DeepSeek  → DeepSeekAdapter → OpenAI SDK     → SSE 流式
  │
  ▼
返回 SSE 事件 → 前端增量渲染
```

## API Key 存储策略

| 层级 | 方式 | 持久化 | 安全 |
|------|------|--------|------|
| 服务端环境变量 | `export OPENAI_API_KEY=sk-xxx` | ✅ 永久 | 🔒 最安全 |
| 前端 sessionStorage | 用户输入保存 | ❌ 会话级 | ⚠️ 仅用于演示 |
| 前端 ProviderConfig | 弹窗输入 | ❌ 不保存 | ⚠️ 需用户输入 |

**生产环境建议**：通过环境变量配置 API Key，前端不做持久化。
